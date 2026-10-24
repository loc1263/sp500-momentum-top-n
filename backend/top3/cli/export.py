"""Exporta a JSON los resultados del día (backtest + Top actual + ETFs + modelo por score) guardados en SQLite.

Escribe el archivo de [output] frontend_data del config. Lo hacen solos los demás comandos al terminar; este
sirve para regenerarlo sin volver a correr nada.
"""
import argparse

from ..report_data import export_report
from .common import add_config_arg, start


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Exporta los resultados de SQLite a JSON para el frontend")
    add_config_arg(ap)
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    cfg = start(args.config, "export_log")
    print(export_report(cfg))
