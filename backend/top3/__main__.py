"""Punto de entrada único: `python -m top3 <comando> [opciones]`."""
import importlib
import sys

from .logs import run_cli

COMMANDS = ("backtest", "actual", "etf", "quant", "export", "prune", "pipeline")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        sys.exit(f"Uso: python -m top3 {{{'|'.join(COMMANDS)}}} [opciones]  (--help en cada comando)")
    command = sys.argv.pop(1)
    module = importlib.import_module(f"top3.cli.{command}")
    if command == "pipeline":
        module.main()
    else:
        run_cli(module.main)


if __name__ == "__main__":
    main()
