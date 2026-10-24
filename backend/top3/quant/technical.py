"""Score técnico de las acciones: indicadores clásicos calculados con los precios y el volumen de cada día.

Cada indicador se traduce a una señal de 0 a 1 (1 = lo más alcista), las señales se promedian en cuatro grupos y el score es
la posición (0-100) de cada acción entre las demás según el promedio de los grupos:

- Tendencia: alineación de medias móviles exponenciales (precio sobre las EMA de 20, 50 y 200, EMA 20 sobre la 50 y la 50
  sobre la 200) y dirección y fuerza de la tendencia (ADX de 14 con +DI / -DI).
- Impulso: MACD (12, 26, 9), RSI de 14, estocástico lento (14, 3) y posición en las bandas de Bollinger (20, 2).
- Volumen: OBV (acumulado de volumen según el precio sube o baja) sobre su media y su nivel de hace 20 ruedas, y MFI de 14
  (el RSI ponderado por volumen).
- Posición: cercanía al máximo de 52 semanas y lugar dentro del rango de 52 semanas.

El RSI, el estocástico y el MFI favorecen la zona alcista (50-70, 50-80 y 50-70) y penalizan la sobrecompra, en vez de
premiar cualquier valor alto.
"""
import numpy as np
import pandas as pd

DAY_YEAR = 252
GROUPS = ["tendencia", "impulso", "volumen", "posicion"]
GROUP_LABELS = {"tendencia": "Tendencia", "impulso": "Impulso", "volumen": "Volumen", "posicion": "Posición"}


def ema(x: pd.DataFrame, span: int) -> pd.DataFrame:
    return x.ewm(span=span, adjust=False, min_periods=span).mean()


def wilder(x: pd.DataFrame, n: int) -> pd.DataFrame:
    """Media de Wilder (la que usan RSI, ADX y MFI): EMA con alpha = 1 / n."""
    return x.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    delta = close.diff()
    gain, loss = wilder(delta.clip(lower=0), n), wilder((-delta).clip(lower=0), n)
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan)).fillna(np.inf)   # sin pérdidas: RSI = 100


def macd(close: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(línea MACD, histograma = línea - señal)."""
    line = ema(close, fast) - ema(close, slow)
    return line, line - line.ewm(span=signal, adjust=False, min_periods=signal).mean()


def stochastic(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, n: int = 14, smooth: int = 3) -> pd.DataFrame:
    """%K lento: el %K de n ruedas suavizado con una media simple de `smooth`."""
    lowest, highest = low.rolling(n).min(), high.rolling(n).max()
    return (100 * (close - lowest) / (highest - lowest).replace(0, np.nan)).rolling(smooth).mean()


def adx(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, n: int = 14) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(ADX, +DI, -DI)."""
    up, down = high.diff(), -low.diff()
    plus = up.where((up > down) & (up > 0), 0.0)
    minus = down.where((down > up) & (down > 0), 0.0)
    prev = close.shift()
    true_range = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()]).groupby(level=0).max()
    atr = wilder(true_range, n)
    plus_di, minus_di = 100 * wilder(plus, n) / atr, 100 * wilder(minus, n) / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return wilder(dx, n), plus_di, minus_di


def obv(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    return (np.sign(close.diff()).fillna(0) * volume).cumsum()


def mfi(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, volume: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    typical = (high + low + close) / 3
    flow = typical * volume
    up = flow.where(typical > typical.shift(), 0.0).rolling(n).sum()
    down = flow.where(typical < typical.shift(), 0.0).rolling(n).sum()
    return 100 - 100 / (1 + up / down.replace(0, np.nan)).fillna(np.inf)     # sin flujo vendedor: MFI = 100


def _peak_score(value: pd.Series, low: float, peak: float, top: float) -> pd.Series:
    """0 en `low` (o menos), sube linealmente a 1 en `peak` y baja a 0,5 en `top` (sobrecompra)."""
    rising = ((value - low) / (peak - low)).clip(0, 1)
    falling = 1 - 0.5 * ((value - peak) / (top - peak)).clip(0, 1)
    return rising.where(value <= peak, falling)


def indicators(ohlcv: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Valor de cada indicador en la última rueda, por ticker. Un ticker sin las últimas 252 ruedas completas queda en NaN."""
    high, low, close, volume = (ohlcv[k].tail(DAY_YEAR + 60) for k in ("high", "low", "close", "volume"))
    ema20, ema50, ema200 = ema(close, 20), ema(close, 50), ema(close, 200)
    line, hist = macd(close)
    sma20, std20 = close.rolling(20).mean(), close.rolling(20).std()
    adx14, plus_di, minus_di = adx(high, low, close)
    flow = obv(close, volume)
    high52, low52 = high.rolling(DAY_YEAR).max(), low.rolling(DAY_YEAR).min()
    last = lambda x: x.iloc[-1]
    out = pd.DataFrame({
        "close": last(close), "ema20": last(ema20), "ema50": last(ema50), "ema200": last(ema200),
        "macd": last(line), "macd_signal": last(line - hist), "macd_hist": last(hist),
        "macd_hist_3d": last(hist.shift(3)),
        "rsi": last(rsi(close)), "stoch": last(stochastic(high, low, close)),
        "pct_b": last((close - (sma20 - 2 * std20)) / (4 * std20).replace(0, np.nan)),
        "adx": last(adx14), "plus_di": last(plus_di), "minus_di": last(minus_di),
        "obv": last(flow), "obv_ema": last(ema(flow, 20)), "obv_20d": last(flow.shift(20)),
        "mfi": last(mfi(high, low, close, volume)), "high52": last(high52), "low52": last(low52),
    })
    out[~close.tail(DAY_YEAR).notna().all()] = np.nan                 # exige un año completo de ruedas
    return out


def technical_score(ind: pd.DataFrame) -> pd.DataFrame:
    """Score técnico 0-100 (`technical`), el de cada grupo (0-100) y los indicadores para mostrar (RSI, MACD y distancia a
    las EMA de 50 y 200)."""
    c = ind["close"]
    alignment = pd.concat([c > ind["ema20"], c > ind["ema50"], c > ind["ema200"], ind["ema20"] > ind["ema50"],
                           ind["ema50"] > ind["ema200"]], axis=1).astype(float).mean(axis=1)
    direction = 0.5 + 0.5 * np.sign(ind["plus_di"] - ind["minus_di"]) * (ind["adx"].clip(upper=50) / 50)
    macd_votes = pd.concat([ind["macd"] > ind["macd_signal"], ind["macd"] > 0,
                            ind["macd_hist"] > ind["macd_hist_3d"]], axis=1).astype(float).mean(axis=1)
    groups = pd.DataFrame({
        "tendencia": pd.concat([alignment, direction], axis=1).mean(axis=1),
        "impulso": pd.concat([macd_votes, _peak_score(ind["rsi"], 30, 70, 100),
                              _peak_score(ind["stoch"], 0, 80, 100), ind["pct_b"].clip(0, 1)], axis=1).mean(axis=1),
        "volumen": pd.concat([((ind["obv"] > ind["obv_ema"]).astype(float) + (ind["obv"] > ind["obv_20d"])) / 2,
                              _peak_score(ind["mfi"], 30, 70, 100)], axis=1).mean(axis=1),
        "posicion": pd.concat([c / ind["high52"], (c - ind["low52"]) / (ind["high52"] - ind["low52"]).replace(0, np.nan)],
                              axis=1).mean(axis=1),
    })
    groups = groups.where(c.notna() & ind["ema200"].notna() & ind["high52"].notna())
    out = (groups * 100).copy()
    out["technical"] = groups.mean(axis=1, skipna=False).rank(pct=True) * 100
    out["rsi"], out["macd_hist"] = ind["rsi"], ind["macd_hist"] / c
    out["vs_ema50"], out["vs_ema200"] = c / ind["ema50"] - 1, c / ind["ema200"] - 1
    return out
