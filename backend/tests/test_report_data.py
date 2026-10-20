import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pandas as pd

from top3.analysis import save_run
from top3.api import ReportCache, make_handler
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


def test_report_cache_rebuilds_only_when_results_change(tmp_path, cfg):
    cfg = make_cfg(cfg, tmp_path)
    from top3.db import open_db
    conn = open_db(cfg["data"]["db_path"])
    seed_run(conn, 4, 0)
    cache = ReportCache(cfg)
    first = cache.get()
    assert cache.get() is first                      # sin cambios: la misma respuesta ya armada
    seed_run(conn, 4, 1)
    conn.close()
    assert cache.get() is not first                  # una corrida nueva invalida la caché


def test_api_endpoints(tmp_path, cfg):
    cfg = make_cfg(cfg, tmp_path)
    from top3.db import open_db
    conn = open_db(cfg["data"]["db_path"])
    seed_run(conn, 4, 0)
    conn.close()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cfg))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_port}"
    try:
        with urllib.request.urlopen(base + "/api/health") as r:
            assert json.load(r) == {"status": "ok"}
        with urllib.request.urlopen(base + "/api/report") as r:
            assert r.headers["Content-Type"].startswith("application/json")
            assert json.load(r)["backtest"][0]["periods"][0]["terms"][0]["calendars"][0]["offset"] == 0
        try:
            urllib.request.urlopen(base + "/nada")
            raise AssertionError("debería dar 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        httpd.shutdown()
        httpd.server_close()
