"""Modelo por score: score de momentum, de salud financiera y técnico de las acciones del S&P 500, su promedio como
score final y Markowitz sobre las mejores. No hace backtest. Los parámetros están en config.toml [quant]. Guarda todo
en SQLite y actualiza el JSON del frontend.
"""
import argparse

from ..quant.run import run_quant
from ..report_data import export_report
from .common import add_config_arg, start


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Scores de momentum, salud financiera y técnico del S&P 500 y Markowitz del top")
    add_config_arg(ap)
    ap.add_argument("--no-cache", action="store_true",
                    help="Vuelve a descargar precios, OHLCV y datos financieros en lugar de reutilizarlos")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    cfg = start(args.config, "quant_log")
    payload = run_quant(cfg, use_cache=not args.no_cache)
    print(f"Ranking al {payload['as_of']} ({payload['coverage']['ranked']} acciones). Las mejores:")
    for r in payload["ranking"][:payload["settings"]["top_n"]]:
        print(f"  {r['rank']:>2}. {r['ticker']:<6} score {r['score']:5.1f} "
              f"(momentum {r['momentum']:5.1f}, salud {r['health']:5.1f}, técnico {r['technical']:5.1f})")
    export_report(cfg)
