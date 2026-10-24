"""Composición del S&P 500 guardada: histórico (CSV), lista actual (Wikipedia) y altas/bajas del índice."""
import sqlite3


def replace_history(conn: sqlite3.Connection, rows: list[tuple[str, str]]) -> None:
    """rows = (fecha, tickers separados por coma)."""
    conn.execute("DELETE FROM constituents_history")
    conn.executemany("INSERT OR REPLACE INTO constituents_history (date, tickers) VALUES (?, ?)", rows)


def replace_current(conn: sqlite3.Connection, tickers: list[str]) -> None:
    conn.execute("DELETE FROM constituents_current")
    conn.executemany("INSERT OR IGNORE INTO constituents_current (ticker) VALUES (?)", [(t,) for t in tickers])


def replace_changes(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    """rows = (fecha, alta, baja, motivo)."""
    conn.execute("DELETE FROM index_changes")
    conn.executemany("INSERT INTO index_changes (date, added, removed, reason) VALUES (?, ?, ?, ?)", rows)


def history(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    return conn.execute("SELECT date, tickers FROM constituents_history ORDER BY date").fetchall()


def current(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT ticker FROM constituents_current")]


def changes_after(conn: sqlite3.Connection, day: str) -> list[tuple[str, str | None, str | None]]:
    """(fecha, alta, baja) posteriores a `day`."""
    return conn.execute("SELECT date, added, removed FROM index_changes WHERE date > ? ORDER BY date",
                        (day,)).fetchall()
