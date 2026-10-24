from datetime import date, timedelta

from top3 import shares as shares_module
from top3.config import DataSettings


def settings_with(cfg, **changes):
    cfg["data"].update(changes)
    return DataSettings.from_config(cfg)


def store(conn, ticker, value, days_ago):
    fetched = (date.today() - timedelta(days=days_ago)).isoformat()
    conn.execute("INSERT OR REPLACE INTO shares (ticker, shares, fetched) VALUES (?, ?, ?)", (ticker, value, fetched))
    conn.commit()


def fake_fetch(monkeypatch, values):
    calls = []

    def fetch(ticker):
        calls.append(ticker)
        return ticker, values.get(ticker)

    monkeypatch.setattr(shares_module, "_fetch_shares", fetch)
    return calls


def test_recent_shares_are_reused_within_the_ttl(conn, cfg, monkeypatch):
    store(conn, "A", 10.0, days_ago=20)           # dentro de los 30 días: no se vuelve a pedir
    store(conn, "B", 20.0, days_ago=40)           # vencida: se pide de nuevo
    calls = fake_fetch(monkeypatch, {"B": 25.0, "C": 30.0})
    out = shares_module.ensure_shares(conn, ["A", "B", "C"], True, settings_with(cfg, shares_ttl_days=30))
    assert out == {"A": 10.0, "B": 25.0, "C": 30.0} and sorted(calls) == ["B", "C"]
    assert conn.execute("SELECT shares FROM shares WHERE ticker = 'B'").fetchone()[0] == 25.0  # y se guarda


def test_ttl_is_configurable(conn, cfg, monkeypatch):
    store(conn, "A", 10.0, days_ago=3)
    calls = fake_fetch(monkeypatch, {"A": 11.0})
    shares_module.ensure_shares(conn, ["A"], True, settings_with(cfg, shares_ttl_days=1))
    assert calls == ["A"]


def test_no_cache_ignores_stored_shares_but_not_what_this_run_already_has(conn, cfg, monkeypatch):
    store(conn, "A", 10.0, days_ago=0)
    calls = fake_fetch(monkeypatch, {"A": 11.0, "B": 20.0, "C": 30.0})
    out = shares_module.ensure_shares(conn, ["A", "B", "C"], False, settings_with(cfg), known={"B": 20.0})
    assert out == {"A": 11.0, "B": 20.0, "C": 30.0} and sorted(calls) == ["A", "C"]


def test_missing_shares_are_reported_and_left_out(conn, cfg, monkeypatch, caplog):
    fake_fetch(monkeypatch, {"A": 1.0})
    out = shares_module.ensure_shares(conn, ["A", "NOPE"], True, settings_with(cfg))
    assert out == {"A": 1.0} and "TOP-DAT-003" in caplog.text
