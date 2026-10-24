"""Limpieza de lo viejo: reportes HTML de output/, corridas del backtest y datos de caché vencidos de SQLite
(y compacta la base). El pipeline la corre al final; ver top3/cleanup.py para lo que se borra y lo que no."""
import argparse

from ..cleanup import run_cleanup
from .common import add_config_arg, start


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Borra reportes, corridas y datos viejos para no llenar el disco")
    add_config_arg(ap)
    ap.add_argument("--keep-days", type=int, default=None, metavar="N",
                    help="Días a conservar de reportes HTML y corridas del backtest "
                         "(default: [output] keep_days y [data] runs_keep_days del config)")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    cfg = start(args.config, "prune_log")
    report = run_cleanup(cfg, args.keep_days)
    print(f"Reportes HTML borrados: {len(report.files)}")
    for name, n in report.rows.items():
        print(f"{name.capitalize()}: {n} filas borradas")
