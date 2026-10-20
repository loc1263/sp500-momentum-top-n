"""Ranking de momentum de los ETFs de Vanguard: retorno ajustado por riesgo, sin backtest.

Toma la lista de [etf] csv (por defecto vanguard_etfs.csv), descarga los precios ajustados y ordena los ETFs por
score = promedio del retorno / volatilidad en los plazos de [etf] horizons_months. Con --as-of calcula el ranking con
los datos hasta esa fecha (usa la lista actual: no es un backtest).
"""
import argparse

from top3.config import load_config
from top3.console import configure_console
from top3.etf import run_etf
from top3.logs import log_config, run_cli, setup_logging


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Ranking de momentum ajustado por riesgo de los ETFs de Vanguard")
    ap.add_argument("--config", default="config.toml", help="Archivo de configuración (default: config.toml)")
    ap.add_argument("--as-of", default=None, metavar="YYYY-MM-DD",
                    help="Calcula el ranking con los datos hasta esa fecha (default: hoy)")
    ap.add_argument("--top-n", type=int, default=None, metavar="N",
                    help="Cuántos ETFs mostrar en la consola (default: [etf] top_n del config)")
    ap.add_argument("--csv", default=None, help="Otra lista de ETFs (default: [etf] csv del config)")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    configure_console()
    cfg = load_config(args.config)
    setup_logging(cfg["output"]["etf_log"], cfg["output"]["log_dir"])
    log_config(cfg, args.config)
    run_etf(cfg, as_of=args.as_of, top_n=args.top_n, csv_path=args.csv)


if __name__ == "__main__":
    run_cli(main)
