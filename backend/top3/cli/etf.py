"""Ranking de momentum de los ETFs de Vanguard: retorno ajustado por riesgo, sin backtest.

Toma la lista de [etf] csv (por defecto vanguard_etfs.csv; antes le agrega los ETFs nuevos que Vanguard publica
en su página de productos, salvo con --no-update), descarga los precios ajustados y ordena los ETFs por
score = promedio del retorno / volatilidad en los plazos de [etf] horizons_months. Con --as-of calcula el ranking con
los datos hasta esa fecha (usa la lista actual: no es un backtest).
"""
import argparse

from ..etf import run_etf
from ..report_data import export_report
from .common import add_config_arg, start


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Ranking de momentum ajustado por riesgo de los ETFs de Vanguard")
    add_config_arg(ap)
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
    cfg = start(args.config, "etf_log")
    run_etf(cfg, as_of=args.as_of, top_n=args.top_n, csv_path=args.csv, update_list=not args.no_update)
    if not args.as_of:  # una consulta a una fecha pasada no se guarda, así que no cambia lo que muestra la web
        export_report(cfg)
