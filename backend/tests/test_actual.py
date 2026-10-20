import pandas as pd
import pytest

from top3 import actual
from top3.universe import Universe


def make_prices(days=140, n=12):
    idx = pd.bdate_range(end="2024-12-31", periods=days)
    return pd.DataFrame({f"T{i:02d}": [100 * (1 + 0.001 * (i + 1)) ** k for k in range(days)] for i in range(n)},
                        index=idx)


def test_compute_top_orders_by_return():
    top, window = actual.compute_top(make_prices(), 4, 3, 21)
    assert list(top.index) == ["T11", "T10", "T09"]
    assert len(window) == 4 * 21 + 1


def test_compute_top_drops_incomplete_tickers():
    prices = make_prices()
    prices.loc[prices.index[-50]:, "T11"] = float("nan")
    top, _ = actual.compute_top(prices, 4, 2, 21)
    assert "T11" not in top.index


def test_compute_top_not_enough_data():
    with pytest.raises(SystemExit):
        actual.compute_top(make_prices(days=30), 4, 3, 21)


def test_compute_top_market_cap_filter():
    prices = make_prices()
    shares = {t: 1.0 for t in prices.columns}
    shares["T05"] = 1e12
    top, _ = actual.compute_top(prices, 4, 3, 21, Universe(shares, 1))
    assert list(top.index) == ["T05"]


def test_get_prices_downloads_when_no_cache(conn, monkeypatch, settings):
    prices = make_prices(days=5, n=2)
    monkeypatch.setattr(actual, "download_recent", lambda tickers, start, end, batch_size: prices[tickers])
    out = actual.get_prices(conn, ["T00", "T01"], "2024-01-01", "2025-01-01", True, settings)
    assert list(out.columns) == ["T00", "T01"]


def test_download_recent_returns_datetime_index(monkeypatch):
    long = pd.DataFrame([("A", "2024-01-02", 1.0), ("A", "2024-01-03", 2.0), ("B", "2024-01-02", 3.0)],
                        columns=["ticker", "date", "close"])
    monkeypatch.setattr(actual, "fetch_prices", lambda tickers, start, end, batch_size: (long, []))
    out = actual.download_recent(["A", "B"], "2024-01-01", "2024-01-05", 100)
    assert isinstance(out.index, pd.DatetimeIndex) and out.index[-1].date().isoformat() == "2024-01-03"
    assert out.shape == (2, 2)


def test_get_current_tickers_applies_aliases(conn, monkeypatch, settings):
    conn.executemany("INSERT INTO constituents_current VALUES (?)", [("BK",), ("AAPL",)])
    conn.commit()
    monkeypatch.setattr(actual, "download_current_constituents", lambda c, s: None)
    assert actual.get_current_tickers(conn, {"BK": "BNY"}, False, settings) == ["BNY", "AAPL"]
