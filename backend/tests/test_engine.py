import pandas as pd
import pytest

from helpers import FakeConstituents, make_prices
from top3.engine import eligible_tickers, hold_return, rank_returns, run_backtest
from top3.shares import add_market_caps
from top3.universe import Universe


def test_run_backtest_picks_best_performers():
    prices = make_prices()
    result = run_backtest(FakeConstituents(list(prices.columns)), prices, "2023-09-01", "2024-12-31",
                          63, "3MS", 1000, 3)
    assert all(h["picks"] == ["T11", "T10", "T09"] for h in result.history)
    assert result.final_capital > 1000 and result.total_return_pct > 0 and result.cagr_pct > 0
    assert result.equity_curve.iloc[-1] == pytest.approx(result.final_capital)
    assert list(result.history[0]["returns"]) == ["T11", "T10", "T09"]


def test_run_backtest_market_cap_filter_leaves_too_few_tickers():
    prices = make_prices()
    shares = {t: (1e12 if t in ("T00", "T01", "T02") else 1.0) for t in prices.columns}
    # solo 3 tickers superan el umbral -> menos de 10 candidatos -> no hay rebalanceos
    with pytest.raises(RuntimeError):
        run_backtest(FakeConstituents(list(prices.columns)), prices, "2023-09-01", "2024-12-31", 63, "3MS",
                     1000, 3, Universe(shares, 1))


def test_run_backtest_without_constituents_raises():
    with pytest.raises(RuntimeError):
        run_backtest(FakeConstituents([]), make_prices(), "2023-09-01", "2024-12-31", 63, "3MS", 1000, 3)


def test_eligible_tickers_requires_prices_and_cap():
    prices = make_prices(n=3)
    when = pd.Timestamp("2024-01-02")
    assert eligible_tickers(["T00", "NOPE", "T02"], prices, when, None) == ["T00", "T02"]
    universe = Universe({"T00": 1e12, "T02": 1.0}, 1)
    assert eligible_tickers(["T00", "NOPE", "T02"], prices, when, universe) == ["T00"]


def test_rank_returns_orders_and_requires_enough_history():
    prices = make_prices(n=4)
    when = pd.Timestamp("2024-06-03")
    returns = rank_returns(prices, list(prices.columns), when, 21)
    assert list(returns.index) == ["T03", "T02", "T01", "T00"]
    assert rank_returns(prices, list(prices.columns), pd.Timestamp("2023-01-10"), 21) is None


def test_hold_return_is_equal_weight_mean():
    idx = pd.bdate_range("2024-01-01", periods=3)
    prices = pd.DataFrame({"A": [100.0, 110.0, 120.0], "B": [100.0, 100.0, 100.0]}, index=idx)
    ret, tickers, last = hold_return(prices, ["A", "B"], idx[0], idx[-1])
    assert ret == pytest.approx(0.10) and tickers == ["A", "B"] and last == idx[-1]
    assert hold_return(prices, ["A"], idx[0], idx[0]) is None       # una sola rueda: sin retorno


def test_add_market_caps():
    prices = make_prices()
    history = [[{"date": "2023-06-01", "returns": {"T00": 0.1, "NOPE": 0.2}}]]
    add_market_caps(history, prices, {"T00": 10.0})
    caps = history[0][0]["caps"]
    assert set(caps) == {"T00"}
    assert caps["T00"] == pytest.approx(prices.loc[:"2023-06-01", "T00"].iloc[-1] * 10)


def test_run_backtest_skipped_collects_dates_instead_of_warning(caplog):
    from top3 import errors as E
    prices = make_prices()
    skipped = {}

    class FewEarly(FakeConstituents):
        def on_date(self, t):
            return self.tickers[:5] if pd.Timestamp(t) < pd.Timestamp("2024-01-01") else self.tickers

    run_backtest(FewEarly(list(prices.columns)), prices, "2023-09-01", "2024-12-31", 63, "3MS", 1000, 3,
                 skipped=skipped)
    assert skipped == {E.BKT_FEW_TICKERS: {"2023-09-01", "2023-12-01"}}
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_run_backtest_without_collector_warns_per_date(caplog):
    prices = make_prices()

    class FewEarly(FakeConstituents):
        def on_date(self, t):
            return self.tickers[:5] if pd.Timestamp(t) < pd.Timestamp("2024-01-01") else self.tickers

    run_backtest(FewEarly(list(prices.columns)), prices, "2023-09-01", "2024-12-31", 63, "3MS", 1000, 3)
    assert len([r for r in caplog.records if "TOP-BKT-003" in r.getMessage()]) == 2


def test_rank_returns_skip_days_ignores_the_most_recent_rows_and_needs_more_history():
    idx = pd.bdate_range("2024-01-01", periods=30)
    prices = pd.DataFrame({"UP_LATE": [100.0] * 20 + [100.0 + 10 * i for i in range(1, 11)],   # sube en el último tramo
                           "UP_EARLY": [100.0 + 5 * i for i in range(20)] + [195.0] * 10},
                          index=idx)
    tickers = list(prices.columns)
    assert list(rank_returns(prices, tickers, idx[-1], 9).index) == ["UP_LATE", "UP_EARLY"]
    assert list(rank_returns(prices, tickers, idx[-1], 9, skip_days=10).index) == ["UP_EARLY", "UP_LATE"]
    assert rank_returns(prices, tickers, idx[-1], 25, skip_days=10) is None      # 26 + 10 ruedas > 30


def test_commission_charges_entry_and_only_the_positions_that_change():
    prices = make_prices()
    args = (FakeConstituents(list(prices.columns)), prices, "2023-09-01", "2024-12-31", 63, "3MS", 1000, 3)
    free = run_backtest(*args)
    paid = run_backtest(*args, commission=0.001)
    # la selección no cambia nunca: solo se paga la compra inicial
    assert len({tuple(h["picks"]) for h in free.history}) == 1
    assert paid.final_capital == pytest.approx(free.final_capital * (1 - 0.001))


def test_commission_is_charged_twice_on_the_names_that_rotate(monkeypatch):
    prices = make_prices()
    rotating = iter([["T11", "T10", "T09"], ["T08", "T07", "T06"], ["T08", "T07", "T05"]])
    import top3.engine as engine
    real = engine.rank_returns

    def fake(*a, **k):
        ranked = real(*a, **k)
        return ranked.loc[next(rotating)] if ranked is not None else None
    monkeypatch.setattr(engine, "rank_returns", fake)
    args = (FakeConstituents(list(prices.columns)), prices, "2023-09-01", "2024-03-01", 63, "3MS", 1000, 3)
    free = run_backtest(*args)
    rotating = iter([["T11", "T10", "T09"], ["T08", "T07", "T06"], ["T08", "T07", "T05"]])
    paid = run_backtest(*args, commission=0.01)
    # entrada 1%; rotación total (3 de 3) 2%; rotación de 1 de 3 = 2% / 3
    expected = (1 - 0.01) * (1 - 0.02) * (1 - 0.02 / 3)
    assert paid.final_capital == pytest.approx(free.final_capital * expected)
