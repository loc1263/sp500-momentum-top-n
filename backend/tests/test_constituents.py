from top3.constituents import Constituents, parse_tickers


def test_parse_tickers():
    assert parse_tickers("['A', 'BRK.B', ' C ']") == ["A", "BRK-B", "C"]
    assert parse_tickers("") == []


def seed(conn, history, current=(), changes=()):
    conn.executemany("INSERT INTO constituents_history VALUES (?, ?)", history)
    conn.executemany("INSERT INTO constituents_current VALUES (?)", [(t,) for t in current])
    conn.executemany("INSERT INTO index_changes VALUES (?, ?, ?, '')", changes)
    conn.commit()


def test_on_date_and_aliases(conn):
    seed(conn, [("2020-01-01", "A,BK,C"), ("2021-01-01", "A,D")], current=["Z"])
    c = Constituents(conn, {"BK": "BNY"})
    assert c.on_date("2020-06-01") == ["A", "BNY", "C"]
    assert c.on_date("2021-01-01") == ["A", "D"]
    assert c.on_date("2019-01-01") == []            # antes del primer dato
    assert c.on_date("2030-01-01") == ["Z"]         # después del último: lista actual


def test_apply_changes(conn):
    seed(conn, [("2020-01-01", "A,B")], changes=[("2020-06-01", "C", "A"), ("2019-01-01", "X", "B")])
    c = Constituents(conn)
    assert c.dates == ["2020-01-01", "2020-06-01"]   # el cambio anterior al CSV se ignora
    assert c.on_date("2020-07-01") == ["B", "C"]


def test_all_between(conn):
    seed(conn, [("2020-01-01", "A,B"), ("2021-01-01", "C"), ("2022-01-01", "D")], current=["E"])
    c = Constituents(conn)
    assert c.all_between("2020-06-01", "2021-06-01") == ["A", "B", "C", "E"]


def test_without_history_uses_current(conn):
    seed(conn, [], current=["X", "Y"])
    c = Constituents(conn)
    assert c.on_date("2024-01-01") == ["X", "Y"]
    assert c.all_between("2020-01-01", "2024-01-01") == ["X", "Y"]
