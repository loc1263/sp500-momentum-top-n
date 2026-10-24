"""Score de momentum de las acciones del S&P 500: promedio del ranking en el retorno de 12 y de 6 meses, sin contar el
último mes (momentum 12-1 y 6-1). Solo usa precios hasta la fecha."""
import pandas as pd

DAY_YEAR = 252
MONTH = 21


def momentum_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Momentum 12-1 y 6-1 de cada ticker en la última rueda de `prices` (fecha x ticker). Un ticker con huecos en el
    último año o sin un año de historia queda en NaN."""
    window = prices.tail(DAY_YEAR + 1)
    if len(window) < DAY_YEAR + 1:
        return pd.DataFrame(columns=["mom_12_1", "mom_6_1"], dtype=float)
    skip = window.iloc[-1 - MONTH]                       # precio de hace un mes: el último mes no cuenta
    out = pd.DataFrame({"mom_12_1": skip / window.iloc[0] - 1, "mom_6_1": skip / window.iloc[-127] - 1})
    out[~window.notna().all()] = float("nan")
    return out


def momentum_score(returns: pd.DataFrame) -> pd.Series:
    """Score 0-100: posición de cada acción (100 = la mejor) según el promedio de su ranking porcentual en el momentum
    12-1 y 6-1 entre todas las que tienen ambos."""
    both = returns.dropna(subset=["mom_12_1", "mom_6_1"])
    average = both[["mom_12_1", "mom_6_1"]].rank(pct=True).mean(axis=1)
    return (average.rank(pct=True) * 100).rename("momentum")
