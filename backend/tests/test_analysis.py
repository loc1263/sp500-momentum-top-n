import json

import pandas as pd
import pytest

from helpers import FakeConstituents, make_calendar as calendar, make_prices
from top3.analysis import Context, Term, run_calendars, run_terms, save_run


def test_term_base_and_stats():
    term = Term(4, [calendar(1, 1500, 40.0), calendar(0, 1100, 10.0), calendar(2, 1300, 25.0)])
    assert term.base.offset == 0
    assert term.cagr_stats() == (25.0, 10.0, 40.0)
    assert term.capital_stats() == (1300, 1100, 1500)
    assert Term(4, [calendar(1, 1500, 40.0)]).base is None


@pytest.fixture
def ctx(conn, cfg, settings):
    prices = make_prices()
    cfg["backtest"]["backtest_years"] = 2
    return Context(conn, cfg, settings, FakeConstituents(list(prices.columns)), prices,
                   pd.Timestamp("2023-09-01"), pd.Timestamp("2024-12-31"))


def test_context_reads_config(ctx):
    assert ctx.initial_capital == 1000.0 and ctx.top_n == 4
    assert ctx.lookback_days(3) == 63
    assert ctx.terms == [3, 4, 6, 8, 12]


def test_run_calendars_saves_one_run_per_offset(ctx, conn):
    term = run_calendars(ctx, 3)
    assert [c.offset for c in term.calendars] == [0, 1, 2]
    rows = conn.execute("SELECT params, start_date FROM runs ORDER BY id").fetchall()
    assert len(rows) == 3
    params = json.loads(rows[1][0])
    assert params["sweep_months"] == 3 and params["offset_months"] == 1
    assert params["min_cap_billions"] is None and params["backtest"]["backtest_years"] == 2
    assert rows[1][1] == "2023-10-01"                                # arranque desfasado un mes
    assert conn.execute("SELECT COUNT(*) FROM equity").fetchone()[0] > 0
    assert conn.execute("SELECT COUNT(*) FROM selections").fetchone()[0] > 0


def test_run_calendars_skips_failed_offsets(ctx):
    ctx.start_date = pd.Timestamp("2024-12-20")       # sin ruedas de ranking suficientes: ningún calendario sirve
    assert run_calendars(ctx, 3).calendars == []


def test_run_terms_covers_configured_months(ctx):
    ctx.cfg["simulation"]["months"] = [2, 3]
    assert [(t.months, len(t.calendars)) for t in run_terms(ctx)] == [(2, 2), (3, 3)]


def test_save_run_returns_id(conn):
    run_id = save_run(conn, {"a": 1}, "2024-01-01", "2024-09-01", calendar(0, 1100, 10.0))
    assert conn.execute("SELECT final_capital, cagr FROM runs WHERE id = ?", (run_id,)).fetchone() == (1100, 10.0)
