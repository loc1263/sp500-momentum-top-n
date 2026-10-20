import pandas as pd
import pytest

from top3 import universe
from top3.universe import Universe


@pytest.mark.parametrize("cap,suffix", [(0, ""), (None, ""), (5, "_cap5B"), (10, "_largecap"), (200, "_megacap")])
def test_suffix(cap, suffix):
    assert universe.suffix(cap) == suffix


def test_labels():
    assert universe.label(None) == universe.label(0) == "índice completo"
    assert universe.label(200) == "mega-cap"
    assert universe.label(10) == "large-cap + mega-cap"
    assert universe.label(5).startswith("cap.")
    assert universe.title(0) == "" and universe.subtitle(0) == ""
    assert "10" in universe.subtitle(10)


def test_select_filters_by_market_cap():
    u = Universe({"A": 2e9, "B": 5e8, "C": 1e12}, min_cap_billions=1)
    last = pd.Series({"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0})
    assert u.min_cap_usd == 1e9
    assert u.select(["A", "B", "C", "D"], last) == ["A", "C"]      # B es muy chica; D no tiene acciones conocidas


def test_select_ignores_missing_prices_and_unknown_shares():
    u = Universe({"A": 1e12, "E": 1e12}, min_cap_billions=1)
    last = pd.Series({"A": 1.0, "D": 1.0, "E": float("nan")})
    assert u.select(["A", "D", "E"], last) == ["A"]


def test_universe_builder_shares_what_it_downloads_with_the_run(conn, settings, monkeypatch):
    from top3 import workflow
    calls = []
    monkeypatch.setattr(workflow, "ensure_shares",
                        lambda c, tickers, use_cache, s, known=None: (calls.append(dict(known)), {t: 1e9 for t in tickers})[1])
    known = {}
    builder = workflow.UniverseBuilder(conn, pd.DataFrame(columns=["A", "B"]), False, settings, known)
    assert builder(10).shares == {"A": 1e9, "B": 1e9}
    assert known == {"A": 1e9, "B": 1e9} and calls == [{}]
    assert builder(200).min_cap_billions == 200 and len(calls) == 1      # no vuelve a pedir
    assert builder(0) is None


def test_select_matches_the_element_by_element_definition():
    import numpy as np
    rng = np.random.default_rng(3)
    tickers = [f"T{i:03d}" for i in range(300)]
    shares = {t: float(rng.integers(1, 10) * 1e8) for t in tickers[:250]}        # 50 sin acciones conocidas
    shares["T000"] = float("nan")
    prices = pd.Series(rng.uniform(1, 500, 300), index=tickers)
    prices[rng.choice(tickers, 30, replace=False)] = np.nan                       # 30 sin precio
    for cap in (0.5, 10, 100):
        u = Universe(shares, cap)
        expected = [t for t in tickers if t in shares and pd.notna(prices[t]) and prices[t] * shares[t] >= u.min_cap_usd]
        assert u.select(tickers, prices) == expected
    assert u.select([], prices) == []
    extra = prices.copy()
    extra["OTRO"] = 1.0                                                           # etiquetas de más en los precios
    assert Universe(shares, 10).select(tickers[:50], extra) == Universe(shares, 10).select(tickers[:50], prices)
