"""Logging del proyecto: consola a nivel INFO (avisos en amarillo, errores en rojo), archivo a nivel DEBUG."""
import logging
import os
import sys
import traceback
from pathlib import Path

from .errors import CFG_MISSING, SYS_PYTHON_WARNING

log = logging.getLogger("top3")
log.setLevel(logging.DEBUG)

FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
YELLOW, RED, RESET = "[33m", "[31m", "[0m"
_ansi_enabled = False


def stderr_color() -> bool:
    """Color ANSI solo si stderr es una terminal y no hay NO_COLOR (al redirigir a archivo/pipe no se ensucia)."""
    global _ansi_enabled
    if not sys.stderr.isatty() or os.environ.get("NO_COLOR"):
        return False
    if not _ansi_enabled:
        os.system("")  # habilita secuencias ANSI en la consola de Windows
        _ansi_enabled = True
    return True


def paint(text: str, level: int) -> str:
    """`text` en amarillo (WARNING) o rojo (ERROR o más) si la consola admite color."""
    if not stderr_color() or level < logging.WARNING:
        return text
    return f"{RED if level >= logging.ERROR else YELLOW}{text}{RESET}"


class ConsoleFormatter(logging.Formatter):
    """Formato de la consola: la línea completa (con el traceback, si lo hay) se pinta según el nivel."""

    def format(self, record: logging.LogRecord) -> str:
        return paint(super().format(record), record.levelno)


def _excepthook(exc_type, exc, tb) -> None:
    """Excepciones sin capturar: el traceback en rojo en la terminal."""
    sys.stderr.write(paint("".join(traceback.format_exception(exc_type, exc, tb)), logging.ERROR))


def run_cli(main) -> None:
    """Ejecuta el `main` de un script: un SystemExit con mensaje se muestra como error (rojo) y queda en el log."""
    try:
        main()
    except SystemExit as e:
        if not isinstance(e.code, str):
            raise
        log.error("%s", e.code)  # sin código: el mensaje del SystemExit ya trae su ID
        raise SystemExit(1) from None


def _tag_python_warning(record: logging.LogRecord) -> bool:
    """Antepone el ID de aviso de Python a lo que captura logging.captureWarnings."""
    if not record.msg.startswith(SYS_PYTHON_WARNING.id):
        record.msg = SYS_PYTHON_WARNING.msg(record.msg)
    return True


def setup_logging(logfile: str, log_dir: str) -> None:
    """Configura los handlers del logger; el archivo se sobrescribe en cada corrida."""
    log.handlers.clear()
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(FORMAT)
    file_handler = logging.FileHandler(Path(log_dir) / logfile, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ConsoleFormatter(FORMAT))
    sys.excepthook = _excepthook
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
