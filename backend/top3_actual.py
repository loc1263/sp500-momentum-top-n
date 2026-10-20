"""Top N actual del S&P 500: las acciones que más subieron en los últimos N meses.

Usa la misma lógica, configuración y base SQLite que top3_backtest.py (plazo en meses, top_n, alias de tickers,
universo por capitalización), pero aplicada a hoy.
"""
import argparse

from top3.actual import run_actual
from top3.config import load_config
from top3.console import configure_console
from top3.logs import log_config, run_cli, setup_logging
from top3.report_data import export_report


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Top N actual del S&P 500 (mismo criterio que top3_backtest.py)")
    ap.add_argument("--config", default="config.toml", help="Archivo de configuración (default: config.toml)")
    ap.add_argument("--no-cache", action="store_true", help="Ignora lo descargado hoy y vuelve a descargar")
    ap.add_argument("--months", type=int, default=None, metavar="N",
                    help="Plazo en meses (default: [backtest] months del config)")
    ap.add_argument("--top-n", type=int, default=None, metavar="N",
                    help="Cantidad de acciones (default: [backtest] top_n del config)")
    ap.add_argument("--large-cap", action="store_true",
                    help="Solo large-cap + mega-cap (config [universe] min_cap_billions)")
    ap.add_argument("--min-cap-billions", type=float, default=None, metavar="N",
                    help="Como --large-cap con otro umbral de capitalización (miles de millones de US$)")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    configure_console()
    cfg = load_config(args.config)
    setup_logging(cfg["output"]["actual_log"], cfg["output"]["log_dir"])
    log_config(cfg, args.config)

    min_cap_b = None
    if args.large_cap or args.min_cap_billions is not None:
        min_cap_b = (args.min_cap_billions if args.min_cap_billions is not None
                     else float(cfg["universe"]["min_cap_billions"]))
    run_actual(cfg, months=args.months or int(cfg["backtest"]["months"]),
               top_n=args.top_n or int(cfg["backtest"]["top_n"]), min_cap_b=min_cap_b,
               use_cache=not args.no_cache)
    export_report(cfg)


if __name__ == "__main__":
    run_cli(main)
