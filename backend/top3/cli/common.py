"""Lo que comparten todos los comandos: argumentos comunes y el arranque (consola, configuración y logging)."""
import argparse

from ..config import Config, load_config
from ..console import configure_console
from ..logs import log_config, setup_logging


def add_config_arg(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--config", default="config.toml", help="Archivo de configuración (default: config.toml)")


def add_universe_args(ap: argparse.ArgumentParser, large_cap_help: str, min_cap_help: str) -> None:
    ap.add_argument("--large-cap", action="store_true", help=large_cap_help)
    ap.add_argument("--min-cap-billions", type=float, default=None, metavar="N", help=min_cap_help)


def start(config_path: str, log_name: str) -> Config:
    """Arranque de un comando: configura la consola, carga la configuración y abre el log `[output] <log_name>`."""
    configure_console()
    cfg = load_config(config_path)
    setup_logging(getattr(cfg.output, log_name), cfg.output.log_dir)
    log_config(cfg, config_path)
    return cfg
