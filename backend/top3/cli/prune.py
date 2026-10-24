"""Limpia las corridas viejas del backtest de la base SQLite (también se hace sola, una vez por día, al correr
el backtest)."""
import argparse

from ..db import open_db
from ..repo.runs import maybe_prune_runs
from .common import add_config_arg, start


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Borra las corridas viejas del backtest de SQLite")
    add_config_arg(ap)
    ap.add_argument("--keep-days", type=int, default=None, metavar="N",
                    help="Días con corridas a conservar (default: [data] runs_keep_days del config)")
    return ap.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    cfg = start(args.config, "prune_log")
    conn = open_db(cfg.data.db_path)
    try:
        n = maybe_prune_runs(conn, args.keep_days or cfg.data.runs_keep_days, force=True)
    finally:
        conn.close()
    print(f"Corridas borradas: {n}")
