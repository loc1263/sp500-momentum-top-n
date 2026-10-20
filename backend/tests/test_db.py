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
