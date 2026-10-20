"""Universos por capitalización: filtro y etiquetas (None o 0 = índice completo)."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

LARGE_CAP_B = 10    # umbral habitual de large-cap (miles de millones de US$)
MEGA_CAP_B = 200    # umbral habitual de mega-cap (miles de millones de US$)

FULL_INDEX_LABEL = "índice completo"


@dataclass(frozen=True)
class Universe:
    """Solo compiten las empresas con capitalización aprox. (precio × acciones actuales) >= el umbral."""

    shares: dict[str, float]
    min_cap_billions: float

    @property
    def min_cap_usd(self) -> float:
        return self.min_cap_billions * 1e9

    def select(self, tickers: list[str], last_prices: pd.Series) -> list[str]:
        """Tickers con acciones conocidas y capitalización >= el umbral, dado el último precio de cada uno."""
        price = last_prices.reindex(tickers).to_numpy(dtype=float)
        shares = np.array([self.shares.get(t, np.nan) for t in tickers], dtype=float)
        with np.errstate(invalid="ignore"):  # NaN (sin precio o sin acciones) nunca cumple el umbral
            ok = price * shares >= self.min_cap_usd
        return [t for t, keep in zip(tickers, ok) if keep]


def label(min_cap_b: float | None) -> str:
    if not min_cap_b:
        return FULL_INDEX_LABEL
    if min_cap_b >= MEGA_CAP_B:
        return "mega-cap"
    if min_cap_b >= LARGE_CAP_B:
        return "large-cap + mega-cap"
    return f"cap. ≥ US$ {min_cap_b:g} B"


def suffix(min_cap_b: float | None) -> str:
    """Sufijo para nombres de archivo."""
    if not min_cap_b:
        return ""
    if min_cap_b >= MEGA_CAP_B:
        return "_megacap"
    return "_largecap" if min_cap_b >= LARGE_CAP_B else f"_cap{min_cap_b:g}B"


def title(min_cap_b: float | None) -> str:
    return f" {label(min_cap_b)}" if min_cap_b else ""


def subtitle(min_cap_b: float | None) -> str:
    return f" · solo empresas con cap. aprox. ≥ US$ {min_cap_b:g} B" if min_cap_b else ""
