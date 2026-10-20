"""Flujos del backtest: arman las corridas, las muestran por consola y escriben los reportes HTML."""
import sqlite3
from pathlib import Path

import pandas as pd

from . import console, errors as E, html_report, universe as universes
from .analysis import Context, attach_market_caps, run_calendars, run_terms
from .config import DataSettings
from .logs import log
from .shares import ensure_shares
from .universe import Universe


class UniverseBuilder:
    """Crea el Universe de cada umbral de capitalización reutilizando las acciones en circulación ya bajadas."""

    def __init__(self, conn: sqlite3.Connection, prices: pd.DataFrame, use_cache: bool, settings: DataSettings):
        self.conn, self.prices, self.use_cache, self.settings = conn, prices, use_cache, settings
        self._shares: dict[str, float] | None = None

    def __call__(self, min_cap_billions: float | None) -> Universe | None:
        """None para el índice completo (umbral 0 o vacío)."""
        if not min_cap_billions:
            return None
        if self._shares is None:
            self._shares = ensure_shares(self.conn, list(self.prices.columns), self.use_cache, self.settings)
        log.info("Universo: %s (cap. aprox. >= US$ %g B)", universes.label(min_cap_billions), min_cap_billions)
        return Universe(self._shares, min_cap_billions)


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
    return [sweep, html_report.offsets_report(ctx, terms, min_cap_b)]


def run_offsets(ctx: Context, universe: Universe | None) -> Path:
    """Solo la sensibilidad al arranque de cada plazo."""
    terms = run_terms(ctx, universe)
    console.print_offsets(ctx, terms, _min_cap(universe))
    return html_report.offsets_report(ctx, terms, _min_cap(universe))
