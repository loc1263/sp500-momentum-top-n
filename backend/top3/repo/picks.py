"""Top actual guardado (actual_picks y actual_alternates) y su historial."""
import sqlite3
from typing import NamedTuple

_KEY = "months = ? AND COALESCE(min_cap_billions, 0) = ?"
_COLUMNS = "run_at, as_of, months, min_cap_billions, rank, ticker, return_lookback, price, market_cap"


class Pick(NamedTuple):
    """Una acción elegida (o suplente) del Top actual."""

    rank: int
    ticker: str
    return_lookback: float
    price: float
    market_cap: float | None


def replace_picks(conn: sqlite3.Connection, run_at: str, as_of: str, months: int, min_cap_b: float | None,
                  picks: list[Pick], alternates: list[Pick]) -> None:
    """Guarda el Top y los suplentes de `as_of`; repetir la corrida con los mismos datos reemplaza la anterior."""
    for table, rows in (("actual_picks", picks), ("actual_alternates", alternates)):
        conn.execute(f"DELETE FROM {table} WHERE as_of = ? AND {_KEY}", (as_of, months, min_cap_b or 0))
        conn.executemany(f"INSERT INTO {table} ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         [(run_at, as_of, months, min_cap_b, *p) for p in rows])
    conn.commit()


def previous_picks(conn: sqlite3.Connection, as_of: str, months: int,
                   min_cap_b: float | None) -> tuple[str | None, list[str]]:
    """(fecha de datos, tickers) de la corrida guardada inmediatamente anterior a `as_of`, o (None, [])."""
    prev = conn.execute(f"SELECT MAX(as_of) FROM actual_picks WHERE as_of < ? AND {_KEY}",
                        (as_of, months, min_cap_b or 0)).fetchone()[0]
    if prev is None:
        return None, []
    rows = conn.execute(f"SELECT ticker FROM actual_picks WHERE as_of = ? AND {_KEY} ORDER BY rank",
                        (prev, months, min_cap_b or 0)).fetchall()
    return prev, [r[0] for r in rows]


def anchor_date(conn: sqlite3.Connection, months: int, min_cap_b: float | None) -> str | None:
    """Fecha de datos de la primera corrida guardada: de ahí se cuenta el calendario de rebalanceo."""
    return conn.execute(f"SELECT MIN(as_of) FROM actual_picks WHERE {_KEY}",
                        (months, min_cap_b or 0)).fetchone()[0]


def latest_run_at(conn: sqlite3.Connection) -> str | None:
    return conn.execute("SELECT MAX(run_at) FROM actual_picks").fetchone()[0]


def runs_of_day(conn: sqlite3.Connection, day: str) -> list[tuple]:
    """Filas (run_at, as_of, months, universo, rank, ticker, retorno, precio, cap.) de las corridas de un día.
    El universo viene como 0 para el índice completo."""
    return conn.execute(
        "SELECT run_at, as_of, months, COALESCE(min_cap_billions, 0), rank, ticker, return_lookback, price, "
        "market_cap FROM actual_picks WHERE substr(run_at, 1, 10) = ? ORDER BY run_at, rank", (day,)).fetchall()


def alternates(conn: sqlite3.Connection, run_at: str, months: int, cap: float) -> list[Pick]:
    return [Pick(*r) for r in conn.execute(
        "SELECT rank, ticker, return_lookback, price, market_cap FROM actual_alternates WHERE run_at = ? "
        "AND COALESCE(min_cap_billions, 0) = ? AND months = ? ORDER BY rank", (run_at, cap, months))]


def latest_picks_by_date(conn: sqlite3.Connection, cap: float, months: int) -> dict[str, list[tuple[str, float]]]:
    """{fecha de datos: [(ticker, precio)]} de la última corrida guardada de cada fecha, para el seguimiento."""
    rows = conn.execute(
        f"SELECT as_of, ticker, price FROM actual_picks WHERE {_KEY} "
        "AND run_at = (SELECT MAX(run_at) FROM actual_picks p WHERE p.as_of = actual_picks.as_of "
        "AND COALESCE(p.min_cap_billions, 0) = ? AND p.months = ?) ORDER BY as_of, rank",
        (months, cap, cap, months)).fetchall()
    by_date: dict[str, list[tuple[str, float]]] = {}
    for as_of, ticker, price in rows:
        by_date.setdefault(as_of, []).append((ticker, price))
    return by_date
