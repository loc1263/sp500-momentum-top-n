import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import top3_etf
from top3 import etf

ROOT = Path(__file__).resolve().parents[1]


def prices(days=300, **drifts):
    """Series con retornos diarios alternados +-vol alrededor de `drift`: precio, deriva y volatilidad conocidos."""
    idx = pd.bdate_range(end="2024-12-31", periods=days)
    cols = {}
    for name, (drift, vol) in drifts.items():
        rets = np.where(np.arange(days) % 2 == 0, drift + vol, drift - vol)
        cols[name] = 100 * np.cumprod(1 + rets)
    return pd.DataFrame(cols, index=idx)


def test_score_rewards_return_per_unit_of_risk():
    # misma deriva, distinta volatilidad: el de menos riesgo rankea primero
    p = prices(CALM=(0.001, 0.002), WILD=(0.001, 0.02), DOWN=(-0.001, 0.002))
    scores, excluded = etf.score_etfs(p, [3, 6, 12])
    assert excluded == {}
    assert list(scores.index) == ["CALM", "WILD", "DOWN"]
    assert list(scores["rank"]) == [1, 2, 3]
    assert scores.loc["CALM", "score"] > scores.loc["WILD", "score"] > 0 > scores.loc["DOWN", "score"]


def test_score_matches_the_definition():
    p = prices(A=(0.001, 0.01))
    scores, _ = etf.score_etfs(p, [3, 12])
    ratios = []
    for h in (3, 12):
        w = p["A"].tail(h * 21 + 1)
        vol = w.pct_change().dropna().std() * math.sqrt(252) * math.sqrt(h / 12)
        ratios.append((w.iloc[-1] / w.iloc[0] - 1) / vol)
    assert scores.loc["A", "score"] == pytest.approx(sum(ratios) / 2)
    assert scores.loc["A", "ret_3"] == pytest.approx(p["A"].iloc[-1] / p["A"].iloc[-64] - 1)


def test_risk_free_reference_is_subtracted_so_cash_like_etfs_do_not_win():
    p = prices(CASH=(0.0002, 0.0001), STOCK=(0.0008, 0.01))
    plain, _ = etf.score_etfs(p, [3, 6, 12])
    assert plain.index[0] == "CASH"            # sin referencia, lo casi sin riesgo gana
    ranked, _ = etf.score_etfs(p, [3, 6, 12], risk_free="CASH")
    assert ranked.index[0] == "STOCK" and ranked.attrs["risk_free"] == "CASH"
    assert ranked.loc["CASH", "score"] == pytest.approx(0)  # la referencia queda en cero


def test_unavailable_risk_free_falls_back_to_no_reference():
    scores, _ = etf.score_etfs(prices(A=(0.001, 0.01)), [3], risk_free="NOPE")
    assert scores.attrs["risk_free"] is None


def test_etfs_with_gaps_or_short_history_are_excluded():
    p = prices(A=(0.001, 0.01), B=(0.002, 0.01), C=(0.003, 0.01))
    p.loc[p.index[-30], "B"] = np.nan       # hueco dentro de la ventana
    p.loc[p.index[:100], "C"] = np.nan      # empezó a cotizar hace poco (no cubre 12 meses)
    scores, excluded = etf.score_etfs(p, [3, 12])
    assert list(scores.index) == ["A"] and set(excluded) == {"B", "C"}


def test_not_enough_rows_for_the_longest_horizon_excludes_everything():
    scores, excluded = etf.score_etfs(prices(days=100, A=(0.001, 0.01)), [3, 12])
    assert scores.empty and set(excluded) == {"A"}


def test_flat_prices_have_no_score():
    p = prices(A=(0.001, 0.01))
    p["FLAT"] = 50.0
    scores, excluded = etf.score_etfs(p, [3])
    assert "FLAT" not in scores.index and excluded["FLAT"] == "volatilidad nula"


def test_trend_columns():
    scores, _ = etf.score_etfs(prices(UP=(0.002, 0.005), DOWN=(-0.002, 0.005)), [3, 12])
    assert scores.loc["UP", "sma_dist"] > 0 > scores.loc["DOWN", "sma_dist"]
    assert scores.loc["DOWN", "max_dd"] < scores.loc["UP", "max_dd"] <= 0


def test_load_universe(tmp_path):
    f = tmp_path / "e.csv"
    f.write_text("ticker,name,category\nvti , Total ,Amplio\nVTI,Dup,X\n,Sin ticker,X\nBND,Bonos,Bonos\n", encoding="utf-8")
    df = etf.load_universe(f)
    assert list(df["ticker"]) == ["VTI", "BND"] and df.loc[0, "name"] == "Total"


def test_load_universe_errors(tmp_path):
    with pytest.raises(SystemExit, match="TOP-ETF-001"):
        etf.load_universe(tmp_path / "no_existe.csv")
    bad = tmp_path / "bad.csv"
    bad.write_text("ticker,name\nVTI,Total\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="category"):
        etf.load_universe(bad)
    empty = tmp_path / "empty.csv"
    empty.write_text("ticker,name,category\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="vacía"):
        etf.load_universe(empty)


def test_the_shipped_etf_list_is_sane():
    df = etf.load_universe(ROOT / "vanguard_etfs.csv")
    assert len(df) > 50 and df["ticker"].is_unique
    assert (df["name"] != "").all() and (df["category"] != "").all()
    assert "VUSB" in set(df["ticker"])  # es la referencia libre de riesgo por defecto


def _run(cfg, tmp_path, monkeypatch, data, **kwargs):
    cfg["data"]["db_path"] = str(tmp_path / "t.db")
    cfg["output"]["dir"] = str(tmp_path / "out")
    csv = tmp_path / "e.csv"
    csv.write_text("ticker,name,category\n" + "\n".join(f"{t},{t} ETF,Cat" for t in data.columns), encoding="utf-8")
    cfg["etf"]["csv"] = str(csv)
    monkeypatch.setattr(etf, "download_recent", lambda tickers, start, end, batch_size: data[tickers])
    return etf.run_etf(cfg, **kwargs)


def test_run_etf_saves_ranking_and_writes_report(cfg, tmp_path, monkeypatch, capsys):
    import sqlite3
    cfg["etf"]["risk_free_ticker"] = ""
    data = prices(A=(0.002, 0.005), B=(0.0005, 0.005), C=(-0.001, 0.005))
    html = _run(cfg, tmp_path, monkeypatch, data, top_n=2).read_text(encoding="utf-8")
    assert "Ranking global" in html and "A ETF" in html and "primera corrida guardada" in html
    out = capsys.readouterr().out
    assert "ETFs DE VANGUARD" in out and out.index("A ") < out.index("B ")
    db = sqlite3.connect(cfg["data"]["db_path"])
    rows = db.execute("SELECT ticker, rank, returns FROM etf_scores ORDER BY rank").fetchall()
    assert [r[0] for r in rows] == ["A", "B", "C"] and set(json.loads(rows[0][2])) == {"3", "6", "12"}


def test_run_etf_twice_replaces_and_reports_changes_against_previous_day(cfg, tmp_path, monkeypatch):
    import sqlite3
    cfg["etf"]["risk_free_ticker"] = ""
    data = prices(A=(0.002, 0.005), B=(0.0005, 0.005), C=(-0.001, 0.005))
    _run(cfg, tmp_path, monkeypatch, data.iloc[:-1], top_n=1)            # ayer: A primero
    swapped = data.copy()
    swapped["B"] = swapped["B"].iloc[0] * np.cumprod(np.r_[1, np.full(len(data) - 1, 1.01)])  # hoy B sube fuerte
    html = _run(cfg, tmp_path, monkeypatch, swapped, top_n=1).read_text(encoding="utf-8")
    assert "entran B; salen A" in html
    _run(cfg, tmp_path, monkeypatch, swapped, top_n=1)                    # repetir no duplica
    db = sqlite3.connect(cfg["data"]["db_path"])
    assert db.execute("SELECT COUNT(*) FROM etf_scores").fetchone()[0] == 6  # 3 ETFs x 2 días


def test_run_etf_as_of_truncates_the_data_and_is_not_saved(cfg, tmp_path, monkeypatch):
    cfg["etf"]["risk_free_ticker"] = ""
    data = prices(A=(0.002, 0.005), B=(0.0005, 0.005))
    as_of = data.index[-20].date().isoformat()
    path = _run(cfg, tmp_path, monkeypatch, data, as_of=as_of)
    assert path.name.startswith(f"top3_etf_asof_{as_of}_") and as_of in path.read_text(encoding="utf-8")
    assert "no se guarda" in path.read_text(encoding="utf-8")
    from top3.db import open_db
    db = open_db(cfg["data"]["db_path"])           # el historial real queda limpio
    assert db.execute("SELECT COUNT(*) FROM etf_scores").fetchone()[0] == 0
    _run(cfg, tmp_path, monkeypatch, data)         # y la corrida de hoy no se compara con la consulta pasada
    assert db.execute("SELECT COUNT(DISTINCT as_of) FROM etf_scores").fetchone()[0] == 1


def test_run_etf_warns_for_missing_prices_and_exclusions(cfg, tmp_path, monkeypatch, caplog):
    cfg["etf"]["risk_free_ticker"] = ""
    data = prices(A=(0.002, 0.005), B=(0.0005, 0.005))
    data["NEW"] = np.nan
    data.loc[data.index[-50:], "NEW"] = 100.0     # ETF nuevo: poca historia
    data["GONE"] = np.nan                          # sin precios en Yahoo
    _run(cfg, tmp_path, monkeypatch, data)
    assert "TOP-ETF-002" in caplog.text and "GONE" in caplog.text
    assert "TOP-ETF-003" in caplog.text and "NEW" in caplog.text


def test_run_etf_without_risk_free_in_list_warns(cfg, tmp_path, monkeypatch, caplog):
    cfg["etf"]["risk_free_ticker"] = "NOPE"
    _run(cfg, tmp_path, monkeypatch, prices(A=(0.002, 0.005), B=(0.0005, 0.005)))
    assert "TOP-ETF-005" in caplog.text


def test_run_etf_with_nothing_rankable_stops_with_an_error(cfg, tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="TOP-ETF-004"):
        _run(cfg, tmp_path, monkeypatch, prices(days=50, A=(0.002, 0.005)))


def test_etf_args():
    args = top3_etf.parse_args(["--as-of", "2025-06-30", "--top-n", "5", "--csv", "x.csv"])
    assert (args.as_of, args.top_n, args.csv) == ("2025-06-30", 5, "x.csv")
