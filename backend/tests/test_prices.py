from datetime import date, timedelta

import pandas as pd
import pytest

from top3 import prices as prices_module
from top3.db import fetched_today, get_meta, set_meta
from top3.repo import prices as store
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

        def __call__(self, tickers, start, end, batch_size, gone=None):
            self.calls.append((sorted(tickers), start, end))
            d = self.data
            return d[d["ticker"].isin(tickers) & (d["date"] >= start)].reset_index(drop=True), []

    fake = Fake()
    monkeypatch.setattr(prices_module, "fetch_prices", fake)
    return fake


def stored(conn):
    return {(t, d): c for t, d, c in conn.execute("SELECT ticker, date, close FROM prices")}


def seed(conn, rows, start="2024-01-01", fetched=None):
    store.save(conn, long(rows))
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


def _yahoo_download(responses, monkeypatch):
    """Simula yf.download: cada respuesta es (DataFrame, {ticker: mensaje que yfinance logueó})."""
    import logging
    calls = []

    def fake(batch, **kwargs):
        frame, errors = responses[len(calls)]
        calls.append(list(batch))
        for ticker, message in errors.items():
            logging.getLogger("yfinance").error(f"${ticker}: {message}")
        return {"Close": frame}

    monkeypatch.setattr(prices_module.yf, "download", fake)
    return calls


def _frame(**series):
    return pd.DataFrame(series, index=pd.to_datetime(["2024-01-02", "2024-01-03"]))


def test_rate_limited_tickers_are_retried_after_waiting(monkeypatch):
    waits = []
    monkeypatch.setattr(prices_module.time, "sleep", waits.append)
    calls = _yahoo_download([
        (_frame(AAA=[1.0, 2.0], ADM=[float("nan")] * 2), {"ADM": "YFRateLimitError('Too Many Requests')"}),
        (_frame(ADM=[5.0, 6.0]), {}),
    ], monkeypatch)
    long, sin_datos = prices_module.fetch_prices(["AAA", "ADM"], "2024-01-01", "2024-02-01", 100, retries=3, wait=10)
    assert calls == [["AAA", "ADM"], ["ADM"]] and waits == [10]
    assert sin_datos == [] and sorted(long["ticker"].unique()) == ["AAA", "ADM"]


def test_rate_limit_that_never_clears_is_reported_and_left_without_data(monkeypatch, caplog):
    waits = []
    monkeypatch.setattr(prices_module.time, "sleep", waits.append)
    limited = (_frame(AAA=[1.0, 2.0], ADM=[float("nan")] * 2), {"ADM": "Rate limited. Try after a while."})
    again = (_frame(ADM=[float("nan")] * 2), {"ADM": "Rate limited. Try after a while."})
    calls = _yahoo_download([limited, again, again], monkeypatch)
    _, sin_datos = prices_module.fetch_prices(["AAA", "ADM"], "2024-01-01", "2024-02-01", 100, retries=2, wait=5)
    assert len(calls) == 3 and waits == [5, 10]  # espera el doble en cada reintento
    assert sin_datos == ["ADM"]
    assert "TOP-NET-005: Yahoo siguió limitando 1 tickers tras 2 reintentos" in caplog.text


def test_delisted_tickers_are_not_retried(monkeypatch):
    monkeypatch.setattr(prices_module.time, "sleep", lambda s: pytest.fail("no debe esperar"))
    calls = _yahoo_download([
        (_frame(AAA=[1.0, 2.0], OLD=[float("nan")] * 2), {"OLD": "possibly delisted; no timezone found"})], monkeypatch)
    _, sin_datos = prices_module.fetch_prices(["AAA", "OLD"], "2024-01-01", "2024-02-01", 100)
    assert len(calls) == 1 and sin_datos == ["OLD"]


def _set_checked(conn, ticker, days_ago):
    checked = (date.today() - timedelta(days=days_ago)).isoformat()
    conn.execute("INSERT OR REPLACE INTO no_data_tickers (ticker, checked) VALUES (?, ?)", (ticker, checked))
    conn.commit()


def test_fetch_prices_reports_tickers_yahoo_says_are_gone_but_not_rate_limited_ones(monkeypatch):
    monkeypatch.setattr(prices_module.time, "sleep", lambda s: None)
    nan = [float("nan")] * 2
    frame = _frame(AAA=[1.0, 2.0], OLD=nan, LIMITED=nan, ODD=nan)
    errors = {"OLD": "possibly delisted; no timezone found", "LIMITED": "Too Many Requests. Rate limited.",
              "ODD": "algo inesperado"}
    still = (_frame(LIMITED=nan), {"LIMITED": "Too Many Requests. Rate limited."})
    _yahoo_download([(frame, errors), still, still, still], monkeypatch)
    gone = set()
    _, sin_datos = prices_module.fetch_prices(["AAA", "OLD", "LIMITED", "ODD"], "2024-01-01", "2024-02-01", 100,
                                              retries=3, wait=0, gone=gone)
    assert sorted(sin_datos) == ["LIMITED", "ODD", "OLD"]
    assert gone == {"OLD"}                                   # solo lo que Yahoo dice que no existe


def test_known_no_data_respects_the_ttl(conn):
    _set_checked(conn, "FRESH", 5)
    _set_checked(conn, "STALE", 40)
    assert store.known_no_data(conn, 30) == {"FRESH"}
    assert store.known_no_data(conn, 0) == set()      # 0 = pedir siempre


def test_remember_no_data_adds_gone_tickers_and_forgets_those_with_data_again(conn):
    _set_checked(conn, "BACK", 40)
    store.remember_no_data(conn, {"OLD"}, ["BACK"])
    assert {r[0] for r in conn.execute("SELECT ticker FROM no_data_tickers")} == {"OLD"}


def test_full_download_skips_known_gone_tickers_and_records_new_ones(conn, settings, monkeypatch):
    _set_checked(conn, "OLD1", 3)
    asked = []

    def fake(tickers, start, end, batch_size, gone=None):
        asked.append(sorted(tickers))
        gone.add("OLD2")
        return long([("AAA", "2024-01-02", 1.0)]), ["OLD2"]

    monkeypatch.setattr(prices_module, "fetch_prices", fake)
    prices_module.download_prices(conn, ["AAA", "OLD1", "OLD2"], "2024-01-01", "2024-02-01", settings)
    assert asked == [["AAA", "OLD2"]]                         # OLD1 ya se sabía: no se pide
    assert store.known_no_data(conn, 30) == {"OLD1", "OLD2"}


def test_incremental_update_does_not_ask_again_for_known_gone_new_tickers(conn, fetch, settings):
    seed(conn, [("A", "2024-03-04", 11.0)])
    _set_checked(conn, "OLD", 3)
    fetch.data = long([("A", "2024-03-04", 11.0), ("A", "2024-03-05", 12.0)])
    ensure_prices(conn, ["A", "OLD"], "2024-01-02", "2024-03-06", True, settings)
    assert all("OLD" not in tickers for tickers, _, _ in fetch.calls)


def test_a_known_gone_ticker_is_asked_again_after_the_ttl(conn, fetch, settings):
    seed(conn, [("A", "2024-03-04", 11.0)])
    _set_checked(conn, "OLD", settings.no_data_ttl_days + 5)
    fetch.data = long([("A", "2024-03-04", 11.0), ("OLD", "2024-03-05", 3.0)])
    ensure_prices(conn, ["A", "OLD"], "2024-01-02", "2024-03-06", True, settings)
    assert any("OLD" in tickers for tickers, _, _ in fetch.calls)
    assert ("OLD", "2024-03-05") in stored(conn)
    assert store.known_no_data(conn, 30) == set()    # y como ahora tiene datos, se olvida


def test_closes_on_or_before_takes_the_last_close_of_each_ticker_in_one_query(conn):
    store.save(conn, long([("A", "2024-01-02", 1.0), ("A", "2024-01-05", 2.0), ("A", "2024-01-09", 3.0),
                           ("B", "2024-01-08", 7.0)]))
    assert store.closes_on_or_before(conn, ["A", "B", "NOPE"], "2024-01-08") == {"A": 2.0, "B": 7.0}
    assert store.closes_on_or_before(conn, [], "2024-01-08") == {}
