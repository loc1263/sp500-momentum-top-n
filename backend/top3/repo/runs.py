"""Corridas del backtest guardadas: resumen (runs), selecciones y curva de capital."""
import json
import sqlite3
from datetime import date, datetime, timedelta
from typing import NamedTuple

from ..db import fetched_today, set_meta
from ..engine import BacktestResult
from ..logs import log


class RunRow(NamedTuple):
    id: int
    params: str
    start_date: str
    end_date: str
    final_capital: float
    total_return: float
    cagr: float


def save_run(conn: sqlite3.Connection, params: dict, start_date: str, end_date: str,
             result: BacktestResult) -> int:
    """Guarda una corrida (resumen, selecciones y curva de capital) y devuelve su id."""
    cur = conn.execute(
        "INSERT INTO runs (run_at, params, start_date, end_date, final_capital, total_return, cagr) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), json.dumps(params, default=str),
         start_date, end_date, result.final_capital, result.total_return_pct, result.cagr_pct))
    run_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO selections (run_id, rebalance_date, rank, ticker, return_lookback) VALUES (?, ?, ?, ?, ?)",
        [(run_id, h["date"], rank, t, r)
         for h in result.history for rank, (t, r) in enumerate(h["returns"].items(), 1)])
    conn.executemany(
        "INSERT INTO equity (run_id, date, capital) VALUES (?, ?, ?)",
        [(run_id, d.strftime("%Y-%m-%d"), float(c)) for d, c in result.equity_curve.items()])
    conn.commit()
    log.info("Resultados guardados en SQLite (runs.id=%d)", run_id)
    return run_id


def run_key(params: dict) -> tuple | None:
    """Qué corrida es para el informe: (universo, años del período, plazo, desfase, meses saltados del modelo).
    None si no es de un sweep. Las corridas anteriores al modelo skip-month cuentan como 0."""
    if "sweep_months" not in params:
        return None
    years = float(params.get("backtest", {}).get("backtest_years", 5))
    return (float(params.get("min_cap_billions") or 0), years, int(params["sweep_months"]),
            int(params.get("offset_months", 0)), int(params.get("skip_months", 0)))


def latest_day(conn: sqlite3.Connection) -> str | None:
    """Fecha (YYYY-MM-DD) de la corrida más reciente, o None si no hay ninguna."""
    return conn.execute("SELECT MAX(substr(run_at, 1, 10)) FROM runs").fetchone()[0]


def runs_of_day(conn: sqlite3.Connection, day: str) -> list[RunRow]:
    """Las corridas de un día, de la más vieja a la más nueva."""
    return [RunRow(*r) for r in conn.execute(
        "SELECT id, params, start_date, end_date, final_capital, total_return, cagr "
        "FROM runs WHERE substr(run_at, 1, 10) = ? ORDER BY id", (day,))]


def equity_curve(conn: sqlite3.Connection, run_id: int) -> list[tuple[str, float]]:
    """(fecha, capital) de una corrida."""
    return conn.execute("SELECT date, capital FROM equity WHERE run_id = ? ORDER BY date", (run_id,)).fetchall()


def selections(conn: sqlite3.Connection, run_id: int) -> list[tuple[str, int, str, float]]:
    """(fecha de rebalanceo, puesto, ticker, retorno del ranking) de una corrida."""
    return conn.execute(
        "SELECT rebalance_date, rank, ticker, return_lookback FROM selections WHERE run_id = ? "
        "ORDER BY rebalance_date, rank", (run_id,)).fetchall()


def prune_runs(conn: sqlite3.Connection, keep_days: int) -> int:
    """Borra las corridas viejas del backtest y devuelve cuántas.

    Se conservan los últimos `keep_days` días con corridas (contados desde el día más reciente, mínimo 1) y, dentro
    de ellos, solo la última corrida de cada `run_key` por día: es la única que usa el informe. Las corridas que no
    son de un sweep se agrupan por sus parámetros exactos. `actual_picks` no se toca (historial del Top actual).
    """
    last_day = latest_day(conn)
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
