"""Datos del frontend: arma el JSON (Top actual + backtest) con los últimos resultados guardados en SQLite."""
import csv
import json
import sqlite3
import statistics
from datetime import date, datetime
from pathlib import Path

from . import rotation
from .db import open_db, run_key
from .logs import log
from .universe import label


def _latest_runs(conn: sqlite3.Connection) -> tuple[str | None, dict]:
    """Última corrida (por id) de cada (min_cap, años, plazo, desfase) entre las de la fecha más reciente."""
    last_day = conn.execute("SELECT MAX(substr(run_at, 1, 10)) FROM runs").fetchone()[0]
    if not last_day:
        return None, {}
    rows = conn.execute(
        "SELECT id, params, start_date, end_date, final_capital, total_return, cagr "
        "FROM runs WHERE substr(run_at, 1, 10) = ? ORDER BY id", (last_day,)).fetchall()
    latest = {}
    for row in rows:
        params = json.loads(row[1])
        key = run_key(params)
        if key is not None:
            latest[key] = row
    return last_day, latest


def _run_detail(conn: sqlite3.Connection, run_id: int, initial_capital: float) -> tuple[list[dict], list[dict]]:
    """Curva de capital y selecciones (con el capital al entrar y la ganancia acumulada) de una corrida."""
    equity = [{"date": d, "capital": c} for d, c in
              conn.execute("SELECT date, capital FROM equity WHERE run_id = ? ORDER BY date", (run_id,))]
    cap_by_date = {e["date"]: e["capital"] for e in equity}
    picks_by_date: dict[str, list[dict]] = {}
    for d, rank, ticker, ret in conn.execute(
            "SELECT rebalance_date, rank, ticker, return_lookback FROM selections WHERE run_id = ? "
            "ORDER BY rebalance_date, rank", (run_id,)):
        picks_by_date.setdefault(d, []).append({"rank": rank, "ticker": ticker, "return": ret})
    history = [{"date": d, "picks": picks, "capital": cap_by_date.get(d),
                "gain": (cap_by_date[d] / initial_capital - 1) if d in cap_by_date else None}
               for d, picks in sorted(picks_by_date.items())]
    return equity, history


def _term_summary(calendars: list[dict]) -> dict:
    cagrs = [c["cagr"] for c in calendars]
    finals = [c["final_capital"] for c in calendars]
    return {"calendars": len(calendars), "cagr_median": statistics.median(cagrs),
            "cagr_min": min(cagrs), "cagr_max": max(cagrs),
            "capital_median": statistics.median(finals), "capital_min": min(finals), "capital_max": max(finals)}


def _backtest(conn: sqlite3.Connection, latest: dict, initial_capital: float) -> list[dict]:
    """Backtest agrupado: universo -> período (años) -> plazo -> calendarios de arranque."""
    grouped: dict[float, dict[float, dict[int, list[dict]]]] = {}
    for (cap, years, months, offset), row in sorted(latest.items()):
        run_id, _, start, end, final, total, cagr = row
        equity, history = _run_detail(conn, run_id, initial_capital)
        calendar = {"offset": offset, "start_date": start, "end_date": end, "final_capital": final,
                    "total_return": total / 100, "cagr": cagr / 100, "rebalances": len(history),
                    "first_rebalance": history[0]["date"] if history else None,
                    "equity": equity, "history": history}
        grouped.setdefault(cap, {}).setdefault(years, {}).setdefault(months, []).append(calendar)

    out = []
    for cap, by_years in sorted(grouped.items()):
        periods = []
        for years, by_term in sorted(by_years.items()):
            terms = []
            for months, calendars in sorted(by_term.items()):
                calendars.sort(key=lambda c: c["offset"])
                terms.append({"months": months, "calendars": calendars, "summary": _term_summary(calendars)})
            base = terms[0]["calendars"][0]  # calendario base (desfase 0): define el período
            periods.append({"years": years, "start_date": base["start_date"], "end_date": base["end_date"],
                            "terms": terms})
        out.append({"min_cap_billions": cap or None, "label": label(cap), "periods": periods})
    return out


def _actual(conn: sqlite3.Connection, today: date | None = None) -> list[dict]:
    """Último Top actual de cada (universo, plazo) entre los de la fecha más reciente."""
    last_run_at = conn.execute("SELECT MAX(run_at) FROM actual_picks").fetchone()[0]
    if not last_run_at:
        return []
    rows = conn.execute(
        "SELECT run_at, as_of, months, COALESCE(min_cap_billions, 0), rank, ticker, return_lookback, price, "
        "market_cap FROM actual_picks WHERE substr(run_at, 1, 10) = ? ORDER BY run_at, rank",
        (last_run_at[:10],)).fetchall()
    latest = {(r[3], r[2]): r[0] for r in rows}  # (universo, plazo) -> run_at de la última corrida
    out = []
    for (cap, months), run_at in sorted(latest.items()):
        mine = [r for r in rows if r[0] == run_at and r[3] == cap and r[2] == months]
        cap_b = cap or None
        prev_as_of, prev = rotation.previous_picks(conn, mine[0][1], months, cap_b)
        anchor = rotation.anchor_date(conn, months, cap_b)
        out.append({"min_cap_billions": cap or None, "label": label(cap), "months": months,
                    "as_of": mine[0][1], "run_at": run_at,
                    "previous_as_of": prev_as_of,
                    "changes": rotation.diff_picks(prev, [r[5] for r in mine]) if prev_as_of else None,
                    "anchor": anchor,
                    "next_rebalance": rotation.next_rebalance(anchor, months, today or date.today()).isoformat(),
                    "picks": [{"rank": r[4], "ticker": r[5], "return": r[6], "price": r[7], "market_cap": r[8]}
                              for r in mine]})
    return out


def _etf(conn: sqlite3.Connection, cfg: dict) -> dict | None:
    """Último ranking de ETFs de Vanguard guardado, con nombre y categoría de la lista (CSV)."""
    as_of = conn.execute("SELECT MAX(as_of) FROM etf_scores").fetchone()[0]
    if not as_of:
        return None
    etf_cfg = cfg["etf"]
    top_n = int(etf_cfg["top_n"])
    try:
        with open(etf_cfg["csv"], encoding="utf-8", newline="") as f:
            info = {r["ticker"].strip().upper(): r for r in csv.DictReader(f)}
    except OSError:
        info = {}
    rows = []
    for rank, ticker, score, vol, max_dd, sma_dist, returns, run_at in conn.execute(
            "SELECT rank, ticker, score, vol, max_dd, sma_dist, returns, run_at FROM etf_scores WHERE as_of = ? "
            "ORDER BY rank", (as_of,)):
        meta = info.get(ticker, {})
        rows.append({"rank": rank, "ticker": ticker, "name": meta.get("name", "").strip(),
                     "category": meta.get("category", "").strip(), "score": score, "vol": vol, "max_dd": max_dd,
                     "sma_dist": sma_dist, "returns": json.loads(returns)})
    prev_as_of, prev = rotation.previous_etf_top(conn, as_of, top_n)
    risk_free = (etf_cfg.get("risk_free_ticker") or "").upper()
    return {"as_of": as_of, "run_at": run_at, "top_n": top_n, "horizons": sorted(int(h) for h in rows[0]["returns"]),
            "risk_free": risk_free if any(r["ticker"] == risk_free for r in rows) else None,
            "previous_as_of": prev_as_of,
            "changes": rotation.diff_picks(prev, [r["ticker"] for r in rows[:top_n]]) if prev_as_of else None,
            "rows": rows}


def build_report(conn: sqlite3.Connection, cfg: dict) -> dict:
    bt = cfg["backtest"]
    initial_capital = float(bt["initial_capital"])
    run_day, latest = _latest_runs(conn)
    if not bt["start_date"]:  # solo los períodos configurados (ignora corridas sueltas de otros años)
        wanted = {float(y) for y in bt["periods_years"]}
        latest = {k: v for k, v in latest.items() if k[1] in wanted}
    backtest = _backtest(conn, latest, initial_capital)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_date": run_day,
        "settings": {"top_n": int(bt["top_n"]), "months": int(bt["months"]), "initial_capital": initial_capital,
                     "terms": [int(m) for m in cfg["simulation"]["months"]],
                     "backtest_years": float(bt["backtest_years"]),
                     "min_cap_billions": float(cfg["universe"]["min_cap_billions"]),
                     "periods_years": sorted({p["years"] for u in backtest for p in u["periods"]})},
        "actual": _actual(conn),
        "etf": _etf(conn, cfg),
        "backtest": backtest,
    }


def export_report(cfg: dict) -> Path:
    """Escribe el JSON para el frontend ([output] frontend_data) y devuelve la ruta."""
    conn = open_db(cfg["data"]["db_path"])
    try:
        report = build_report(conn, cfg)
    finally:
        conn.close()
    path = Path(cfg["output"]["frontend_data"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log.info("JSON del frontend guardado: %s (%d universos de backtest, %d Top actual)",
             path.resolve(), len(report["backtest"]), len(report["actual"]))
    return path
