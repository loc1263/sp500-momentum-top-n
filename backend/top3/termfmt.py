"""Formato de terminal: ancho máximo de línea y paleta de colores ANSI (sin depender del resto del paquete)."""
import re
import textwrap

MAX_WIDTH = 130   # ninguna línea de la consola pasa de acá: más ancho se desborda y se corta feo

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN = (f"\033[{n}m" for n in (31, 32, 33, 34, 35, 36))

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def visible_len(text: str) -> int:
    """Largo de `text` sin contar las secuencias de color."""
    return len(_ANSI.sub("", text))


def color(text: str, *codes: str) -> str:
    return f"{''.join(codes)}{text}{RESET}"


def wrap(text: str, width: int = MAX_WIDTH, indent: str | None = None) -> list[str]:
    """`text` partido en líneas de hasta `width` caracteres, cortando en espacios. Las líneas siguientes a la primera
    se sangran con `indent` (por defecto, la sangría de la línea original + 4). Un texto que ya trae colores no se parte:
    el color abierto en una línea quedaría sin cerrar en la otra (los llamadores parten primero y pintan después)."""
    out: list[str] = []
    for line in text.split("\n"):
        if visible_len(line) <= width or _ANSI.search(line):
            out.append(line)
            continue
        base = line[:len(line) - len(line.lstrip())]
        out.extend(textwrap.wrap(line, width, subsequent_indent=base + "    " if indent is None else indent,
                                 break_long_words=True, break_on_hyphens=False, drop_whitespace=True,
                                 replace_whitespace=False, expand_tabs=False) or [""])
    return out


def truncate(text: str, width: int) -> str:
    """`text` recortado a `width` caracteres con «…» al final si no entraba."""
    return text if len(text) <= width else text[:max(width - 1, 0)] + "…"


def fit_widths(widths: list[int], separator: int = 3, limit: int = MAX_WIDTH, minimum: int = 8) -> list[int]:
    """Anchos de columna reducidos (de la más ancha a la más angosta) hasta que la tabla entre en `limit`."""
    widths = list(widths)
    total = lambda: sum(widths) + separator * (len(widths) - 1)   # noqa: E731
    while total() > limit:
        widest = max(range(len(widths)), key=widths.__getitem__)
        if widths[widest] <= minimum:
            break
        widths[widest] -= 1
    return widths
