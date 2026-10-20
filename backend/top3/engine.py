"""Motor del backtest: cada N meses se compran, con ponderación igual, las N acciones que más subieron."""
from dataclasses import dataclass

import pandas as pd

from . import errors as E
from .constituents import Constituents
from .logs import log
from .universe import Universe

MIN_TICKERS = 10  # con menos candidatos el ranking no es representativo y el rebalanceo se omite


@dataclass
class BacktestResult:
    """Resultado de una corrida. Los retornos van en porcentaje (retorno total y CAGR)."""

    equity_curve: pd.Series
    history: list[dict]   # un dict por rebalanceo: date, picks, returns ({ticker: retorno}) y luego caps
    final_capital: float
    total_return_pct: float
    cagr_pct: float


Skipped = dict[E.Code, set[str]]  # rebalanceos omitidos, por motivo: fechas (se avisan juntos al final)

_SKIP_TEXT = {E.BKT_NO_CONSTITUENTS: "Sin constituyentes", E.BKT_FEW_TICKERS: "Pocos tickers disponibles",
              E.BKT_SHORT_WINDOW: "Ventana de precios insuficiente"}


def _skip(code: E.Code, when: pd.Timestamp, skipped: Skipped | None, detail: str = "") -> None:
    """Un rebalanceo que se omite. Con `skipped` solo se anota la fecha (quien lo pasó avisa una vez con
    `report_skipped`); sin él se avisa en el momento."""
    if skipped is None:
        log.warning(code.msg("%s en %s%s, se omite"), _SKIP_TEXT[code], when.date(), detail)
    else:
        skipped.setdefault(code, set()).add(when.date().isoformat())
        log.debug("%s en %s%s, se omite", _SKIP_TEXT[code], when.date(), detail)


def report_skipped(skipped: Skipped, where: str) -> None:
    """Un solo aviso por motivo con el rango de fechas omitidas (en vez de uno por fecha y corrida)."""
    for code, dates in skipped.items():
        ordered = sorted(dates)
        log.warning(code.msg("%s en %d fechas de rebalanceo (de %s a %s), omitidas - %s"), _SKIP_TEXT[code],
                    len(ordered), ordered[0], ordered[-1], where)


def eligible_tickers(constituents_now: list[str], prices: pd.DataFrame, when: pd.Timestamp,
                     universe: Universe | None) -> list[str]:
    """Constituyentes con precios y, si hay universo, con capitalización suficiente."""
    available = [t for t in constituents_now if t in prices.columns]
    log.debug("%s: %d/%d constituyentes con precios", when.date(), len(available), len(constituents_now))
    if universe is not None and available:
        last_px = prices.loc[:when, available].ffill().iloc[-1]
        big = universe.select(available, last_px)
        log.debug("%s: filtro de capitalización (>= US$ %.0f B): %d -> %d tickers", when.date(),
                  universe.min_cap_usd / 1e9, len(available), len(big))
        return big
    return available


def rank_returns(prices: pd.DataFrame, tickers: list[str], when: pd.Timestamp, lookback_days: int,
                 skipped: Skipped | None = None) -> pd.Series | None:
    """Retorno de cada ticker en las últimas `lookback_days` ruedas hasta `when`, de mayor a menor.
    None si no hay ruedas suficientes."""
    window = prices.loc[:when, tickers].tail(lookback_days + 1).dropna(axis=1, how="any")
    log.debug("%s: ventana shape=%s (desde %s)", when.date(), window.shape,
              window.index[0].date() if len(window) else None)
    if len(window) < lookback_days + 1:
        _skip(E.BKT_SHORT_WINDOW, when, skipped, f" (solo {len(window)} filas de precios, <{lookback_days + 1})")
        return None
    return (window.iloc[-1] / window.iloc[0] - 1).dropna().sort_values(ascending=False)


def hold_return(prices: pd.DataFrame, tickers: list[str], start: pd.Timestamp,
                end: pd.Timestamp) -> tuple[float, list[str], pd.Timestamp] | None:
    """Retorno medio (ponderación igual) de mantener `tickers` entre `start` y `end`.
    Devuelve (retorno, tickers con datos, última rueda con precios) o None si no hay datos suficientes."""
    held = prices.loc[start:end, tickers].dropna(axis=1)
    if len(held) <= 1:
        return None
    return float((held.iloc[-1] / held.iloc[0] - 1).mean()), list(held.columns), held.index[-1]


def run_backtest(constituents: Constituents, prices: pd.DataFrame, start_date, end_date, lookback_days: int,
                 freq: str, initial_capital: float, top_n: int, universe: Universe | None = None,
                 skipped: Skipped | None = None) -> BacktestResult:
    """Simula la estrategia entre `start_date` y `end_date`, rebalanceando según `freq` (p. ej. "4MS").

    Lanza RuntimeError si no hubo ningún rebalanceo (fechas fuera del histórico, universo demasiado chico...).
    """
    rebalance_dates = pd.date_range(start=start_date, end=end_date, freq=freq)
    log.info("Rebalanceos: %d (%s a %s, freq=%s)", len(rebalance_dates),
             rebalance_dates[0].date() if len(rebalance_dates) else None,
             rebalance_dates[-1].date() if len(rebalance_dates) else None, freq)

    equity, dates, history = [], [], []
    capital = initial_capital
    held: list[str] | None = None
    entry_date = None

    for when in rebalance_dates:
        constituents_now = constituents.on_date(when)
        if not constituents_now:
            _skip(E.BKT_NO_CONSTITUENTS, when, skipped)
            continue
        candidates = eligible_tickers(constituents_now, prices, when, universe)
        if len(candidates) < MIN_TICKERS:
            _skip(E.BKT_FEW_TICKERS, when, skipped)
            continue
        returns = rank_returns(prices, candidates, when, lookback_days, skipped)
        if returns is None:
            continue

        picks = returns.head(top_n)
        history.append({"date": when.strftime("%Y-%m-%d"), "picks": picks.index.tolist(),
                        "returns": picks.round(4).to_dict()})

        if held is not None:  # rendimiento del período anterior
            period = hold_return(prices, held, entry_date, when)
            if period is not None:
                period_ret, with_data, _ = period
                log.debug("Período %s→%s: tickers=%s retorno=%.4f", entry_date.date(), when.date(),
                          with_data, period_ret)
                capital *= 1 + period_ret
            else:
                log.warning(E.BKT_NO_PRICES.msg("Período %s→%s: sin datos para %s"), entry_date.date(), when.date(), held)

        held, entry_date = picks.index.tolist(), when
        equity.append(capital)
        dates.append(when)
        log.info("%s → Top %d: %s | Capital: $%s", when.date(), top_n, held, f"{capital:,.0f}")

    if held is not None:  # último tramo hasta el final
        period = hold_return(prices, held, entry_date, end_date)
        if period is not None:
            period_ret, with_data, last_day = period
            log.debug("Último tramo %s→%s: tickers=%s retorno=%.4f", entry_date.date(), last_day.date(),
                      with_data, period_ret)
            capital *= 1 + period_ret
            equity.append(capital)
            dates.append(last_day)

    if not dates:
        raise RuntimeError(E.BKT_EMPTY.msg("El backtest no generó ningún rebalanceo; revisa fechas/histórico en la configuración."))

    years = max((dates[-1] - dates[0]).days / 365.25, 0.1)
    return BacktestResult(
        equity_curve=pd.Series(equity, index=dates),
        history=history,
        final_capital=capital,
        total_return_pct=(capital / initial_capital - 1) * 100,
        cagr_pct=((capital / initial_capital) ** (1 / years) - 1) * 100,
    )
