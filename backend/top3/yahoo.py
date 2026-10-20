"""Errores que yfinance informa por su propio logger: se clasifican, se capturan para reintentar y se ordenan.

No importa `logs` (lo importa él): solo trabaja con `logging` y el catálogo de códigos.
"""
import logging
from contextlib import contextmanager

from . import errors as E

_RATE_LIMIT = ("rate limit", "too many requests", "yfratelimiterror")
_EXPECTED = ("possibly delisted", "no price data", "no data found", "no timezone found", "quote not found",
             "http error 404")


def is_expected_absence(text: str) -> bool:
    """True si el mensaje de yfinance dice que el ticker no existe o no tiene datos (dado de baja, renombrado)."""
    lower = text.lower()
    return any(s in lower for s in _EXPECTED)


def is_rate_limit(text: str) -> bool:
    """True si el mensaje de yfinance indica que Yahoo limitó las solicitudes."""
    lower = text.lower()
    return any(s in lower for s in _RATE_LIMIT)


def triage(record: logging.LogRecord) -> bool:
    """Filtro del logger «yfinance»: deja en el log solo lo que importa, con su ID.

    - Rate limit: error TOP-NET-005 (pierde datos de verdad; ver `fetch_prices`, que reintenta).
    - Tickers dados de baja / sin datos: esperables (cientos por corrida); solo al archivo, a nivel DEBUG.
    - Cualquier otro error de yfinance: aviso TOP-NET-007.
    - Las líneas por ticker («$ADM: ...») y el encabezado («2 Failed downloads:») repiten la línea agrupada:
      van a DEBUG para no contar el mismo fallo varias veces.
    """
    if record.levelno < logging.ERROR:
        return True
    text = record.getMessage().strip()
    if text.startswith("$") or "Failed download" in text:
        level, code = logging.DEBUG, None
    elif is_rate_limit(text):
        level, code = logging.ERROR, E.NET_RATE_LIMIT
    elif is_expected_absence(text):
        level, code = logging.DEBUG, None
    else:
        level, code = logging.WARNING, E.NET_YAHOO
    record.levelno, record.levelname = level, logging.getLevelName(level)
    record.msg, record.args = (code.msg(text) if code else text), ()
    return True


class _Collector(logging.Handler):
    """Guarda el último mensaje por ticker de las líneas «$TICKER: mensaje» que emite yfinance."""

    def __init__(self) -> None:
        super().__init__(logging.NOTSET)
        self.by_ticker: dict[str, str] = {}

    def emit(self, record: logging.LogRecord) -> None:
        text = record.getMessage().strip()
        if text.startswith("$") and ": " in text:
            ticker, message = text[1:].split(": ", 1)
            self.by_ticker[ticker] = message


@contextmanager
def capture_errors():
    """Con `with capture_errors() as errors:` queda en `errors` {ticker: mensaje} de lo que yfinance no pudo bajar."""
    collector = _Collector()
    yf_log = logging.getLogger("yfinance")
    yf_log.addHandler(collector)
    try:
        yield collector.by_ticker
    finally:
        yf_log.removeHandler(collector)
