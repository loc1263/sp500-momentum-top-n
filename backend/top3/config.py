"""Configuración tipada: una dataclass por sección de config.toml, con los valores por defecto en los campos."""
import tomllib
from datetime import date, timedelta
import typing
from dataclasses import dataclass, field, fields
from pathlib import Path

from . import errors as E


@dataclass
class DataConfig:
    """[data]: histórico, base SQLite y parámetros de las descargas (Wikipedia, CSV histórico y Yahoo)."""

    history_years: float = 12
    db_path: str = "data/top3.db"
    historical_url: str = ("https://raw.githubusercontent.com/hanshof/sp500_constituents/main/"
                           "sp_500_historical_components.csv")
    wikipedia_url: str = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    wikipedia_changes_url: str = "https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500"
    user_agent: str = "Mozilla/5.0"
    http_timeout: int = 30
    historical_timeout: int = 60
    batch_size: int = 100
    shares_workers: int = 8
    price_overlap_days: int = 7
    stale_days: int = 30
    price_drift_tolerance: float = 0.0001
    runs_keep_days: int = 7
    shares_ttl_days: int = 30
    no_data_ttl_days: int = 30

    def history_start(self, today: date) -> str:
        """Primer día del histórico a descargar (YYYY-MM-DD): `history_years` años antes de `today`."""
        return (today - timedelta(days=round(self.history_years * 365.25))).isoformat()


@dataclass
class BacktestConfig:
    """[backtest]: período, plazo, cartera y costos."""

    start_date: str = ""
    end_date: str = ""
    backtest_years: float = 5
    periods_years: list[float] = field(default_factory=lambda: [3, 5, 10])
    months: int = 4
    initial_capital: float = 1000
    top_n: int = 4
    commission: float = 0.0005
    alternates: int = 4
    trading_days_per_month: int = 21


@dataclass
class TickersConfig:
    """[tickers]: símbolo viejo -> símbolo actual en Yahoo (renombres que Wikipedia registra distinto en cada tabla)."""

    aliases: dict[str, str] = field(default_factory=lambda: {
        "BK": "BNY", "FI": "FISV", "MMC": "MRSH", "EQR": "VMRK", "PSKY": "SKYD", "SATS": "ECHO"})


@dataclass
class SimulationConfig:
    """[simulation]: plazos que compara --sweep."""

    months: list[int] = field(default_factory=lambda: [3, 4, 6, 8, 12])


@dataclass
class OutputConfig:
    """[output]: reportes HTML, logs y JSON del frontend."""

    dir: str = "output"
    backtest_subdir: str = "backtest"
    actual_subdir: str = "actual"
    backtest_prefix: str = "top3_backtest"
    sweep_prefix: str = "top3_sweep"
    offsets_prefix: str = "top3_offsets"
    actual_prefix: str = "top3_actual"
    etf_subdir: str = "etf"
    etf_prefix: str = "top3_etf"
    log_dir: str = "log"
    backtest_log: str = "top3_backtest.log"
    actual_log: str = "top3_actual.log"
    etf_log: str = "top3_etf.log"
    quant_log: str = "top3_quant.log"
    export_log: str = "export_frontend.log"
    prune_log: str = "top3_prune.log"
    frontend_data: str = "../frontend/public/data/report.json"


@dataclass
class EtfConfig:
    """[etf]: ranking de los ETFs de Vanguard."""

    update_list: bool = True            # al correr `top3 etf` agrega a la lista los ETFs nuevos de Vanguard
    list_url: str = "https://investor.vanguard.com/investment-products/list/funddetail/all"
    csv: str = "vanguard_etfs.csv"      # lista de ETFs de Vanguard (ticker, name, category)
    horizons_months: list[int] = field(default_factory=lambda: [3, 6, 12])  # el score es el promedio de los plazos
    top_n: int = 15                     # cuántos se muestran en la consola
    min_vol: float = 0.01               # volatilidad anual mínima para rankear: bajo eso es tipo efectivo
    risk_free_ticker: str = "VUSB"      # ETF de bonos ultracortos cuyo retorno se resta al de cada ETF; "" = sin restar


@dataclass
class QuantConfig:
    """[quant]: modelo por score y Markowitz."""

    weights: list[float] = field(default_factory=lambda: [1, 1, 1])         # momentum, salud financiera y técnico
    health_weights: list[float] = field(default_factory=lambda: [1, 1, 1, 2])  # rentabilidad, solvencia, liquidez, caja
    top_n: int = 10                     # acciones del ranking final sobre las que corre Markowitz
    vol_target: float = 0.20            # volatilidad anual máxima de la cartera de máximo retorno
    w_max: float = 0.25                 # peso máximo por acción
    sector_max: float = 0.40            # peso máximo por sector
    mu_shrink: float = 0.25             # peso del retorno pasado de cada acción frente al de largo plazo
    equity_premium: float = 0.05        # prima de mercado anual (largo plazo = tasa libre de riesgo + prima)
    risk_free: float = 0.04             # tasa libre de riesgo anual (para el Sharpe)
    fundamentals_ttl_days: int = 7      # días que se reutilizan los datos financieros descargados


@dataclass
class UniverseConfig:
    """[universe]: filtro por capitalización."""

    min_cap_billions: float = 10
    sweep_min_cap_billions: list[float] = field(default_factory=lambda: [0, 10, 200])


@dataclass
class Config:
    """Toda la configuración: valores por defecto con lo que defina el TOML encima (sección por sección)."""

    data: DataConfig = field(default_factory=DataConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    tickers: TickersConfig = field(default_factory=TickersConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    etf: EtfConfig = field(default_factory=EtfConfig)
    quant: QuantConfig = field(default_factory=QuantConfig)
    universe: UniverseConfig = field(default_factory=UniverseConfig)

    @classmethod
    def from_dict(cls, raw: dict) -> "Config":
        """Arma la configuración desde un dict de secciones (lo que lee el TOML). Convierte cada valor al tipo del
        campo; una sección o clave desconocida es un error (casi siempre un typo que de otro modo se ignoraría)."""
        sections = {f.name: f for f in fields(cls)}
        unknown = sorted(set(raw) - set(sections))
        if unknown:
            raise SystemExit(E.CFG_UNKNOWN_KEY.msg(f"Sección desconocida en la configuración: [{', '.join(unknown)}]"))
        return cls(**{name: _build_section(sections[name].type, name, values) for name, values in raw.items()})


def _coerce(value, hint):
    """`value` convertido al tipo `hint` (int, float, str, bool, list[...] o dict[...])."""
    origin = typing.get_origin(hint)
    if origin is list:
        (item,) = typing.get_args(hint)
        return [_coerce(v, item) for v in value]
    if origin is dict:
        _, item = typing.get_args(hint)
        return {str(k): _coerce(v, item) for k, v in value.items()}
    return hint(value)


def _build_section(section_cls, name: str, values: dict):
    hints = typing.get_type_hints(section_cls)
    known = {f.name for f in fields(section_cls)}
    unknown = sorted(set(values) - known)
    if unknown:
        raise SystemExit(E.CFG_UNKNOWN_KEY.msg(f"Clave desconocida en [{name}]: {', '.join(unknown)}"))
    return section_cls(**{k: _coerce(v, hints[k]) for k, v in values.items()})


def load_config(path: str | Path) -> Config:
    """Valores por defecto con lo que defina el TOML encima (sección por sección)."""
    path = Path(path)
    raw: dict = {}
    if path.exists():
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    return Config.from_dict(raw)
