"""Top N actual del S&P 500: las acciones que más subieron en los últimos N meses.

Usa la misma lógica, configuración y base SQLite que el backtest (plazo en meses, top_n, alias de tickers,
universo por capitalización), pero aplicada a hoy.
"""
import argparse

from ..actual import run_actual
from ..report_data import export_report
from ..universe import explicit_min_cap
from .common import add_config_arg, add_universe_args, start


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Top N actual del S&P 500 (mismo criterio que el backtest)")
    add_config_arg(ap)
    ap.add_argument("--no-cache", action="store_true", help="Ignora lo descargado hoy y vuelve a descargar")
    ap.add_argument("--months", type=int, default=None, metavar="N",
                    help="Plazo en meses (default: [backtest] months del config)")
    ap.add_argument("--top-n", type=int, default=None, metavar="N",
                    help="Cantidad de acciones (default: [backtest] top_n del config)")
    add_universe_args(ap,
                      "Solo large-cap + mega-cap (config [universe] min_cap_billions)",
                      "Como --large-cap con otro umbral de capitalización (miles de millones de US$)")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    cfg = start(args.config, "actual_log")
    run_actual(cfg, months=args.months or cfg.backtest.months, top_n=args.top_n or cfg.backtest.top_n,
               min_cap_b=explicit_min_cap(cfg, args.large_cap, args.min_cap_billions), use_cache=not args.no_cache)
    export_report(cfg)
