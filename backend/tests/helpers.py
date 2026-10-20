import pandas as pd

from top3.analysis import Calendar
from top3.engine import BacktestResult


def make_prices(start="2023-01-02", end="2024-12-31", n=12) -> pd.DataFrame:
    """n tickers T00..T{n-1} que crecen a ritmos distintos: T{n-1} siempre es el que más sube."""
    idx = pd.bdate_range(start, end)
    return pd.DataFrame({f"T{i:02d}": [100 * (1 + 0.0005 * (i + 1)) ** k for k in range(len(idx))]
                         for i in range(n)}, index=idx)


class FakeConstituents:
    """Mismos constituyentes en todas las fechas."""

    def __init__(self, tickers):
        self.tickers = tickers

    def on_date(self, _):
        return self.tickers


def make_calendar(offset: int, final: float, cagr_pct: float) -> Calendar:
    """Calendario mínimo (una selección, dos puntos de capital) para probar tablas y resúmenes."""
    result = BacktestResult(pd.Series([1000.0, final], index=pd.to_datetime(["2024-01-01", "2024-09-01"])),
                            [{"date": "2024-01-01", "picks": ["A"], "returns": {"A": 0.5}}], final,
                            (final / 1000 - 1) * 100, cagr_pct)
    return Calendar(**vars(result), offset=offset)
