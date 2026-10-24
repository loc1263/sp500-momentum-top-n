"""Limpia las corridas viejas del backtest de la base SQLite (también se hace sola, una vez por día, al correr
top3_backtest.py)."""
import argparse

from top3.config import load_config
from top3.console import configure_console
from top3.db import maybe_prune_runs, open_db
from top3.logs import log_config, run_cli, setup_logging


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Borra las corridas viejas del backtest de SQLite")
    ap.add_argument("--config", default="config.toml", help="Archivo de configuración (default: config.toml)")
    ap.add_argument("--keep-days", type=int, default=None, metavar="N",
                    help="Días con corridas a conservar (default: [data] runs_keep_days del config)")
    args = ap.parse_args(argv)
    configure_console()
    cfg = load_config(args.config)
    setup_logging(cfg.output.prune_log, cfg.output.log_dir)
    log_config(cfg, args.config)
    conn = open_db(cfg.data.db_path)
    try:
        n = maybe_prune_runs(conn, args.keep_days or cfg.data.runs_keep_days, force=True)
    finally:
        conn.close()
    print(f"Corridas borradas: {n}")


if __name__ == "__main__":
    run_cli(main)
