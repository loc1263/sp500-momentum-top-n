"""Limpia las corridas viejas del backtest. Ver top3/cli/prune.py."""
from top3.cli.prune import main
from top3.logs import run_cli

if __name__ == "__main__":
    run_cli(main)
