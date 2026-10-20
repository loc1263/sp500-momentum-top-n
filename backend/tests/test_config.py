from pathlib import Path

from top3.config import DataSettings, load_config
from top3.logs import log, setup_logging

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"


def test_load_config_defaults_when_missing(tmp_path):
    cfg = load_config(tmp_path / "no_existe.toml")
    assert cfg["backtest"]["top_n"] == 4
    assert cfg["data"]["batch_size"] == 100


def test_load_config_overrides_section_by_section(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[backtest]\ntop_n = 7\n[data]\nbatch_size = 50\n[tickers.aliases]\nAAA = "BBB"\n',
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg["backtest"]["top_n"] == 7
    assert cfg["backtest"]["months"] == 4              # lo no definido conserva el default
    assert cfg["data"]["db_path"] == "data/top3.db"
    assert cfg["data"]["batch_size"] == 50
    assert cfg["tickers"]["aliases"] == {"AAA": "BBB"}


def test_load_config_does_not_mutate_defaults(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[backtest]\ntop_n = 9\n", encoding="utf-8")
    load_config(p)
    assert load_config(tmp_path / "otro.toml")["backtest"]["top_n"] == 4


def test_repo_config_toml_is_valid():
    cfg = load_config(REPO_CONFIG)
    assert REPO_CONFIG.exists()
    for key in ("log_dir", "backtest_prefix", "actual_subdir", "frontend_data"):
        assert key in cfg["output"]
    DataSettings.from_config(cfg)                       # todas las claves de descarga están y son del tipo correcto


def test_data_settings_converts_types(cfg):
    cfg["data"]["batch_size"] = "25"
    cfg["data"]["price_drift_tolerance"] = "0.5"
    s = DataSettings.from_config(cfg)
    assert s.batch_size == 25 and s.price_drift_tolerance == 0.5


def test_setup_logging_creates_dir(tmp_path):
    folder = tmp_path / "logs"
    setup_logging("x.log", str(folder))
    log.info("hola")
    for h in log.handlers:
        h.flush()
    assert (folder / "x.log").read_text(encoding="utf-8").count("hola") == 1
    for h in list(log.handlers):
        h.close()
    log.handlers.clear()


def test_setup_logging_captures_python_warnings(tmp_path):
    import logging
    import warnings
    setup_logging("w.log", str(tmp_path))
    try:
        warnings.showwarning("aviso de prueba", UserWarning, "archivo.py", 7)  # lo que invoca warnings.warn
        for h in log.handlers:
            h.flush()
        text = (tmp_path / "w.log").read_text(encoding="utf-8")
        assert "[WARNING] TOP-SYS-001: " in text and "aviso de prueba" in text
    finally:
        logging.captureWarnings(False)
        logging.getLogger("py.warnings").handlers.clear()
        for h in list(log.handlers):
            h.close()
        log.handlers.clear()
