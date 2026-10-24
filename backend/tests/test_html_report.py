from datetime import date

import pandas as pd

from helpers import make_calendar as calendar
from top3 import html_report
from top3.analysis import Context, Term


def test_html_table_classes_and_escape():
    h = html_report.html_table(["A<b>", "R"], [["x&y", "+5.0%"], ["z", "-3.0%"], ["w", "+0.0%"]],
                               right_cols=(1,), signed_cols=(1,))
    assert "A&lt;b&gt;" in h and "x&amp;y" in h
    assert 'class="r pos"' in h and 'class="r neg"' in h
    assert h.count("pos") == 1


def test_write_html(tmp_path):
    p = html_report.write_html(str(tmp_path), "pre", "Título <x>", "sub", "<p>cuerpo</p>", subdir="s")
    assert p.parent == tmp_path / "s"
    assert p.name == f"pre_{date.today():%Y%m%d}.html"
    text = p.read_text(encoding="utf-8")
    assert "Título &lt;x&gt;" in text and "<p>cuerpo</p>" in text


def test_compact_layout():
    assert "max-width:1280px" in html_report.HTML_CSS and "padding:1px 14px" in html_report.HTML_CSS


def test_write_report_names_and_folders(cfg, tmp_path):
    cfg.output.dir = str(tmp_path)
    sweep = html_report.write_report(cfg, "sweep", 10, "t", "s", "b", "_5y")
    actual = html_report.write_report(cfg, "actual", None, "t", "s", "b")
    assert sweep.parent == tmp_path / "backtest" and sweep.name == f"top3_sweep_largecap_5y_{date.today():%Y%m%d}.html"
    assert actual.parent == tmp_path / "actual" and actual.name == f"top3_actual_{date.today():%Y%m%d}.html"


def test_reports_for_each_kind(cfg, conn, settings, tmp_path):
    cfg.output.dir = str(tmp_path)
    ctx = Context(conn, cfg, settings, None, pd.DataFrame(), pd.Timestamp("2023-01-01"), pd.Timestamp("2024-01-01"),
                  file_suffix="_1y")
    terms = [Term(3, [calendar(0, 1500, 30.0), calendar(1, 1200, 20.0)]), Term(6, [])]

    backtest = html_report.backtest_report(ctx, terms[0], 10).read_text(encoding="utf-8")
    assert "2023-01-01 a 2024-01-01" in backtest and "Universo filtrado" in backtest and "Rango CAGR (2 calendarios)" in backtest

    sweep = html_report.sweep_report(ctx, terms, None).read_text(encoding="utf-8")
    assert "Mejor plazo: 3 meses" in sweep and "sin datos" in sweep and "Selecciones - plazo 3 meses" in sweep

    offsets = html_report.offsets_report(ctx, terms, None).read_text(encoding="utf-8")
    assert "Resumen por plazo" in offsets and "Plazo 3 meses - detalle por calendario" in offsets
    assert "Plazo 6 meses - detalle" not in offsets

    window = pd.DataFrame({"A": [1.0, 2.0]}, index=pd.to_datetime(["2024-01-02", "2024-01-03"]))
    actual = html_report.actual_report(cfg, 4, 4, None, "2024-01-03", window, ["#", "Ticker", "Retorno", "Cap", "P", "W"],
                                       [["1", "A", "+100.0%", "n/d", "2.00", "25.0%"]], 25.0)
    assert actual.parent == tmp_path / "actual"
    assert "Ventana 2024-01-02 a 2024-01-03" in actual.read_text(encoding="utf-8")
