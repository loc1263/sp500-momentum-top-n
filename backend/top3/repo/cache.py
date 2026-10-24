"""Datos de Yahoo que se reutilizan por días: acciones en circulación (shares) y datos financieros (fundamentals)."""
import sqlite3


def fresh_shares(conn: sqlite3.Connection, cutoff: str) -> dict[str, float]:
    """Acciones en circulación guardadas desde `cutoff` (YYYY-MM-DD) en adelante."""
    return {r[0]: r[1] for r in conn.execute("SELECT ticker, shares FROM shares WHERE fetched >= ?", (cutoff,))}


def save_shares(conn: sqlite3.Connection, ticker: str, shares: float, fetched: str) -> None:
    conn.execute("INSERT OR REPLACE INTO shares (ticker, shares, fetched) VALUES (?, ?, ?)",
                 (ticker, shares, fetched))


def delete_shares_before(conn: sqlite3.Connection, day: str) -> int:
    """Borra las acciones en circulación guardadas antes de `day` y devuelve cuántas filas."""
    return conn.execute("DELETE FROM shares WHERE fetched < ?", (day,)).rowcount


def delete_fundamentals_before(conn: sqlite3.Connection, day: str) -> int:
    """Borra los datos financieros guardados antes de `day` y devuelve cuántas filas."""
    return conn.execute("DELETE FROM fundamentals WHERE fetched < ?", (day,)).rowcount


def fresh_fundamentals(conn: sqlite3.Connection, cutoff: str) -> list[tuple[str, str]]:
    """(ticker, JSON de datos financieros) guardados desde `cutoff` en adelante."""
    return conn.execute("SELECT ticker, data FROM fundamentals WHERE fetched >= ?", (cutoff,)).fetchall()


def save_fundamentals(conn: sqlite3.Connection, ticker: str, fetched: str, data_json: str) -> None:
    conn.execute("INSERT OR REPLACE INTO fundamentals (ticker, fetched, data) VALUES (?, ?, ?)",
                 (ticker, fetched, data_json))
