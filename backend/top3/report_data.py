"""Datos del frontend: arma el JSON (Top actual + backtest) con los últimos resultados guardados en SQLite."""
import json
import sqlite3
import statistics
from datetime import datetime
from pathlib import Path

from .db import open_db
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
        if "sweep_months" not in params:
            continue
        years = float(params.get("backtest", {}).get("backtest_years", 5))
        key = (float(params.get("min_cap_billions") or 0), years, int(params["sweep_months"]),
               int(params.get("offset_months", 0)))
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


def _actual(conn: sqlite3.Connection) -> list[dict]:
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
        out.append({"min_cap_billions": cap or None, "label": label(cap), "months": months,
                    "as_of": mine[0][1], "run_at": run_at,
                    "picks": [{"rank": r[4], "ticker": r[5], "return": r[6], "price": r[7], "market_cap": r[8]}
                              for r in mine]})
    return out


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
