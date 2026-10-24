"""Exporta los resultados de SQLite al JSON del frontend. Ver top3/cli/export.py."""
from top3.cli.export import main
from top3.logs import run_cli

if __name__ == "__main__":
    run_cli(main)
