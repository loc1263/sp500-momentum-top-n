"""Acciones en circulación y capitalización aproximada (precio de la fecha x acciones actuales)."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd
import yfinance as yf

from .config import DataSettings
from .logs import log


def _fetch_shares(ticker: str) -> tuple[str, float | None]:
    try:
        return ticker, yf.Ticker(ticker).fast_info.get("shares")
    except Exception as e:
        log.debug("Sin acciones en circulación para %s: %s", ticker, e)
        return ticker, None


def ensure_shares(conn: sqlite3.Connection, tickers: list[str], use_cache: bool, settings: DataSettings,
                  known: dict[str, float] | None = None) -> dict[str, float]:
    """Acciones en circulación (actuales) de `tickers`; se reutilizan las descargadas hoy salvo --no-cache.
    `known` son datos ya obtenidos en esta corrida (no se vuelven a pedir)."""
    today = date.today().isoformat()
    known = known or {}
    cached = {r[0]: r[1] for r in conn.execute("SELECT ticker, shares FROM shares WHERE fetched = ?", (today,))}
    shares = {t: known[t] if t in known else cached[t]
              for t in tickers if t in known or (use_cache and t in cached)}
    todo = [t for t in tickers if t not in shares]
    log.info("Acciones en circulación: %d ya disponibles, %d a descargar", len(shares), len(todo))
    missing = []
    with ThreadPoolExecutor(max_workers=settings.shares_workers) as pool:
        for t, value in pool.map(_fetch_shares, todo):
            if value:
                shares[t] = float(value)
                conn.execute("INSERT OR REPLACE INTO shares (ticker, shares, fetched) VALUES (?, ?, ?)",
                             (t, float(value), today))
            else:
                missing.append(t)
    conn.commit()
    if missing:
        log.warning("Sin dato de acciones en circulación para %d tickers (capitalización n/d)", len(missing))
        log.debug("Sin acciones en circulación: %s", sorted(missing))
    return shares


def add_market_caps(histories: list[list[dict]], prices: pd.DataFrame, shares: dict[str, float]) -> None:
    """Agrega h['caps'] = {ticker: cap aprox.} a cada rebalanceo: precio de esa fecha × acciones actuales."""
    for history in histories:
        for h in history:
            caps = {}
            for t in h["returns"]:
                px = prices.loc[:h["date"], t].dropna() if t in prices.columns else []
                if len(px) and t in shares:
                    caps[t] = float(px.iloc[-1]) * shares[t]
            h["caps"] = caps
