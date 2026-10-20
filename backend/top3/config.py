"""Configuración: valores por defecto, lectura de config.toml y ajustes de descarga."""
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG: dict[str, dict] = {
    "data": {
        "history_years": 12,
        "db_path": "data/top3.db",
        "historical_url": "https://raw.githubusercontent.com/hanshof/sp500_constituents/main/sp_500_historical_components.csv",
        "wikipedia_url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "wikipedia_changes_url": "https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500",
        "user_agent": "Mozilla/5.0",
        "http_timeout": 30,
        "historical_timeout": 60,
        "batch_size": 100,
        "shares_workers": 8,
        "price_overlap_days": 7,
        "stale_days": 30,
        "price_drift_tolerance": 0.0001,
        "runs_keep_days": 7,
    },
    "backtest": {
        "start_date": "",
        "end_date": "",
        "backtest_years": 5,
        "periods_years": [3, 5, 10],
        "months": 4,
        "initial_capital": 1000,
        "top_n": 4,
        "trading_days_per_month": 21,
    },
    "tickers": {
        # Símbolo viejo -> símbolo actual en Yahoo (renombres que Wikipedia registra distinto en cada tabla)
        "aliases": {"BK": "BNY", "FI": "FISV", "MMC": "MRSH", "EQR": "VMRK", "PSKY": "SKYD", "SATS": "ECHO"},
    },
    "simulation": {
        "months": [3, 4, 6, 8, 12],
    },
    "output": {
        "dir": "output",
        "backtest_subdir": "backtest",
        "actual_subdir": "actual",
        "backtest_prefix": "top3_backtest",
        "sweep_prefix": "top3_sweep",
        "offsets_prefix": "top3_offsets",
        "actual_prefix": "top3_actual",
        "log_dir": "log",
        "backtest_log": "top3_backtest.log",
        "actual_log": "top3_actual.log",
        "export_log": "export_frontend.log",
        "server_log": "server.log",
        "frontend_data": "../frontend/public/data/report.json",
    },
    "server": {
        "host": "127.0.0.1",
        "port": 8000,
        "cors_origin": "*",
    },
    "universe": {
        "min_cap_billions": 10,
        "sweep_min_cap_billions": [0, 10, 200],
    },
}


def load_config(path: str | Path) -> dict:
    """Valores por defecto con lo que defina el TOML encima (sección por sección)."""
    cfg = {section: dict(values) for section, values in DEFAULT_CONFIG.items()}
    path = Path(path)
    if path.exists():
        with open(path, "rb") as f:
            user = tomllib.load(f)
        for section, values in user.items():
            cfg.setdefault(section, {}).update(values)
    return cfg


@dataclass(frozen=True)
class DataSettings:
    """Parámetros de las descargas (Wikipedia, CSV histórico y Yahoo) y de la actualización de precios."""

    historical_url: str
    wikipedia_url: str
    wikipedia_changes_url: str
    user_agent: str
    http_timeout: int
    historical_timeout: int
    batch_size: int
    shares_workers: int
    price_overlap_days: int
    stale_days: int
    price_drift_tolerance: float

    @classmethod
    def from_config(cls, cfg: dict) -> "DataSettings":
        d = cfg["data"]
        return cls(
            historical_url=d["historical_url"],
            wikipedia_url=d["wikipedia_url"],
            wikipedia_changes_url=d["wikipedia_changes_url"],
            user_agent=d["user_agent"],
            http_timeout=int(d["http_timeout"]),
            historical_timeout=int(d["historical_timeout"]),
            batch_size=int(d["batch_size"]),
            shares_workers=int(d["shares_workers"]),
            price_overlap_days=int(d["price_overlap_days"]),
            stale_days=int(d["stale_days"]),
            price_drift_tolerance=float(d["price_drift_tolerance"]),
        )
