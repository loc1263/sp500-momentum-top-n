"""Modelo base: score de momentum, de salud financiera y técnico de las acciones del S&P 500, su promedio como score final y
Markowitz sobre las mejores. No hace backtest. Los parámetros están en config.toml [quant]. Guarda todo en SQLite y
actualiza el JSON del frontend.
"""
import argparse

from top3.config import load_config
from top3.console import configure_console
from top3.logs import log_config, run_cli, setup_logging
from top3.quant.run import run_quant
from top3.report_data import export_report


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Scores de momentum, salud financiera y técnico del S&P 500 y Markowitz del top")
    ap.add_argument("--config", default="config.toml", help="Archivo de configuración (default: config.toml)")
    ap.add_argument("--no-cache", action="store_true",
                    help="Vuelve a descargar precios, OHLCV y datos financieros en lugar de reutilizarlos")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    configure_console()
    cfg = load_config(args.config)
    setup_logging(cfg["output"]["quant_log"], cfg["output"]["log_dir"])
    log_config(cfg, args.config)
    payload = run_quant(cfg, use_cache=not args.no_cache)
    print(f"Ranking al {payload['as_of']} ({payload['coverage']['ranked']} acciones). Las mejores:")
    for r in payload["ranking"][:payload["settings"]["top_n"]]:
        print(f"  {r['rank']:>2}. {r['ticker']:<6} score {r['score']:5.1f} "
              f"(momentum {r['momentum']:5.1f}, salud {r['health']:5.1f}, técnico {r['technical']:5.1f})")
    export_report(cfg)


if __name__ == "__main__":
    run_cli(main)
