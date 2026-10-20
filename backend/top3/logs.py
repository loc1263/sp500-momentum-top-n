"""Logging del proyecto: consola a nivel INFO, archivo a nivel DEBUG."""
import logging
from pathlib import Path

from .errors import CFG_MISSING, SYS_PYTHON_WARNING

log = logging.getLogger("top3")
log.setLevel(logging.DEBUG)


def _tag_python_warning(record: logging.LogRecord) -> bool:
    """Antepone el ID de aviso de Python a lo que captura logging.captureWarnings."""
    if not record.msg.startswith(SYS_PYTHON_WARNING.id):
        record.msg = SYS_PYTHON_WARNING.msg(record.msg)
    return True


def setup_logging(logfile: str, log_dir: str) -> None:
    """Configura los handlers del logger; el archivo se sobrescribe en cada corrida."""
    log.handlers.clear()
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = logging.FileHandler(Path(log_dir) / logfile, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)
    log.addHandler(file_handler)
    log.addHandler(console_handler)
    # Los avisos de Python (pandas, yfinance...) quedan en el log con archivo y línea, no solo en stderr
    logging.captureWarnings(False)  # reinstala el gancho aunque ya estuviera activo
    logging.captureWarnings(True)
    warnings_log = logging.getLogger("py.warnings")
    warnings_log.handlers.clear()
    warnings_log.filters.clear()
    warnings_log.addFilter(_tag_python_warning)
    warnings_log.addHandler(file_handler)
    warnings_log.addHandler(console_handler)


def log_config(cfg: dict, path: str | Path) -> None:
    """Deja en el log qué configuración se usó."""
    if Path(path).exists():
        log.info("Configuración cargada desde %s", path)
    else:
        log.warning(CFG_MISSING.msg("No existe %s, uso valores por defecto"), path)
    log.debug("Configuración efectiva: %s", cfg)
