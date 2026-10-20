"""Catálogo de códigos de error y aviso (al estilo ORA-00942): cada mensaje del log y de las excepciones lleva su ID.

Formato: TOP-<ÁREA>-<NNN>. Áreas: CFG configuración, NET descargas, DAT datos, BKT backtest, ACT Top actual,
API servidor, SYS avisos de Python. Los IDs no se reutilizan ni se renumeran: documentarlos en docs/errores.md.
"""
from dataclasses import dataclass

LEVELS = ("warning", "error")


@dataclass(frozen=True)
class Code:
    id: str
    level: str      # "warning": se sigue con lo que haya; "error": la operación se corta o falla
    title: str
    action: str     # qué hacer

    def msg(self, text: str) -> str:
        """`text` precedido por el ID: "TOP-BKT-003: Pocos tickers...". Sirve como formato de log."""
        return f"{self.id}: {text}"


CATALOG: dict[str, Code] = {}


def _code(id: str, level: str, title: str, action: str) -> Code:
    assert level in LEVELS and id not in CATALOG, id
    CATALOG[id] = code = Code(id, level, title, action)
    return code


# Configuración
CFG_MISSING = _code("TOP-CFG-001", "warning", "No existe el archivo de configuración",
                    "Se usan los valores por defecto. Crea config.toml o pasa --config con la ruta correcta.")
CFG_BAD_DATES = _code("TOP-CFG-002", "error", "start_date no es anterior a end_date",
                      "Corrige [backtest] start_date / end_date o backtest_years en config.toml.")
CFG_SHORT_HISTORY = _code("TOP-CFG-003", "warning", "El período del backtest empieza antes del histórico descargado",
                          "Sube [data] history_years (debe superar el mayor período + 1 año).")

# Descargas
NET_COMPOSITION = _code("TOP-NET-001", "error", "Falló la descarga de la composición del índice",
                        "Revisa la conexión; se usa lo guardado en SQLite. Reintenta o usa --no-cache.")
NET_FALLBACK = _code("TOP-NET-002", "warning", "Se usa la composición guardada en SQLite",
                     "Los datos pueden estar desactualizados; vuelve a correr cuando haya conexión.")
NET_CURRENT_LIST = _code("TOP-NET-003", "error", "Falló la descarga de la lista actual del S&P 500",
                         "Se usa la guardada en SQLite (puede ser vieja). Revisa la conexión.")
NET_WIKI_FORMAT = _code("TOP-NET-004", "error", "No se encontró la tabla de cambios en Wikipedia",
                        "Es probable que Wikipedia cambiara el formato de la página; hay que ajustar el lector.")

# Datos
DAT_BAD_DATES = _code("TOP-DAT-001", "warning", "Filas con fecha no interpretable en la tabla de cambios",
                      "Se ignoran. Si son muchas, el formato de la fuente cambió.")
DAT_NO_HISTORY = _code("TOP-DAT-002", "warning", "Sin composición histórica para esa fecha",
                       "Esa fecha queda sin constituyentes; revisa history_years y el CSV histórico.")
DAT_NO_SHARES = _code("TOP-DAT-003", "warning", "Sin dato de acciones en circulación para algunos tickers",
                      "Su capitalización queda en n/d y no entran en un universo filtrado por capitalización.")
DAT_NO_CURRENT = _code("TOP-DAT-004", "error", "No hay lista actual del S&P 500",
                       "No se descargó ni existe en SQLite. Corre con conexión a internet.")

# Backtest
BKT_EMPTY = _code("TOP-BKT-001", "error", "El backtest no generó ningún rebalanceo",
                  "Revisa las fechas, el histórico descargado y que el universo no sea demasiado chico.")
BKT_NO_CONSTITUENTS = _code("TOP-BKT-002", "warning", "Sin constituyentes en la fecha de rebalanceo",
                            "Se omite ese rebalanceo.")
BKT_FEW_TICKERS = _code("TOP-BKT-003", "warning", "Pocos tickers disponibles en la fecha de rebalanceo",
                        "Se omite ese rebalanceo (menos de 10 candidatos). Frecuente en mega-cap con períodos largos.")
BKT_SHORT_WINDOW = _code("TOP-BKT-004", "warning", "Ventana de precios insuficiente para rankear",
                         "Se omite ese rebalanceo.")
BKT_NO_PRICES = _code("TOP-BKT-005", "warning", "Sin precios para mantener la selección durante el período",
                      "El retorno de ese período no se computa.")
BKT_TERM_FAILED = _code("TOP-BKT-006", "warning", "Un plazo/calendario de arranque no produjo resultado",
                        "Se omite ese calendario; el resto continúa.")

# Top actual
ACT_SHORT_WINDOW = _code("TOP-ACT-001", "error", "No hay ruedas de precios suficientes",
                         "Descarga más historia (--no-cache) o reduce el plazo en meses.")
ACT_GAPS = _code("TOP-ACT-002", "warning", "Tickers con huecos en la ventana quedan fuera del ranking",
                 "Misma regla que el backtest. Revisa si Yahoo falló para esos tickers y reintenta.")

# Servidor
API_REPORT = _code("TOP-API-001", "error", "Error armando /api/report",
                   "Revisa que exista la base SQLite y que se haya corrido el pipeline al menos una vez.")

# Sistema
SYS_PYTHON_WARNING = _code("TOP-SYS-001", "warning", "Aviso de Python (pandas, yfinance u otra librería)",
                           "El mensaje original trae el archivo y la línea.")
