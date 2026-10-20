"""Precios como matriz numpy con lo necesario para consultar ventanas sin copiar historia en cada llamada.

El backtest consulta miles de veces "retorno de estos tickers en las últimas N ruedas hasta tal fecha" y "retorno de
mantenerlos entre dos fechas". Con pandas (`prices.loc[:fecha, tickers].tail(n)`) cada consulta copia toda la
historia hasta esa fecha. Aquí se calcula una sola vez la matriz de precios, los NaN acumulados (para saber en O(1)
si una ventana está completa) y, a pedido, los precios con relleno hacia adelante; cada consulta es indexar filas.

Las reglas son las mismas de siempre: una ventana vale solo para los tickers sin ningún hueco (NaN) en ella.
"""
import numpy as np
import pandas as pd


class PriceMatrix:
    """Precios (fecha x ticker) listos para consultar. El índice debe estar ordenado de menor a mayor."""

    def __init__(self, prices: pd.DataFrame):
        self.index = pd.DatetimeIndex(prices.index)
        self.columns = list(prices.columns)
        self._col = {t: i for i, t in enumerate(self.columns)}
        self.px = prices.to_numpy(dtype=float)
        # nan_cum[k, j] = cantidad de NaN del ticker j en las filas [0, k): una ventana [a, b) está completa si
        # nan_cum[b, j] == nan_cum[a, j]
        nan_cum = np.zeros((len(self.px) + 1, self.px.shape[1]), dtype=np.int32)
        np.cumsum(np.isnan(self.px), axis=0, out=nan_cum[1:])
        self._nan_cum = nan_cum
        self._ffilled: np.ndarray | None = None

    @classmethod
    def of(cls, prices: "pd.DataFrame | PriceMatrix") -> "PriceMatrix":
        return prices if isinstance(prices, cls) else cls(prices)

    def __contains__(self, ticker: str) -> bool:
        return ticker in self._col

    def _cols(self, tickers: list[str]) -> np.ndarray:
        return np.fromiter((self._col[t] for t in tickers), dtype=np.intp, count=len(tickers))

    def rows_until(self, when) -> int:
        """Cantidad de ruedas con fecha <= `when` (la última es la fila `rows_until(when) - 1`)."""
        return int(self.index.searchsorted(pd.Timestamp(when), side="right"))

    def returns(self, tickers: list[str], when, lookback_days: int) -> pd.Series:
        """Retorno de cada ticker en las últimas `lookback_days` ruedas hasta `when`, de mayor a menor.

        Solo entran los tickers sin huecos en la ventana de `lookback_days + 1` ruedas. Exige que haya al menos
        esas ruedas hasta `when` (`rows_until(when) >= lookback_days + 1`)."""
        end = self.rows_until(when)
        start = end - (lookback_days + 1)
        if start < 0:
            raise ValueError(f"{when}: solo hay {end} ruedas, se necesitan {lookback_days + 1}")
        cols = self._cols(tickers)
        complete = self._nan_cum[end, cols] == self._nan_cum[start, cols]
        first, last = self.px[start, cols][complete], self.px[end - 1, cols][complete]
        kept = [t for t, ok in zip(tickers, complete) if ok]
        return (pd.Series(last / first - 1, index=kept)).dropna().sort_values(ascending=False)

    def window_shape(self, tickers: list[str], when, lookback_days: int) -> tuple[tuple[int, int], object]:
        """((ruedas, tickers completos), primera fecha) de la ventana, para el log de depuración."""
        end = self.rows_until(when)
        start = max(end - (lookback_days + 1), 0)
        cols = self._cols(tickers)
        complete = int((self._nan_cum[end, cols] == self._nan_cum[start, cols]).sum())
        return (end - start, complete), (self.index[start].date() if end > start else None)

    def hold_return(self, tickers: list[str], start, end) -> tuple[float, list[str], pd.Timestamp] | None:
        """Retorno medio (ponderación igual) de mantener `tickers` entre `start` y `end` (ambos inclusive).
        Devuelve (retorno, tickers con datos, última rueda) o None si hay una rueda o menos."""
        lo = int(self.index.searchsorted(pd.Timestamp(start), side="left"))
        hi = int(self.index.searchsorted(pd.Timestamp(end), side="right"))
        if hi - lo <= 1:
            return None
        cols = self._cols(tickers)
        complete = self._nan_cum[hi, cols] == self._nan_cum[lo, cols]
        first, last = self.px[lo, cols][complete], self.px[hi - 1, cols][complete]
        kept = [t for t, ok in zip(tickers, complete) if ok]
        return float(pd.Series(last / first - 1).mean()), kept, self.index[hi - 1]

    def last_prices(self, tickers: list[str], when) -> pd.Series:
        """Último precio disponible de cada ticker hasta `when` (NaN si todavía no cotizaba)."""
        if self._ffilled is None:
            self._ffilled = pd.DataFrame(self.px).ffill().to_numpy()
        row = self.rows_until(when) - 1
        if row < 0:
            return pd.Series(np.nan, index=tickers, dtype=float)
        return pd.Series(self._ffilled[row, self._cols(tickers)], index=tickers)
