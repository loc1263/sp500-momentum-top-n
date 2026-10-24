from pathlib import Path

import pytest

from top3.config import load_config
from top3.logs import log, setup_logging

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"


def test_load_config_defaults_when_missing(tmp_path):
    cfg = load_config(tmp_path / "no_existe.toml")
    assert cfg.backtest.top_n == 4
    assert cfg.data.batch_size == 100


def test_load_config_overrides_section_by_section(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[backtest]\ntop_n = 7\n[data]\nbatch_size = 50\n[tickers.aliases]\nAAA = "BBB"\n',
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg.backtest.top_n == 7
    assert cfg.backtest.months == 4              # lo no definido conserva el default
    assert cfg.data.db_path == "data/top3.db"
    assert cfg.data.batch_size == 50
    assert cfg.tickers.aliases == {"AAA": "BBB"}


def test_load_config_does_not_mutate_defaults(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[backtest]\ntop_n = 9\n", encoding="utf-8")
    load_config(p)
    assert load_config(tmp_path / "otro.toml").backtest.top_n == 4


def test_repo_config_toml_is_valid():
    cfg = load_config(REPO_CONFIG)
    assert REPO_CONFIG.exists()
    assert cfg.output.frontend_data and cfg.data.batch_size > 0     # el TOML del repo no tiene claves desconocidas


def test_values_are_converted_to_the_field_types(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[data]\nbatch_size = "25"\nprice_drift_tolerance = "0.5"\n[backtest]\nperiods_years = [2, 4]\n',
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg.data.batch_size == 25 and cfg.data.price_drift_tolerance == 0.5
    assert cfg.backtest.periods_years == [2.0, 4.0]


@pytest.mark.parametrize("toml, message", [("[backtest]\ntop_m = 3\n", "[backtest]: top_m"),
                                           ("[bakctest]\ntop_n = 3\n", "[bakctest]")])
def test_unknown_sections_and_keys_are_rejected(tmp_path, toml, message):
    p = tmp_path / "c.toml"
    p.write_text(toml, encoding="utf-8")
    with pytest.raises(SystemExit, match="TOP-CFG-004") as e:
        load_config(p)
    assert message in str(e.value)


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


def test_console_colors_warnings_yellow_and_errors_red(monkeypatch):
    import logging
    from top3 import logs
    monkeypatch.setattr(logs, "stderr_color", lambda: True)
    fmt = logs.ConsoleFormatter("[%(levelname)s] %(message)s")

    def render(level):
        return fmt.format(logging.LogRecord("t", level, __file__, 1, "msg", None, None))

    assert render(logging.INFO) == "[INFO] msg"
    assert render(logging.WARNING) == f"{logs.YELLOW}[WARNING] msg{logs.RESET}"
    assert render(logging.ERROR) == f"{logs.RED}[ERROR] msg{logs.RESET}"
    assert render(logging.CRITICAL).startswith(logs.RED)


def test_no_color_when_not_a_terminal(monkeypatch):
    import logging
    from top3 import logs
    monkeypatch.setattr(logs, "stderr_color", lambda: False)
    assert logs.paint("x", logging.ERROR) == "x"


def test_stderr_color_respects_no_color(monkeypatch):
    import sys
    from top3 import logs
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True, raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    assert logs.stderr_color() is False


def test_run_cli_logs_systemexit_message_as_error(tmp_path):
    import pytest
    from top3 import logs
    logs.setup_logging("c.log", str(tmp_path))
    try:
        def boom():
            raise SystemExit("TOP-BKT-001: sin rebalanceos")
        with pytest.raises(SystemExit) as e:
            logs.run_cli(boom)
        assert e.value.code == 1
        for h in logs.log.handlers:
            h.flush()
        assert "[ERROR] TOP-BKT-001: sin rebalanceos" in (tmp_path / "c.log").read_text(encoding="utf-8")
        with pytest.raises(SystemExit) as e:  # los códigos numéricos pasan tal cual
            logs.run_cli(lambda: (_ for _ in ()).throw(SystemExit(2)))
        assert e.value.code == 2
    finally:
        import logging
        logging.captureWarnings(False)
        for h in list(logs.log.handlers):
            h.close()
        logs.log.handlers.clear()


def _fresh_logging(tmp_path):
    from top3 import logs
    logs.setup_logging("s.log", str(tmp_path))
    return logs


def _close_logging():
    import logging
    from top3 import logs
    logging.captureWarnings(False)
    for h in list(logs.log.handlers):
        h.close()
    logs.log.handlers.clear()


def test_run_cli_prints_a_summary_grouped_by_code(tmp_path, capsys, monkeypatch):
    from top3 import errors as E
    monkeypatch.delenv("TOP3_SUMMARY_FILE", raising=False)
    logs = _fresh_logging(tmp_path)
    try:
        def main():
            for day in ("2016-11-01", "2016-12-01", "2017-01-01"):
                logs.log.warning(E.BKT_FEW_TICKERS.msg("Pocos tickers disponibles en %s"), day)
            logs.log.error(E.BKT_EMPTY.msg("sin rebalanceos"))
        logs.run_cli(main)
    finally:
        _close_logging()
    err = capsys.readouterr().err
    assert "RESUMEN DE AVISOS Y ERRORES: 1 errores, 3 avisos" in err
    assert err.index("ERROR TOP-BKT-001  x1") < err.index("AVISO TOP-BKT-003  x3")  # errores primero
    assert "ej.: Pocos tickers disponibles en 2016-11-01" in err and "qué hacer:" in err
    assert "s.log" in err


def test_run_cli_prints_no_summary_without_warnings(tmp_path, capsys):
    logs = _fresh_logging(tmp_path)
    try:
        logs.run_cli(lambda: logs.log.info("todo bien"))
    finally:
        _close_logging()
    assert "RESUMEN" not in capsys.readouterr().err


def test_summary_counts_python_warnings_and_uncoded_messages(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("TOP3_SUMMARY_FILE", raising=False)
    logs = _fresh_logging(tmp_path)
    try:
        def main():
            logs.log.warning("sin código propio")
            logs.log.warning(logs.SYS_PYTHON_WARNING.msg("PerformanceWarning: fragmentado"))
        logs.run_cli(main)
    finally:
        _close_logging()
    err = capsys.readouterr().err
    assert "sin código" in err and "TOP-SYS-001" in err


def test_summary_goes_to_the_pipeline_file_when_requested(tmp_path, capsys, monkeypatch):
    from top3 import errors as E
    f = tmp_path / "sum.jsonl"
    monkeypatch.setenv("TOP3_SUMMARY_FILE", str(f))
    monkeypatch.setenv("TOP3_STEP", "Paso A")
    logs = _fresh_logging(tmp_path)
    try:
        logs.run_cli(lambda: logs.log.warning(E.DAT_NO_SHARES.msg("faltan %d"), 6))
        monkeypatch.setenv("TOP3_STEP", "Paso B")
        logs.run_cli(lambda: logs.log.warning(E.DAT_NO_SHARES.msg("faltan %d"), 2))
    finally:
        _close_logging()
    assert "RESUMEN" not in capsys.readouterr().err  # el paso no imprime: lo hace el pipeline
    (item,) = logs.merge_summaries(f)
    assert item["code"] == "TOP-DAT-003" and item["steps"] == ["Paso A", "Paso B"]
    assert logs.merge_summaries(tmp_path / "no_existe.jsonl") == []


def test_yfinance_errors_are_triaged_into_the_log(tmp_path, capsys, monkeypatch):
    import logging
    monkeypatch.delenv("TOP3_SUMMARY_FILE", raising=False)
    logs = _fresh_logging(tmp_path)
    yf_log = logging.getLogger("yfinance")
    try:
        def main():
            yf_log.error("$ADM: YFRateLimitError('Too Many Requests')")             # por ticker: DEBUG
            yf_log.error("\n1 Failed download:")                                    # encabezado: DEBUG
            yf_log.error("['ADM']: YFRateLimitError('Too Many Requests. Rate limited.')")  # la que cuenta
            yf_log.error("['ATVI', 'CELG']: possibly delisted; no timezone found")  # esperable: DEBUG
            yf_log.error('HTTP Error 404: {"quoteSummary":{"error":{"description":"Quote not found for symbol: BCR"}}}')
            yf_log.error("['XYZ']: algo raro")                                      # otro error: aviso
        logs.run_cli(main)
        for h in logs.log.handlers:
            h.flush()
    finally:
        _close_logging()
    err = capsys.readouterr().err
    assert "[ERROR] TOP-NET-005: ['ADM']" in err and "[WARNING] TOP-NET-007: ['XYZ']" in err
    assert "delisted" not in err and "Failed download" not in err and "BCR" not in err       # no ensucian la consola
    assert "RESUMEN DE AVISOS Y ERRORES: 1 errores, 1 avisos" in err     # y no se cuentan de más


def test_headings_are_green_only_when_the_stream_supports_color(monkeypatch):
    import io
    from top3 import logs

    class Terminal(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    assert logs.heading("RESUMEN", Terminal()) == f"{logs.GREEN}RESUMEN{logs.RESET}"
    assert logs.heading("RESUMEN", io.StringIO()) == "RESUMEN"                 # redirigido: sin color
    monkeypatch.setenv("NO_COLOR", "1")
    assert logs.heading("RESUMEN", Terminal()) == "RESUMEN"
    monkeypatch.setattr(logs, "stderr_color", lambda: True)                      # por defecto va a stderr
    assert logs.heading("x") == f"{logs.GREEN}x{logs.RESET}"


def test_warning_summary_title_and_frame_are_green(monkeypatch):
    from top3 import logs
    item = {"code": "TOP-BKT-003", "count": 2, "level": 30, "sample": "TOP-BKT-003: Pocos tickers"}
    monkeypatch.setattr(logs, "stderr_color", lambda: True)
    lines = logs.format_summary([item], "log/x.log")
    green = lambda text: f"{logs.GREEN}{text}{logs.RESET}"
    assert lines[0] == green("=" * 78) and lines[2] == green("=" * 78)
    assert lines[1] == green("RESUMEN DE AVISOS Y ERRORES: 0 errores, 2 avisos")
    assert logs.YELLOW in lines[3]                                               # el detalle conserva su color de nivel


def test_pipeline_step_titles_and_summary_are_green(monkeypatch):
    import io
    import sys

    import pytest
    from top3.cli import pipeline as run_pipeline
    from top3 import logs

    class Terminal(io.StringIO):
        def isatty(self):
            return True

    out = Terminal()
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--config", "no_existe.toml", "--skip-backtest",
                                      "--skip-actual", "--skip-etf", "--skip-quant"])
    monkeypatch.setattr(run_pipeline.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})())
    with pytest.raises(SystemExit) as e:
        run_pipeline.main()
    assert e.value.code == 0
    text = out.getvalue()
    green = lambda t: f"{logs.GREEN}{t}{logs.RESET}"
    assert green("[1/1] Exportar JSON del frontend") in text
    assert green("=" * 78) in text and green("RESUMEN") in text
    detail = [line for line in text.split("\n") if "Exportar JSON del frontend" in line and "OK" in line]
    assert len(detail) == 1 and logs.GREEN not in detail[0]                       # el detalle de cada paso no


def test_history_start_is_history_years_before_today():
    from datetime import date

    from top3.config import DataConfig
    assert DataConfig(history_years=10).history_start(date(2026, 6, 15)) == "2016-06-15"
