"""Salida por consola: tablas de texto y resúmenes de cada tipo de corrida."""
import os
import re
import sys
from functools import cache

import pandas as pd

from . import tables, termfmt, universe
from .context import Context
from .results import Term
from .termfmt import BOLD, GREEN, RED

_SIGNED_PERCENT = re.compile(r"^[+-]\d[\d,]*(\.\d+)?%$")


def configure_console() -> None:
    """Si la salida se redirige (pipe/archivo) en Windows el códec por defecto (cp1252) no soporta → ni ≥."""
    for stream in (sys.stdout, sys.stderr):
        if not stream.isatty():
            stream.reconfigure(encoding="utf-8")


@cache
def use_color() -> bool:
    """Color ANSI solo si la salida es una terminal (al redirigir a archivo/pipe no se ensucia)."""
    enabled = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    if enabled:
        os.system("")  # habilita secuencias ANSI en la consola de Windows
    return enabled


def out(text: str = "") -> None:
    """print() que parte las líneas más largas que termfmt.MAX_WIDTH, para que no se desborden."""
    for line in termfmt.wrap(text):
        print(line)


def print_banner(text: str, width: int) -> None:
    frame = termfmt.color("=" * width, GREEN) if use_color() else "=" * width
    print("\n" + frame)
    out(termfmt.color(text, BOLD) if use_color() and len(text) <= termfmt.MAX_WIDTH else text)
    print(frame)


def _paint_cell(cell: str, padded: str) -> str:
    """Ganancias en verde y pérdidas en rojo (celdas con forma de porcentaje con signo); el 0 queda sin color."""
    if _SIGNED_PERCENT.match(cell.strip()) and float(cell.strip().rstrip("%").replace(",", "")) != 0:
        return termfmt.color(padded, GREEN if cell.strip().startswith("+") else RED)
    return padded


def print_table(headers: list[str], rows: list[list[str]], right_from: int = 1) -> None:
    """Tabla de texto: las columnas desde `right_from` van alineadas a la derecha. Si no entra en el ancho máximo se
    recortan (con «…») las columnas más anchas. Encabezado en negrita; ganancias en verde y pérdidas en rojo."""
    widths = termfmt.fit_widths([max(len(x) for x in col) for col in zip(headers, *rows)])
    colored = use_color()

    def line(cells, paint=False):
        parts = []
        for i, (cell, w) in enumerate(zip(cells, widths)):
            cell = termfmt.truncate(cell, w)
            padded = cell.rjust(w) if i >= right_from else cell.ljust(w)
            parts.append(_paint_cell(cell, padded) if paint and colored else padded)
        return " | ".join(parts)

    head = line(headers)
    print(termfmt.color(head, BOLD) if colored else head)
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(line(row, paint=True))


def print_history(history: list[dict], equity_curve: pd.Series, initial_capital: float) -> None:
    headers, rows = tables.history_table(history, equity_curve, initial_capital)
    print_table(headers, rows, right_from=len(headers) - 2)


def print_backtest(ctx: Context, term: Term, min_cap_b: float | None) -> None:
    base = term.base
    n = term.months
    median, low, high = term.cagr_stats()
    years = ctx.cfg.backtest.backtest_years
    print_banner(f"RESULTADOS BACKTEST - Top {ctx.top_n}{universe.title(min_cap_b)} (Point-in-Time)", 65)
    out(f"Período:             {ctx.start_date.date()} a {ctx.end_date.date()} ({years:g} años)")
    out(f"Plazo:               {n} meses (ranking {n} meses, rebalanceo cada {n} meses)")
    out(f"Capital inicial:     US$ {ctx.initial_capital:,.2f}")
    out(f"Capital final:       US$ {base.final_capital:,.2f}   (calendario base)")
    out(f"Retorno total:       {base.total_return_pct:.1f}%")
    out(f"CAGR aproximado:     {base.cagr_pct:.1f}%")
    out(f"CAGR mediana:        {median:+.1f}%   (rango {low:+.1f}% a {high:+.1f}%, {len(term.calendars)} calendarios)")
    out("=" * 65)

    out("\nHistorial de selecciones (calendario base):")
    print_history(base.history, base.equity_curve, ctx.initial_capital)

    out(f"\nCalendarios de arranque posibles ({len(term.calendars)}):")
    print_table(*tables.calendar_table(term.calendars))

    out("\nCurva de capital:")
    print(base.equity_curve.round(2))


def print_sweep(ctx: Context, terms: list[Term], min_cap_b: float | None) -> None:
    if min_cap_b:
        out(f"\nUniverso: {universe.label(min_cap_b)} (cap. aprox. ≥ US$ {min_cap_b:g} B)")
    for t in terms:
        if t.base:
            print_banner(f"SELECCIONES - plazo {t.months} meses "
                         f"(ranking {t.months} meses, rebalanceo cada {t.months} meses)", 65)
            print_history(t.base.history, t.base.equity_curve, ctx.initial_capital)

    print_banner(f"COMPARACIÓN DE PLAZOS - {ctx.start_date.date()} a {ctx.end_date.date()}", 100)
    print_table(*tables.sweep_table(terms))
    out("Capital final / Retorno total / CAGR = calendario base (arranque en el primer mes); "
          "mediana y rango = los N calendarios posibles del plazo.")
    best = tables.sweep_best(terms, ctx.initial_capital)
    if best:
        out(f"\n{best}")


def print_models(ctx: Context, terms: list[Term], skip_terms: list[Term], min_cap_b: float | None) -> None:
    print_banner(f"MODELO N-0 vs. SKIP-MONTH N-1 - {ctx.start_date.date()} a {ctx.end_date.date()}"
                 + (f" - {universe.label(min_cap_b)}" if min_cap_b else ""), 85)
    print_table(*tables.models_table(terms, skip_terms))
    out("N-0 = ranking con los últimos N meses hasta hoy; N-1 = los N meses que terminan un mes antes. "
          "CAGR y capital = mediana de los calendarios de arranque.")


def print_offsets(ctx: Context, terms: list[Term], min_cap_b: float | None) -> None:
    print_banner(f"SENSIBILIDAD AL ARRANQUE - {ctx.start_date.date()} a {ctx.end_date.date()}"
                 + (f" - {universe.label(min_cap_b)}" if min_cap_b else ""), 85)
    print_table(*tables.offsets_table(terms))
    best = tables.offsets_best(terms)
    if best:
        out(f"\n{best}")
    for t in terms:
        if t.calendars:
            out(f"\nPlazo {t.months} meses - un calendario por mes de arranque:")
            print_table(*tables.calendar_table(t.calendars))


def print_etf(as_of: str, horizons: list[int], top_n: int, ranked: int, headers: list[str], rows: list[list[str]],
              notes: list[str], historical: bool, risk_free: str | None = None) -> None:
    print_banner(f"ETFs DE VANGUARD - momentum ajustado por riesgo ({ranked} rankeados)", 78)
    out(f"Datos al cierre del {as_of}" + (" (fecha pedida con --as-of: lista actual, no es un backtest)"
                                            if historical else ""))
    excess = f" (exceso sobre {risk_free})" if risk_free else ""
    out(f"Score = promedio del retorno{excess} / volatilidad en {', '.join(str(h) for h in horizons)} meses. "
          f"Top {top_n}:\n")
    print_table(headers[:2] + headers[3:], [r[:2] + r[3:] for r in rows[:top_n]], right_from=3)
    out()
    for line in filter(None, notes):
        out(line)


def print_actual(top_n: int, months: int, min_cap_b: float | None, as_of, window: pd.DataFrame,
                 headers: list[str], rows: list[list[str]], weight: float, notes: list[str] = (),
                 alternates: list[list[str]] = ()) -> None:
    print_banner(f"TOP {top_n} S&P 500{universe.title(min_cap_b)} - últimos {months} meses", 70)
    out(f"Datos al cierre del {as_of} (ventana {window.index[0].date()} a {as_of}, {len(window)} ruedas)")
    if min_cap_b:
        out(f"Universo: {universe.label(min_cap_b)} (cap. aprox. >= US$ {min_cap_b:g} B)")
    out()
    print_table(headers, rows)
    out(f"\n→ Ponderación igual: {weight:.1f}% cada una. Se rebalancea cada {months} meses.")
    if alternates:
        out("\nSuplentes (puestos siguientes, como reemplazo posible de alguna acción del top):")
        print_table(headers, alternates)
