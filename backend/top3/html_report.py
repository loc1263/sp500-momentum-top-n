"""Reportes HTML autocontenidos (un archivo por reporte, sin dependencias externas)."""
import html
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from . import tables, universe
from .analysis import Context, Term
from .logs import log

HTML_CSS = """
:root { --bg:#ffffff; --fg:#1f2328; --muted:#656d76; --line:#d8dee4; --card:#f6f8fa;
        --pos:#1a7f37; --neg:#cf222e; --accent:#0969da; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0d1117; --fg:#e6edf3; --muted:#8b949e; --line:#30363d; --card:#161b22;
          --pos:#3fb950; --neg:#f85149; --accent:#58a6ff; } }
* { box-sizing: border-box; }
body { margin:0; padding:24px 16px 48px; background:var(--bg); color:var(--fg);
       font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
main { max-width:1280px; margin:0 auto; }
h1 { font-size:1.6rem; margin:0 0 4px; }
h2 { font-size:1.15rem; margin:32px 0 4px; }
.sub { color:var(--muted); margin:0 0 16px; font-size:.9rem; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:16px 0; }
.card { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px 14px; }
.card .k { color:var(--muted); font-size:.78rem; text-transform:uppercase; letter-spacing:.04em; }
.card .v { font-size:1.35rem; font-weight:600; font-variant-numeric:tabular-nums; }
.best { background:var(--card); border:1px solid var(--line); border-left:4px solid var(--pos);
        border-radius:8px; padding:12px 14px; margin:16px 0; }
.wrap { overflow-x:auto; border:1px solid var(--line); border-radius:8px; }
table { border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }
th, td { padding:1px 14px; line-height:1.35; text-align:left; white-space:nowrap; border-bottom:1px solid var(--line); }
th { background:var(--card); font-size:.8rem; color:var(--muted); font-weight:600; }
tr:last-child td { border-bottom:0; }
td.r, th.r { text-align:right; }
.pos { color:var(--pos); font-weight:600; }
.neg { color:var(--neg); }
footer { margin-top:32px; color:var(--muted); font-size:.8rem; }
"""


def html_table(headers: list[str], rows: list[list[str]], right_cols=(), signed_cols=()) -> str:
    """Tabla HTML; `signed_cols` se colorean según el signo (+ verde, - rojo)."""
    def cell(i, text):
        cls = []
        if i in right_cols:
            cls.append("r")
        if i in signed_cols and text.startswith("+") and text != "+0.0%":
            cls.append("pos")
        elif i in signed_cols and text.startswith("-") and text != "-":
            cls.append("neg")
        return f'<td class="{" ".join(cls)}">{html.escape(text)}</td>'

    head = "".join(f'<th class="{"r" if i in right_cols else ""}">{html.escape(h)}</th>'
                   for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(cell(i, c) for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def card(key: str, value: str, cls: str = "") -> str:
    return f'<div class="card"><div class="k">{html.escape(key)}</div><div class="v {cls}">{html.escape(value)}</div></div>'


def sign_class(value: float) -> str:
    return "pos" if value > 0 else "neg"


def history_html(history: list[dict], equity_curve: pd.Series, initial_capital: float) -> str:
    headers, rows = tables.history_table(history, equity_curve, initial_capital)
    last = len(headers) - 1  # columnas finales: Capital, Gan/Pérd
    return html_table(headers, rows, right_cols=(last - 1, last), signed_cols=(last,))


def calendars_html(calendars) -> str:
    headers, rows = tables.calendar_table(calendars)
    return html_table(headers, rows, right_cols=(1, 2, 3, 4), signed_cols=(3, 4))


def universe_note(min_cap_b: float | None) -> str:
    if not min_cap_b:
        return ""
    return (f'<p class="sub">Universo filtrado: en cada rebalanceo solo compiten las empresas del índice con '
            f'capitalización aprox. ≥ US$ {min_cap_b:g} B ({universe.label(min_cap_b)}).</p>')


def best_box(text: str | None) -> str:
    return f'<div class="best"><strong>{html.escape(text)}</strong></div>' if text else ""


def write_html(output_dir: str, prefix: str, title: str, subtitle: str, body: str, subdir: str = "") -> Path:
    """Guarda el reporte en <output_dir>/<subdir>/<prefix>_YYYYMMDD.html y devuelve la ruta."""
    out = Path(output_dir) / subdir
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{prefix}_{date.today():%Y%m%d}.html"
    doc = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{HTML_CSS}</style></head>
<body><main>
<h1>{html.escape(title)}</h1><p class="sub">{html.escape(subtitle)}</p>
{body}
<footer>Generado el {datetime.now():%Y-%m-%d %H:%M}. Backtest sin comisiones ni impuestos, ponderación igual entre los tickers seleccionados.
Excluye tickers sin datos en Yahoo (sesgo de supervivencia).</footer>
</main></body></html>"""
    path.write_text(doc, encoding="utf-8")
    log.info("Reporte HTML guardado: %s", path.resolve())
    return path


def write_report(cfg: dict, kind: str, min_cap_b: float | None, title: str, subtitle: str, body: str,
                 file_suffix: str = "") -> Path:
    """Escribe un reporte de tipo `kind` ("backtest", "sweep", "offsets" o "actual") con el nombre y la carpeta
    definidos en [output] del config, más el sufijo de universo y de período."""
    out = cfg["output"]
    subdir = out["actual_subdir"] if kind == "actual" else out["backtest_subdir"]
    prefix = out[f"{kind}_prefix"] + universe.suffix(min_cap_b) + file_suffix
    return write_html(out["dir"], prefix, title, subtitle, body, subdir)


def _period_subtitle(ctx: Context) -> str:
    return f"{ctx.start_date.date()} a {ctx.end_date.date()} · capital inicial US$ {ctx.initial_capital:,.0f}"


def backtest_report(ctx: Context, term: Term, min_cap_b: float | None) -> Path:
    base, n = term.base, term.months
    median, low, high = term.cagr_stats()
    body = (
        '<div class="cards">'
        + card("Capital inicial", f"US$ {ctx.initial_capital:,.2f}")
        + card("Capital final (calendario base)", f"US$ {base.final_capital:,.2f}")
        + card("Retorno total", tables.pct(base.total_return_pct), sign_class(base.total_return_pct))
        + card("CAGR (calendario base)", tables.pct(base.cagr_pct), sign_class(base.cagr_pct))
        + card("CAGR mediana", tables.pct(median), sign_class(median))
        + card(f"Rango CAGR ({len(term.calendars)} calendarios)", f"{tables.pct(low)} a {tables.pct(high)}")
        + '</div><h2>Historial de selecciones (calendario base)</h2>'
        '<p class="sub">Capital = valor al momento de entrar a los tickers de esa fila. '
        'Gan/Pérd = acumulado vs. el capital inicial. Cap. aprox. = capitalización informativa de cada ticker '
        '(precio de esa fecha × acciones en circulación actuales, en miles de millones de US$, en el orden #1, #2…). '
        + ('Se usa para filtrar el universo.' if min_cap_b else 'No se usa para filtrar.') + '</p>'
        + universe_note(min_cap_b)
        + history_html(base.history, base.equity_curve, ctx.initial_capital)
        + f'<h2>Calendarios de arranque posibles ({len(term.calendars)})</h2>'
        f'<p class="sub">El mismo plazo de {n} meses empezando en cada uno de los {n} meses posibles. '
        'Muestra cuánto del resultado depende de la fecha de arranque.</p>'
        + calendars_html(term.calendars))
    subtitle = (f"{ctx.start_date.date()} a {ctx.end_date.date()} · plazo {n} meses (ranking {n} meses, "
                f"rebalanceo cada {n} meses)" + universe.subtitle(min_cap_b))
    return write_report(ctx.cfg, "backtest", min_cap_b,
                        f"Backtest Top {ctx.top_n} S&P 500{universe.title(min_cap_b)} (Point-in-Time)",
                        subtitle, body, ctx.file_suffix)


def sweep_report(ctx: Context, terms: list[Term], min_cap_b: float | None) -> Path:
    headers, rows = tables.sweep_table(terms)
    body = universe_note(min_cap_b) + best_box(tables.sweep_best(terms, ctx.initial_capital))
    body += ('<h2>Comparación de plazos</h2><p class="sub">Cada plazo N usa un ranking de N meses hacia atrás '
             'y rebalancea cada N meses. Capital final, Retorno total y CAGR corresponden al calendario base '
             '(arranque en el primer mes); la mediana y el rango resumen los N calendarios posibles '
             '(arranque desfasado 0 a N-1 meses), que muestran cuánto depende el resultado de la fecha de arranque. '
             'Ordenado por CAGR mediano.</p>'
             + html_table(headers, rows, right_cols=tuple(range(1, 9)), signed_cols=(3, 4, 6, 7, 8)))
    for t in terms:
        if t.base:
            body += (f'<h2>Selecciones - plazo {t.months} meses</h2>'
                     f'<p class="sub">Ranking {t.months} meses, rebalanceo cada {t.months} meses.</p>'
                     + history_html(t.base.history, t.base.equity_curve, ctx.initial_capital))
    return write_report(ctx.cfg, "sweep", min_cap_b,
                        f"Comparación de plazos - Top {ctx.top_n} S&P 500{universe.title(min_cap_b)}",
                        _period_subtitle(ctx) + universe.subtitle(min_cap_b), body, ctx.file_suffix)


def offsets_report(ctx: Context, terms: list[Term], min_cap_b: float | None) -> Path:
    headers, rows = tables.offsets_table(terms)
    detail = "".join(
        f"<h2>Plazo {t.months} meses - detalle por calendario</h2>"
        '<p class="sub">Un backtest por cada mes de arranque posible; el primer rebalanceo cambia, '
        f'el resto sigue cada {t.months} meses.</p>' + calendars_html(t.calendars)
        for t in terms if t.calendars)
    body = universe_note(min_cap_b) + best_box(tables.offsets_best(terms))
    body += ('<h2>Resumen por plazo</h2><p class="sub">Cada plazo N se probó con sus N calendarios posibles '
             '(arranque desfasado 0 a N-1 meses). La mediana y el rango muestran cuánto depende el resultado '
             'de la fecha de arranque. Ordenado por CAGR mediano; los calendarios más tardíos cubren un período '
             'algo más corto, por eso se compara el CAGR.</p>'
             + html_table(headers, rows, right_cols=tuple(range(1, len(headers))), signed_cols=(2, 3, 4)) + detail)
    return write_report(ctx.cfg, "offsets", min_cap_b,
                        f"Sensibilidad al arranque - Top {ctx.top_n} S&P 500{universe.title(min_cap_b)}",
                        _period_subtitle(ctx) + universe.subtitle(min_cap_b), body, ctx.file_suffix)


def etf_report(cfg: dict, as_of: str, horizons: list[int], top_n: int, headers: list[str], rows: list[list[str]],
               notes: list[str], historical: bool, risk_free: str | None = None) -> Path:
    out = cfg["output"]
    right = tuple(range(4, len(headers)))
    signed = tuple(range(5, 5 + len(horizons))) + (len(headers) - 2, len(headers) - 1)
    excess = (f" El retorno es el exceso sobre {html.escape(risk_free)}, un ETF de bonos ultracortos usado como "
              "referencia libre de riesgo (sin eso, los ETFs casi sin riesgo ganarían siempre)." if risk_free else "")
    body = (
        '<div class="cards">' + card("Datos al cierre del", as_of) + card("ETFs rankeados", str(len(rows)))
        + card("Plazos", ", ".join(f"{h}m" for h in sorted(horizons))) + '</div>'
        + ('<p class="sub"><strong>Fecha pedida con --as-of:</strong> se usa la lista actual de ETFs, así que no es '
           'un backtest (no incluye los ETFs lanzados después ni los cerrados).</p>' if historical else '')
        + f'<h2>Ranking global (top {top_n} arriba)</h2>'
        '<p class="sub">Score = promedio, entre los plazos, del retorno dividido por la volatilidad anual escalada al '
        f'plazo: cuánto subió por unidad de riesgo.{excess} «vs SMA200» es la distancia del precio a su media de 200 '
        'ruedas (positivo = en tendencia alcista). Herramienta de análisis, no una recomendación de inversión.</p>'
        + html_table(headers, rows, right_cols=right, signed_cols=signed)
        + ''.join(f'<p class="sub">{html.escape(n)}</p>' for n in notes if n))
    suffix = f"_asof_{as_of}" if historical else ""
    return write_html(out["dir"], out["etf_prefix"] + suffix, "ETFs de Vanguard - momentum ajustado por riesgo",
                      f"Datos al {as_of}", body, out["etf_subdir"])


def actual_report(cfg: dict, top_n: int, months: int, min_cap_b: float | None, as_of, window: pd.DataFrame,
                  headers: list[str], rows: list[list[str]], weight: float, notes: list[str] = (),
                  alternates: list[list[str]] = ()) -> Path:
    body = (
        '<div class="cards">'
        + card("Datos al cierre del", str(as_of))
        + card("Plazo", f"{months} meses")
        + card("Peso por acción", f"{weight:.1f}%")
        + '</div>' + universe_note(min_cap_b)
        + f'<h2>Top {top_n} de los últimos {months} meses</h2>'
        f'<p class="sub">Ventana {window.index[0].date()} a {as_of} ({len(window)} ruedas). '
        'Cap. aprox. = precio × acciones en circulación actuales, informativa.</p>'
        + html_table(headers, rows, right_cols=(2, 3, 4, 5), signed_cols=(2,))
        + (f'<h2>Suplentes</h2><p class="sub">Las que siguen al top {top_n}, por si querés cambiar alguna.</p>'
           + html_table(headers, alternates, right_cols=(2, 3, 4, 5), signed_cols=(2,)) if alternates else '')
        + ''.join(f'<p class="sub">{html.escape(n)}</p>' for n in notes))
    return write_report(cfg, "actual", min_cap_b, f"Top {top_n} actual S&P 500{universe.title(min_cap_b)}",
                        f"Últimos {months} meses · {as_of}" + universe.subtitle(min_cap_b), body)
