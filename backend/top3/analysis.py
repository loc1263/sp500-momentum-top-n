"""Corridas del backtest por plazo y por calendario de arranque, y su resumen estadístico."""
import json
import sqlite3
import statistics
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from . import errors as E
from .config import DataSettings
from .constituents import Constituents
from .engine import BacktestResult, Skipped, report_skipped, run_backtest
from .logs import log
from .shares import add_market_caps, ensure_shares
from .universe import Universe, label


@dataclass
class Context:
    """Todo lo que comparten las corridas de un período: datos, fechas y configuración."""

    conn: sqlite3.Connection
    cfg: dict
    settings: DataSettings
    constituents: Constituents
    prices: pd.DataFrame
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    use_cache: bool = True
    file_suffix: str = ""   # se agrega al nombre de los reportes HTML (p. ej. "_5y")

    @property
    def initial_capital(self) -> float:
        return float(self.cfg["backtest"]["initial_capital"])

    @property
    def top_n(self) -> int:
        return int(self.cfg["backtest"]["top_n"])

    @property
    def terms(self) -> list[int]:
        return [int(m) for m in self.cfg["simulation"]["months"]]

    def lookback_days(self, months: int) -> int:
        return months * int(self.cfg["backtest"]["trading_days_per_month"])


@dataclass(kw_only=True)
class Calendar(BacktestResult):
    """Una corrida de un plazo con el arranque desfasado `offset` meses (0 = calendario base)."""

    offset: int


@dataclass
class Term:
    """Un plazo de N meses con todos sus calendarios de arranque posibles."""

    months: int
    calendars: list[Calendar]

    @property
    def base(self) -> Calendar | None:
        """Calendario base: el que arranca en el primer mes del período."""
        return next((c for c in self.calendars if c.offset == 0), None)

    def cagr_stats(self) -> tuple[float, float, float]:
        """(mediana, mínimo, máximo) del CAGR % entre los calendarios."""
        cagrs = [c.cagr_pct for c in self.calendars]
        return statistics.median(cagrs), min(cagrs), max(cagrs)

    def capital_stats(self) -> tuple[float, float, float]:
        """(mediana, mínimo, máximo) del capital final entre los calendarios."""
        finals = [c.final_capital for c in self.calendars]
        return statistics.median(finals), min(finals), max(finals)


def save_run(conn: sqlite3.Connection, params: dict, start_date: str, end_date: str,
             result: BacktestResult) -> int:
    """Guarda una corrida (resumen, selecciones y curva de capital) y devuelve su id."""
    cur = conn.execute(
        "INSERT INTO runs (run_at, params, start_date, end_date, final_capital, total_return, cagr) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), json.dumps(params, default=str),
         start_date, end_date, result.final_capital, result.total_return_pct, result.cagr_pct))
    run_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO selections (run_id, rebalance_date, rank, ticker, return_lookback) VALUES (?, ?, ?, ?, ?)",
        [(run_id, h["date"], rank, t, r)
         for h in result.history for rank, (t, r) in enumerate(h["returns"].items(), 1)])
    conn.executemany(
        "INSERT INTO equity (run_id, date, capital) VALUES (?, ?, ?)",
        [(run_id, d.strftime("%Y-%m-%d"), float(c)) for d, c in result.equity_curve.items()])
    conn.commit()
    log.info("Resultados guardados en SQLite (runs.id=%d)", run_id)
    return run_id


def _where(ctx: Context, universe: Universe | None) -> str:
    return f"{label(universe.min_cap_billions if universe else None)}, backtest {ctx.start_date.date()} a {ctx.end_date.date()}"


def run_calendars(ctx: Context, months: int, universe: Universe | None = None,
                  skipped: Skipped | None = None) -> Term:
    """Plazo de N meses con sus N calendarios posibles (arranque desfasado 0..N-1 meses).
    Guarda cada corrida en SQLite; los calendarios que fallan se omiten. Los rebalanceos omitidos se avisan juntos
    al final (o, si el que llama pasa `skipped`, cuando él lo decida)."""
    min_cap_b = universe.min_cap_billions if universe else None
    own = skipped is None
    skipped = {} if own else skipped
    calendars = []
    for offset in range(months):
        start = ctx.start_date + pd.DateOffset(months=offset)
        log.info("=== Plazo %d meses, desfase %d/%d (arranque desde %s) ===",
                 months, offset, months - 1, start.date())
        try:
            result = run_backtest(ctx.constituents, ctx.prices, start, ctx.end_date, ctx.lookback_days(months),
                                  f"{months}MS", ctx.initial_capital, ctx.top_n, universe, skipped)
        except Exception as e:
            log.warning(E.BKT_TERM_FAILED.msg("Plazo %d meses, desfase %d sin resultado: %s"), months, offset, e)
            continue
        save_run(ctx.conn, {**ctx.cfg, "sweep_months": months, "offset_months": offset,
                            "min_cap_billions": min_cap_b},
                 start.strftime("%Y-%m-%d"), ctx.end_date.strftime("%Y-%m-%d"), result)
        calendars.append(Calendar(**vars(result), offset=offset))
    if own:
        report_skipped(skipped, _where(ctx, universe))
    return Term(months, calendars)


def run_terms(ctx: Context, universe: Universe | None = None, months: list[int] | None = None) -> list[Term]:
    """Corre cada plazo (por defecto los de [simulation] months) con todos sus calendarios."""
    skipped: Skipped = {}  # todos los plazos y desfases juntos: un solo aviso por motivo
    terms = [run_calendars(ctx, m, universe, skipped) for m in (months or ctx.terms)]
    report_skipped(skipped, _where(ctx, universe))
    return terms


def attach_market_caps(ctx: Context, terms: list[Term], universe: Universe | None = None) -> None:
    """Agrega la capitalización aprox. de cada selección del calendario base (solo informativa)."""
    histories = [t.base.history for t in terms if t.base]
    if not histories:
        return
    picked = sorted({t for history in histories for h in history for t in h["returns"]})
    shares = ensure_shares(ctx.conn, picked, ctx.use_cache, ctx.settings, known=universe.shares if universe else None)
    add_market_caps(histories, ctx.prices, shares)
