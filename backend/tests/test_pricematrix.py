import numpy as np
import pandas as pd
import pytest

from helpers import FakeConstituents, make_prices
from top3 import engine
from top3.pricematrix import PriceMatrix
from top3.universe import Universe


def short_prices(days, n):
    return make_prices("2024-01-01", pd.bdate_range("2024-01-01", periods=days)[-1].date().isoformat(), n)


def messy_prices(days=400, tickers=40, seed=7):
    """Precios con huecos sueltos, tickers que empiezan tarde y otros que dejan de cotizar."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=days)
    data = 100 * np.cumprod(1 + rng.normal(0.0005, 0.02, (days, tickers)), axis=0)
    df = pd.DataFrame(data, index=idx, columns=[f"T{i:02d}" for i in range(tickers)])
    for col in rng.choice(df.columns, 8, replace=False):          # huecos sueltos
        df.loc[idx[rng.integers(10, days - 10, 3)], col] = np.nan
    for col in rng.choice(df.columns, 5, replace=False):          # empieza tarde
        df.loc[idx[: rng.integers(50, 300)], col] = np.nan
    for col in rng.choice(df.columns, 4, replace=False):          # deja de cotizar
        df.loc[idx[rng.integers(100, days - 20):], col] = np.nan
    return df


# --- las implementaciones de siempre (pandas): la referencia contra la que se compara ---

def reference_rank(prices, tickers, when, lookback):
    window = prices.loc[:when, tickers].tail(lookback + 1).dropna(axis=1, how="any")
    if len(window) < lookback + 1:
        return None
    return (window.iloc[-1] / window.iloc[0] - 1).dropna().sort_values(ascending=False)


def reference_hold(prices, tickers, start, end):
    held = prices.loc[start:end, tickers].dropna(axis=1)
    if len(held) <= 1:
        return None
    return float((held.iloc[-1] / held.iloc[0] - 1).mean()), list(held.columns), held.index[-1]


def reference_last_prices(prices, tickers, when):
    return prices.loc[:when, tickers].ffill().iloc[-1]


def sample_calls(prices, n=60, seed=1):
    rng = np.random.default_rng(seed)
    cols = list(prices.columns)
    for _ in range(n):
        tickers = [cols[i] for i in rng.permutation(len(cols))[: rng.integers(5, len(cols))]]
        a, b = sorted(rng.choice(len(prices), 2, replace=False))
        yield tickers, prices.index[a], prices.index[b]


def test_returns_match_the_pandas_reference_exactly():
    prices = messy_prices()
    matrix = PriceMatrix(prices)
    checked = 0
    for tickers, when, _ in sample_calls(prices):
        for lookback in (21, 63, 126):
            expected = reference_rank(prices, tickers, when, lookback)
            if expected is None:
                assert matrix.rows_until(when) < lookback + 1
                continue
            got = matrix.returns(tickers, when, lookback)
            pd.testing.assert_series_equal(got, expected, check_exact=True, check_names=False)
            checked += 1
    assert checked > 100


def test_hold_return_matches_the_pandas_reference_exactly():
    prices = messy_prices()
    matrix = PriceMatrix(prices)
    for tickers, start, end in sample_calls(prices):
        expected = reference_hold(prices, tickers, start, end)
        got = matrix.hold_return(tickers, start, end)
        if expected is None:
            assert got is None
        else:
            assert got[1] == expected[1] and got[2] == expected[2]
            assert got[0] == expected[0] or (np.isnan(got[0]) and np.isnan(expected[0]))


def test_hold_return_accepts_dates_that_are_not_trading_days_and_strings():
    prices = messy_prices()
    matrix = PriceMatrix(prices)
    tickers = ["T00", "T01", "T02"]
    saturday, monday = "2022-03-05", "2022-04-04"                 # 2022-03-05 es sábado
    expected = reference_hold(prices, tickers, saturday, monday)
    assert matrix.hold_return(tickers, saturday, monday) == expected
    assert matrix.hold_return(tickers, saturday, saturday) is None


def test_last_prices_match_the_reference_and_use_the_last_known_value():
    prices = messy_prices()
    matrix = PriceMatrix(prices)
    for tickers, _, when in sample_calls(prices):
        pd.testing.assert_series_equal(matrix.last_prices(tickers, when), reference_last_prices(prices, tickers, when),
                                       check_exact=True, check_names=False)
    assert matrix.last_prices(["T00"], "2000-01-01").isna().all()          # antes de que existan precios


def test_a_window_with_a_gap_leaves_that_ticker_out():
    prices = short_prices(200, 3)
    prices.loc[prices.index[-10], "T01"] = np.nan
    got = PriceMatrix(prices).returns(["T00", "T01", "T02"], prices.index[-1], 63)
    assert set(got.index) == {"T00", "T02"}


def test_not_enough_rows_raises_and_unknown_tickers_are_a_key_error():
    matrix = PriceMatrix(short_prices(50, 2))
    with pytest.raises(ValueError, match="se necesitan 64"):
        matrix.returns(["T00"], matrix.index[-1], 63)
    with pytest.raises(KeyError):
        matrix.returns(["NOPE"], matrix.index[-1], 10)
    assert "T00" in matrix and "NOPE" not in matrix


def test_empty_prices_do_not_break():
    matrix = PriceMatrix(pd.DataFrame())
    assert matrix.rows_until("2024-01-01") == 0 and matrix.columns == []


def test_engine_functions_accept_a_dataframe_or_a_matrix():
    prices = make_prices()
    when = prices.index[-1]
    tickers = list(prices.columns)
    from_frame = engine.rank_returns(prices, tickers, when, 63)
    from_matrix = engine.rank_returns(PriceMatrix(prices), tickers, when, 63)
    pd.testing.assert_series_equal(from_frame, from_matrix)
    assert engine.rank_returns(prices.head(10), tickers, prices.index[9], 63) is None
    assert engine.hold_return(prices, tickers, prices.index[0], when) == \
        engine.hold_return(PriceMatrix(prices), tickers, prices.index[0], when)
    universe = Universe({t: 1e12 if t == "T03" else 1.0 for t in tickers}, 1)
    assert engine.eligible_tickers(tickers, prices, when, universe) == ["T03"]


def test_backtest_gives_the_same_result_with_a_prebuilt_matrix():
    prices = messy_prices(days=500, tickers=30)
    cons = FakeConstituents(list(prices.columns))
    args = (cons, "2022-06-01", "2023-11-30", 63, "3MS", 1000, 3)
    a = engine.run_backtest(args[0], prices, *args[1:])
    b = engine.run_backtest(args[0], PriceMatrix(prices), *args[1:])
    assert a.history == b.history and a.final_capital == b.final_capital
    pd.testing.assert_series_equal(a.equity_curve, b.equity_curve)


def test_context_builds_the_matrix_once(conn, cfg, settings):
    from top3.analysis import Context
    ctx = Context(conn, cfg, settings, FakeConstituents([]), short_prices(30, 2),
                  pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01"))
    assert ctx.matrix is ctx.matrix and ctx.matrix.columns == ["T00", "T01"]
