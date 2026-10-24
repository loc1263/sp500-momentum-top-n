import numpy as np
import pandas as pd
import pytest

from top3.config import DEFAULT_CONFIG
from top3.quant import fundamentals as FU, markowitz as MK, momentum as MO, technical as TE
from top3.quant.run import compute


def synthetic_prices(n=12, days=400, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2025-01-01", periods=days)
    drift = np.linspace(0.0001, 0.0012, n)          # T{n-1} es el que más sube
    rets = rng.normal(drift, 0.01, size=(days, n))
    return pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=idx, columns=[f"T{i:02d}" for i in range(n)])


def ohlcv_of(prices: pd.DataFrame, seed=1) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    wiggle = pd.DataFrame(rng.uniform(0.002, 0.02, size=prices.shape), index=prices.index, columns=prices.columns)
    return {"open": prices, "high": prices * (1 + wiggle), "low": prices * (1 - wiggle), "close": prices,
            "volume": pd.DataFrame(rng.uniform(1e6, 5e6, size=prices.shape), index=prices.index, columns=prices.columns)}


def info(**kw):
    base = {"fcf_history": [1e9, 1.1e9, 0.9e9, 1e9], "v": FU.VERSION, "netIncomeToCommon": 2e9, "shortName": "X", "sector": "Technology", "marketCap": 1e11, "returnOnEquity": 0.2, "returnOnAssets": 0.1,
            "profitMargins": 0.15, "operatingMargins": 0.2, "debtToEquity": 50.0, "currentRatio": 1.5, "quickRatio": 1.0,
            "freeCashflow": 1e9, "operatingCashflow": 2e9, "totalRevenue": 1e10, "totalDebt": 5e9, "totalCash": 3e9,
            "ebitda": 3e9}
    return {**base, **kw}


def test_momentum_uses_12_and_6_months_without_the_last_month():
    prices = synthetic_prices()
    ret = MO.momentum_returns(prices)
    t = "T05"
    assert ret.at[t, "mom_12_1"] == pytest.approx(prices[t].iloc[-22] / prices[t].iloc[-253] - 1)
    assert ret.at[t, "mom_6_1"] == pytest.approx(prices[t].iloc[-22] / prices[t].iloc[-127] - 1)


def test_momentum_leaves_out_tickers_with_gaps_or_short_history():
    prices = synthetic_prices()
    prices.loc[prices.index[-100], "T01"] = np.nan
    prices.loc[prices.index[:300], "T02"] = np.nan                 # empezó a cotizar hace menos de un año
    ret = MO.momentum_returns(prices)
    assert ret.loc[["T01", "T02"]].isna().all().all()
    assert MO.momentum_returns(prices.tail(100)).empty
    score = MO.momentum_score(ret)
    assert score.between(0, 100).all() and {"T01", "T02"}.isdisjoint(score.index)
    both = ret.dropna()
    best = both.rank(pct=True).mean(axis=1).idxmax()
    assert score[best] >= score.max() - 1e-9                                 # la mejor por ranking promedio tiene el mayor score


def test_indicators_handle_banks_negative_equity_and_missing_data():
    data = {
        "OK": info(),
        "BANK": info(sector="Financial Services", debtToEquity=None, currentRatio=None, freeCashflow=None),
        "NEGEQ": info(debtToEquity=-80.0),
        "NOCASH": info(totalCash=None, ebitda=-1e9),
        "RICH": info(totalDebt=0.0),
    }
    f = FU.indicators(data)
    assert f.loc["BANK", ["debt_to_equity", "net_debt_ebitda", "current_ratio", "fcf_margin"]].isna().all()
    assert f.loc["BANK", "roe"] == 0.2                                   # la rentabilidad sí se mide
    card = FU.indicators({"CARD": info(sector="Financial Services")}).loc["CARD"]     # financiera con balance común
    assert card["current_ratio"] == 1.5 and card["fcf_margin"] == pytest.approx(0.1)
    assert np.isinf(f.loc["NEGEQ", "debt_to_equity"])                    # patrimonio negativo: lo peor
    assert np.isnan(f.loc["NOCASH", "net_debt_ebitda"])
    assert f.loc["OK", "net_debt_ebitda"] == pytest.approx((5e9 - 3e9) / 3e9)
    assert f.loc["RICH", "net_debt_ebitda"] == 0.0                       # más caja que deuda
    assert f.loc["OK", "fcf_margin"] == pytest.approx(0.1)


def test_cash_flow_indicators():
    data = {
        "OK": info(),
        "LOSS": info(netIncomeToCommon=-1e9, freeCashflow=-2e9, fcf_history=[-2e9, 1e9, -1e9, 1e9]),
        "DEBTFREE": info(totalDebt=0.0),
        "NOHIST": info(fcf_history=[]),
        "NOFCF": info(freeCashflow=None),
    }
    f = FU.indicators(data)
    assert f.loc["OK", "fcf_yield"] == pytest.approx(1e9 / 1e11)
    assert f.loc["OK", "cash_conversion"] == pytest.approx(0.5)               # flujo libre / utilidad neta
    assert f.loc["OK", "ocf_to_debt"] == pytest.approx(2e9 / 5e9)
    assert f.loc["OK", "fcf_positive_years"] == 1.0
    assert np.isnan(f.loc["LOSS", "cash_conversion"])                          # sin utilidad positiva no hay base
    assert f.loc["LOSS", "fcf_positive_years"] == 0.5
    assert np.isinf(f.loc["DEBTFREE", "ocf_to_debt"])                          # sin deuda: la mejor cobertura
    assert np.isnan(f.loc["NOHIST", "fcf_positive_years"])                     # menos de 3 años de historia
    assert np.isnan(f.loc["NOFCF", "fcf_yield"])
    capped = FU.indicators({"X": info(freeCashflow=9e9, netIncomeToCommon=1e9)})
    assert capped.loc["X", "cash_conversion"] == 2.0                           # tope de la conversión


def test_cash_group_weight_changes_the_health_score():
    cash_king = info(freeCashflow=5e9, operatingCashflow=6e9, fcf_history=[5e9, 4e9, 5e9, 4e9], returnOnEquity=0.02,
                     returnOnAssets=0.01, operatingMargins=0.03, profitMargins=0.02)
    profitable = info(freeCashflow=-1e9, operatingCashflow=0.1e9, fcf_history=[-1e9, -1e9, -2e9, -1e9],
                      returnOnEquity=0.5, returnOnAssets=0.3, operatingMargins=0.5, profitMargins=0.4)
    frame = FU.indicators({"CASH": cash_king, "PROFIT": profitable, "MID": info()})
    equal = FU.health_score(frame)
    heavy = FU.health_score(frame, {"rentabilidad": 1, "solvencia": 1, "liquidez": 1, "caja": 6})
    assert equal.loc["PROFIT", "health"] > equal.loc["CASH", "health"]
    assert heavy.loc["CASH", "health"] > heavy.loc["PROFIT", "health"]        # con más peso a la caja, gana la que genera caja


def test_health_score_ranks_the_sounder_company_higher_and_counts_groups():
    strong = info(returnOnEquity=0.4, operatingMargins=0.4, debtToEquity=10.0, currentRatio=3.0, quickRatio=2.5,
                  freeCashflow=4e9, operatingCashflow=5e9, totalDebt=1e9, totalCash=5e9)
    weak = info(returnOnEquity=-0.1, operatingMargins=0.01, debtToEquity=400.0, currentRatio=0.5, quickRatio=0.3,
                freeCashflow=-1e9, operatingCashflow=0.0, totalDebt=9e9, totalCash=1e8, ebitda=-1e8)
    bank = info(sector="Financial Services", debtToEquity=None, currentRatio=None, quickRatio=None, freeCashflow=None,
                operatingCashflow=None, totalDebt=None, totalCash=None, ebitda=None)
    scores = FU.health_score(FU.indicators({"STRONG": strong, "MID": info(), "WEAK": weak, "BANK": bank}))
    assert scores.loc["STRONG", "health"] > scores.loc["MID", "health"] > scores.loc["WEAK", "health"]
    assert scores["health"].between(0, 100).all()
    assert scores.loc["BANK", "groups"] == 1 and scores.loc["STRONG", "groups"] == 4


def test_rsi_and_macd_match_a_plain_reference_implementation():
    close = synthetic_prices(n=3, days=400)
    c = close["T01"].to_numpy()
    d = np.diff(c)
    gain, loss = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    ag, al = gain[:14].mean(), loss[:14].mean()
    for i in range(14, len(d)):                                   # media de Wilder, escrita a mano
        ag, al = (ag * 13 + gain[i]) / 14, (al * 13 + loss[i]) / 14
    assert TE.rsi(close)["T01"].iloc[-1] == pytest.approx(100 - 100 / (1 + ag / al))

    series = pd.Series(c)
    line = series.ewm(span=12, adjust=False).mean() - series.ewm(span=26, adjust=False).mean()
    hist = line - line.ewm(span=9, adjust=False).mean()
    assert TE.macd(close)[1]["T01"].iloc[-1] == pytest.approx(hist.iloc[-1])


def test_indicator_bounds_and_special_cases():
    prices = synthetic_prices(n=4, days=400)
    o = ohlcv_of(prices)
    assert TE.rsi(prices).iloc[30:].stack().between(0, 100).all()
    assert TE.stochastic(o["high"], o["low"], o["close"]).iloc[30:].stack().between(0, 100).all()
    assert TE.mfi(o["high"], o["low"], o["close"], o["volume"]).iloc[30:].stack().between(0, 100).all()
    assert TE.adx(o["high"], o["low"], o["close"])[0].iloc[60:].stack().between(0, 100).all()
    rising = pd.DataFrame({"A": np.arange(1.0, 60.0)})
    assert TE.rsi(rising)["A"].iloc[-1] == 100                    # sin pérdidas: RSI = 100
    obv = TE.obv(pd.DataFrame({"A": [1.0, 2.0, 1.5, 1.5]}), pd.DataFrame({"A": [10.0, 10.0, 20.0, 30.0]}))
    assert obv["A"].tolist() == [0.0, 10.0, -10.0, -10.0]


def test_technical_score_prefers_an_uptrend_and_needs_a_full_year():
    days = 400
    idx = pd.bdate_range("2025-01-01", periods=days)
    rng = np.random.default_rng(5)
    noise = rng.normal(0, 0.004, size=(days, 3))
    up = 100 * np.cumprod(1 + 0.002 + noise[:, 0])
    down = 100 * np.cumprod(1 - 0.002 + noise[:, 1])
    flat = 100 * np.cumprod(1 + noise[:, 2])
    prices = pd.DataFrame({"UP": up, "DOWN": down, "FLAT": flat, "SHORT": flat}, index=idx)
    prices.loc[idx[:300], "SHORT"] = np.nan                         # menos de un año de ruedas
    out = TE.technical_score(TE.indicators(ohlcv_of(prices)))
    assert out["technical"].idxmax() == "UP" and out["technical"].idxmin() == "DOWN"
    assert out["technical"].dropna().between(0, 100).all()
    assert np.isnan(out.loc["SHORT", "technical"])
    assert out.loc["UP", "vs_ema200"] > 0 > out.loc["DOWN", "vs_ema200"]
    assert set(TE.GROUPS) <= set(out.columns)


def test_markowitz_respects_the_limits_and_orders_risk():
    prices = synthetic_prices(n=10, days=300)
    mu, sigma = MK.inputs(prices, mu_shrink=0.25, prior=0.09)
    assert mu.between(-1, 1).all()
    out = MK.frontier(mu, sigma, vol_target=0.30, w_max=0.25, risk_free=0.04)
    by_key = {p["key"]: p for p in out["portfolios"]}
    assert set(by_key) == {"max_return", "max_sharpe", "min_var"}
    for p in by_key.values():
        weights = [w["weight"] for w in p["weights"]]
        assert sum(weights) == pytest.approx(1) and max(weights) <= 0.25 + 1e-6 and min(weights) >= 0
    assert by_key["min_var"]["vol"] <= by_key["max_sharpe"]["vol"] + 1e-6
    assert by_key["max_return"]["vol"] <= 0.30 + 1e-4
    assert by_key["max_return"]["exp_return"] >= by_key["min_var"]["exp_return"] - 1e-6
    assert by_key["max_sharpe"]["sharpe"] >= by_key["min_var"]["sharpe"] - 1e-6
    assert out["min_vol"] == pytest.approx(by_key["min_var"]["vol"])


def test_markowitz_caps_the_weight_of_each_sector():
    prices = synthetic_prices(n=10, days=300)
    mu, sigma = MK.inputs(prices, 0.25, 0.09)
    mu.iloc[:5] += 0.5                                          # las cinco primeras (mismo sector) son las más atractivas
    sectors = pd.Series(["A"] * 5 + ["B"] * 3 + ["C"] * 2, index=mu.index)
    free = MK.frontier(mu, sigma, 0.40, 0.25, 0.04)
    capped = MK.frontier(mu, sigma, 0.40, 0.25, 0.04, sectors, 0.40)
    assert not capped["sector_relaxed"]
    for p in capped["portfolios"]:
        assert max(x["weight"] for x in p["sectors"]) <= 0.40 + 1e-6
        assert sum(x["weight"] for x in p["sectors"]) == pytest.approx(1)
    assert free["portfolios"][1]["sectors"][0]["weight"] > 0.40 + 1e-3         # sin tope el sector A pesa más
    assert capped["portfolios"][0]["exp_return"] <= free["portfolios"][0]["exp_return"] + 1e-6


def test_markowitz_relaxes_the_sector_cap_when_it_cannot_invest_everything():
    sectors = pd.Series(["A"] * 6 + ["B"] * 4)
    assert MK.feasible_sector_cap(sectors, 0.25, 0.40) == pytest.approx(0.50)   # con 40% por sector solo se coloca 80%: sube a 50%
    assert MK.feasible_sector_cap(pd.Series(["A"] * 10), 0.25, 0.40) == pytest.approx(1.0)
    assert MK.feasible_sector_cap(pd.Series(list("ABCDE") * 2), 0.25, 0.40) == pytest.approx(0.40)
    prices = synthetic_prices(n=4, days=300)
    mu, sigma = MK.inputs(prices, 0.25, 0.09)
    out = MK.frontier(mu, sigma, 0.5, 0.5, 0.04, pd.Series(["A"] * 4, index=mu.index), 0.40)
    assert out["sector_relaxed"] and out["sector_max"] == pytest.approx(1.0)
    assert sum(w["weight"] for w in out["portfolios"][0]["weights"]) == pytest.approx(1)


def test_markowitz_drops_the_max_return_portfolio_when_the_risk_target_is_unreachable():
    prices = synthetic_prices(n=10, days=300)
    mu, sigma = MK.inputs(prices, 0.25, 0.09)
    out = MK.frontier(mu, sigma, vol_target=0.001, w_max=0.25, risk_free=0.04)
    assert [p["key"] for p in out["portfolios"]] == ["max_sharpe", "min_var"]


def test_compute_builds_the_final_ranking_and_markowitz():
    prices = synthetic_prices(n=14, days=400)
    tickers = list(prices.columns) + ["NODATA"]
    rng = np.random.default_rng(3)
    data = {t: info(returnOnEquity=float(rng.uniform(-0.1, 0.5)), debtToEquity=float(rng.uniform(5, 300)),
                    operatingMargins=float(rng.uniform(0, 0.4))) for t in prices.columns}
    cfg = {section: dict(values) for section, values in DEFAULT_CONFIG.items()}
    cfg["quant"].update(top_n=6, weights=[1, 1, 2])
    out = compute(prices, tickers, data, ohlcv_of(prices), cfg)

    ranking = out["ranking"]
    assert out["coverage"]["universe"] == 15 and out["coverage"]["ranked"] == 14
    assert out["coverage"]["technical"] == 14 and "NODATA" in out["coverage"]["excluded"]["sin_datos_tecnicos"]
    assert "NODATA" in out["coverage"]["excluded"]["sin_momentum"]
    assert [r["rank"] for r in ranking] == list(range(1, 15))
    assert [r["score"] for r in ranking] == sorted((r["score"] for r in ranking), reverse=True)
    for r in ranking:                                                   # promedio ponderado de los tres scores
        assert r["score"] == pytest.approx((r["momentum"] + r["health"] + 2 * r["technical"]) / 4)
        assert set(r["technical_groups"]) == set(TE.GROUPS) and r["rsi"] is not None

    top = [r["ticker"] for r in ranking[:6]]
    assert [t["ticker"] for t in out["markowitz"]["tickers"]] == top
    main = next(p for p in out["markowitz"]["portfolios"] if p["key"] == out["markowitz"]["main"])
    assert {w["ticker"] for w in main["weights"]} <= set(top)
    assert sum(r["weight"] for r in ranking) == pytest.approx(1)
    assert all(r["weight"] == 0 for r in ranking[6:])
    import json
    json.dumps(out, allow_nan=False)                                    # sin NaN ni infinitos: es JSON válido
