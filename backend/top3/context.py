"""Contexto de una corrida de backtest: datos, fechas y configuración que comparten todas las simulaciones."""
import sqlite3
from dataclasses import dataclass, field

import pandas as pd

from .config import Config, DataConfig
from .constituents import Constituents
from .pricematrix import PriceMatrix


@dataclass
class Context:
    """Todo lo que comparten las corridas de un período: datos, fechas y configuración."""

    conn: sqlite3.Connection
    cfg: Config
    settings: DataConfig
    constituents: Constituents
    prices: pd.DataFrame
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    use_cache: bool = True
    file_suffix: str = ""   # se agrega al nombre de los reportes HTML (p. ej. "_5y")
    known_shares: dict[str, float] = field(default_factory=dict)  # acciones ya bajadas en esta corrida
    _matrix: PriceMatrix | None = field(default=None, repr=False)

    @property
    def matrix(self) -> PriceMatrix:
        """Los precios como matriz numpy, armada una sola vez y compartida por todas las simulaciones."""
        if self._matrix is None:
            self._matrix = PriceMatrix(self.prices)
        return self._matrix

    @property
    def initial_capital(self) -> float:
        return self.cfg.backtest.initial_capital

    @property
    def commission(self) -> float:
        return self.cfg.backtest.commission

    @property
    def top_n(self) -> int:
        return self.cfg.backtest.top_n

    @property
    def terms(self) -> list[int]:
        return list(self.cfg.simulation.months)

    def lookback_days(self, months: int) -> int:
        return months * self.cfg.backtest.trading_days_per_month

    def skip_days(self, skip_months: int) -> int:
        return skip_months * self.cfg.backtest.trading_days_per_month
