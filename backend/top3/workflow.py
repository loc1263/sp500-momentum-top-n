"""Flujos del backtest: arman las corridas, las muestran por consola y escriben los reportes HTML."""
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import pandas as pd

from . import console, errors as E, html_report, universe as universes
from .analysis import SKIP_MONTHS, Context, attach_market_caps, run_calendars, run_terms
from .config import BacktestConfig, Config
from .db import open_db
from .logs import log
from .market import refresh_market_data
from .universe import Universe, UniverseBuilder


def _min_cap(universe: Universe | None) -> float | None:
    return universe.min_cap_billions if universe else None


def run_single(ctx: Context, months: int, universe: Universe | None) -> Path:
    """Backtest normal de un plazo (con sus calendarios de arranque): imprime el resultado y escribe el HTML."""
    log.info("Ejecutando backtest Point-in-Time (plazo %d meses)...", months)
    term = run_calendars(ctx, months, universe)
    if term.base is None:
        raise SystemExit(E.BKT_EMPTY.msg("El backtest no generó ningún rebalanceo; revisa fechas/histórico en la configuración."))
    attach_market_caps(ctx, [term], universe)
    console.print_backtest(ctx, term, _min_cap(universe))
    return html_report.backtest_report(ctx, term, _min_cap(universe))


def run_sweep(ctx: Context, universe: Universe | None) -> list[Path]:
    """Compara todos los plazos y su sensibilidad al arranque: dos reportes (sweep y offsets)."""
    terms = run_terms(ctx, universe)
    attach_market_caps(ctx, terms, universe)
    min_cap_b = _min_cap(universe)
    console.print_sweep(ctx, terms, min_cap_b)
    sweep = html_report.sweep_report(ctx, terms, min_cap_b)
    console.print_offsets(ctx, terms, min_cap_b)
    # El modelo skip-month (N-1) corre siempre junto al de siempre, con los mismos datos, para compararlos
    skip_terms = run_terms(ctx, universe, skip_months=SKIP_MONTHS)
    console.print_models(ctx, terms, skip_terms, min_cap_b)
    return [sweep, html_report.offsets_report(ctx, terms, min_cap_b)]


def run_offsets(ctx: Context, universe: Universe | None) -> Path:
    """Solo la sensibilidad al arranque de cada plazo."""
    terms = run_terms(ctx, universe)
    console.print_offsets(ctx, terms, _min_cap(universe))
    return html_report.offsets_report(ctx, terms, _min_cap(universe))


@dataclass
class BacktestJob:
    """Qué pidió el usuario para el backtest (los flags de la línea de comandos)."""

    sweep: bool = False
    offsets: bool = False
    months: int | None = None
    years: float | None = None
    large_cap: bool = False
    min_cap_billions: float | None = None
    use_cache: bool = True


def resolve_periods(bt_cfg: BacktestConfig, end_date: pd.Timestamp,
                    years: float | None) -> list[tuple[float, pd.Timestamp]]:
    """Períodos a evaluar como (años, fecha de inicio). Un start_date explícito en el config es un único período."""
    if bt_cfg.start_date:
        start = pd.to_datetime(bt_cfg.start_date)
        return [(round((end_date - start).days / 365.25, 1), start)]
    years_list = [years] if years else [float(y) for y in bt_cfg.periods_years]
    return [(y, end_date - pd.DateOffset(years=int(y))) for y in sorted(years_list)]


def resolve_levels(job: BacktestJob, cfg: Config) -> list[float]:
    """Umbrales de capitalización a correr (0 = índice completo)."""
    explicit = universes.explicit_min_cap(cfg, job.large_cap, job.min_cap_billions)
    if explicit is not None:
        return [explicit]
    if job.sweep:  # --sweep sin filtro explícito: todos los universos configurados
        return [float(x) for x in cfg.universe.sweep_min_cap_billions]
    return [0.0]


def run_backtest_job(cfg: Config, job: BacktestJob) -> list[Path]:
    """Actualiza los datos y corre el backtest de cada período; devuelve los reportes HTML generados."""
    log.info("Caché: %s", "activada (se reutiliza lo descargado hoy)" if job.use_cache
             else "DESACTIVADA (--no-cache)")
    bt_cfg = cfg.backtest
    settings = cfg.data

    today = date.today()
    history_start = settings.history_start(today)

    end_date = pd.to_datetime(bt_cfg.end_date or today)
    periods = resolve_periods(bt_cfg, end_date, job.years)
    for years, start_date in periods:
        if start_date >= end_date:
            raise SystemExit(E.CFG_BAD_DATES.msg(
                f"start_date ({start_date.date()}) debe ser anterior a end_date ({end_date.date()})"))
        log.info("Histórico: %s a %s | Backtest de %g años: %s a %s", history_start, today, years,
                 start_date.date(), end_date.date())
        if start_date < pd.to_datetime(history_start):
            log.warning(E.CFG_SHORT_HISTORY.msg("El inicio del backtest de %g años (%s) es anterior al histórico "
                                                "descargado (%s); subí [data] history_years"),
                        years, start_date.date(), history_start)

    conn = open_db(settings.db_path)
    try:
        market = refresh_market_data(conn, cfg, job.use_cache, today)
        constituents, prices = market.constituents, market.prices

        levels = resolve_levels(job, cfg)
        known_shares: dict[str, float] = {}  # acciones en circulación ya bajadas: se reutilizan en toda la corrida
        build_universe = UniverseBuilder(conn, prices, job.use_cache, settings, known_shares)
        months = job.months or bt_cfg.months

        reports: list[Path] = []
        for years, start_date in periods:
            # Cada período lleva su propio config (años) y sufijo de los HTML (_5y, _10y...)
            ctx = Context(conn, replace(cfg, backtest=replace(bt_cfg, backtest_years=years)), settings, constituents,
                          prices, start_date, end_date, job.use_cache, file_suffix=f"_{years:g}y",
                          known_shares=known_shares)
            log.info("########## Período: %g años (%s a %s) ##########", years, start_date.date(), end_date.date())
            for level in levels:
                universe = build_universe(level)
                if job.sweep:
                    log.info("##### Sweep - universo: %s #####", universes.label(level))
                    reports += run_sweep(ctx, universe)
                elif job.offsets:
                    reports.append(run_offsets(ctx, universe))
                else:
                    reports.append(run_single(ctx, months, universe))
    finally:
        conn.close()
    return reports
