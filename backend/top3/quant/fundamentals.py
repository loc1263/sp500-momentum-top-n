"""Datos financieros de cada acción (yfinance) y score de salud financiera.

El score es la posición (0-100) de cada empresa entre las demás en cuatro grupos de indicadores; cada grupo promedia su
ranking en los indicadores que tenga y el score de salud promedia los grupos disponibles:

- Rentabilidad: ROE, ROA, margen operativo y margen neto.
- Solvencia: deuda/patrimonio, deuda neta/EBITDA y caja/deuda (menos deuda = mejor).
- Liquidez: liquidez corriente y prueba ácida.
- Generación de caja: flujo de caja libre y flujo operativo sobre ventas, rendimiento del flujo libre sobre la
  capitalización, conversión de la utilidad en caja (flujo libre / utilidad neta), flujo operativo sobre la deuda y
  consistencia (cuántos de los últimos 4 años el flujo libre fue positivo). Una empresa que genera caja de forma sostenida
  es más confiable, así que este grupo pesa el doble por defecto (`[quant] health_weights`).

Las empresas financieras que no informan liquidez corriente (bancos, aseguradoras) no tienen deuda neta, liquidez ni flujo
de caja comparables, así que se miden solo con los indicadores que sí tienen sentido para ellas; las clasificadas como
financieras pero con un balance común (Visa, Mastercard) se miden con los cuatro grupos. Es una foto de los últimos datos publicados, no una serie
histórica.
"""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

from .. import errors as E
from ..logs import log

FIELDS = ["shortName", "sector", "marketCap", "returnOnEquity", "returnOnAssets", "profitMargins", "operatingMargins",
          "debtToEquity", "currentRatio", "quickRatio", "freeCashflow", "operatingCashflow", "totalRevenue",
          "totalDebt", "totalCash", "ebitda", "netIncomeToCommon"]
VERSION = 2            # versión de los datos guardados: los de una versión anterior se vuelven a bajar
FCF_YEARS = 4          # años de flujo libre anual que se miran para la consistencia
FINANCIAL_SECTOR = "Financial Services"

# grupo -> [(indicador, True si "más alto es mejor")]
GROUPS = {
    "rentabilidad": [("roe", True), ("roa", True), ("operating_margin", True), ("profit_margin", True)],
    "solvencia": [("debt_to_equity", False), ("net_debt_ebitda", False), ("cash_to_debt", True)],
    "liquidez": [("current_ratio", True), ("quick_ratio", True)],
    "caja": [("fcf_margin", True), ("ocf_margin", True), ("fcf_yield", True), ("cash_conversion", True),
             ("ocf_to_debt", True), ("fcf_positive_years", True)],
}
GROUP_LABELS = {"rentabilidad": "Rentabilidad", "solvencia": "Solvencia", "liquidez": "Liquidez", "caja": "Caja"}
NOT_FOR_FINANCIALS = {"debt_to_equity", "net_debt_ebitda", "cash_to_debt", "current_ratio", "quick_ratio", "fcf_margin",
                      "ocf_margin", "fcf_yield", "cash_conversion", "ocf_to_debt", "fcf_positive_years"}


def _fcf_history(ticker: str) -> list[float | None]:
    """Flujo de caja libre de los últimos `FCF_YEARS` años (el más reciente primero; None si falta el dato)."""
    try:
        cash = yf.Ticker(ticker).cashflow
        row = cash.loc["Free Cash Flow"].iloc[:FCF_YEARS]
        return [float(v) if np.isfinite(v) else None for v in row]
    except Exception:
        return []


def _fetch(ticker: str) -> tuple[str, dict | None]:
    try:
        info = yf.Ticker(ticker).info
        data = {k: info.get(k) for k in FIELDS}
        data["fcf_history"] = _fcf_history(ticker)
        data["v"] = VERSION
        return ticker, data if any(data[k] is not None for k in FIELDS[3:]) else None
    except Exception as e:
        log.debug("Sin datos financieros para %s: %s", ticker, e)
        return ticker, None


def ensure_fundamentals(conn: sqlite3.Connection, tickers: list[str], use_cache: bool, ttl_days: int,
                        workers: int) -> dict[str, dict]:
    """Datos financieros de `tickers`. Los guardados hace menos de `ttl_days` días se reutilizan (cambian por trimestre);
    con --no-cache se vuelven a pedir todos."""
    cutoff = (date.today() - timedelta(days=ttl_days)).isoformat()
    cached = {t: d for t, d in ((t, json.loads(d)) for t, d in
                                conn.execute("SELECT ticker, data FROM fundamentals WHERE fetched >= ?", (cutoff,)))
              if d.get("v") == VERSION}
    data = {t: cached[t] for t in tickers if use_cache and t in cached}
    todo = [t for t in tickers if t not in data]
    log.info("Datos financieros: %d ya disponibles, %d a descargar", len(data), len(todo))
    missing = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for ticker, fetched in pool.map(_fetch, todo):
            if fetched is None:
                missing.append(ticker)
                continue
            data[ticker] = fetched
            conn.execute("INSERT OR REPLACE INTO fundamentals (ticker, fetched, data) VALUES (?, ?, ?)",
                         (ticker, date.today().isoformat(), json.dumps(fetched)))
    conn.commit()
    if missing:
        log.warning(E.DAT_NO_FUNDAMENTALS.msg("Sin datos financieros para %d tickers (quedan fuera del score final)"),
                    len(missing))
        log.debug("Sin datos financieros: %s", sorted(missing))
    return data


def indicators(data: dict[str, dict]) -> pd.DataFrame:
    """Indicadores de salud por ticker (columnas de GROUPS) más nombre, sector y capitalización."""
    rows = {}
    for ticker, d in data.items():
        num = {k: (float(v) if isinstance(v, (int, float)) and np.isfinite(v) else np.nan) for k, v in d.items()
               if k not in ("shortName", "sector")}
        revenue = num["totalRevenue"] if num["totalRevenue"] > 0 else np.nan
        debt, cash, ebitda = num["totalDebt"], num["totalCash"], num["ebitda"]
        market_cap, income, ocf = num["marketCap"], num["netIncomeToCommon"], num["operatingCashflow"]
        history = [v for v in d.get("fcf_history") or [] if v is not None]
        net_debt = debt - cash if not np.isnan(debt) and not np.isnan(cash) else np.nan
        if np.isnan(net_debt) or np.isnan(ebitda):
            net_debt_ebitda = np.nan
        elif net_debt <= 0:
            net_debt_ebitda = 0.0                      # más caja que deuda: la mejor situación
        else:
            net_debt_ebitda = net_debt / ebitda if ebitda > 0 else np.inf    # sin EBITDA positivo: la peor
        equity_ok = num["debtToEquity"] >= 0 if not np.isnan(num["debtToEquity"]) else True
        rows[ticker] = {
            "name": d.get("shortName") or ticker, "sector": d.get("sector") or "n/d", "market_cap": num["marketCap"],
            "roe": num["returnOnEquity"], "roa": num["returnOnAssets"], "operating_margin": num["operatingMargins"],
            "profit_margin": num["profitMargins"],
            "debt_to_equity": num["debtToEquity"] if equity_ok else np.inf,   # patrimonio negativo: la peor
            "net_debt_ebitda": net_debt_ebitda,
            "cash_to_debt": cash / debt if debt > 0 and not np.isnan(cash) else (np.inf if debt == 0 else np.nan),
            "current_ratio": num["currentRatio"], "quick_ratio": num["quickRatio"],
            "fcf_margin": num["freeCashflow"] / revenue, "ocf_margin": ocf / revenue,
            "fcf_yield": num["freeCashflow"] / market_cap if market_cap > 0 else np.nan,
            # utilidad que se convierte en caja; sin utilidad positiva no hay base de comparación
            "cash_conversion": min(max(num["freeCashflow"] / income, -1.0), 2.0) if income > 0 else np.nan,
            "ocf_to_debt": ocf / debt if debt > 0 else (np.inf if debt == 0 and not np.isnan(ocf) else np.nan),
            "fcf_positive_years": sum(v > 0 for v in history) / len(history) if len(history) >= 3 else np.nan,
        }
    frame = pd.DataFrame.from_dict(rows, orient="index")
    # Bancos y aseguradoras: su deuda es materia prima del negocio y no informan liquidez corriente. Visa, Mastercard y otras
    # clasificadas como financieras pero con un balance común sí la informan y se miden con los cuatro grupos
    financial = (frame["sector"] == FINANCIAL_SECTOR) & frame["current_ratio"].isna()
    frame.loc[financial, sorted(NOT_FOR_FINANCIALS)] = np.nan
    return frame


def health_score(frame: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.DataFrame:
    """Score de salud 0-100 y los scores de cada grupo (columnas 'rentabilidad'... 'caja', 0-100), más `groups` = cuántos
    grupos se pudieron medir. La salud es el promedio de los grupos medidos con los pesos `weights` (por defecto, iguales;
    un grupo sin medir no cuenta). Sin ningún grupo, el score queda en NaN."""
    groups = {}
    for name, metrics in GROUPS.items():
        # rank ordena también los infinitos: deuda infinita (sin EBITDA o patrimonio negativo) es lo peor y caja sin deuda lo mejor
        ranks = pd.concat([frame[m].rank(pct=True, ascending=up) for m, up in metrics], axis=1)
        groups[name] = ranks.mean(axis=1)
    groups = pd.DataFrame(groups)
    out = (groups * 100).copy()
    out["groups"] = groups.notna().sum(axis=1)
    w = pd.Series({g: (weights or {}).get(g, 1.0) for g in GROUPS})
    average = (groups * w).sum(axis=1, skipna=True) / groups.notna().mul(w).sum(axis=1).replace(0, np.nan)
    out["health"] = average.rank(pct=True) * 100
    return out
