"""SQLite: esquema, conexión y metadatos de caché."""
import sqlite3
from datetime import date, datetime, timedelta
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


def prune_runs(conn: sqlite3.Connection, keep_days: int) -> int:
    """Borra las corridas viejas del backtest y devuelve cuántas.

    Se conservan los últimos `keep_days` días con corridas (contados desde el día más reciente, mínimo 1) y, dentro
    de ellos, solo la última corrida de cada combinación de parámetros por día: es la única que usa el informe.
    `actual_picks` no se toca (es el historial de las selecciones de hoy).
    """
    last_day = conn.execute("SELECT MAX(substr(run_at, 1, 10)) FROM runs").fetchone()[0]
    if not last_day:
        return 0
    cutoff = (datetime.fromisoformat(last_day) - timedelta(days=max(keep_days, 1) - 1)).date().isoformat()
    doomed = """
        SELECT id FROM runs WHERE substr(run_at, 1, 10) < :cutoff
        OR id NOT IN (SELECT MAX(id) FROM runs GROUP BY substr(run_at, 1, 10), params)"""
    conn.execute(f"CREATE TEMP TABLE doomed AS {doomed}", {"cutoff": cutoff})
    try:
        n = conn.execute("SELECT COUNT(*) FROM doomed").fetchone()[0]
        if n:
            for table, column in (("selections", "run_id"), ("equity", "run_id"), ("runs", "id")):
                conn.execute(f"DELETE FROM {table} WHERE {column} IN (SELECT id FROM doomed)")
            conn.commit()
            log.info("Limpieza: %d corridas viejas borradas (se conservan %d días, hasta %s)", n, keep_days, last_day)
    finally:
        conn.execute("DROP TABLE doomed")
    return n


def maybe_prune_runs(conn: sqlite3.Connection, keep_days: int, force: bool = False) -> int:
    """`prune_runs` como mucho una vez por día (salvo `force`); compacta el archivo si borró algo."""
    if not force and fetched_today(conn, "runs_pruned"):
        return 0
    n = prune_runs(conn, keep_days)
    set_meta(conn, "runs_pruned", date.today().isoformat())
    conn.commit()
    if n:
        conn.execute("VACUUM")  # fuera de transacción; devuelve el espacio al disco
    return n
