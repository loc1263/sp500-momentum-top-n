"""Ranking de ETFs de Vanguard. Ver top3/cli/etf.py o --help."""
from top3.cli.etf import main
from top3.logs import run_cli

if __name__ == "__main__":
    run_cli(main)
