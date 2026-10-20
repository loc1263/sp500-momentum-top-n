"""Precios ajustados: descarga completa e incremental a SQLite y carga como matriz fecha x ticker."""
import sqlite3
import time
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from . import errors as E, yahoo
from .config import DataSettings
from .db import fetched_today, get_meta, set_meta
from .logs import log

PRICE_COLUMNS = ["ticker", "date", "close"]
RATE_LIMIT_RETRIES = 3   # reintentos de los tickers que Yahoo rechazó por rate limit
RATE_LIMIT_WAIT = 10.0   # segundos antes del primer reintento (se duplica en cada uno)


def _download(batch: list[str], start: str, end: str) -> pd.DataFrame:
    """Precios de cierre ajustados de `batch` (fecha x ticker)."""
    data = yf.download(batch, start=start, end=end, auto_adjust=True,
                       progress=False, threads=True)["Close"].copy()  # yfinance lo arma columna a columna: se desfragmenta
    if isinstance(data, pd.Series):
        data = data.to_frame(name=batch[0])
    return data


def _download_batch(batch: list[str], start: str, end: str, retries: int,
                    wait: float) -> tuple[pd.DataFrame, set[str]]:
    """Descarga un lote; los tickers que Yahoo rechazó por rate limit se piden de nuevo tras esperar
    (`wait` segundos, el doble en cada reintento). Si siguen rechazados quedan sin datos y se avisa como error.
    Devuelve (precios, tickers que Yahoo dice que no existen o están dados de baja)."""
    with yahoo.capture_errors() as errors:
        data = _download(batch, start, end)
    absent = {t for t, message in errors.items() if yahoo.is_expected_absence(message)}
    for attempt in range(1, retries + 1):
        limited = [t for t, message in errors.items() if yahoo.is_rate_limit(message)]
        if not limited:
            return data, absent
        delay = wait * 2 ** (attempt - 1)
        log.warning(E.NET_RATE_RETRY.msg("Yahoo limitó %d tickers (%s); reintento %d/%d en %g s"),
                    len(limited), ", ".join(limited[:8]) + (" ..." if len(limited) > 8 else ""), attempt, retries,
                    delay)
        time.sleep(delay)
        with yahoo.capture_errors() as errors:
            again = _download(limited, start, end)
        data = pd.concat([data.drop(columns=limited, errors="ignore"), again], axis=1)
    limited = [t for t, message in errors.items() if yahoo.is_rate_limit(message)]
    if limited:
        log.error(E.NET_RATE_LIMIT.msg("Yahoo siguió limitando %d tickers tras %d reintentos; quedan sin datos: %s"),
                  len(limited), retries, ", ".join(limited))
    return data, absent


def fetch_prices(tickers: list[str], start: str, end: str, batch_size: int, retries: int = RATE_LIMIT_RETRIES,
                 wait: float = RATE_LIMIT_WAIT, gone: set[str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Baja precios ajustados en lotes. Devuelve (DataFrame largo ticker/date/close, tickers sin datos).
    Si se pasa `gone`, se le agregan los tickers sin datos que Yahoo dijo que no existen o están dados de baja
    (a diferencia de los que fallaron por rate limit u otro motivo, que pueden tener datos más tarde)."""
    frames, sin_datos = [], []
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        data, absent = _download_batch(batch, start, end, retries, wait)
        got = set(data.columns[data.notna().any()])
        sin_datos.extend(t for t in batch if t not in got)
        if gone is not None:
            gone.update(t for t in absent if t not in got)
        long = (data.rename_axis("date").reset_index()
                .melt(id_vars="date", var_name="ticker", value_name="close").dropna())
        long["date"] = pd.to_datetime(long["date"]).dt.strftime("%Y-%m-%d")
        frames.append(long[PRICE_COLUMNS])
        log.info("Lote %d/%d: %d tickers con datos, %d filas",
                 i // batch_size + 1, -(-len(tickers) // batch_size), len(got), len(long))
    prices = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=PRICE_COLUMNS)
    return prices, sin_datos


def _save_prices(conn: sqlite3.Connection, long: pd.DataFrame) -> None:
    conn.executemany("INSERT OR REPLACE INTO prices (ticker, date, close) VALUES (?, ?, ?)",
                     list(zip(long["ticker"], long["date"], long["close"])))
    conn.commit()


def known_no_data(conn: sqlite3.Connection, ttl_days: int) -> set[str]:
    """Tickers que Yahoo dijo hace menos de `ttl_days` días que no existen o están dados de baja."""
    if ttl_days <= 0:
        return set()
    cutoff = (date.today() - timedelta(days=ttl_days)).isoformat()
    return {r[0] for r in conn.execute("SELECT ticker FROM no_data_tickers WHERE checked > ?", (cutoff,))}


def remember_no_data(conn: sqlite3.Connection, gone: set[str], long: pd.DataFrame) -> None:
    """Anota los tickers sin datos de esta descarga y olvida los que ahora sí tienen."""
    today = date.today().isoformat()
    conn.executemany("INSERT OR REPLACE INTO no_data_tickers (ticker, checked) VALUES (?, ?)",
                     [(t, today) for t in sorted(gone)])
    conn.executemany("DELETE FROM no_data_tickers WHERE ticker = ?", [(t,) for t in long["ticker"].unique()])


def download_prices(conn: sqlite3.Connection, tickers: list[str], start: str, end: str,
                    settings: DataSettings) -> None:
    """Descarga completa: baja precios ajustados de todos los tickers y reemplaza lo guardado."""
    skip = known_no_data(conn, settings.no_data_ttl_days) & set(tickers)
    if skip:
        log.info("Precios: %d tickers sin datos en Yahoo (consultados hace menos de %d días) no se vuelven a pedir",
                 len(skip), settings.no_data_ttl_days)
        tickers = [t for t in tickers if t not in skip]
    log.info("Descargando precios de %d tickers (%s a %s) en lotes de %d...",
             len(tickers), start, end, settings.batch_size)
    conn.execute("DELETE FROM prices")
    conn.commit()
    gone: set[str] = set()
    long, sin_datos = fetch_prices(tickers, start, end, settings.batch_size, gone=gone)
    _save_prices(conn, long)
    remember_no_data(conn, gone, long)
    set_meta(conn, "prices_fetched", date.today().isoformat())
    set_meta(conn, "prices_start", start)
    set_meta(conn, "prices_end", end)
    conn.commit()
    log.info("Precios guardados: %d filas | tickers sin datos: %d", len(long), len(sin_datos) + len(skip))
    log.debug("Tickers sin datos (delisted/renombrados): %s", sorted(sin_datos))


def update_prices(conn: sqlite3.Connection, tickers: list[str], start: str, end: str,
                  settings: DataSettings) -> None:
    """Descarga incremental: solo lo que falta desde la última descarga.

    - Tickers nuevos (sin precios guardados): rango completo.
    - Tickers con datos: desde su último día guardado, con unos días de solape (price_overlap_days).
    - Como los precios son ajustados por dividendos/splits, el solape se compara con lo guardado: si un ticker
      cambió su base de ajuste (pagó dividendo o hizo split desde la última descarga), el historial guardado ya
      no es comparable con el nuevo y solo ese ticker se vuelve a bajar completo.
    - Tickers que dejaron de cotizar (último dato de hace más de stale_days) no se vuelven a pedir.
    """
    last = dict(conn.execute("SELECT ticker, MAX(date) FROM prices GROUP BY ticker").fetchall())
    newest = pd.to_datetime(max(last.values()))
    stale_before = (newest - pd.Timedelta(days=settings.stale_days)).strftime("%Y-%m-%d")
    skip = known_no_data(conn, settings.no_data_ttl_days)
    new = [t for t in tickers if t not in last and t not in skip]
    active = [t for t in tickers if t in last and last[t] >= stale_before]
    log.info("Actualización incremental de precios: %d tickers nuevos, %d a actualizar, %d sin cotizar",
             len(new), len(active), len(tickers) - len(new) - len(active))

    refetch = list(new)
    if active:
        since = (pd.to_datetime(min(last[t] for t in active))
                 - pd.Timedelta(days=settings.price_overlap_days)).strftime("%Y-%m-%d")
        fresh, _ = fetch_prices(active, since, end, settings.batch_size)
        stored = pd.read_sql("SELECT ticker, date, close AS old FROM prices WHERE date >= ?", conn, params=(since,))
        both = fresh.merge(stored, on=["ticker", "date"])
        drift = (both["close"] / both["old"] - 1).abs().groupby(both["ticker"]).max()
        changed = sorted(drift[drift > settings.price_drift_tolerance].index)
        no_overlap = sorted(set(active) - set(drift.index))
        refetch += changed + no_overlap
        log.info("Precios: %d tickers cambiaron su ajuste (dividendo/split) y se vuelven a bajar completos; "
                 "%d sin solape", len(changed), len(no_overlap))
        log.debug("Ajuste cambiado: %s | sin solape: %s", changed, no_overlap)
        _save_prices(conn, fresh[~fresh["ticker"].isin(changed + no_overlap)])
    if refetch:
        gone: set[str] = set()
        long, sin_datos = fetch_prices(refetch, start, end, settings.batch_size, gone=gone)
        conn.executemany("DELETE FROM prices WHERE ticker = ?", [(t,) for t in refetch])
        _save_prices(conn, long)
        remember_no_data(conn, gone, long)
        log.debug("Tickers sin datos (delisted/renombrados): %s", sorted(sin_datos))
    set_meta(conn, "prices_fetched", date.today().isoformat())
    set_meta(conn, "prices_end", end)
    conn.commit()


def ensure_prices(conn: sqlite3.Connection, tickers: list[str], start: str, end: str, use_cache: bool,
                  settings: DataSettings) -> None:
    """Deja en SQLite los precios de `tickers` desde `start`: caché del día, actualización o descarga completa."""
    cached_start = get_meta(conn, "prices_start")
    has_data = conn.execute("SELECT 1 FROM prices LIMIT 1").fetchone() is not None
    if not use_cache:
        return download_prices(conn, tickers, start, end, settings)
    if fetched_today(conn, "prices_fetched") and cached_start and cached_start <= start:
        log.info("Precios: usando caché SQLite (descargados hoy, desde %s)", cached_start)
        return
    if not has_data or not cached_start:
        log.info("Precios: no hay datos guardados, descarga completa")
        return download_prices(conn, tickers, start, end, settings)
    if start < cached_start:
        log.info("Precios: la caché empieza en %s y se piden desde %s, descarga completa", cached_start, start)
        return download_prices(conn, tickers, start, end, settings)
    update_prices(conn, tickers, start, end, settings)


def load_prices(conn: sqlite3.Connection) -> pd.DataFrame:
    """Todos los precios guardados como matriz (índice = fecha, columnas = ticker)."""
    df = pd.read_sql("SELECT date, ticker, close FROM prices", conn, parse_dates=["date"])
    prices = df.pivot(index="date", columns="ticker", values="close").sort_index()
    log.info("Precios cargados desde SQLite: shape=%s (%s a %s)", prices.shape,
             prices.index.min().date() if len(prices) else None,
             prices.index.max().date() if len(prices) else None)
    return prices
