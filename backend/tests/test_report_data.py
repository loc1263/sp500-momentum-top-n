import json
import pandas as pd
import pytest

from top3.analysis import save_run
from top3.engine import BacktestResult
from top3.report_data import _actual, build_report, export_report


def seed_run(conn, months, offset, cap=None, years=5):
    equity = pd.Series([1000.0, 1100.0, 1210.0], index=pd.to_datetime(["2024-01-01", "2024-05-01", "2024-09-01"]))
    history = [{"date": "2024-01-01", "returns": {"AAA": 0.5, "BBB": 0.4}},
               {"date": "2024-05-01", "returns": {"CCC": 0.3, "AAA": 0.2}}]
    save_run(conn, {"sweep_months": months, "offset_months": offset, "min_cap_billions": cap,
                    "backtest": {"backtest_years": years}},
             "2024-01-01", "2024-09-01", BacktestResult(equity, history, 1210.0, 21.0, 30.0))


def test_build_report_groups_latest_runs(conn, cfg):
    seed_run(conn, 4, 0)
    seed_run(conn, 4, 1)
    seed_run(conn, 4, 0)            # repetida: gana la última
    seed_run(conn, 6, 0, cap=10)
    seed_run(conn, 4, 0, years=10)
    seed_run(conn, 4, 0, years=7)   # período fuera de [backtest] periods_years: se ignora
    report = build_report(conn, cfg)

    assert [u["min_cap_billions"] for u in report["backtest"]] == [None, 10]
    full = report["backtest"][0]
    assert full["label"] == "índice completo"
    assert [p["years"] for p in full["periods"]] == [5, 10]
    assert full["periods"][0]["start_date"] == "2024-01-01" and full["periods"][0]["end_date"] == "2024-09-01"
    assert report["settings"]["periods_years"] == [5, 10]
    term = full["periods"][0]["terms"][0]
    assert term["months"] == 4 and [c["offset"] for c in term["calendars"]] == [0, 1]
    assert term["summary"]["calendars"] == 2
    cal = term["calendars"][0]
    assert cal["total_return"] == 0.21 and cal["cagr"] == 0.30
    assert [p["ticker"] for p in cal["history"][0]["picks"]] == ["AAA", "BBB"]
    assert cal["history"][1]["capital"] == 1100.0 and abs(cal["history"][1]["gain"] - 0.1) < 1e-9
    assert report["actual"] == []


def test_build_report_with_empty_database(conn, cfg):
    report = build_report(conn, cfg)
    assert report["run_date"] is None and report["backtest"] == [] and report["actual"] == []


def test_actual_picks(conn):
    conn.executemany("INSERT INTO actual_picks VALUES (?,?,?,?,?,?,?,?,?)", [
        ("2024-09-01T10:00:00", "2024-08-30", 4, None, 1, "OLD", 0.1, 1.0, 1e9),
        ("2024-09-01T11:00:00", "2024-08-30", 4, None, 1, "AAA", 0.9, 10.0, 5e9),
        ("2024-09-01T11:00:00", "2024-08-30", 4, None, 2, "BBB", 0.8, 20.0, None),
        ("2024-09-01T11:00:00", "2024-08-30", 4, 200.0, 1, "MEGA", 0.5, 30.0, 3e11)])
    conn.commit()
    result = _actual(conn)
    assert [a["label"] for a in result] == ["índice completo", "mega-cap"]
    assert [p["ticker"] for p in result[0]["picks"]] == ["AAA", "BBB"]
    assert result[0]["as_of"] == "2024-08-30"


def make_cfg(cfg, tmp_path):
    cfg["data"]["db_path"] = str(tmp_path / "t.db")
    cfg["output"]["frontend_data"] = str(tmp_path / "x" / "report.json")
    return cfg


def test_export_report_writes_json(tmp_path, cfg):
    cfg = make_cfg(cfg, tmp_path)
    from top3.db import open_db
    conn = open_db(cfg["data"]["db_path"])
    seed_run(conn, 4, 0)
    conn.close()
    path = export_report(cfg)
    assert json.loads(path.read_text(encoding="utf-8"))["backtest"][0]["periods"][0]["terms"][0]["months"] == 4


def test_actual_includes_rotation(conn):
    from datetime import date
    conn.executemany("INSERT INTO actual_picks VALUES (?,?,?,?,?,?,?,?,?)", [
        ("2024-08-29T10:00:00", "2024-08-29", 4, None, 1, "AAA", 0.9, 10.0, None),
        ("2024-08-29T10:00:00", "2024-08-29", 4, None, 2, "OLD", 0.8, 10.0, None),
        ("2024-08-30T10:00:00", "2024-08-30", 4, None, 1, "AAA", 0.9, 10.0, None),
        ("2024-08-30T10:00:00", "2024-08-30", 4, None, 2, "NEW", 0.8, 10.0, None)])
    conn.commit()
    (item,) = _actual(conn, today=date(2024, 9, 5))
    assert item["previous_as_of"] == "2024-08-29"
    assert item["changes"] == {"entered": ["NEW"], "exited": ["OLD"], "kept": ["AAA"]}
    assert item["anchor"] == "2024-08-29"
    assert item["next_rebalance"] == "2024-12-01"


def test_actual_without_previous_run_has_no_changes(conn):
    from datetime import date
    conn.execute("INSERT INTO actual_picks VALUES (?,?,?,?,?,?,?,?,?)",
                 ("2024-08-30T10:00:00", "2024-08-30", 4, None, 1, "AAA", 0.9, 10.0, None))
    conn.commit()
    (item,) = _actual(conn, today=date(2024, 9, 5))
    assert item["previous_as_of"] is None and item["changes"] is None


def _add_etf(conn, as_of, ranking):
    conn.executemany("INSERT INTO etf_scores VALUES (?,?,?,?,?,?,?,?,?)", [
        (f"{as_of}T10:00:00", as_of, rank, ticker, 2.0 - rank / 10, 0.1, -0.05, 0.03, '{"3": 0.05, "12": 0.2}')
        for rank, ticker in enumerate(ranking, 1)])
    conn.commit()


def test_etf_ranking_in_the_report(conn, cfg, tmp_path):
    from top3.report_data import _etf
    csv = tmp_path / "e.csv"
    csv.write_text("ticker,name,category\nVTI,Total Stock Market,Amplio\nVUSB,Ultra-Short Bond,Bonos\n", encoding="utf-8")
    cfg["etf"].update(csv=str(csv), top_n=1, risk_free_ticker="VUSB")
    assert _etf(conn, cfg) is None
    _add_etf(conn, "2024-08-29", ["VTI", "VUSB"])
    _add_etf(conn, "2024-08-30", ["VUSB", "VTI"])
    etf = _etf(conn, cfg)
    assert etf["as_of"] == "2024-08-30" and etf["horizons"] == [3, 12] and etf["risk_free"] == "VUSB"
    assert [r["ticker"] for r in etf["rows"]] == ["VUSB", "VTI"]
    assert etf["rows"][1] == {"rank": 2, "ticker": "VTI", "name": "Total Stock Market", "category": "Amplio",
                              "score": pytest.approx(1.8), "vol": 0.1, "max_dd": -0.05, "sma_dist": 0.03,
                              "returns": {"3": 0.05, "12": 0.2}}
    assert etf["previous_as_of"] == "2024-08-29"
    assert etf["changes"] == {"entered": ["VUSB"], "exited": ["VTI"], "kept": []}   # top_n = 1


def test_etf_report_survives_a_missing_csv(conn, cfg, tmp_path):
    from top3.report_data import _etf
    cfg["etf"].update(csv=str(tmp_path / "no_existe.csv"), risk_free_ticker="")
    _add_etf(conn, "2024-08-30", ["VTI"])
    etf = _etf(conn, cfg)
    assert etf["rows"][0]["name"] == "" and etf["risk_free"] is None and etf["changes"] is None


def test_build_report_separates_the_skip_month_model(conn, cfg):
    seed_run(conn, 4, 0)
    save_run(conn, {"sweep_months": 4, "offset_months": 0, "min_cap_billions": None, "skip_months": 1,
                    "backtest": {"backtest_years": 5}},
             "2024-01-01", "2024-09-01",
             BacktestResult(pd.Series([1000.0, 1500.0], index=pd.to_datetime(["2024-01-01", "2024-09-01"])),
                            [{"date": "2024-01-01", "returns": {"ZZZ": 0.1}}], 1500.0, 50.0, 60.0))
    report = build_report(conn, cfg)
    base = report["backtest"][0]["periods"][0]["terms"][0]["calendars"][0]
    skip = report["backtest_skip"][0]["periods"][0]["terms"][0]["calendars"][0]
    assert base["final_capital"] == 1210.0 and skip["final_capital"] == 1500.0
    assert skip["history"][0]["picks"][0]["ticker"] == "ZZZ"


def test_halves_split_the_period_at_its_midpoint():
    from top3.report_data import _halves
    # 4 años: capital x2 en la primera mitad y x1,5 en la segunda
    cal = {"offset": 0, "start_date": "2020-01-01", "end_date": "2024-01-01",
           "equity": [{"date": "2020-01-01", "capital": 1000.0}, {"date": "2022-01-01", "capital": 2000.0},
                      {"date": "2024-01-01", "capital": 3000.0}]}
    halves = _halves([cal])
    assert halves["split"] == "2021-12-31"      # mitad exacta del período
    assert halves["first"] == pytest.approx(2 ** 0.5 - 1, abs=0.01)
    assert halves["second"] == pytest.approx(1.5 ** 0.5 - 1, abs=0.01)


def test_halves_leave_a_too_short_half_empty():
    from top3.report_data import _halves
    cal = {"offset": 0, "start_date": "2024-01-01", "end_date": "2024-03-01",
           "equity": [{"date": "2024-01-01", "capital": 1000.0}, {"date": "2024-03-01", "capital": 1100.0}]}
    assert _halves([cal])["first"] is None


def seed_picks(conn, as_of, rows, run_at=None):
    conn.executemany("INSERT INTO actual_picks VALUES (?,?,?,?,?,?,?,?,?)",
                     [(run_at or as_of + "T10:00:00", as_of, 4, None, rank, t, 0.5, price, 1e9)
                      for rank, (t, price) in enumerate(rows, 1)])


def test_tracking_measures_open_and_closed_selections(conn):
    from top3.report_data import _tracking
    conn.executemany("INSERT INTO prices VALUES (?,?,?)", [
        ("AAA", "2024-01-02", 10.0), ("AAA", "2024-05-02", 12.0), ("AAA", "2024-07-01", 15.0),
        ("BBB", "2024-01-02", 20.0), ("BBB", "2024-05-02", 18.0), ("BBB", "2024-07-01", 18.0)])
    seed_picks(conn, "2024-01-02", [("AAA", 10.0), ("BBB", 20.0)])
    seed_picks(conn, "2024-06-03", [("AAA", 14.0), ("BBB", 20.0)])
    conn.commit()
    closed, opened = _tracking(conn, 0, 4)[::-1]
    assert opened["as_of"] == "2024-06-03" and opened["closed"] is False
    assert opened["return"] == pytest.approx((15 / 14 - 1 + 18 / 20 - 1) / 2)
    assert closed["as_of"] == "2024-01-02" and closed["closed"] is True and closed["until"] == "2024-05-02"
    assert closed["return"] == pytest.approx((0.2 - 0.1) / 2)       # solo hasta que terminó la tenencia de 4 meses


def test_tracking_skips_the_selection_of_the_last_day_and_empty_data(conn):
    from top3.report_data import _tracking
    assert _tracking(conn, 0, 4) == []                               # sin precios
    conn.execute("INSERT INTO prices VALUES ('AAA', '2024-01-02', 10.0)")
    seed_picks(conn, "2024-01-02", [("AAA", 10.0)])
    conn.commit()
    assert _tracking(conn, 0, 4) == []                               # todavía no pasó ni un día
