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
