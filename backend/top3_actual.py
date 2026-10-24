"""Top N actual del S&P 500. Ver top3/cli/actual.py o --help."""
from top3.cli.actual import main
from top3.logs import run_cli

if __name__ == "__main__":
    run_cli(main)
