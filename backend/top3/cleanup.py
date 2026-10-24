"""Limpieza de lo viejo para que el disco no se llene: reportes HTML, corridas del backtest y datos de caché vencidos.

Qué NO se borra, a propósito: `actual_picks`/`actual_alternates` y `etf_scores` (de ahí salen el calendario de
rebalanceo, los cambios contra la corrida anterior y el seguimiento de cada selección; pesan muy poco) y los precios
dentro de la ventana de `[data] history_years` (el backtest los necesita)."""
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import Config
from .db import open_db
from .logs import log
from .repo import cache as cache_store, prices as prices_store, runs as runs_store

_FILE_DAY = re.compile(r"_(\d{8})\.html$")   # los reportes terminan en _YYYYMMDD.html (ver html_report.write_html)


@dataclass
class CleanupReport:
    files: list[Path] = field(default_factory=list)
    rows: dict[str, int] = field(default_factory=dict)    # filas borradas por concepto

    @property
    def empty(self) -> bool:
        return not self.files and not any(self.rows.values())


def prune_output_files(output_dir: str | Path, keep_days: int) -> list[Path]:
    """Borra los reportes HTML de `output_dir` (y sus subcarpetas) de hace más de `keep_days` días. Los días se cuentan
    desde el reporte más reciente (no desde hoy) y siempre se conserva al menos ese último día, para que dejar de correr
    el pipeline una semana no borre todos los reportes."""
    dated = []
    for path in Path(output_dir).rglob("*.html"):
        m = _FILE_DAY.search(path.name)
        if m:
            dated.append((datetime.strptime(m.group(1), "%Y%m%d").date(), path))
    if not dated:
        return []
    cutoff = max(d for d, _ in dated) - timedelta(days=max(keep_days, 1) - 1)
    doomed = sorted(path for day, path in dated if day < cutoff)
    for path in doomed:
        path.unlink()
    return doomed


def prune_stale_data(conn: sqlite3.Connection, cfg: Config, today: date | None = None) -> dict[str, int]:
    """Borra de SQLite lo que ya no se va a usar: precios anteriores a la ventana del histórico y datos de caché
    (acciones en circulación, datos financieros, tickers sin datos) más viejos que su propia vigencia."""
    today = today or date.today()
    data = cfg.data

    def before(days: int) -> str:
        return (today - timedelta(days=days)).isoformat()

    rows = {
        "precios fuera de la ventana": prices_store.delete_before(conn, data.history_start(today)),
        "acciones en circulación vencidas": cache_store.delete_shares_before(conn, before(data.shares_ttl_days)),
        "datos financieros vencidos": cache_store.delete_fundamentals_before(
            conn, before(cfg.quant.fundamentals_ttl_days)),
        "tickers sin datos vencidos": prices_store.forget_no_data_before(conn, before(data.no_data_ttl_days)),
    }
    conn.commit()
    return rows


def run_cleanup(cfg: Config, keep_days: int | None = None) -> CleanupReport:
    """Limpieza completa: reportes HTML, corridas viejas del backtest y datos vencidos; luego compacta la base."""
    report = CleanupReport()
    report.files = prune_output_files(cfg.output.dir, keep_days or cfg.output.keep_days)
    conn = open_db(cfg.data.db_path)
    try:
        report.rows["corridas del backtest"] = runs_store.prune_runs(conn, keep_days or cfg.data.runs_keep_days)
        report.rows.update(prune_stale_data(conn, cfg))
        if any(report.rows.values()):
            conn.execute("VACUUM")   # devuelve el espacio al disco; fuera de transacción (todo está confirmado)
    finally:
        conn.close()
    log.info("Limpieza: %d reportes HTML borrados; %s", len(report.files),
             ", ".join(f"{name}: {n}" for name, n in report.rows.items()))
    return report
