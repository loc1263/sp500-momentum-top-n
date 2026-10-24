"""Precios de apertura, máximo, mínimo y cierre ajustados, y volumen, del último año y medio (para los indicadores técnicos).

La base de precios del proyecto guarda solo el cierre; los indicadores que usan el rango del día (estocástico, ADX) o el
volumen (OBV, MFI) necesitan el resto. Se guardan en `ohlcv` y se bajan de nuevo una vez por día.
"""
import sqlite3
import time
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from .. import errors as E, yahoo
from ..db import fetched_today, set_meta
from ..logs import log

FIELDS = ["Open", "High", "Low", "Close", "Volume"]
HISTORY_DAYS = 460          # ~ 315 ruedas: alcanza para la EMA de 200 y el máximo de 52 semanas
RETRIES = 3
WAIT = 10.0


def _download(batch: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    data = yf.download(batch, start=start, end=end, auto_adjust=True, progress=False, threads=True)
    out = {}
    for field in FIELDS:
        frame = data[field].copy()
        out[field] = frame.to_frame(name=batch[0]) if isinstance(frame, pd.Series) else frame
    return out


def _download_batch(batch: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """Un lote; los tickers que Yahoo limitó por rate limit se piden de nuevo tras esperar (el doble en cada reintento)."""
    with yahoo.capture_errors() as errors:
        data = _download(batch, start, end)
    for attempt in range(1, RETRIES + 1):
        limited = [t for t, message in errors.items() if yahoo.is_rate_limit(message)]
        if not limited:
            return data
        delay = WAIT * 2 ** (attempt - 1)
        log.warning(E.NET_RATE_RETRY.msg("Yahoo limitó %d tickers (%s); reintento %d/%d en %g s"), len(limited),
                    ", ".join(limited[:8]) + (" ..." if len(limited) > 8 else ""), attempt, RETRIES, delay)
        time.sleep(delay)
        with yahoo.capture_errors() as errors:
            again = _download(limited, start, end)
        data = {f: pd.concat([data[f].drop(columns=limited, errors="ignore"), again[f]], axis=1) for f in FIELDS}
    limited = [t for t, message in errors.items() if yahoo.is_rate_limit(message)]
    if limited:
        log.error(E.NET_RATE_LIMIT.msg("Yahoo siguió limitando %d tickers tras %d reintentos; quedan sin datos: %s"),
                  len(limited), RETRIES, ", ".join(limited))
    return data


def ensure_ohlcv(conn: sqlite3.Connection, tickers: list[str], use_cache: bool, batch_size: int) -> None:
    """Deja en SQLite el OHLCV de `tickers`: reutiliza lo bajado hoy o lo descarga de nuevo (reemplaza lo anterior)."""
    if use_cache and fetched_today(conn, "ohlcv_fetched"):
        log.info("OHLCV: usando caché SQLite (descargado hoy)")
        return
    today = date.today()
    start, end = (today - timedelta(days=HISTORY_DAYS)).isoformat(), (today + timedelta(days=1)).isoformat()
    log.info("Descargando OHLCV de %d tickers (%s a %s) en lotes de %d...", len(tickers), start, end, batch_size)
    rows, missing = [], []
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        data = _download_batch(batch, start, end)
        got = [t for t in data["Close"].columns if data["Close"][t].notna().any()]
        missing.extend(t for t in batch if t not in got)
        for t in got:
            frame = pd.DataFrame({f: data[f][t] for f in FIELDS}).dropna(subset=["Close"])
            frame["Volume"] = frame["Volume"].fillna(0)
            for day, r in frame.iterrows():
                rows.append((t, pd.Timestamp(day).strftime("%Y-%m-%d"), float(r["Open"]), float(r["High"]),
                             float(r["Low"]), float(r["Close"]), float(r["Volume"])))
        log.info("Lote %d/%d: %d tickers con datos", i // batch_size + 1, -(-len(tickers) // batch_size), len(got))
    if not rows:
        log.warning(E.DAT_NO_OHLCV.msg("No se pudo descargar ningún OHLCV; se usa lo guardado"))
        return
    conn.execute("DELETE FROM ohlcv")
    conn.executemany("INSERT OR REPLACE INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    set_meta(conn, "ohlcv_fetched", today.isoformat())
    conn.commit()
    if missing:
        log.warning(E.DAT_NO_OHLCV.msg("Sin OHLCV para %d tickers (quedan fuera del score técnico)"), len(missing))
        log.debug("Sin OHLCV: %s", sorted(missing))
    log.info("OHLCV guardado: %d filas", len(rows))


def load_ohlcv(conn: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    """Campos como matrices fecha x ticker: open, high, low, close, volume."""
    df = pd.read_sql("SELECT * FROM ohlcv", conn, parse_dates=["date"])
    return {f: df.pivot(index="date", columns="ticker", values=f).sort_index()
            for f in ("open", "high", "low", "close", "volume")}
