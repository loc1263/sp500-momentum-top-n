from datetime import date, timedelta

from top3 import cleanup
from top3.db import open_db


def touch(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text("x", encoding="utf-8")
    return path


def test_old_reports_are_deleted_counting_days_from_the_newest_report(tmp_path):
    old = touch(tmp_path / "actual", "top3_actual_20261010.html")
    edge = touch(tmp_path / "backtest", "top3_sweep_10y_20261018.html")      # 7 días contando el 24 como el primero
    newest = touch(tmp_path / "actual", "top3_actual_largecap_20261024.html")
    other = touch(tmp_path, "notas.txt")                                     # lo que no es un reporte no se toca
    assert cleanup.prune_output_files(tmp_path, 7) == [old]
    assert not old.exists() and edge.exists() and newest.exists() and other.exists()


def test_the_latest_day_is_kept_even_when_everything_is_older_than_the_limit(tmp_path):
    a = touch(tmp_path, "top3_actual_20240101.html")
    assert cleanup.prune_output_files(tmp_path, 7) == [] and a.exists()
    assert cleanup.prune_output_files(tmp_path / "no_existe", 7) == []


def test_stale_data_is_deleted_but_fresh_data_and_the_history_window_stay(cfg, conn):
    today = date(2026, 10, 24)
    days = lambda n: (today - timedelta(days=n)).isoformat()          # noqa: E731
    conn.executemany("INSERT INTO prices VALUES (?, ?, 1.0)", [("A", days(10)), ("A", days(365 * 13))])
    conn.executemany("INSERT INTO shares VALUES (?, 1.0, ?)", [("OLD", days(cfg.data.shares_ttl_days + 1)), ("NEW", days(1))])
    conn.executemany("INSERT INTO fundamentals VALUES (?, ?, '{}')",
                     [("OLD", days(cfg.quant.fundamentals_ttl_days + 1)), ("NEW", days(1))])
    conn.executemany("INSERT INTO no_data_tickers VALUES (?, ?)",
                     [("GONE", days(cfg.data.no_data_ttl_days + 1)), ("RECENT", days(1))])
    conn.execute("INSERT INTO actual_picks VALUES (?, ?, 4, NULL, 1, 'A', 0.1, 1.0, NULL)", (days(100), days(100)))
    conn.execute("INSERT INTO etf_scores VALUES (?, ?, 1, 'VOO', 1, 1, 1, 1, '{}')", (days(100), days(100)))
    rows = cleanup.prune_stale_data(conn, cfg, today)
    assert list(rows.values()) == [1, 1, 1, 1]
    assert [r[0] for r in conn.execute("SELECT date FROM prices")] == [days(10)]
    assert [r[0] for r in conn.execute("SELECT ticker FROM shares")] == ["NEW"]
    assert [r[0] for r in conn.execute("SELECT ticker FROM fundamentals")] == ["NEW"]
    assert [r[0] for r in conn.execute("SELECT ticker FROM no_data_tickers")] == ["RECENT"]
    for table in ("actual_picks", "etf_scores"):                       # el historial del Top y de los ETFs no se toca
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1


def test_run_cleanup_does_everything_and_reports(cfg, tmp_path):
    cfg.data.db_path = str(tmp_path / "t.db")
    cfg.output.dir = str(tmp_path / "out")
    old = touch(tmp_path / "out" / "actual", "top3_actual_20240101.html")
    touch(tmp_path / "out" / "actual", f"top3_actual_{date.today():%Y%m%d}.html")
    conn = open_db(cfg.data.db_path)
    conn.execute("INSERT INTO prices VALUES ('A', '2000-01-03', 1.0)")
    conn.commit()
    conn.close()
    report = cleanup.run_cleanup(cfg)
    assert report.files == [old] and report.rows["precios fuera de la ventana"] == 1 and not report.empty
    assert cleanup.run_cleanup(cfg).empty
