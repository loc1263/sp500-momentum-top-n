"""SQLite: esquema, conexión y metadatos de caché."""
import sqlite3
from datetime import date
from pathlib import Path

from .logs import log

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS constituents_history (date TEXT PRIMARY KEY, tickers TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS constituents_current (ticker TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS index_changes (
    date TEXT NOT NULL, added TEXT, removed TEXT, reason TEXT
);
CREATE TABLE IF NOT EXISTS prices (
    ticker TEXT NOT NULL, date TEXT NOT NULL, close REAL NOT NULL,
    PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS shares (ticker TEXT PRIMARY KEY, shares REAL, fetched TEXT);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT, params TEXT,
    start_date TEXT, end_date TEXT,
    final_capital REAL, total_return REAL, cagr REAL
);
CREATE TABLE IF NOT EXISTS selections (
    run_id INTEGER, rebalance_date TEXT, rank INTEGER, ticker TEXT, return_lookback REAL
);
CREATE TABLE IF NOT EXISTS equity (run_id INTEGER, date TEXT, capital REAL);
CREATE TABLE IF NOT EXISTS actual_picks (
    run_at TEXT, as_of TEXT, months INTEGER, min_cap_billions REAL,
    rank INTEGER, ticker TEXT, return_lookback REAL, price REAL, market_cap REAL
);
CREATE INDEX IF NOT EXISTS idx_selections_run ON selections (run_id);
CREATE INDEX IF NOT EXISTS idx_equity_run ON equity (run_id);
CREATE INDEX IF NOT EXISTS idx_runs_run_at ON runs (run_at);
"""


def open_db(path: str | Path) -> sqlite3.Connection:
    """Abre la base (creando carpeta y tablas si faltan)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    log.debug("SQLite abierta: %s", Path(path).resolve())
    return conn


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(value)))


def fetched_today(conn: sqlite3.Connection, key: str) -> bool:
    """True si el dato `key` se descargó hoy."""
    return get_meta(conn, key) == date.today().isoformat()
