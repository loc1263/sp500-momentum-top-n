"""Corridas del backtest por plazo y por calendario de arranque, y su resumen estadístico."""
from dataclasses import asdict

import pandas as pd

from . import errors as E
from .context import Context
from .engine import Skipped, report_skipped, run_backtest
from .logs import log
from .repo.runs import save_run
from .results import Calendar, Term
from .shares import add_market_caps, ensure_shares
from .universe import Universe, label


SKIP_MONTHS = 1  # el modelo skip-month (N-1) ignora el último mes al armar el ranking


def _where(ctx: Context, universe: Universe | None) -> str:
    return f"{label(universe.min_cap_billions if universe else None)}, backtest {ctx.start_date.date()} a {ctx.end_date.date()}"


def run_calendars(ctx: Context, months: int, universe: Universe | None = None,
                  skipped: Skipped | None = None, skip_months: int = 0) -> Term:
    """Plazo de N meses con sus N calendarios posibles (arranque desfasado 0..N-1 meses).
    Guarda cada corrida en SQLite; los calendarios que fallan se omiten. Los rebalanceos omitidos se avisan juntos
    al final (o, si el que llama pasa `skipped`, cuando él lo decida). Con `skip_months` es el modelo skip-month."""
    min_cap_b = universe.min_cap_billions if universe else None
    own = skipped is None
    skipped = {} if own else skipped
    calendars = []
    for offset in range(months):
        start = ctx.start_date + pd.DateOffset(months=offset)
        log.info("=== Plazo %d-%d meses, desfase %d/%d (arranque desde %s) ===",
                 months, skip_months, offset, months - 1, start.date())
        try:
            result = run_backtest(ctx.constituents, ctx.matrix, start, ctx.end_date, ctx.lookback_days(months),
                                  f"{months}MS", ctx.initial_capital, ctx.top_n, universe, skipped,
                                  ctx.skip_days(skip_months), ctx.commission)
        except Exception as e:
            log.warning(E.BKT_TERM_FAILED.msg("Plazo %d meses, desfase %d sin resultado: %s"), months, offset, e)
            continue
        save_run(ctx.conn, {**asdict(ctx.cfg), "sweep_months": months, "offset_months": offset,
                            "min_cap_billions": min_cap_b, "skip_months": skip_months},
                 start.strftime("%Y-%m-%d"), ctx.end_date.strftime("%Y-%m-%d"), result)
        calendars.append(Calendar(**vars(result), offset=offset))
    if own:
        report_skipped(skipped, _where(ctx, universe))
    return Term(months, calendars)


def run_terms(ctx: Context, universe: Universe | None = None, months: list[int] | None = None,
              skip_months: int = 0) -> list[Term]:
    """Corre cada plazo (por defecto los de [simulation] months) con todos sus calendarios."""
    skipped: Skipped = {}  # todos los plazos y desfases juntos: un solo aviso por motivo
    terms = [run_calendars(ctx, m, universe, skipped, skip_months) for m in (months or ctx.terms)]
    report_skipped(skipped, _where(ctx, universe))
    return terms


def attach_market_caps(ctx: Context, terms: list[Term], universe: Universe | None = None) -> None:
    """Agrega la capitalización aprox. de cada selección del calendario base (solo informativa)."""
    histories = [t.base.history for t in terms if t.base]
    if not histories:
        return
    picked = sorted({t for history in histories for h in history for t in h["returns"]})
    known = {**(universe.shares if universe else {}), **ctx.known_shares}
    shares = ensure_shares(ctx.conn, picked, ctx.use_cache, ctx.settings, known=known)
    ctx.known_shares.update(shares)  # el período siguiente no vuelve a pedir lo mismo, tampoco con --no-cache
    add_market_caps(histories, ctx.prices, shares)
