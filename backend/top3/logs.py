"""Logging del proyecto: consola a nivel INFO (avisos en amarillo, errores en rojo), archivo a nivel DEBUG."""
import json
import logging
import os
import re
import sys
import traceback
from pathlib import Path

from . import yahoo
from .errors import CATALOG, CFG_MISSING, SYS_PYTHON_WARNING

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


SUMMARY_FILE_ENV = "TOP3_SUMMARY_FILE"  # run_pipeline.py lo define para juntar los resúmenes de todos sus pasos
STEP_ENV = "TOP3_STEP"
_CODE = re.compile(r"^(TOP-[A-Z]{3}-\d{3}): ")


class SummaryHandler(logging.Handler):
    """Junta los avisos y errores de la corrida, agrupados por código, para el resumen final."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.items: dict[str, dict] = {}

    def emit(self, record: logging.LogRecord) -> None:
        text = record.getMessage()
        m = _CODE.match(text)
        code = m.group(1) if m else "sin código"
        item = self.items.setdefault(code, {"code": code, "count": 0, "level": logging.WARNING, "sample": text})
        item["count"] += 1
        item["level"] = max(item["level"], record.levelno)


_summary = SummaryHandler()


def format_summary(items: list[dict], logfile: str | None = None) -> list[str]:
    """Líneas del resumen. Cada item: code, count, level y sample (y steps, si vienen de varios pasos)."""
    errors = sum(i["count"] for i in items if i["level"] >= logging.ERROR)
    warnings = sum(i["count"] for i in items if i["level"] < logging.ERROR)
    lines = [paint("=" * 78, logging.INFO), f"RESUMEN DE AVISOS Y ERRORES: {errors} errores, {warnings} avisos",
             paint("=" * 78, logging.INFO)]
    ordered = sorted(items, key=lambda i: (-i["level"], i["code"]))  # errores primero
    for item in ordered:
        entry = CATALOG.get(item["code"])
        kind = "ERROR" if item["level"] >= logging.ERROR else "AVISO"
        title = entry.title if entry else item["sample"]
        steps = f"  [{', '.join(item['steps'])}]" if item.get("steps") else ""
        lines.append(paint(f"  {kind:<5} {item['code']}  x{item['count']}  {title}{steps}", item["level"]))
        if entry:
            lines.append(f"        ej.: {item['sample'][len(item['code']) + 2:]}")
            lines.append(f"        qué hacer: {entry.action}")
    lines.append(f"  Detalle: {logfile or 'log/'}  (buscar por código, p. ej. grep {ordered[0]['code']})")
    return lines


def print_summary() -> None:
    """Imprime el resumen de la corrida (nada si no hubo avisos ni errores). Si corre dentro del pipeline,
    en vez de imprimirlo lo deja en el archivo que junta el resumen de todos los pasos."""
    items = list(_summary.items.values())
    if not items:
        return
    path = os.environ.get(SUMMARY_FILE_ENV)
    if path:
        step = os.environ.get(STEP_ENV, "")
        with open(path, "a", encoding="utf-8") as f:
            f.writelines(json.dumps({**i, "step": step}) + "\n" for i in items)
        return
    print("\n" + "\n".join(format_summary(items, _logfile)), file=sys.stderr)


def merge_summaries(path: str | Path) -> list[dict]:
    """Junta lo que dejaron los pasos del pipeline: un item por código, con los pasos donde apareció."""
    merged: dict[str, dict] = {}
    p = Path(path)
    for line in (p.read_text(encoding="utf-8").splitlines() if p.exists() else []):
        item = json.loads(line)
        out = merged.setdefault(item["code"], {**item, "count": 0, "steps": []})
        out["count"] += item["count"]
        out["level"] = max(out["level"], item["level"])
        if item["step"] and item["step"] not in out["steps"]:
            out["steps"].append(item["step"])
    return list(merged.values())


def run_cli(main) -> None:
    """Ejecuta el `main` de un script. Un SystemExit con mensaje o una excepción se muestran como error (rojo) y
    quedan en el log; al final se imprime el resumen de avisos y errores, si los hubo."""
    code = None
    try:
        main()
    except SystemExit as e:
        if isinstance(e.code, str):
            log.error("%s", e.code)  # sin código: el mensaje del SystemExit ya trae su ID
            code = 1
        else:
            code = e.code
    except Exception:
        _excepthook(*sys.exc_info())
        code = 1
    print_summary()
    if code:
        raise SystemExit(code)


def _tag_python_warning(record: logging.LogRecord) -> bool:
    """Antepone el ID de aviso de Python a lo que captura logging.captureWarnings."""
    if not record.msg.startswith(SYS_PYTHON_WARNING.id):
        record.msg = SYS_PYTHON_WARNING.msg(record.msg)
    return True


_logfile: str | None = None


def setup_logging(logfile: str, log_dir: str) -> None:
    """Configura los handlers del logger; el archivo se sobrescribe en cada corrida."""
    global _logfile, _summary
    _logfile = str(Path(log_dir) / logfile)
    _summary = SummaryHandler()
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
    log.addHandler(_summary)
    # Los avisos de Python (pandas, yfinance...) quedan en el log con archivo y línea, no solo en stderr
    logging.captureWarnings(False)  # reinstala el gancho aunque ya estuviera activo
    logging.captureWarnings(True)
    warnings_log = logging.getLogger("py.warnings")
    warnings_log.handlers.clear()
    warnings_log.filters.clear()
    warnings_log.addFilter(_tag_python_warning)
    warnings_log.addHandler(file_handler)
    warnings_log.addHandler(console_handler)
    warnings_log.addHandler(_summary)
    # yfinance escribe sus errores por su propio logger: se ordenan (ver yahoo.triage) y quedan en el log y el resumen
    yf_log = logging.getLogger("yfinance")
    yf_log.propagate = False
    yf_log.handlers.clear()
    yf_log.filters.clear()
    yf_log.addFilter(yahoo.triage)
    for handler in (file_handler, console_handler, _summary):
        yf_log.addHandler(handler)


def log_config(cfg: dict, path: str | Path) -> None:
    """Deja en el log qué configuración se usó."""
    if Path(path).exists():
        log.info("Configuración cargada desde %s", path)
    else:
        log.warning(CFG_MISSING.msg("No existe %s, uso valores por defecto"), path)
    log.debug("Configuración efectiva: %s", cfg)
