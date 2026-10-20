"""Rotación del Top actual: qué entra y qué sale respecto de la corrida anterior, y cuándo toca rebalancear."""
import sqlite3
from datetime import date

import pandas as pd

_KEY = "months = ? AND COALESCE(min_cap_billions, 0) = ?"


def previous_picks(conn: sqlite3.Connection, as_of: str, months: int,
                   min_cap_b: float | None) -> tuple[str | None, list[str]]:
    """(fecha de datos, tickers) de la corrida guardada inmediatamente anterior a `as_of`, o (None, [])."""
    prev = conn.execute(f"SELECT MAX(as_of) FROM actual_picks WHERE as_of < ? AND {_KEY}",
                        (as_of, months, min_cap_b or 0)).fetchone()[0]
    if prev is None:
        return None, []
    rows = conn.execute(f"SELECT ticker FROM actual_picks WHERE as_of = ? AND {_KEY} ORDER BY rank",
                        (prev, months, min_cap_b or 0)).fetchall()
    return prev, [r[0] for r in rows]


def diff_picks(previous: list[str], current: list[str]) -> dict[str, list[str]]:
    """Tickers que entran, salen y se mantienen (en el orden del ranking actual / anterior)."""
    return {"entered": [t for t in current if t not in previous],
            "exited": [t for t in previous if t not in current],
            "kept": [t for t in current if t in previous]}


def anchor_date(conn: sqlite3.Connection, months: int, min_cap_b: float | None) -> str | None:
    """Fecha de datos de la primera corrida guardada: de ahí se cuenta el calendario de rebalanceo."""
    return conn.execute(f"SELECT MIN(as_of) FROM actual_picks WHERE {_KEY}",
                        (months, min_cap_b or 0)).fetchone()[0]


def next_rebalance(anchor: str, months: int, today: date) -> date:
    """Primer inicio de mes de la grilla `anchor + k x months` que no es anterior a `today`."""
    d = pd.Timestamp(anchor).replace(day=1)
    while d.date() < today:
        d += pd.DateOffset(months=months)
    return d.date()


def describe(previous_as_of: str | None, changes: dict[str, list[str]], anchor: str | None, months: int,
             today: date) -> list[str]:
    """Líneas de texto para la consola y el HTML."""
    lines = []
    if previous_as_of is None:
        lines.append("Cambios: primera corrida guardada, sin selección anterior para comparar.")
    elif not changes["entered"] and not changes["exited"]:
        lines.append(f"Cambios vs. {previous_as_of}: ninguno, la selección se mantiene.")
    else:
        lines.append(f"Cambios vs. {previous_as_of}: entran {', '.join(changes['entered']) or '-'}; "
                     f"salen {', '.join(changes['exited']) or '-'}; "
                     f"se mantienen {', '.join(changes['kept']) or '-'}.")
    if anchor:
        lines.append(f"Próximo rebalanceo: {next_rebalance(anchor, months, today)} "
                     f"(cada {months} meses desde la primera corrida guardada, {anchor}).")
    return lines
