from datetime import date, timedelta

from top3.db import fetched_today, get_meta, set_meta


def test_open_db_creates_parent_and_schema(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"meta", "prices", "constituents_history", "runs", "equity", "actual_picks"} <= names


def test_meta_and_fetched_today(conn):
    assert get_meta(conn, "k") is None
    set_meta(conn, "k", date.today().isoformat())
    assert fetched_today(conn, "k")
    set_meta(conn, "k", (date.today() - timedelta(days=1)).isoformat())
    assert not fetched_today(conn, "k")


def add_run(conn, run_at, params="p"):
    cur = conn.execute("INSERT INTO runs (run_at, params) VALUES (?, ?)", (run_at, params))
    conn.execute("INSERT INTO selections (run_id, rebalance_date, rank, ticker, return_lookback) "
                 "VALUES (?, '2024-01-01', 1, 'A', 0.1)", (cur.lastrowid,))
    conn.execute("INSERT INTO equity (run_id, date, capital) VALUES (?, '2024-01-01', 1000)", (cur.lastrowid,))
    conn.commit()
    return cur.lastrowid


def test_prune_runs_drops_old_days_and_same_day_duplicates(conn):
    from top3.db import prune_runs
    old = add_run(conn, "2024-01-01T10:00:00")
    first = add_run(conn, "2024-01-09T10:00:00")
    last = add_run(conn, "2024-01-09T11:00:00")  # reemplaza a la anterior del mismo día
    other = add_run(conn, "2024-01-09T11:00:00", params="q")
    assert prune_runs(conn, 3) == 2
    assert {r[0] for r in conn.execute("SELECT id FROM runs")} == {last, other}
    for table in ("selections", "equity"):
        assert {r[0] for r in conn.execute(f"SELECT run_id FROM {table}")} == {last, other}
    assert old not in {r[0] for r in conn.execute("SELECT id FROM runs")} and first != last


def test_prune_runs_keeps_the_last_days_counted_from_the_latest_run(conn):
    from top3.db import prune_runs
    add_run(conn, "2024-01-06T10:00:00")   # 4.º día contando desde el último: fuera con keep_days=3
    kept_a = add_run(conn, "2024-01-08T10:00:00", params="a")
    kept_b = add_run(conn, "2024-01-09T10:00:00", params="b")
    assert prune_runs(conn, 3) == 1
    assert {r[0] for r in conn.execute("SELECT id FROM runs")} == {kept_a, kept_b}


def test_prune_runs_never_removes_the_latest_day(conn):
    from top3.db import prune_runs
    keep = add_run(conn, "2024-01-09T10:00:00")
    assert prune_runs(conn, 0) == 0
    assert [r[0] for r in conn.execute("SELECT id FROM runs")] == [keep]


def test_prune_runs_on_empty_database(conn):
    from top3.db import prune_runs
    assert prune_runs(conn, 7) == 0


def sweep_params(**extra):
    import json
    return json.dumps({"sweep_months": 4, "offset_months": 0, "min_cap_billions": None,
                       "backtest": {"backtest_years": 5}, **extra})


def test_prune_runs_dedupes_by_report_key_not_by_exact_params(conn):
    from top3.db import prune_runs
    add_run(conn, "2024-01-09T10:00:00", params=sweep_params(data={"runs_keep_days": None}))  # config vieja
    new = add_run(conn, "2024-01-09T11:00:00", params=sweep_params(data={"runs_keep_days": 7}))
    other_term = add_run(conn, "2024-01-09T11:00:00", params=sweep_params(sweep_months=6))
    other_universe = add_run(conn, "2024-01-09T11:00:00", params=sweep_params(min_cap_billions=200.0))
    assert prune_runs(conn, 7) == 1
    assert {r[0] for r in conn.execute("SELECT id FROM runs")} == {new, other_term, other_universe}


def test_report_and_prune_use_the_same_run_key():
    from top3.db import run_key
    assert run_key(json_loads(sweep_params())) == (0.0, 5.0, 4, 0, 0)
    assert run_key(json_loads(sweep_params(skip_months=1))) == (0.0, 5.0, 4, 0, 1)
    assert run_key({"months": 4}) is None


def json_loads(text):
    import json
    return json.loads(text)


def test_maybe_prune_runs_prunes_every_time_but_vacuums_once_a_day(conn, monkeypatch):
    from top3 import db
    from top3.db import get_meta, maybe_prune_runs
    add_run(conn, "2020-01-01T10:00:00", params="a")
    add_run(conn, "2024-01-09T10:00:00", params="b")
    assert maybe_prune_runs(conn, 1) == 1
    assert get_meta(conn, "runs_vacuumed") == db.date.today().isoformat()
    add_run(conn, "2020-01-01T10:00:00", params="c")  # otra corrida el mismo día: se limpia igual
    assert maybe_prune_runs(conn, 1) == 1
    assert maybe_prune_runs(conn, 1) == 0
