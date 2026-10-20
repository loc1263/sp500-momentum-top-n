from datetime import date, timedelta

import pandas as pd
import pytest

from top3 import prices as prices_module
from top3.db import fetched_today, get_meta, set_meta
from top3.prices import ensure_prices, load_prices


def long(rows):
    return pd.DataFrame(rows, columns=["ticker", "date", "close"])


@pytest.fixture
def fetch(monkeypatch):
    """Reemplaza la descarga a Yahoo: `fetch.data` es lo que "devuelve" y `fetch.calls` lo que se pidió."""
    class Fake:
        data = long([])

        def __init__(self):
            self.calls = []

        def __call__(self, tickers, start, end, batch_size):
            self.calls.append((sorted(tickers), start, end))
            d = self.data
            return d[d["ticker"].isin(tickers) & (d["date"] >= start)].reset_index(drop=True), []

    fake = Fake()
    monkeypatch.setattr(prices_module, "fetch_prices", fake)
    return fake


def stored(conn):
    return {(t, d): c for t, d, c in conn.execute("SELECT ticker, date, close FROM prices")}


def seed(conn, rows, start="2024-01-01", fetched=None):
    prices_module._save_prices(conn, long(rows))
    set_meta(conn, "prices_start", start)
    set_meta(conn, "prices_fetched", fetched or (date.today() - timedelta(days=1)).isoformat())
    conn.commit()


def test_load_prices_pivot(conn):
    conn.executemany("INSERT INTO prices VALUES (?, ?, ?)",
                     [("A", "2024-01-01", 1.0), ("A", "2024-01-02", 2.0), ("B", "2024-01-01", 3.0)])
    conn.commit()
    p = load_prices(conn)
    assert list(p.columns) == ["A", "B"] and p.shape == (2, 2)
    assert pd.isna(p.loc["2024-01-02", "B"])


def test_incremental_only_downloads_missing_days(conn, fetch, settings):
    seed(conn, [("A", "2024-03-01", 10.0), ("A", "2024-03-04", 11.0), ("B", "2024-03-04", 20.0)])
    fetch.data = long([("A", "2024-03-04", 11.0), ("A", "2024-03-05", 12.0),
                       ("B", "2024-03-04", 20.0), ("B", "2024-03-05", 21.0)])
    ensure_prices(conn, ["A", "B"], "2024-01-02", "2024-03-06", True, settings)

    assert len(fetch.calls) == 1
    tickers, since, _ = fetch.calls[0]
    assert tickers == ["A", "B"] and since == "2024-02-26"        # último día (03-04) - 7 de solape
    s = stored(conn)
    assert s[("A", "2024-03-05")] == 12.0 and s[("B", "2024-03-05")] == 21.0
    assert s[("A", "2024-03-01")] == 10.0                          # lo viejo no se toca
    assert fetched_today(conn, "prices_fetched")
    assert get_meta(conn, "prices_start") == "2024-01-01"


def test_new_ticker_gets_full_history(conn, fetch, settings):
    seed(conn, [("A", "2024-03-04", 11.0)])
    fetch.data = long([("A", "2024-03-04", 11.0), ("A", "2024-03-05", 12.0),
                       ("N", "2024-01-02", 5.0), ("N", "2024-03-05", 6.0)])
    ensure_prices(conn, ["A", "N"], "2024-01-02", "2024-03-06", True, settings)

    assert (["N"], "2024-01-02", "2024-03-06") in fetch.calls
    assert ("N", "2024-01-02") in stored(conn)


def test_adjustment_change_refetches_only_that_ticker(conn, fetch, settings):
    seed(conn, [("A", "2024-01-02", 10.0), ("A", "2024-03-04", 11.0),
                ("B", "2024-01-02", 20.0), ("B", "2024-03-04", 22.0)])
    # A pagó un dividendo: todo su historial ajustado cambió; B no
    fetch.data = long([("A", "2024-01-02", 9.5), ("A", "2024-03-04", 10.45), ("A", "2024-03-05", 11.5),
                       ("B", "2024-01-02", 20.0), ("B", "2024-03-04", 22.0), ("B", "2024-03-05", 23.0)])
    ensure_prices(conn, ["A", "B"], "2024-01-02", "2024-03-06", True, settings)

    assert fetch.calls[-1] == (["A"], "2024-01-02", "2024-03-06")  # A completo, B no
    s = stored(conn)
    assert s[("A", "2024-01-02")] == 9.5                            # historial de A reemplazado
    assert s[("B", "2024-01-02")] == 20.0 and s[("B", "2024-03-05")] == 23.0


def test_delisted_ticker_is_not_requested(conn, fetch, settings):
    seed(conn, [("OLD", "2023-01-03", 3.0), ("A", "2024-03-04", 11.0)])
    fetch.data = long([("A", "2024-03-04", 11.0), ("A", "2024-03-05", 12.0)])
    ensure_prices(conn, ["OLD", "A"], "2024-01-02", "2024-03-06", True, settings)
    assert all("OLD" not in c[0] for c in fetch.calls)
    assert ("OLD", "2023-01-03") in stored(conn)


def test_full_download_when_start_is_earlier_than_cache(conn, fetch, settings):
    seed(conn, [("A", "2024-03-04", 11.0)], start="2024-01-01")
    fetch.data = long([("A", "2023-06-01", 8.0), ("A", "2024-03-05", 12.0)])
    ensure_prices(conn, ["A"], "2023-06-01", "2024-03-06", True, settings)
    assert fetch.calls == [(["A"], "2023-06-01", "2024-03-06")]
    assert get_meta(conn, "prices_start") == "2023-06-01"
    assert ("A", "2024-03-04") not in stored(conn)                  # reemplazo completo


def test_no_cache_flag_forces_full_download(conn, fetch, settings):
    seed(conn, [("A", "2024-03-04", 11.0)])
    fetch.data = long([("A", "2024-01-02", 10.0)])
    ensure_prices(conn, ["A"], "2024-01-02", "2024-03-06", False, settings)
    assert fetch.calls == [(["A"], "2024-01-02", "2024-03-06")]


def test_empty_database_downloads_everything(conn, fetch, settings):
    fetch.data = long([("A", "2024-01-02", 10.0)])
    ensure_prices(conn, ["A"], "2024-01-02", "2024-03-06", True, settings)
    assert fetch.calls == [(["A"], "2024-01-02", "2024-03-06")]


def test_same_day_uses_cache(conn, fetch, settings):
    seed(conn, [("A", "2024-03-04", 11.0)], fetched=date.today().isoformat())
    ensure_prices(conn, ["A"], "2024-01-02", "2024-03-06", True, settings)
    assert fetch.calls == []
