"""Markowitz sobre unas pocas acciones: tres carteras de la frontera eficiente (sin posiciones cortas, con un máximo por
acción y por sector).

- Máximo retorno: el mayor retorno esperado con volatilidad anual de hasta `vol_target`.
- Máximo Sharpe: la mejor relación entre el exceso de retorno sobre la tasa libre de riesgo y la volatilidad.
- Mínima varianza: la de menor volatilidad posible.

Entradas: el retorno esperado de cada acción es su retorno anual de los últimos 252 días (limitado a +-100%) encogido
hacia un retorno de largo plazo (`prior` = tasa libre de riesgo + prima de mercado), con `mu_shrink` como peso del dato
propio: el retorno pasado de una sola acción es muy ruidoso y el de las líderes de momentum, desmesurado. La covarianza es
la de Ledoit-Wolf sobre esos mismos 252 días. Los pesos salen sobre todo del riesgo y, en menor medida, del retorno pasado.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

DAY_YEAR = 252


def inputs(prices: pd.DataFrame, mu_shrink: float, prior: float) -> tuple[pd.Series, pd.DataFrame]:
    """(retorno esperado anual, covarianza anual) de las columnas de `prices` (últimas 252 ruedas, sin huecos)."""
    returns = prices.tail(DAY_YEAR + 1).pct_change().iloc[1:]
    mean = (returns.mean() * DAY_YEAR).clip(-1, 1)
    mu = mu_shrink * mean + (1 - mu_shrink) * prior
    sigma = pd.DataFrame(LedoitWolf().fit(returns.to_numpy()).covariance_ * DAY_YEAR, index=returns.columns,
                         columns=returns.columns)
    return mu, sigma


def _solve(objective, constraints, n: int, w_max: float, start: np.ndarray) -> np.ndarray | None:
    res = minimize(objective, start, bounds=[(0.0, w_max)] * n, constraints=constraints, method="SLSQP",
                   options={"maxiter": 500, "ftol": 1e-12})
    if not res.success:
        return None
    w = np.clip(res.x, 0, None)
    return w / w.sum()


def feasible_sector_cap(sectors: pd.Series, w_max: float, sector_max: float) -> float:
    """`sector_max`, o el menor tope mayor que él con el que se puede invertir todo: con pocos sectores (o sectores con pocas
    acciones y `w_max`) el tope pedido puede no dejar colocar el 100%."""
    sizes = sectors.value_counts().to_numpy()
    cap = sector_max
    while np.minimum(cap, sizes * w_max).sum() < 1 - 1e-9 and cap < 1:
        cap = min(cap + 0.01, 1.0)
    return cap


def frontier(mu: pd.Series, sigma: pd.DataFrame, vol_target: float, w_max: float, risk_free: float,
             sectors: pd.Series | None = None, sector_max: float = 1.0) -> dict:
    """Las carteras (máximo retorno con vol <= vol_target, máximo Sharpe y mínima varianza) con sus pesos, retorno
    esperado, volatilidad y Sharpe (y su peso por sector), más `min_vol`, la menor volatilidad posible. Si `vol_target` es
    menor que `min_vol`, no hay cartera de máximo retorno y se omite. Con menos acciones que 1/w_max, o sectores que no
    alcanzan para colocar todo con `sector_max`, el tope se sube lo mínimo necesario (`sector_max` en el resultado)."""
    n = len(mu)
    w_max = max(w_max, 1 / n + 1e-9)
    sectors = sectors.reindex(mu.index) if sectors is not None else pd.Series("todas", index=mu.index)
    requested, sector_max = sector_max, feasible_sector_cap(sectors, w_max, sector_max)
    m, cov = mu.to_numpy(), sigma.to_numpy()
    vol = lambda w: float(np.sqrt(w @ cov @ w))
    full = {"type": "eq", "fun": lambda w: w.sum() - 1}
    groups = [np.flatnonzero((sectors == s).to_numpy()) for s in sectors.unique()]
    by_sector = [{"type": "ineq", "fun": lambda w, idx=idx: sector_max - w[idx].sum()} for idx in groups] \
        if sector_max < 1 else []
    start = np.full(n, 1 / n)

    min_var = _solve(lambda w: w @ cov @ w, [full, *by_sector], n, w_max, start)
    max_sharpe = _solve(lambda w: -(m @ w - risk_free) / np.sqrt(w @ cov @ w), [full, *by_sector], n, w_max, min_var)
    cap = {"type": "ineq", "fun": lambda w: vol_target**2 - w @ cov @ w}
    min_vol = vol(min_var)
    max_return = (_solve(lambda w: -(m @ w), [full, cap, *by_sector], n, w_max, min_var)
                  if min_vol <= vol_target else None)

    portfolios = []
    for key, label, w in (("max_return", f"Máximo retorno (volatilidad hasta {vol_target:.0%})", max_return),
                          ("max_sharpe", "Máximo Sharpe", max_sharpe), ("min_var", "Mínima varianza", min_var)):
        if w is None:
            continue
        w = pd.Series(w, index=mu.index)
        ret, risk = float(mu @ w), vol(w.to_numpy())
        by = w.groupby(sectors).sum()
        portfolios.append({"key": key, "label": label, "exp_return": ret, "vol": risk, "sharpe": (ret - risk_free) / risk,
                           "weights": [{"ticker": t, "weight": float(x)}
                                       for t, x in w[w > 1e-4].sort_values(ascending=False).items()],
                           "sectors": [{"sector": s, "weight": float(x)} for s, x in by[by > 1e-4].sort_values(ascending=False).items()]})
    return {"portfolios": portfolios, "min_vol": min_vol, "vol_target": vol_target, "w_max": w_max,
            "sector_max": sector_max, "sector_relaxed": bool(sector_max > requested + 1e-9)}
