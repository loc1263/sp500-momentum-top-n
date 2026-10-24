"""Ranking de momentum de los ETFs de Vanguard: retorno ajustado por riesgo, sin backtest.

Toma la lista de [etf] csv (por defecto vanguard_etfs.csv; antes le agrega los ETFs nuevos que Vanguard publica
en su página de productos, salvo con --no-update), descarga los precios ajustados y ordena los ETFs por
score = promedio del retorno / volatilidad en los plazos de [etf] horizons_months. Con --as-of calcula el ranking con
los datos hasta esa fecha (usa la lista actual: no es un backtest).
"""
import argparse

from top3.config import load_config
from top3.console import configure_console
from top3.etf import run_etf
from top3.logs import log_config, run_cli, setup_logging
from top3.report_data import export_report


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Ranking de momentum ajustado por riesgo de los ETFs de Vanguard")
    ap.add_argument("--config", default="config.toml", help="Archivo de configuración (default: config.toml)")
    ap.add_argument("--as-of", default=None, metavar="YYYY-MM-DD",
                    help="Calcula el ranking con los datos hasta esa fecha (default: hoy)")
    ap.add_argument("--top-n", type=int, default=None, metavar="N",
                    help="Cuántos ETFs mostrar en la consola (default: [etf] top_n del config)")
    ap.add_argument("--csv", default=None, help="Otra lista de ETFs (default: [etf] csv del config)")
    ap.add_argument("--no-update", action="store_true",
                    help="No agrega a la lista los ETFs nuevos de Vanguard (default: los agrega, [etf] update_list)")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    configure_console()
    cfg = load_config(args.config)
    setup_logging(cfg.output.etf_log, cfg.output.log_dir)
    log_config(cfg, args.config)
    run_etf(cfg, as_of=args.as_of, top_n=args.top_n, csv_path=args.csv, update_list=not args.no_update)
    if not args.as_of:  # una consulta a una fecha pasada no se guarda, así que no cambia lo que muestra la web
        export_report(cfg)


if __name__ == "__main__":
    run_cli(main)
