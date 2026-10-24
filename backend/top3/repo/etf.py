"""Ranking de ETFs guardado (etf_scores)."""
import json
import sqlite3
from datetime import datetime


def replace_scores(conn: sqlite3.Connection, as_of: str, rows: list[tuple]) -> None:
    """Guarda el ranking de `as_of` como filas (puesto, ticker, score, vol, caída máx., dist. SMA, retornos por
    plazo); repetir la corrida con los mismos datos lo reemplaza."""
    run_at = datetime.now().isoformat(timespec="seconds")
    conn.execute("DELETE FROM etf_scores WHERE as_of = ?", (as_of,))
    conn.executemany(
        "INSERT INTO etf_scores (run_at, as_of, rank, ticker, score, vol, max_dd, sma_dist, returns) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(run_at, as_of, rank, ticker, score, vol, max_dd, sma_dist, json.dumps(returns))
         for rank, ticker, score, vol, max_dd, sma_dist, returns in rows])
    conn.commit()


def previous_top(conn: sqlite3.Connection, as_of: str, top_n: int) -> tuple[str | None, list[str]]:
    """(fecha, tickers del top) del ranking guardado inmediatamente anterior a `as_of`, o (None, [])."""
    prev = conn.execute("SELECT MAX(as_of) FROM etf_scores WHERE as_of < ?", (as_of,)).fetchone()[0]
    if prev is None:
        return None, []
    rows = conn.execute("SELECT ticker FROM etf_scores WHERE as_of = ? AND rank <= ? ORDER BY rank",
                        (prev, top_n)).fetchall()
    return prev, [r[0] for r in rows]


def latest_as_of(conn: sqlite3.Connection) -> str | None:
    return conn.execute("SELECT MAX(as_of) FROM etf_scores").fetchone()[0]


def ranking(conn: sqlite3.Connection, as_of: str) -> list[tuple]:
    """(puesto, ticker, score, vol, caída máx., dist. SMA, retornos por plazo (dict), run_at) de un día."""
    return [(rank, ticker, score, vol, max_dd, sma_dist, json.loads(returns), run_at)
            for rank, ticker, score, vol, max_dd, sma_dist, returns, run_at in conn.execute(
                "SELECT rank, ticker, score, vol, max_dd, sma_dist, returns, run_at FROM etf_scores "
                "WHERE as_of = ? ORDER BY rank", (as_of,))]
