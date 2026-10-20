"""Top N actual del S&P 500: las acciones que más subieron en los últimos N meses (el criterio del backtest, hoy)."""
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from . import console, html_report, universe as universes
from .config import DataSettings
from .constituents import download_current_constituents
from .db import fetched_today, get_meta, open_db
from .logs import log
from .prices import fetch_prices
from .shares import ensure_shares
from .universe import Universe


def get_current_tickers(conn: sqlite3.Connection, aliases: dict[str, str], use_cache: bool,
                        settings: DataSettings) -> list[str]:
    """Lista actual del S&P 500 (descargada hoy o la guardada) con los alias aplicados."""
    if not (use_cache and fetched_today(conn, "constituents_current_fetched")):
        try:
            download_current_constituents(conn, settings)
        except Exception:
            log.exception("No se pudo descargar la lista actual; se usa la guardada en SQLite")
    else:
        log.info("Lista actual del S&P 500: usando caché SQLite (descargada hoy)")
    tickers = [r[0] for r in conn.execute("SELECT ticker FROM constituents_current")]
    if not tickers:
        raise SystemExit("No hay lista actual del S&P 500 (ni descargada ni en SQLite).")
    tickers = list(dict.fromkeys(aliases.get(t, t) for t in tickers))
    log.info("Tickers del S&P 500 actual: %d", len(tickers))
    return tickers


def download_recent(tickers: list[str], start: str, end: str, batch_size: int) -> pd.DataFrame:
    """Precios ajustados de `tickers` en lotes (no se guardan: solo la ventana reciente)."""
    long, _ = fetch_prices(tickers, start, end, batch_size)
    long["date"] = pd.to_datetime(long["date"])
    return long.pivot(index="date", columns="ticker", values="close").sort_index()


def get_prices(conn: sqlite3.Connection, tickers: list[str], start: str, end: str, use_cache: bool,
               settings: DataSettings) -> pd.DataFrame:
    """Precios desde `start`: usa la base SQLite si se descargó hoy (la deja el backtest) y completa lo que falte."""
    frames = []
    cached_start = get_meta(conn, "prices_start")
    if use_cache and fetched_today(conn, "prices_fetched") and cached_start and cached_start <= start:
        df = pd.read_sql("SELECT date, ticker, close FROM prices WHERE date >= ?", conn,
                         params=(start,), parse_dates=["date"])
        stored = df.pivot(index="date", columns="ticker", values="close").sort_index()
        stored = stored[[t for t in tickers if t in stored.columns]]
        log.info("Precios: %d tickers desde la caché SQLite (hasta %s)", stored.shape[1],
                 stored.index.max().date() if len(stored) else None)
        frames.append(stored)
        missing = [t for t in tickers if t not in stored.columns]
    else:
        missing = list(tickers)
    if missing:
        log.info("Descargando precios de %d tickers (%s a %s)...", len(missing), start, end)
        frames.append(download_recent(missing, start, end, settings.batch_size))
    prices = pd.concat(frames, axis=1).sort_index() if frames else pd.DataFrame()
    return prices.loc[:, ~prices.columns.duplicated()]


def compute_top(prices: pd.DataFrame, months: int, top_n: int, trading_days_per_month: int,
                universe: Universe | None = None) -> tuple[pd.Series, pd.DataFrame]:
    """Los `top_n` tickers con mayor retorno en los últimos `months` meses y la ventana de precios usada."""
    lookback = months * trading_days_per_month
    prices = prices.dropna(axis=1, how="all")
    if universe is not None:
        last_px = prices.ffill().iloc[-1]
        big = universe.select(list(prices.columns), last_px)
        log.info("Filtro de capitalización (>= US$ %.0f B): %d -> %d tickers",
                 universe.min_cap_usd / 1e9, prices.shape[1], len(big))
        prices = prices[big]
    window = prices.tail(lookback + 1)
    if len(window) < lookback + 1:
        raise SystemExit(f"Solo hay {len(window)} ruedas de precios; se necesitan {lookback + 1}.")
    window = window.dropna(axis=1, how="any")
    log.debug("Ventana: %s a %s, %d ruedas, %d tickers completos",
              window.index[0].date(), window.index[-1].date(), len(window), window.shape[1])
    returns = (window.iloc[-1] / window.iloc[0] - 1).dropna().sort_values(ascending=False)
    log.debug("Top 10 retornos:\n%s", returns.head(10).round(4).to_string())
    return returns.head(top_n), window


def run_actual(cfg: dict, months: int, top_n: int, min_cap_b: float | None, use_cache: bool) -> Path:
    """Calcula el Top actual, lo guarda en SQLite, lo imprime y escribe el reporte HTML."""
    log.info("Plazo: %d meses | Top %d | Universo: %s", months, top_n, universes.label(min_cap_b))
    settings = DataSettings.from_config(cfg)
    today = date.today()
    start = (today - timedelta(days=months * 31 + 45)).isoformat()  # margen para cubrir las ruedas necesarias
    end = (today + timedelta(days=1)).isoformat()

    conn = open_db(cfg["data"]["db_path"])
    try:
        tickers = get_current_tickers(conn, cfg["tickers"]["aliases"], use_cache, settings)
        prices = get_prices(conn, tickers, start, end, use_cache, settings)

        known, universe = None, None
        if min_cap_b:
            known = ensure_shares(conn, list(prices.columns), use_cache, settings)
            universe = Universe(known, min_cap_b)

        top, window = compute_top(prices, months, top_n, int(cfg["backtest"]["trading_days_per_month"]), universe)
        shares = ensure_shares(conn, list(top.index), use_cache, settings, known=known)

        as_of = window.index[-1].date()
        run_at = datetime.now().isoformat(timespec="seconds")
        rows = []
        for rank, (ticker, ret) in enumerate(top.items(), 1):
            price = float(window[ticker].iloc[-1])
            cap = price * shares[ticker] if ticker in shares else None
            rows.append((run_at, as_of.isoformat(), months, min_cap_b, rank, ticker, float(ret), price, cap))
        conn.executemany("INSERT INTO actual_picks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
        log.info("Resultado guardado en SQLite (tabla actual_picks)")
    finally:
        conn.close()

    weight = 100 / len(rows)
    headers = ["#", "Ticker", f"Retorno {months} meses", "Cap. aprox. (US$ B)", "Precio (US$)", "Peso"]
    table = [[str(r[4]), r[5], f"{r[6] * 100:+.1f}%", f"{r[8] / 1e9:,.0f}" if r[8] else "n/d",
              f"{r[7]:,.2f}", f"{weight:.1f}%"] for r in rows]
    console.print_actual(top_n, months, min_cap_b, as_of, window, headers, table, weight)
    return html_report.actual_report(cfg, top_n, months, min_cap_b, as_of, window, headers, table, weight)
