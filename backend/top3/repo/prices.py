"""Precios ajustados guardados (prices), tickers sin datos en Yahoo (no_data_tickers) y OHLCV (ohlcv)."""
import sqlite3
from datetime import date, timedelta

import pandas as pd


def save(conn: sqlite3.Connection, long: pd.DataFrame) -> None:
    """Guarda precios en formato largo (columnas ticker, date, close)."""
    conn.executemany("INSERT OR REPLACE INTO prices (ticker, date, close) VALUES (?, ?, ?)",
                     list(zip(long["ticker"], long["date"], long["close"])))
    conn.commit()


def clear(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM prices")
    conn.commit()


def delete_tickers(conn: sqlite3.Connection, tickers: list[str]) -> None:
    conn.executemany("DELETE FROM prices WHERE ticker = ?", [(t,) for t in tickers])


def exists(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM prices LIMIT 1").fetchone() is not None


def last_dates(conn: sqlite3.Connection) -> dict[str, str]:
    """{ticker: último día con precio}."""
    return dict(conn.execute("SELECT ticker, MAX(date) FROM prices GROUP BY ticker").fetchall())


def latest_date(conn: sqlite3.Connection) -> str | None:
    return conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]


def close_on_or_before(conn: sqlite3.Connection, ticker: str, day: str) -> float | None:
    row = conn.execute("SELECT close FROM prices WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT 1",
                       (ticker, day)).fetchone()
    return row[0] if row else None


def stored_since(conn: sqlite3.Connection, since: str) -> pd.DataFrame:
    """Columnas ticker, date y old (el cierre guardado) desde `since`."""
    return pd.read_sql("SELECT ticker, date, close AS old FROM prices WHERE date >= ?", conn, params=(since,))


def matrix_since(conn: sqlite3.Connection, start: str) -> pd.DataFrame:
    """Cierres desde `start` como matriz (índice = fecha, columnas = ticker)."""
    df = pd.read_sql("SELECT date, ticker, close FROM prices WHERE date >= ?", conn, params=(start,),
                     parse_dates=["date"])
    return df.pivot(index="date", columns="ticker", values="close").sort_index()


def matrix(conn: sqlite3.Connection) -> pd.DataFrame:
    """Todos los cierres como matriz (índice = fecha, columnas = ticker)."""
    df = pd.read_sql("SELECT date, ticker, close FROM prices", conn, parse_dates=["date"])
    return df.pivot(index="date", columns="ticker", values="close").sort_index()


def known_no_data(conn: sqlite3.Connection, ttl_days: int) -> set[str]:
    """Tickers que Yahoo dijo hace menos de `ttl_days` días que no existen o están dados de baja."""
    if ttl_days <= 0:
        return set()
    cutoff = (date.today() - timedelta(days=ttl_days)).isoformat()
    return {r[0] for r in conn.execute("SELECT ticker FROM no_data_tickers WHERE checked > ?", (cutoff,))}


def remember_no_data(conn: sqlite3.Connection, gone: set[str], with_data: list[str]) -> None:
    """Anota los tickers sin datos de esta descarga y olvida los que ahora sí tienen."""
    today = date.today().isoformat()
    conn.executemany("INSERT OR REPLACE INTO no_data_tickers (ticker, checked) VALUES (?, ?)",
                     [(t, today) for t in sorted(gone)])
    conn.executemany("DELETE FROM no_data_tickers WHERE ticker = ?", [(t,) for t in with_data])


def replace_ohlcv(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """rows = (ticker, fecha, open, high, low, close, volume)."""
    conn.execute("DELETE FROM ohlcv")
    conn.executemany("INSERT OR REPLACE INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)", rows)


def ohlcv_frame(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM ohlcv", conn, parse_dates=["date"])
