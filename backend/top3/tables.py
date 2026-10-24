"""Tablas de resultados como (encabezados, filas) de texto; las usan tanto la consola como el HTML."""
import pandas as pd

from .results import Calendar, Term

Table = tuple[list[str], list[list[str]]]


def pct(value: float) -> str:
    return f"{value:+.1f}%"


def history_table(history: list[dict], equity_curve: pd.Series, initial_capital: float) -> Table:
    """Una fila por rebalanceo: el Top N, el capital al momento de entrar y su % vs. el capital inicial."""
    cap_by_date = {d.strftime("%Y-%m-%d"): c for d, c in equity_curve.items()}
    n = max(len(h["returns"]) for h in history)
    headers = ["Fecha"] + [f"#{i}" for i in range(1, n + 1)] + ["Cap. aprox. (US$ B)", "Capital (US$)", "Gan/Pérd"]

    def caps_col(h):
        caps = h.get("caps", {})
        return " / ".join(f"{caps[t] / 1e9:,.0f}" if t in caps else "n/d" for t in h["returns"])

    def capital_cols(capital):
        return [f"{capital:,.2f}", pct((capital / initial_capital - 1) * 100)]

    rows = []
    for h in history:
        picks = [f"{t} {pct(r * 100)}" for t, r in h["returns"].items()]
        picks += [""] * (n - len(picks))
        rows.append([h["date"]] + picks + [caps_col(h)] + capital_cols(cap_by_date[h["date"]]))
    # Fila final: valor al cierre del último tramo
    last_date = equity_curve.index[-1].strftime("%Y-%m-%d")
    if last_date not in {h["date"] for h in history}:
        rows.append([last_date] + [""] * (n + 1) + capital_cols(equity_curve.iloc[-1]))
    return headers, rows


def calendar_table(calendars: list[Calendar]) -> Table:
    """Una fila por calendario de arranque: primer rebalanceo, rebalanceos y resultado."""
    headers = ["Primer rebalanceo", "Rebalanceos", "Capital final (US$)", "Retorno total", "CAGR"]
    rows = [[c.history[0]["date"], str(len(c.history)), f"{c.final_capital:,.2f}",
             pct(c.total_return_pct), pct(c.cagr_pct)] for c in calendars]
    return headers, rows


def _by_median_cagr(terms: list[Term]) -> list[Term]:
    return sorted(terms, key=lambda t: t.cagr_stats()[0], reverse=True)


def sweep_table(terms: list[Term]) -> Table:
    """Comparación de plazos, de mejor a peor CAGR mediano; los plazos sin resultado van al final."""
    headers = ["Plazo", "Rebalanceos", "Capital final (US$)", "Retorno total", "CAGR",
               "Calendarios", "CAGR mediana", "CAGR mín", "CAGR máx"]
    rows = []
    for t in _by_median_cagr([t for t in terms if t.base]):
        median, low, high = t.cagr_stats()
        rows.append([f"{t.months} meses", str(len(t.base.history)), f"{t.base.final_capital:,.2f}",
                     pct(t.base.total_return_pct), pct(t.base.cagr_pct), str(len(t.calendars)),
                     pct(median), pct(low), pct(high)])
    rows += [[f"{t.months} meses", "0", "sin datos"] + ["-"] * 6 for t in terms if not t.base]
    return headers, rows


def sweep_best(terms: list[Term], initial_capital: float) -> str | None:
    ranked = _by_median_cagr([t for t in terms if t.base])
    if not ranked:
        return None
    t = ranked[0]
    median, low, high = t.cagr_stats()
    return (f"Mejor plazo: {t.months} meses (CAGR mediano {pct(median)}, rango {pct(low)} a {pct(high)}; "
            f"calendario base US$ {initial_capital:,.0f} → US$ {t.base.final_capital:,.2f}, "
            f"{pct(t.base.total_return_pct)})")


def offsets_table(terms: list[Term]) -> Table:
    """Sensibilidad al arranque: mediana y rango del CAGR y del capital final de cada plazo."""
    headers = ["Plazo", "Calendarios", "CAGR mediana", "CAGR mín", "CAGR máx",
               "Capital mediana", "Capital mín", "Capital máx"]
    rows = []
    for t in _by_median_cagr([t for t in terms if t.calendars]):
        cagr_median, cagr_low, cagr_high = t.cagr_stats()
        cap_median, cap_low, cap_high = t.capital_stats()
        rows.append([f"{t.months} meses", str(len(t.calendars)), pct(cagr_median), pct(cagr_low), pct(cagr_high),
                     f"{cap_median:,.0f}", f"{cap_low:,.0f}", f"{cap_high:,.0f}"])
    return headers, rows


def offsets_best(terms: list[Term]) -> str | None:
    ranked = _by_median_cagr([t for t in terms if t.calendars])
    if not ranked:
        return None
    t = ranked[0]
    median, low, high = t.cagr_stats()
    return (f"Mejor plazo por CAGR mediano: {t.months} meses (mediana {pct(median)}, "
            f"rango {pct(low)} a {pct(high)}, {len(t.calendars)} calendarios)")


def models_table(terms: list[Term], skip_terms: list[Term]) -> Table:
    """Modelo de siempre (N-0) frente al skip-month (N-1), plazo por plazo: CAGR mediano y capital mediano."""
    headers = ["Plazo", "CAGR N-0", "CAGR N-1", "Dif. CAGR", "Capital N-0", "Capital N-1", "Gana"]
    skip_by_months = {t.months: t for t in skip_terms if t.calendars}
    rows = []
    for t in _by_median_cagr([t for t in terms if t.calendars]):
        other = skip_by_months.get(t.months)
        median, _, _ = t.cagr_stats()
        capital, _, _ = t.capital_stats()
        if other is None:
            rows.append([f"{t.months} meses", pct(median), "sin datos", "-", f"{capital:,.0f}", "-", "-"])
            continue
        other_median, _, _ = other.cagr_stats()
        other_capital, _, _ = other.capital_stats()
        winner = "N-1" if other_median > median else "N-0" if median > other_median else "empate"
        rows.append([f"{t.months} meses", pct(median), pct(other_median), f"{other_median - median:+.1f} pp",
                     f"{capital:,.0f}", f"{other_capital:,.0f}", winner])
    return headers, rows
