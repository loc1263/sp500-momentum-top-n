"""Salida por consola: tablas de texto y resúmenes de cada tipo de corrida."""
import os
import sys
from functools import cache

import pandas as pd

from . import tables, universe
from .analysis import Context, Term

GREEN, RESET = "\033[32m", "\033[0m"


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


def print_banner(text: str, width: int) -> None:
    print("\n" + "=" * width)
    print(text)
    print("=" * width)


def print_table(headers: list[str], rows: list[list[str]], right_from: int = 1, color_last: bool = False) -> None:
    """Tabla de texto: las columnas desde `right_from` van alineadas a la derecha. Con `color_last` la última
    columna se pinta de verde cuando es una ganancia."""
    widths = [max(len(x) for x in col) for col in zip(headers, *rows)]

    def line(cells):
        return " | ".join(c.rjust(w) if i >= right_from else c.ljust(w)
                          for i, (c, w) in enumerate(zip(cells, widths)))

    print(line(headers))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        text = line(row)
        if color_last and use_color() and row[-1].startswith("+") and row[-1] != "+0.0%":
            head, _, last = text.rpartition(" | ")  # color después de alinear para no romper el ancho
            text = f"{head} | {GREEN}{last}{RESET}"
        print(text)


def print_history(history: list[dict], equity_curve: pd.Series, initial_capital: float) -> None:
    headers, rows = tables.history_table(history, equity_curve, initial_capital)
    print_table(headers, rows, right_from=len(headers) - 2, color_last=True)


def print_backtest(ctx: Context, term: Term, min_cap_b: float | None) -> None:
    base = term.base
    n = term.months
    median, low, high = term.cagr_stats()
    years = ctx.cfg["backtest"]["backtest_years"]
    print_banner(f"RESULTADOS BACKTEST - Top {ctx.top_n}{universe.title(min_cap_b)} (Point-in-Time)", 65)
    print(f"Período:             {ctx.start_date.date()} a {ctx.end_date.date()} ({years:g} años)")
    print(f"Plazo:               {n} meses (ranking {n} meses, rebalanceo cada {n} meses)")
    print(f"Capital inicial:     US$ {ctx.initial_capital:,.2f}")
    print(f"Capital final:       US$ {base.final_capital:,.2f}   (calendario base)")
    print(f"Retorno total:       {base.total_return_pct:.1f}%")
    print(f"CAGR aproximado:     {base.cagr_pct:.1f}%")
    print(f"CAGR mediana:        {median:+.1f}%   (rango {low:+.1f}% a {high:+.1f}%, {len(term.calendars)} calendarios)")
    print("=" * 65)

    print("\nHistorial de selecciones (calendario base):")
    print_history(base.history, base.equity_curve, ctx.initial_capital)

    print(f"\nCalendarios de arranque posibles ({len(term.calendars)}):")
    print_table(*tables.calendar_table(term.calendars))

    print("\nCurva de capital:")
    print(base.equity_curve.round(2))


def print_sweep(ctx: Context, terms: list[Term], min_cap_b: float | None) -> None:
    if min_cap_b:
        print(f"\nUniverso: {universe.label(min_cap_b)} (cap. aprox. ≥ US$ {min_cap_b:g} B)")
    for t in terms:
        if t.base:
            print_banner(f"SELECCIONES - plazo {t.months} meses "
                         f"(ranking {t.months} meses, rebalanceo cada {t.months} meses)", 65)
            print_history(t.base.history, t.base.equity_curve, ctx.initial_capital)

    print_banner(f"COMPARACIÓN DE PLAZOS - {ctx.start_date.date()} a {ctx.end_date.date()}", 100)
    print_table(*tables.sweep_table(terms))
    print("Capital final / Retorno total / CAGR = calendario base (arranque en el primer mes); "
          "mediana y rango = los N calendarios posibles del plazo.")
    best = tables.sweep_best(terms, ctx.initial_capital)
    if best:
        print(f"\n{best}")


def print_offsets(ctx: Context, terms: list[Term], min_cap_b: float | None) -> None:
    print_banner(f"SENSIBILIDAD AL ARRANQUE - {ctx.start_date.date()} a {ctx.end_date.date()}"
                 + (f" - {universe.label(min_cap_b)}" if min_cap_b else ""), 85)
    print_table(*tables.offsets_table(terms))
    best = tables.offsets_best(terms)
    if best:
        print(f"\n{best}")
    for t in terms:
        if t.calendars:
            print(f"\nPlazo {t.months} meses - un calendario por mes de arranque:")
            print_table(*tables.calendar_table(t.calendars))


def print_etf(as_of: str, horizons: list[int], top_n: int, ranked: int, headers: list[str], rows: list[list[str]],
              notes: list[str], historical: bool, risk_free: str | None = None) -> None:
    print_banner(f"ETFs DE VANGUARD - momentum ajustado por riesgo ({ranked} rankeados)", 78)
    print(f"Datos al cierre del {as_of}" + (" (fecha pedida con --as-of: lista actual, no es un backtest)"
                                            if historical else ""))
    excess = f" (exceso sobre {risk_free})" if risk_free else ""
    print(f"Score = promedio del retorno{excess} / volatilidad en {', '.join(str(h) for h in horizons)} meses. "
          f"Top {top_n}:\n")
    print_table(headers[:2] + headers[3:], [r[:2] + r[3:] for r in rows[:top_n]], right_from=3)
    print()
    for line in filter(None, notes):
        print(line)


def print_actual(top_n: int, months: int, min_cap_b: float | None, as_of, window: pd.DataFrame,
                 headers: list[str], rows: list[list[str]], weight: float, notes: list[str] = ()) -> None:
    print_banner(f"TOP {top_n} S&P 500{universe.title(min_cap_b)} - últimos {months} meses", 70)
    print(f"Datos al cierre del {as_of} (ventana {window.index[0].date()} a {as_of}, {len(window)} ruedas)")
    if min_cap_b:
        print(f"Universo: {universe.label(min_cap_b)} (cap. aprox. >= US$ {min_cap_b:g} B)")
    print()
    print_table(headers, rows)
    print(f"\n→ Ponderación igual: {weight:.1f}% cada una. Se rebalancea cada {months} meses.")
