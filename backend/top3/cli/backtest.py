"""Backtest Top N del S&P 500 (Point-in-Time), comparación de plazos y sensibilidad al calendario de arranque.

Cada N meses se compran, con ponderación igual, las N acciones del S&P 500 que más subieron en los últimos N meses.
Todo se guarda en SQLite y, al terminar, se actualiza el JSON que lee el frontend.
"""
import argparse

from ..db import open_db
from ..repo.runs import maybe_prune_runs
from ..report_data import export_report
from ..workflow import BacktestJob, run_backtest_job
from .common import add_config_arg, add_universe_args, start


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Backtest Top N S&P 500 (Point-in-Time) con caché SQLite")
    add_config_arg(ap)
    ap.add_argument("--no-cache", action="store_true",
                    help="Ignora la información guardada hoy y vuelve a descargar todo")
    ap.add_argument("--sweep", action="store_true",
                    help="Simula varios plazos (config [simulation] months) y compara el retorno final")
    ap.add_argument("--months", type=int, default=None, metavar="N",
                    help="Plazo del backtest normal en meses (default: [backtest] months del config)")
    ap.add_argument("--offsets", action="store_true",
                    help="Para cada plazo de --sweep prueba todos los calendarios de arranque posibles "
                         "y reporta mediana y rango (mide cuánto es azar de calendario)")
    add_universe_args(ap,
                      "Universo solo large-cap + mega-cap (config [universe] min_cap_billions); "
                      "el reporte HTML lleva el sufijo _largecap",
                      "Como --large-cap pero con otro umbral de capitalización (miles de millones de US$); "
                      "por ejemplo 200 = mega-cap")
    ap.add_argument("--years", type=float, default=None, metavar="N",
                    help="Corre un único período de N años (default: todos los de [backtest] periods_years)")
    return ap.parse_args(argv)


def job_from_args(args: argparse.Namespace) -> BacktestJob:
    return BacktestJob(sweep=args.sweep, offsets=args.offsets, months=args.months, years=args.years,
                       large_cap=args.large_cap, min_cap_billions=args.min_cap_billions,
                       use_cache=not args.no_cache)


def main(argv=None) -> None:
    args = parse_args(argv)
    cfg = start(args.config, "backtest_log")
    job = job_from_args(args)
    reports = run_backtest_job(cfg, job)
    if job.sweep or job.offsets:
        print("\nReportes HTML generados:")
        for path in reports:
            print(f"  {path}")
    export_report(cfg)
    conn = open_db(cfg.data.db_path)
    try:
        maybe_prune_runs(conn, cfg.data.runs_keep_days)
    finally:
        conn.close()
