from datetime import date

from top3 import rotation
from top3.repo import picks as picks_store


def add(conn, as_of, tickers, months=4, cap=None):
    conn.executemany("INSERT INTO actual_picks VALUES (?,?,?,?,?,?,?,?,?)",
                     [(f"{as_of}T10:00:00", as_of, months, cap, i, t, 0.1, 1.0, 1e9)
                      for i, t in enumerate(tickers, 1)])
    conn.commit()


def test_previous_picks_is_the_latest_before_as_of(conn):
    add(conn, "2024-01-01", ["A", "B"])
    add(conn, "2024-02-01", ["B", "C"])
    add(conn, "2024-03-01", ["C", "D"])
    assert picks_store.previous_picks(conn, "2024-03-01", 4, None) == ("2024-02-01", ["B", "C"])


def test_previous_picks_ignores_other_universe_and_term(conn):
    add(conn, "2024-01-01", ["A"], cap=200.0)
    add(conn, "2024-01-01", ["B"], months=6)
    assert picks_store.previous_picks(conn, "2024-02-01", 4, None) == (None, [])
    assert picks_store.previous_picks(conn, "2024-02-01", 4, 200.0) == ("2024-01-01", ["A"])


def test_diff_picks():
    assert rotation.diff_picks(["A", "B", "C"], ["C", "D", "A"]) == {
        "entered": ["D"], "exited": ["B"], "kept": ["C", "A"]}


def test_anchor_date_is_the_first_run(conn):
    add(conn, "2024-02-15", ["A"])
    add(conn, "2024-01-10", ["A"])
    assert picks_store.anchor_date(conn, 4, None) == "2024-01-10"
    assert picks_store.anchor_date(conn, 6, None) is None


def test_next_rebalance_steps_from_the_anchor_month():
    assert rotation.next_rebalance("2024-01-10", 4, date(2024, 2, 1)) == date(2024, 5, 1)
    assert rotation.next_rebalance("2024-01-10", 4, date(2024, 5, 2)) == date(2024, 9, 1)


def test_next_rebalance_today_counts_when_it_is_rebalance_day():
    assert rotation.next_rebalance("2024-01-10", 4, date(2024, 5, 1)) == date(2024, 5, 1)


def test_describe_first_run():
    lines = rotation.describe(None, rotation.diff_picks([], ["A"]), "2024-01-10", 4, date(2024, 2, 1))
    assert "primera corrida" in lines[0]
    assert "2024-05-01" in lines[1]


def test_describe_changes_and_no_changes():
    changed = rotation.describe("2024-01-01", rotation.diff_picks(["A", "B"], ["B", "C"]), None, 4, date(2024, 2, 1))
    assert changed == ["Cambios vs. 2024-01-01: entran C; salen A; se mantienen B."]
    same = rotation.describe("2024-01-01", rotation.diff_picks(["A"], ["A"]), None, 4, date(2024, 2, 1))
    assert "ninguno" in same[0]
