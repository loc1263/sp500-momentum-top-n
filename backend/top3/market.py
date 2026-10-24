"""Datos de mercado que necesitan el backtest y el modelo por score: composición del índice y precios al día."""
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from .config import Config
from .constituents import Constituents, ensure_constituents
from .logs import log
from .prices import ensure_prices, load_prices


@dataclass
class MarketData:
    constituents: Constituents
    prices: pd.DataFrame      # fecha x ticker, todos los que pasaron por el índice en el histórico
    history_start: str


def refresh_market_data(conn: sqlite3.Connection, cfg: Config, use_cache: bool, today: date | None = None) -> MarketData:
    """Deja en SQLite la composición del S&P 500 y los precios de todos sus miembros del histórico (descargando lo
    que falte) y los carga."""
    today = today or date.today()
    history_start = cfg.data.history_start(today)
    ensure_constituents(conn, cfg.data, use_cache)
    constituents = Constituents(conn, cfg.tickers.aliases)
    tickers = constituents.all_between(history_start, today)
    log.info("Tickers únicos que pasaron por el S&P 500 en el histórico: %d", len(tickers))
    price_end = (today + timedelta(days=1)).isoformat()  # yfinance: end exclusivo
    ensure_prices(conn, tickers, history_start, price_end, use_cache, cfg.data)
    return MarketData(constituents, load_prices(conn), history_start)
