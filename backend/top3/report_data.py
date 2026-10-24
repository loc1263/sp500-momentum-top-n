"""Datos del frontend: arma el JSON (Top actual + backtest) con los últimos resultados guardados en SQLite."""
import csv
import json
import sqlite3
import statistics
from datetime import date, datetime
from pathlib import Path

from . import rotation
from .config import Config
from .db import open_db
from .logs import log
from .repo import etf as etf_store, picks as picks_store, prices as prices_store, quant as quant_store, runs as runs_store
from .universe import label


def _latest_runs(conn: sqlite3.Connection) -> tuple[str | None, dict]:
    """Última corrida (por id) de cada (min_cap, años, plazo, desfase) entre las de la fecha más reciente."""
    last_day = runs_store.latest_day(conn)
    if not last_day:
        return None, {}
    latest = {}
    for row in runs_store.runs_of_day(conn, last_day):
        params = json.loads(row.params)
        key = runs_store.run_key(params)
        if key is not None:
            latest[key] = row
    return last_day, latest


def _run_detail(conn: sqlite3.Connection, run_id: int, initial_capital: float) -> tuple[list[dict], list[dict]]:
    """Curva de capital y selecciones (con el capital al entrar y la ganancia acumulada) de una corrida."""
    equity = [{"date": d, "capital": c} for d, c in runs_store.equity_curve(conn, run_id)]
    cap_by_date = {e["date"]: e["capital"] for e in equity}
    picks_by_date: dict[str, list[dict]] = {}
    for d, rank, ticker, ret in runs_store.selections(conn, run_id):
        picks_by_date.setdefault(d, []).append({"rank": rank, "ticker": ticker, "return": ret})
    history = [{"date": d, "picks": picks, "capital": cap_by_date.get(d),
                "gain": (cap_by_date[d] / initial_capital - 1) if d in cap_by_date else None}
               for d, picks in sorted(picks_by_date.items())]
    return equity, history


MIN_HALF_DAYS = 90  # una mitad más corta que esto no da un CAGR con sentido


def _halves(calendars: list[dict]) -> dict:
    """CAGR mediano de cada mitad del período (por fecha), para ver si el resultado se sostiene en el tiempo.

    Se parte la curva de capital de cada calendario en la fecha media del período; el corte se hace en el punto de la
    curva más cercano a esa fecha (hay uno por rebalanceo). Una mitad sin datos suficientes queda en None."""
    base = next((c for c in calendars if c["offset"] == 0), calendars[0])
    start, end = date.fromisoformat(base["start_date"]), date.fromisoformat(base["end_date"])
    mid = start + (end - start) / 2
    firsts, seconds = [], []

    def cagr(v0: float, d0: date, v1: float, d1: date) -> float | None:
        days = (d1 - d0).days
        return (v1 / v0) ** (365.25 / days) - 1 if days >= MIN_HALF_DAYS and v0 > 0 else None

    for c in calendars:
        points = [(date.fromisoformat(e["date"]), e["capital"]) for e in c["equity"]]
        d_mid, v_mid = min(points, key=lambda p: abs((p[0] - mid).days))   # el punto de la curva más cercano
        for out, value in ((firsts, cagr(points[0][1], points[0][0], v_mid, d_mid)),
                           (seconds, cagr(v_mid, d_mid, points[-1][1], points[-1][0]))):
            if value is not None:
                out.append(value)
    return {"split": mid.isoformat(), "first": statistics.median(firsts) if firsts else None,
            "second": statistics.median(seconds) if seconds else None}


def _term_summary(calendars: list[dict]) -> dict:
    cagrs = [c["cagr"] for c in calendars]
    finals = [c["final_capital"] for c in calendars]
    return {"calendars": len(calendars), "cagr_median": statistics.median(cagrs),
            "cagr_min": min(cagrs), "cagr_max": max(cagrs),
            "capital_median": statistics.median(finals), "capital_min": min(finals), "capital_max": max(finals),
            "halves": _halves(calendars)}


def _calendar(conn: sqlite3.Connection, offset: int, row, initial_capital: float) -> dict:
    """Un calendario de arranque: resumen de la corrida, curva de capital e historial de selecciones."""
    equity, history = _run_detail(conn, row.id, initial_capital)
    return {"offset": offset, "start_date": row.start_date, "end_date": row.end_date,
            "final_capital": row.final_capital, "total_return": row.total_return / 100, "cagr": row.cagr / 100,
            "rebalances": len(history), "first_rebalance": history[0]["date"] if history else None,
            "equity": equity, "history": history}


def _universe(cap: float, by_years: dict[float, dict[int, list[dict]]]) -> dict:
    """Un universo: sus períodos (años) con los plazos y calendarios de cada uno."""
    periods = []
    for years, by_term in sorted(by_years.items()):
        terms = []
        for months, calendars in sorted(by_term.items()):
            calendars.sort(key=lambda c: c["offset"])
            terms.append({"months": months, "calendars": calendars, "summary": _term_summary(calendars)})
        base = terms[0]["calendars"][0]  # calendario base (desfase 0): define el período
        periods.append({"years": years, "start_date": base["start_date"], "end_date": base["end_date"],
                        "terms": terms})
    return {"min_cap_billions": cap or None, "label": label(cap), "periods": periods}


def _backtest(conn: sqlite3.Connection, latest: dict, initial_capital: float, skip_months: int = 0) -> list[dict]:
    """Backtest agrupado: universo -> período (años) -> plazo -> calendarios de arranque, de un modelo
    (`skip_months` = 0 el de siempre, 1 el skip-month)."""
    grouped: dict[float, dict[float, dict[int, list[dict]]]] = {}
    for (cap, years, months, offset, skip), row in sorted(latest.items()):
        if skip == skip_months:
            grouped.setdefault(cap, {}).setdefault(years, {}).setdefault(months, []).append(
                _calendar(conn, offset, row, initial_capital))
    return [_universe(cap, by_years) for cap, by_years in sorted(grouped.items())]


def _tracking(conn: sqlite3.Connection, cap: float, months: int) -> list[dict]:
    """Cómo le fue a cada selección guardada del Top actual (de la más nueva a la más vieja).

    Se mide con el precio guardado al elegirla y el último precio disponible, sin pasar de los `months` meses que
    dura la tenencia: si ya pasaron, la selección figura como cerrada y su retorno es el del plazo completo."""
    last = prices_store.latest_date(conn)
    if not last:
        return []
    last_day = date.fromisoformat(last)
    by_date = picks_store.latest_picks_by_date(conn, cap, months)
    out = []
    for as_of, picks in sorted(by_date.items(), reverse=True):
        bought = date.fromisoformat(as_of)
        # fin de la tenencia: mismo día del mes, `months` meses después
        year, month = divmod(bought.month - 1 + months, 12)
        try:
            term_end = bought.replace(year=bought.year + year, month=month + 1)
        except ValueError:                       # 29-31 en un mes más corto
            term_end = bought.replace(year=bought.year + year, month=month + 1, day=28)
        end = min(term_end, last_day)
        if end <= bought:
            continue
        closes = prices_store.closes_on_or_before(conn, [t for t, _ in picks], end.isoformat())
        returns = [{"ticker": ticker, "price": price, "now": closes[ticker], "return": closes[ticker] / price - 1}
                   for ticker, price in picks if ticker in closes and price]
        if returns:
            out.append({"as_of": as_of, "until": end.isoformat(), "days": (end - bought).days,
                        "closed": term_end <= last_day, "picks": returns,
                        "return": statistics.mean(r["return"] for r in returns)})
    return out


def _actual(conn: sqlite3.Connection, today: date | None = None) -> list[dict]:
    """Último Top actual de cada (universo, plazo) entre los de la fecha más reciente."""
    last_run_at = picks_store.latest_run_at(conn)
    if not last_run_at:
        return []
    rows = picks_store.runs_of_day(conn, last_run_at[:10])
    latest = {(r[3], r[2]): r[0] for r in rows}  # (universo, plazo) -> run_at de la última corrida
    out = []
    for (cap, months), run_at in sorted(latest.items()):
        mine = [r for r in rows if r[0] == run_at and r[3] == cap and r[2] == months]
        cap_b = cap or None
        prev_as_of, prev = picks_store.previous_picks(conn, mine[0][1], months, cap_b)
        anchor = picks_store.anchor_date(conn, months, cap_b)
        alts = picks_store.alternates(conn, run_at, months, cap)
        out.append({"min_cap_billions": cap or None, "label": label(cap), "months": months,
                    "as_of": mine[0][1], "run_at": run_at,
                    "previous_as_of": prev_as_of,
                    "changes": rotation.diff_picks(prev, [r[5] for r in mine]) if prev_as_of else None,
                    "anchor": anchor,
                    "next_rebalance": rotation.next_rebalance(anchor, months, today or date.today()).isoformat(),
                    "picks": [{"rank": r[4], "ticker": r[5], "return": r[6], "price": r[7], "market_cap": r[8]}
                              for r in mine],
                    "alternates": [{"rank": r.rank, "ticker": r.ticker, "return": r.return_lookback,
                                    "price": r.price, "market_cap": r.market_cap} for r in alts],
                    "tracking": _tracking(conn, cap, months)})
    return out


def _etf(conn: sqlite3.Connection, cfg: Config) -> dict | None:
    """Último ranking de ETFs de Vanguard guardado, con nombre y categoría de la lista (CSV)."""
    as_of = etf_store.latest_as_of(conn)
    if not as_of:
        return None
    etf_cfg = cfg.etf
    top_n = etf_cfg.top_n
    try:
        with open(etf_cfg.csv, encoding="utf-8", newline="") as f:
            info = {r["ticker"].strip().upper(): r for r in csv.DictReader(f)}
    except OSError:
        info = {}
    rows = []
    for rank, ticker, score, vol, max_dd, sma_dist, returns, run_at in etf_store.ranking(conn, as_of):
        meta = info.get(ticker, {})
        rows.append({"rank": rank, "ticker": ticker, "name": meta.get("name", "").strip(),
                     "category": meta.get("category", "").strip(), "score": score, "vol": vol, "max_dd": max_dd,
                     "sma_dist": sma_dist, "returns": returns})
    prev_as_of, prev = etf_store.previous_top(conn, as_of, top_n)
    risk_free = etf_cfg.risk_free_ticker.upper()
    return {"as_of": as_of, "run_at": run_at, "top_n": top_n, "horizons": sorted(int(h) for h in rows[0]["returns"]),
            "risk_free": risk_free if any(r["ticker"] == risk_free for r in rows) else None,
            "previous_as_of": prev_as_of,
            "changes": rotation.diff_picks(prev, [r["ticker"] for r in rows[:top_n]]) if prev_as_of else None,
            "rows": rows}


def _quant(conn: sqlite3.Connection) -> dict | None:
    """Último resultado guardado del modelo cuantitativo (ya es un JSON armado por top3.quant)."""
    return quant_store.latest(conn)


def build_report(conn: sqlite3.Connection, cfg: Config) -> dict:
    bt = cfg.backtest
    initial_capital = bt.initial_capital
    run_day, latest = _latest_runs(conn)
    if not bt.start_date:  # solo los períodos configurados (ignora corridas sueltas de otros años)
        wanted = {float(y) for y in bt.periods_years}
        latest = {k: v for k, v in latest.items() if k[1] in wanted}
    backtest = _backtest(conn, latest, initial_capital)
    backtest_skip = _backtest(conn, latest, initial_capital, skip_months=1)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_date": run_day,
        "settings": {"top_n": bt.top_n, "months": bt.months, "initial_capital": initial_capital,
                     "commission": bt.commission,
                     "terms": list(cfg.simulation.months),
                     "backtest_years": bt.backtest_years,
                     "min_cap_billions": cfg.universe.min_cap_billions,
                     "periods_years": sorted({p["years"] for u in backtest for p in u["periods"]})},
        "actual": _actual(conn),
        "etf": _etf(conn, cfg),
        "quant": _quant(conn),
        "backtest": backtest,
        "backtest_skip": backtest_skip,
    }


def export_report(cfg: Config) -> Path:
    """Escribe el JSON para el frontend ([output] frontend_data) y devuelve la ruta."""
    conn = open_db(cfg.data.db_path)
    try:
        report = build_report(conn, cfg)
    finally:
        conn.close()
    path = Path(cfg.output.frontend_data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log.info("JSON del frontend guardado: %s (%d universos de backtest, %d Top actual)",
             path.resolve(), len(report["backtest"]), len(report["actual"]))
    return path
