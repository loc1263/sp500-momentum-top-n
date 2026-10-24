"""Resultados del backtest por plazo y calendario de arranque (los consumen la consola, el HTML y las tablas)."""
import statistics
from dataclasses import dataclass

from .engine import BacktestResult


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
