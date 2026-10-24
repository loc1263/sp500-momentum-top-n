import pandas as pd

from helpers import make_calendar as calendar
from top3 import tables
from top3.analysis import Term


def terms():
    return [Term(3, [calendar(0, 1500, 30.0), calendar(1, 1200, 20.0)]),
            Term(6, [calendar(0, 2000, 50.0), calendar(1, 1100, 10.0)]),   # mediana 30
            Term(8, [calendar(1, 1400, 35.0)]),                             # sin calendario base
            Term(12, [calendar(0, 1300, 28.0)])]


def test_pct():
    assert tables.pct(12.345) == "+12.3%" and tables.pct(-0.04) == "-0.0%" and tables.pct(0) == "+0.0%"


def test_sweep_table_orders_by_median_and_lists_failed_last():
    headers, rows = tables.sweep_table(terms())
    assert len(headers) == len(rows[0]) == 9
    assert [r[0] for r in rows] == ["6 meses", "12 meses", "3 meses", "8 meses"]   # por CAGR mediano; sin base al final
    assert rows[0][2] == "2,000.00" and rows[0][6] == "+30.0%"
    assert rows[-1][1:3] == ["0", "sin datos"]                                      # plazo sin calendario base


def test_sweep_best_text():
    text = tables.sweep_best(terms(), 1000)
    assert text.startswith("Mejor plazo: 6 meses (CAGR mediano +30.0%, rango +10.0% a +50.0%")
    assert "US$ 1,000 → US$ 2,000.00" in text
    assert tables.sweep_best([Term(3, [])], 1000) is None


def test_offsets_table_includes_terms_without_base():
    headers, rows = tables.offsets_table(terms())
    assert [r[0] for r in rows] == ["8 meses", "6 meses", "12 meses", "3 meses"]  # incluye el plazo sin calendario base
    by_term = {r[0]: r for r in rows}
    assert by_term["6 meses"][2:5] == ["+30.0%", "+10.0%", "+50.0%"]
    assert by_term["6 meses"][5:] == ["1,550", "1,100", "2,000"]
    assert tables.offsets_best([Term(3, [])]) is None
    assert "Mejor plazo por CAGR mediano" in tables.offsets_best(terms())


def test_calendar_table():
    headers, rows = tables.calendar_table([calendar(0, 1100, 10.0)])
    assert rows == [["2024-01-01", "1", "1,100.00", "+10.0%", "+10.0%"]]


def test_history_table_adds_final_row_and_caps():
    equity = pd.Series([1000.0, 1100.0], index=pd.to_datetime(["2024-01-01", "2024-05-01"]))
    history = [{"date": "2024-01-01", "returns": {"A": 0.5, "B": 0.25}, "caps": {"A": 3e9}}]
    headers, rows = tables.history_table(history, equity, 1000.0)
    assert headers == ["Fecha", "#1", "#2", "Cap. aprox. (US$ B)", "Capital (US$)", "Gan/Pérd"]
    assert rows[0] == ["2024-01-01", "A +50.0%", "B +25.0%", "3 / n/d", "1,000.00", "+0.0%"]
    assert rows[1] == ["2024-05-01", "", "", "", "1,100.00", "+10.0%"]        # valor al cierre del último tramo


def test_models_table_compares_both_models_term_by_term():
    skip = [Term(3, [calendar(0, 1300, 40.0)]), Term(6, [calendar(0, 1000, 5.0)])]
    headers, rows = tables.models_table(terms(), skip)
    assert len(headers) == len(rows[0]) == 7
    by_term = {r[0]: r for r in rows}
    assert by_term["3 meses"][1:4] == ["+25.0%", "+40.0%", "+15.0 pp"] and by_term["3 meses"][-1] == "N-1"
    assert by_term["6 meses"][-1] == "N-0"
    assert by_term["12 meses"][2] == "sin datos"            # sin resultado del modelo skip-month
