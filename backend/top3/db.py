"""SQLite: conexión, migraciones del esquema y metadatos de caché."""
import sqlite3
from datetime import date
from pathlib import Path

from . import errors as E
from .logs import log

# Cada migración es (versión, script SQL). La versión aplicada queda en PRAGMA user_version; para cambiar el esquema
# se agrega una migración al final (nunca se edita una ya publicada) y open_db la aplica sola.
MIGRATIONS: list[tuple[int, str]] = [
    (1, """
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
CREATE TABLE IF NOT EXISTS no_data_tickers (ticker TEXT PRIMARY KEY, checked TEXT);
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
CREATE TABLE IF NOT EXISTS actual_alternates (
    run_at TEXT, as_of TEXT, months INTEGER, min_cap_billions REAL,
    rank INTEGER, ticker TEXT, return_lookback REAL, price REAL, market_cap REAL
);
CREATE TABLE IF NOT EXISTS etf_scores (
    run_at TEXT, as_of TEXT, rank INTEGER, ticker TEXT, score REAL, vol REAL, max_dd REAL, sma_dist REAL,
    returns TEXT
);
CREATE TABLE IF NOT EXISTS fundamentals (ticker TEXT PRIMARY KEY, fetched TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS ohlcv (
    ticker TEXT NOT NULL, date TEXT NOT NULL, open REAL, high REAL, low REAL, close REAL NOT NULL, volume REAL,
    PRIMARY KEY (ticker, date)
);
CREATE TABLE IF NOT EXISTS quant_runs (run_at TEXT PRIMARY KEY, as_of TEXT, payload TEXT);
CREATE INDEX IF NOT EXISTS idx_selections_run ON selections (run_id);
CREATE INDEX IF NOT EXISTS idx_equity_run ON equity (run_id);
CREATE INDEX IF NOT EXISTS idx_runs_run_at ON runs (run_at);
"""),
    (2, """
CREATE INDEX IF NOT EXISTS idx_actual_picks_key ON actual_picks (months, min_cap_billions, as_of);
CREATE INDEX IF NOT EXISTS idx_actual_alternates_run ON actual_alternates (run_at);
CREATE INDEX IF NOT EXISTS idx_etf_scores_as_of ON etf_scores (as_of);
CREATE INDEX IF NOT EXISTS idx_prices_date ON prices (date);
"""),
]
LATEST_VERSION = MIGRATIONS[-1][0]


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection) -> None:
    """Lleva el esquema a la última versión aplicando, en orden, las migraciones que faltan."""
    current = schema_version(conn)
    if current > LATEST_VERSION:
        raise SystemExit(E.DAT_DB_NEWER.msg(f"La base tiene el esquema v{current} y este código llega a v{LATEST_VERSION}."))
    for version, script in MIGRATIONS:
        if version > current:
            conn.executescript(script)
            conn.execute(f"PRAGMA user_version = {version}")  # PRAGMA no admite parámetros
            log.debug("Esquema SQLite migrado a v%d", version)


def open_db(path: str | Path) -> sqlite3.Connection:
    """Abre la base (creando carpeta y tablas si faltan) con el esquema al día."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    migrate(conn)
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
