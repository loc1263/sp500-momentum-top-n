"""Exporta a JSON los resultados del día (backtest + Top actual) guardados en SQLite, para el frontend.

Escribe el archivo de [output] frontend_data del config. Lo hacen solos top3_backtest.py y top3_actual.py al
terminar; este script sirve para regenerarlo sin volver a correr nada.
"""
import argparse

from top3.config import load_config
from top3.logs import log_config, setup_logging
from top3.report_data import export_report


def main() -> None:
    ap = argparse.ArgumentParser(description="Exporta los resultados de SQLite a JSON para el frontend")
    ap.add_argument("--config", default="config.toml", help="Archivo de configuración (default: config.toml)")
    args = ap.parse_args()
    cfg = load_config(args.config)
    setup_logging(cfg["output"]["export_log"], cfg["output"]["log_dir"])
    log_config(cfg, args.config)
    print(export_report(cfg))


if __name__ == "__main__":
    main()
