"""Modelo por score: score de momentum + score de salud financiera de las acciones del S&P 500, su promedio como score final y
Markowitz sobre las mejores.

No hay backtest: es una foto de hoy (precios hasta la última rueda y últimos datos financieros publicados)."""
import json
import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from .. import errors as E
from ..config import DataSettings
from ..constituents import Constituents, ensure_constituents
from ..db import open_db
from ..logs import log
from ..prices import ensure_prices, load_prices
from . import fundamentals as FU, markowitz as MK, momentum as MO, ohlcv as OH, technical as TE


def _clean(value):
    """Valores aptos para JSON: NaN e infinitos pasan a None (JSON no los admite)."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


def run_quant(cfg: dict, use_cache: bool = True) -> dict:
    """Actualiza precios, OHLCV y datos financieros, calcula los scores y Markowitz y guarda el resultado en SQLite."""
    settings = DataSettings.from_config(cfg)
    q = cfg["quant"]
    today = date.today()
    history_start = (today - timedelta(days=round(float(cfg["data"]["history_years"]) * 365.25))).isoformat()
    conn = open_db(cfg["data"]["db_path"])
    try:
        ensure_constituents(conn, settings, use_cache)
        constituents = Constituents(conn, cfg["tickers"]["aliases"])
        tickers = sorted(constituents.current)
        ensure_prices(conn, constituents.all_between(history_start, today), history_start,
                      (today + timedelta(days=1)).isoformat(), use_cache, settings)
        prices = load_prices(conn)
        data = FU.ensure_fundamentals(conn, tickers, use_cache, int(q["fundamentals_ttl_days"]),
                                      settings.shares_workers)
        OH.ensure_ohlcv(conn, tickers, use_cache, settings.batch_size)
        ohlcv = OH.load_ohlcv(conn)
    finally:
        conn.close()
    payload = compute(prices, tickers, data, ohlcv, cfg)
    save(cfg, payload)
    return payload


def compute(prices: pd.DataFrame, tickers: list[str], data: dict[str, dict], ohlcv: dict[str, pd.DataFrame],
            cfg: dict) -> dict:
    q = cfg["quant"]
    top_n = int(q["top_n"])
    prices = prices.reindex(columns=tickers)
    as_of = prices.index[-1]

    returns = MO.momentum_returns(prices)
    momentum = MO.momentum_score(returns)
    frame = FU.indicators(data)
    health = FU.health_score(frame, dict(zip(FU.GROUPS, (float(w) for w in q["health_weights"]))))
    technical = TE.technical_score(TE.indicators({k: v.reindex(columns=tickers) for k, v in ohlcv.items()}))
    table = frame.join(returns).join(momentum).join(health).join(technical.add_prefix("tec_"))
    scores = ["momentum", "health", "tec_technical"]
    ranked = table.dropna(subset=scores).copy()
    if len(ranked) < top_n:
        raise SystemExit(E.QNT_NO_SIGNAL.msg(f"Solo {len(ranked)} acciones tienen los tres scores."))
    weights = np.array([float(w) for w in q["weights"]])
    ranked["score"] = ranked[scores].to_numpy() @ weights / weights.sum()
    ranked = ranked.sort_values(["score", "momentum"], ascending=False)
    log.info("Acciones: %d en el índice, %d con momentum, %d con datos financieros, %d con datos técnicos, %d en el ranking "
             "final", len(tickers), int(momentum.notna().sum()), int(health["health"].notna().sum()),
             int(technical["technical"].notna().sum()), len(ranked))

    top = list(ranked.index[:top_n])
    prior = float(q["risk_free"]) + float(q["equity_premium"])
    mu, sigma = MK.inputs(prices[top], float(q["mu_shrink"]), prior)
    optimal = MK.frontier(mu, sigma, float(q["vol_target"]), float(q["w_max"]), float(q["risk_free"]),
                          ranked.loc[top, "sector"], float(q["sector_max"]))
    # los pesos de la tabla son los de la primera cartera disponible: máximo retorno o, si no se alcanza el riesgo, Sharpe
    weight = {w["ticker"]: w["weight"] for w in optimal["portfolios"][0]["weights"]}

    rows = []
    for rank, (ticker, r) in enumerate(ranked.iterrows(), 1):
        rows.append({
            "rank": rank, "ticker": ticker, "name": r["name"], "sector": r["sector"], "market_cap": r["market_cap"],
            "score": r["score"], "momentum": r["momentum"], "health": r["health"], "technical": r["tec_technical"],
            "groups": int(r["groups"]), "health_groups": {g: r[g] for g in FU.GROUPS},
            "technical_groups": {g: r["tec_" + g] for g in TE.GROUPS}, "rsi": r["tec_rsi"],
            "macd_hist": r["tec_macd_hist"], "vs_ema50": r["tec_vs_ema50"], "vs_ema200": r["tec_vs_ema200"],
            "mom_12_1": r["mom_12_1"], "mom_6_1": r["mom_6_1"],
            "roe": r["roe"], "operating_margin": r["operating_margin"], "debt_to_equity": r["debt_to_equity"],
            "net_debt_ebitda": r["net_debt_ebitda"], "current_ratio": r["current_ratio"], "fcf_margin": r["fcf_margin"],
            "fcf_yield": r["fcf_yield"], "cash_conversion": r["cash_conversion"], "ocf_to_debt": r["ocf_to_debt"],
            "fcf_positive_years": r["fcf_positive_years"],
            "weight": weight.get(ticker, 0.0) if rank <= top_n else 0.0})
    vol = pd.Series(np.sqrt(np.diag(sigma)), index=sigma.index)
    excluded = {"sin_momentum": sorted(momentum.index.difference(momentum.dropna().index).tolist()
                                       + [t for t in tickers if t not in momentum.index]),
                "sin_datos_financieros": sorted(t for t in tickers if t not in health["health"].dropna().index),
                "sin_datos_tecnicos": sorted(t for t in tickers if t not in technical["technical"].dropna().index)}
    return _clean({
        "as_of": as_of.date().isoformat(), "generated_at": datetime.now().isoformat(timespec="seconds"),
        "settings": {"top_n": top_n, "vol_target": float(q["vol_target"]), "w_max": float(q["w_max"]),
                     "sector_max": float(q["sector_max"]),
                     "mu_shrink": float(q["mu_shrink"]), "risk_free": float(q["risk_free"]), "prior": prior,
                     "weights": [float(w) for w in q["weights"]],
                     "health_weights": dict(zip(FU.GROUPS, (float(w) for w in q["health_weights"])))},
        "coverage": {"universe": len(tickers), "momentum": int(momentum.notna().sum()),
                     "health": int(health["health"].notna().sum()), "technical": int(technical["technical"].notna().sum()),
                     "ranked": len(ranked), "excluded": excluded},
        "ranking": rows,
        "markowitz": {"tickers": [{"ticker": t, "exp_return": mu[t], "vol": vol[t]} for t in top], **optimal,
                      "main": optimal["portfolios"][0]["key"]},
    })


def save(cfg: dict, payload: dict) -> None:
    """Guarda solo el último resultado."""
    conn = open_db(cfg["data"]["db_path"])
    try:
        conn.execute("DELETE FROM quant_runs")
        conn.execute("INSERT INTO quant_runs (run_at, as_of, payload) VALUES (?, ?, ?)",
                     (payload["generated_at"], payload["as_of"], json.dumps(payload, ensure_ascii=False)))
        conn.commit()
    finally:
        conn.close()
    log.info("Modelo por score guardado en SQLite (tabla quant_runs)")
