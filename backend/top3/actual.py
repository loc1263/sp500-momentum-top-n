"""Top N actual del S&P 500: las acciones que más subieron en los últimos N meses (el criterio del backtest, hoy)."""
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from . import console, errors as E, html_report, rotation, universe as universes
from .config import Config, DataConfig
from .constituents import download_current_constituents
from .db import fetched_today, get_meta, open_db
from .engine import rank_returns
from .logs import log
from .prices import fetch_prices
from .repo import constituents as constituents_store, picks as store, prices as prices_store
from .shares import ensure_shares
from .universe import Universe


def get_current_tickers(conn: sqlite3.Connection, aliases: dict[str, str], use_cache: bool,
                        settings: DataConfig) -> list[str]:
    """Lista actual del S&P 500 (descargada hoy o la guardada) con los alias aplicados."""
    if not (use_cache and fetched_today(conn, "constituents_current_fetched")):
        try:
            download_current_constituents(conn, settings)
        except Exception:
            log.exception(E.NET_CURRENT_LIST.msg("No se pudo descargar la lista actual; se usa la guardada en SQLite"))
    else:
        log.info("Lista actual del S&P 500: usando caché SQLite (descargada hoy)")
    tickers = constituents_store.current(conn)
    if not tickers:
        raise SystemExit(E.DAT_NO_CURRENT.msg("No hay lista actual del S&P 500 (ni descargada ni en SQLite)."))
    tickers = list(dict.fromkeys(aliases.get(t, t) for t in tickers))
    log.info("Tickers del S&P 500 actual: %d", len(tickers))
    return tickers


def download_recent(tickers: list[str], start: str, end: str, batch_size: int) -> pd.DataFrame:
    """Precios ajustados de `tickers` en lotes (no se guardan: solo la ventana reciente)."""
    long, _ = fetch_prices(tickers, start, end, batch_size)
    long["date"] = pd.to_datetime(long["date"])
    return long.pivot(index="date", columns="ticker", values="close").sort_index()


def get_prices(conn: sqlite3.Connection, tickers: list[str], start: str, end: str, use_cache: bool,
               settings: DataConfig) -> pd.DataFrame:
    """Precios desde `start`: usa la base SQLite si se descargó hoy (la deja el backtest) y completa lo que falte."""
    frames = []
    cached_start = get_meta(conn, "prices_start")
    if use_cache and fetched_today(conn, "prices_fetched") and cached_start and cached_start <= start:
        stored = prices_store.matrix_since(conn, start)
        stored = stored[[t for t in tickers if t in stored.columns]]
        log.info("Precios: %d tickers desde la caché SQLite (hasta %s)", stored.shape[1],
                 stored.index.max().date() if len(stored) else None)
        frames.append(stored)
        missing = [t for t in tickers if t not in stored.columns]
    else:
        missing = list(tickers)
    if missing:
        log.info("Descargando precios de %d tickers (%s a %s)...", len(missing), start, end)
        frames.append(download_recent(missing, start, end, settings.batch_size))
    prices = pd.concat(frames, axis=1).sort_index() if frames else pd.DataFrame()
    return prices.loc[:, ~prices.columns.duplicated()]


def compute_top(prices: pd.DataFrame, months: int, top_n: int, trading_days_per_month: int,
                universe: Universe | None = None, extra: int = 0) -> tuple[pd.Series, pd.DataFrame]:
    """Los `top_n` (+ `extra` suplentes) tickers con mayor retorno en los últimos `months` meses y la ventana usada."""
    lookback = months * trading_days_per_month
    prices = prices.dropna(axis=1, how="all")
    if universe is not None:
        last_px = prices.ffill().iloc[-1]
        big = universe.select(list(prices.columns), last_px)
        log.info("Filtro de capitalización (>= US$ %.0f B): %d -> %d tickers",
                 universe.min_cap_usd / 1e9, prices.shape[1], len(big))
        prices = prices[big]
    window = prices.tail(lookback + 1)
    if len(window) < lookback + 1:
        raise SystemExit(E.ACT_SHORT_WINDOW.msg(f"Solo hay {len(window)} ruedas de precios; se necesitan {lookback + 1}."))
    # Misma regla que el backtest: un ticker con huecos en la ventana no puede rankearse
    incomplete = [t for t in window.columns if window[t].isna().any()]
    if incomplete:
        log.warning(E.ACT_GAPS.msg("%d tickers con huecos en la ventana quedan fuera del ranking: %s%s"), len(incomplete),
                    ", ".join(incomplete[:15]), " ..." if len(incomplete) > 15 else "")
    returns = rank_returns(prices, list(prices.columns), prices.index[-1], lookback)
    window = window.dropna(axis=1, how="any")
    log.debug("Ventana: %s a %s, %d ruedas, %d tickers completos",
              window.index[0].date(), window.index[-1].date(), len(window), window.shape[1])
    log.debug("Top 10 retornos:\n%s", returns.head(10).round(4).to_string())
    return returns.head(top_n + extra), window


@dataclass
class ActualResult:
    """El Top actual calculado: los elegidos, los suplentes y la ventana de precios usada."""

    months: int
    top_n: int
    min_cap_b: float | None
    as_of: date
    window: pd.DataFrame
    picks: list[store.Pick]
    alternates: list[store.Pick]


def compute_actual(conn: sqlite3.Connection, cfg: Config, months: int, top_n: int, min_cap_b: float | None,
                   use_cache: bool) -> ActualResult:
    """Baja (o toma de SQLite) los datos y calcula el Top actual y sus suplentes. No guarda ni imprime nada."""
    settings = cfg.data
    today = date.today()
    start = (today - timedelta(days=months * 31 + 45)).isoformat()  # margen para cubrir las ruedas necesarias
    end = (today + timedelta(days=1)).isoformat()
    tickers = get_current_tickers(conn, cfg.tickers.aliases, use_cache, settings)
    prices = get_prices(conn, tickers, start, end, use_cache, settings)

    known, universe = None, None
    if min_cap_b:
        known = ensure_shares(conn, list(prices.columns), use_cache, settings)
        universe = Universe(known, min_cap_b)

    ranked, window = compute_top(prices, months, top_n, cfg.backtest.trading_days_per_month, universe,
                                 cfg.backtest.alternates)
    shares = ensure_shares(conn, list(ranked.index), use_cache, settings, known=known)
    picks = []
    for rank, (ticker, ret) in enumerate(ranked.items(), 1):
        price = float(window[ticker].iloc[-1])
        cap = price * shares[ticker] if ticker in shares else None
        picks.append(store.Pick(rank, ticker, float(ret), price, cap))
    return ActualResult(months, top_n, min_cap_b, window.index[-1].date(), window, picks[:top_n], picks[top_n:])


def save_actual(conn: sqlite3.Connection, result: ActualResult, today: date | None = None) -> list[str]:
    """Guarda el Top actual (repetir la corrida con los mismos datos reemplaza la anterior) y devuelve las notas de
    rotación: qué entró y salió contra la corrida anterior y cuándo toca rebalancear."""
    as_of, months, min_cap_b = result.as_of.isoformat(), result.months, result.min_cap_b
    previous_as_of, previous = store.previous_picks(conn, as_of, months, min_cap_b)
    store.replace_picks(conn, datetime.now().isoformat(timespec="seconds"), as_of, months, min_cap_b,
                        result.picks, result.alternates)
    log.info("Resultado guardado en SQLite (tabla actual_picks)")
    return rotation.describe(previous_as_of, rotation.diff_picks(previous, [p.ticker for p in result.picks]),
                             store.anchor_date(conn, months, min_cap_b), months, today or date.today())


def present_actual(cfg: Config, result: ActualResult, notes: list[str]) -> Path:
    """Imprime el Top actual por consola y escribe el reporte HTML."""
    months = result.months
    weight = 100 / len(result.picks)
    headers = ["#", "Ticker", f"Retorno {months} meses", "Cap. aprox. (US$ B)", "Precio (US$)", "Peso"]

    def fmt(p, w):
        return [str(p.rank), p.ticker, f"{p.return_lookback * 100:+.1f}%",
                f"{p.market_cap / 1e9:,.0f}" if p.market_cap else "n/d", f"{p.price:,.2f}", w]

    table = [fmt(p, f"{weight:.1f}%") for p in result.picks]
    alternates = [fmt(p, "-") for p in result.alternates]
    console.print_actual(result.top_n, months, result.min_cap_b, result.as_of, result.window, headers, table, weight,
                         notes, alternates)
    return html_report.actual_report(cfg, result.top_n, months, result.min_cap_b, result.as_of, result.window,
                                     headers, table, weight, notes, alternates)


def run_actual(cfg: Config, months: int, top_n: int, min_cap_b: float | None, use_cache: bool) -> Path:
    """Calcula el Top actual, lo guarda en SQLite, lo imprime y escribe el reporte HTML."""
    log.info("Plazo: %d meses | Top %d | Universo: %s", months, top_n, universes.label(min_cap_b))
    conn = open_db(cfg.data.db_path)
    try:
        result = compute_actual(conn, cfg, months, top_n, min_cap_b, use_cache)
        notes = save_actual(conn, result)
    finally:
        conn.close()
    return present_actual(cfg, result, notes)
