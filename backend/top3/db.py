"""SQLite: esquema, conexión y metadatos de caché."""
import json
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
CREATE TABLE IF NOT EXISTS etf_scores (
    run_at TEXT, as_of TEXT, rank INTEGER, ticker TEXT, score REAL, vol REAL, max_dd REAL, sma_dist REAL,
    returns TEXT
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


def run_key(params: dict) -> tuple | None:
    """Qué corrida es para el informe: (universo, años del período, plazo, desfase). None si no es de un sweep."""
    if "sweep_months" not in params:
        return None
    years = float(params.get("backtest", {}).get("backtest_years", 5))
    return (float(params.get("min_cap_billions") or 0), years, int(params["sweep_months"]),
            int(params.get("offset_months", 0)))


def prune_runs(conn: sqlite3.Connection, keep_days: int) -> int:
    """Borra las corridas viejas del backtest y devuelve cuántas.

    Se conservan los últimos `keep_days` días con corridas (contados desde el día más reciente, mínimo 1) y, dentro
    de ellos, solo la última corrida de cada `run_key` por día: es la única que usa el informe. Las corridas que no
    son de un sweep se agrupan por sus parámetros exactos. `actual_picks` no se toca (historial del Top actual).
    """
    last_day = conn.execute("SELECT MAX(substr(run_at, 1, 10)) FROM runs").fetchone()[0]
    if not last_day:
        return 0
    cutoff = (datetime.fromisoformat(last_day) - timedelta(days=max(keep_days, 1) - 1)).date().isoformat()
    latest: dict[tuple, int] = {}
    doomed: list[int] = []
    for run_id, day, params in conn.execute("SELECT id, substr(run_at, 1, 10), params FROM runs ORDER BY id"):
        if day < cutoff:
            doomed.append(run_id)
            continue
        try:
            parsed = json.loads(params)
        except (TypeError, ValueError):
            parsed = {}
        group = (day, (run_key(parsed) if isinstance(parsed, dict) else None) or params)
        if group in latest:
            doomed.append(latest[group])  # la anterior del mismo día queda reemplazada
        latest[group] = run_id
    for table, column in (("selections", "run_id"), ("equity", "run_id"), ("runs", "id")):
        conn.executemany(f"DELETE FROM {table} WHERE {column} = ?", [(i,) for i in doomed])
    conn.commit()
    if doomed:
        log.info("Limpieza: %d corridas viejas borradas (se conservan %d días, hasta %s)", len(doomed), keep_days,
                 last_day)
    return len(doomed)


def maybe_prune_runs(conn: sqlite3.Connection, keep_days: int, force: bool = False) -> int:
    """Borra las corridas viejas en cada llamada (es rápido). Compactar el archivo (VACUUM) es lo caro: se hace
    como mucho una vez por día, salvo `force`."""
    n = prune_runs(conn, keep_days)
    if n and (force or not fetched_today(conn, "runs_vacuumed")):
        set_meta(conn, "runs_vacuumed", date.today().isoformat())
        conn.commit()
        conn.execute("VACUUM")  # fuera de transacción; devuelve el espacio al disco
    return n
