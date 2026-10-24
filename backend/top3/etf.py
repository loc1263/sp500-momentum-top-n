"""Ranking de momentum de los ETFs de Vanguard: retorno ajustado por riesgo, sin backtest.

Para cada ETF y cada plazo de `[etf] horizons_months` se calcula el retorno del plazo dividido por la volatilidad del
plazo (anualizada y llevada a la escala del plazo): cuánto subió por cada unidad de riesgo que corrió. El score es el
promedio de esos cocientes. Es un ranking global de la lista de `[etf] csv`.
"""
import math
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from . import console, errors as E, html_report, rotation, vanguard
from .actual import download_recent
from .config import Config
from .db import open_db
from .logs import log
from .repo import etf as store

TRADING_DAYS_YEAR = 252
SMA_DAYS = 200  # la tendencia se mide contra la media simple de 200 ruedas


def load_universe(path: str | Path) -> pd.DataFrame:
    """Lista de ETFs (columnas ticker, name, category) sin duplicados."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(E.ETF_NO_LIST.msg(f"No existe la lista de ETFs: {p}"))
    df = pd.read_csv(p, dtype=str).fillna("")
    missing = {"ticker", "name", "category"} - set(df.columns)
    if missing:
        raise SystemExit(E.ETF_NO_LIST.msg(f"A {p} le faltan las columnas: {', '.join(sorted(missing))}"))
    for column in ("name", "category"):
        df[column] = df[column].str.strip()
    df["ticker"] = df["ticker"].str.strip().str.upper()
    df = df[df["ticker"] != ""].drop_duplicates("ticker").reset_index(drop=True)
    if df.empty:
        raise SystemExit(E.ETF_NO_LIST.msg(f"La lista de ETFs está vacía: {p}"))
    return df


def score_etfs(prices: pd.DataFrame, horizons: list[int], trading_days_per_month: int = 21,
               risk_free: str | None = None, min_vol: float = 0.0) -> tuple[pd.DataFrame, dict]:
    """Ranking por retorno ajustado por riesgo. `prices` = precios ajustados (fecha x ticker).

    Con `risk_free` (un ticker de la propia tabla, p. ej. un ETF de bonos ultracortos) el retorno de cada plazo es el
    exceso sobre el de esa referencia: sin eso, un ETF casi sin riesgo siempre ganaría. Si la referencia no está
    disponible se calcula sin ella y `result.attrs["risk_free"]` queda en None.

    Con `min_vol` (volatilidad anual) los ETFs de tipo efectivo (letras del Tesoro, bonos ultracortos) quedan fuera
    del ranking: con tan poco riesgo cualquier exceso diminuto sobre la referencia da un score enorme. Se listan en
    `result.attrs["cash_like"]` (la referencia libre de riesgo, aunque no rankee, sigue restándose).

    Devuelve (tabla ordenada de mayor a menor score, {ticker: motivo} de los excluidos). La tabla trae, por ETF:
    `ret_<h>` (retorno de cada plazo), `vol` (volatilidad anualizada del plazo más largo), `max_dd` (caída máxima del
    plazo más largo), `sma_dist` (distancia a la media de 200 ruedas), `score` y `rank`.
    Se excluye el ETF con huecos de precios en la ventana o con menos historia que el plazo más largo.
    """
    longest = max(horizons) * trading_days_per_month
    window = prices.tail(longest + 1)
    excluded = {}
    if len(window) < longest + 1:
        return pd.DataFrame(), {t: f"solo hay {len(window)} ruedas, se necesitan {longest + 1}" for t in prices.columns}
    for t in window.columns:
        if window[t].isna().any():
            excluded[t] = "huecos o historia menor al plazo más largo"
    window = window.drop(columns=list(excluded))
    if risk_free not in window.columns:
        risk_free = None

    out = pd.DataFrame(index=window.columns)
    ratios = []
    for h in sorted(horizons):
        w = window.tail(h * trading_days_per_month + 1)
        ret = w.iloc[-1] / w.iloc[0] - 1
        excess = ret - ret[risk_free] if risk_free else ret
        vol = w.pct_change().dropna().std() * math.sqrt(TRADING_DAYS_YEAR)
        scaled_vol = vol * math.sqrt(h / 12)  # la volatilidad anual llevada a la escala del plazo
        out[f"ret_{h}"] = ret
        ratios.append(excess / scaled_vol.where(scaled_vol > 0))
    out["vol"] = window.pct_change().dropna().std() * math.sqrt(TRADING_DAYS_YEAR)
    out["max_dd"] = (window / window.cummax() - 1).min()
    out["sma_dist"] = window.iloc[-1] / window.tail(SMA_DAYS).mean() - 1
    out["score"] = pd.concat(ratios, axis=1).mean(axis=1, skipna=False)
    flat = out["score"].isna()
    excluded.update({t: "volatilidad nula" for t in out.index[flat]})
    cash_like = [t for t in out.index[~flat] if out.at[t, "vol"] < min_vol]
    out = out[~flat].drop(index=cash_like).sort_values("score", ascending=False)
    out["rank"] = range(1, len(out) + 1)
    out.attrs["risk_free"] = risk_free
    out.attrs["cash_like"] = sorted(cash_like)
    return out, excluded


def _pct(value: float, signed: bool = True) -> str:
    return "n/d" if pd.isna(value) else f"{value * 100:{'+' if signed else ''}.1f}%"


def table_rows(scores: pd.DataFrame, universe: pd.DataFrame, horizons: list[int]) -> tuple[list[str], list[list[str]]]:
    """Encabezados y filas de texto del ranking (para la consola y el HTML)."""
    info = universe.set_index("ticker")
    headers = ["#", "Ticker", "Nombre", "Categoría", "Score", *[f"Ret. {h}m" for h in sorted(horizons)],
               "Vol. anual", "Caída máx.", "vs SMA200"]
    rows = []
    for ticker, r in scores.iterrows():
        rows.append([str(int(r["rank"])), ticker, info.at[ticker, "name"], info.at[ticker, "category"],
                     f"{r['score']:.2f}", *[_pct(r[f"ret_{h}"]) for h in sorted(horizons)], _pct(r["vol"], False),
                     _pct(r["max_dd"]), _pct(r["sma_dist"])])
    return headers, rows


def save_scores(conn: sqlite3.Connection, as_of: str, scores: pd.DataFrame, horizons: list[int]) -> None:
    """Guarda el ranking; repetir la corrida con los mismos datos lo reemplaza."""
    store.replace_scores(conn, as_of, [
        (int(r["rank"]), t, float(r["score"]), float(r["vol"]), float(r["max_dd"]), float(r["sma_dist"]),
         {str(h): float(r[f"ret_{h}"]) for h in horizons})
        for t, r in scores.iterrows()])


def describe_changes(previous_as_of: str | None, changes: dict[str, list[str]], top_n: int) -> str:
    if previous_as_of is None:
        return f"Cambios del top {top_n}: primera corrida guardada, sin ranking anterior para comparar."
    if not changes["entered"] and not changes["exited"]:
        return f"Cambios del top {top_n} vs. {previous_as_of}: ninguno."
    return (f"Cambios del top {top_n} vs. {previous_as_of}: entran {', '.join(changes['entered']) or '-'}; "
            f"salen {', '.join(changes['exited']) or '-'}.")


def refresh_list(cfg: Config) -> None:
    """Agrega a la lista (`[etf] csv`) los ETFs nuevos de Vanguard. Si no se puede, sigue con la lista guardada."""
    etf_cfg, data = cfg.etf, cfg.data
    try:
        etfs = vanguard.fetch_etfs(etf_cfg.list_url, data.user_agent, data.http_timeout)
        added, gone = vanguard.update_list(etf_cfg.csv, etfs)
    except Exception as e:
        log.warning(E.ETF_LIST_UPDATE.msg("No se pudo actualizar la lista desde Vanguard: %s"), e)
        return
    if added:
        log.info("Lista de ETFs: se agregaron %d de Vanguard: %s", len(added), ", ".join(added))
    else:
        log.info("Lista de ETFs: al día con Vanguard (%d ETFs)", len(etfs))
    if gone:
        log.info("Lista de ETFs: Vanguard ya no lista %s (quítalos de %s si dejaron de cotizar)",
                 ", ".join(gone), etf_cfg.csv)


def run_etf(cfg: Config, as_of: str | None = None, top_n: int | None = None, csv_path: str | None = None,
            update_list: bool = True) -> Path:
    """Descarga los precios, calcula el ranking, lo guarda en SQLite, lo imprime y escribe el reporte HTML.

    Con la lista del config (sin `csv_path`) y `[etf] update_list`, antes agrega los ETFs nuevos de Vanguard."""
    etf_cfg = cfg.etf
    if update_list and csv_path is None and etf_cfg.update_list:
        refresh_list(cfg)
    horizons = sorted(etf_cfg.horizons_months)
    top_n = top_n or etf_cfg.top_n
    tdpm = cfg.backtest.trading_days_per_month
    universe = load_universe(csv_path or etf_cfg.csv)
    end_day = datetime.fromisoformat(as_of).date() if as_of else date.today()
    start = (end_day - timedelta(days=max(horizons) * 31 + 60)).isoformat()  # margen para las ruedas necesarias
    log.info("ETFs de Vanguard: %d en la lista | plazos %s meses | datos hasta %s", len(universe), horizons, end_day)

    prices = download_recent(list(universe["ticker"]), start, (end_day + timedelta(days=1)).isoformat(),
                             cfg.data.batch_size)
    prices = prices[prices.index <= pd.Timestamp(end_day)].dropna(axis=1, how="all")
    without_prices = [t for t in universe["ticker"] if t not in prices.columns]
    if without_prices:
        log.warning(E.ETF_NO_PRICES.msg("%d ETFs de la lista sin precios en Yahoo: %s"), len(without_prices),
                    ", ".join(without_prices))

    risk_free = etf_cfg.risk_free_ticker.upper() or None
    min_vol = etf_cfg.min_vol
    scores, excluded = score_etfs(prices, horizons, tdpm, risk_free, min_vol)
    if risk_free and not scores.empty and scores.attrs["risk_free"] is None:
        log.warning(E.ETF_NO_RISK_FREE.msg("La referencia libre de riesgo %s no está disponible: el score se calcula "
                                           "sin restarla"), risk_free)
    if excluded:
        log.warning(E.ETF_EXCLUDED.msg("%d ETFs fuera del ranking (huecos o poca historia): %s"), len(excluded),
                    ", ".join(sorted(excluded)))
    if scores.empty:
        raise SystemExit(E.ETF_EMPTY.msg("Ningún ETF tiene historia suficiente para el plazo más largo."))
    data_day = prices.index[-1].date().isoformat()

    if as_of:  # consulta puntual al pasado: no se guarda ni se compara, para no mezclarla con el historial real
        note = "Consulta a una fecha pedida: no se guarda ni se compara con otras corridas."
    else:
        conn = open_db(cfg.data.db_path)
        try:
            prev_as_of, prev_top = store.previous_top(conn, data_day, top_n)
            save_scores(conn, data_day, scores, horizons)
        finally:
            conn.close()
        note = describe_changes(prev_as_of, rotation.diff_picks(prev_top, list(scores.index[:top_n])), top_n)

    headers, rows = table_rows(scores, universe, horizons)
    excluded_note = ("Fuera del ranking: " + ", ".join(f"{t} ({why})" for t, why in sorted(excluded.items()))
                     if excluded else "")
    cash_like = scores.attrs["cash_like"]
    cash_note = (f"Tipo efectivo, fuera del ranking (volatilidad anual < {min_vol * 100:g}%): {', '.join(cash_like)}"
                 if cash_like else "")
    notes = [note, excluded_note, cash_note]
    ref = scores.attrs["risk_free"]
    console.print_etf(data_day, horizons, top_n, len(scores), headers, rows, notes, bool(as_of), ref)
    return html_report.etf_report(cfg, data_day, horizons, top_n, headers, rows, notes, bool(as_of), ref)
