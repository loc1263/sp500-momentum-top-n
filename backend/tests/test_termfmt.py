import logging

from top3 import console, logs, termfmt
from top3.termfmt import MAX_WIDTH


def test_wrap_splits_long_lines_and_indents_the_rest():
    text = "  " + " ".join(f"TICKER{i}" for i in range(60))
    lines = termfmt.wrap(text)
    assert len(lines) > 1 and all(len(line) <= MAX_WIDTH for line in lines)
    assert lines[1].startswith("      ")                      # sangría original + 4
    assert " ".join(" ".join(lines).split()) == " ".join(text.split())      # no se pierde nada


def test_wrap_leaves_short_lines_and_colored_text_alone():
    assert termfmt.wrap("corto") == ["corto"] and termfmt.wrap("") == [""]
    colored = termfmt.color("x " * 200, termfmt.RED)
    assert termfmt.wrap(colored) == [colored]


def test_fit_widths_shrinks_the_widest_columns_only():
    fitted = termfmt.fit_widths([5, 200, 10, 6])
    assert sum(fitted) + 3 * 3 <= MAX_WIDTH
    assert fitted[0] == 5 and fitted[2] == 10 and fitted[3] == 6 and fitted[1] < 200
    assert termfmt.fit_widths([5, 10]) == [5, 10]
    assert termfmt.truncate("abcdefghij", 5) == "abcd…" and termfmt.truncate("abc", 5) == "abc"


def test_print_table_never_exceeds_the_max_width(capsys):
    rows = [["1", "VOO", "Nombre larguísimo " * 12, "Categoría " * 8, "+12.3%"]]
    console.print_table(["#", "Ticker", "Nombre", "Categoría", "Ret."], rows, right_from=4)
    lines = capsys.readouterr().out.splitlines()
    assert lines and all(len(line) <= MAX_WIDTH for line in lines) and "…" in lines[2]


def test_print_table_paints_gains_green_and_losses_red(capsys, monkeypatch):
    monkeypatch.setattr(console, "use_color", lambda: True)
    console.print_table(["Ticker", "Ret."], [["A", "+5.0%"], ["B", "-3.0%"], ["C", "+0.0%"], ["D", "n/d"]], right_from=1)
    a, b, c, d = capsys.readouterr().out.splitlines()[2:]
    assert termfmt.GREEN in a and termfmt.RED in b and "\033" not in c and "\033" not in d


def test_console_formatter_wraps_and_colors_info_lines(monkeypatch):
    monkeypatch.setattr(logs, "stderr_color", lambda: True)
    fmt = logs.ConsoleFormatter("%(asctime)s [%(levelname)s] %(message)s")
    long_text = "TOP-NET-005 " + " ".join(f"T{i}" for i in range(80))
    record = logging.LogRecord("t", logging.INFO, __file__, 1, long_text, None, None)
    lines = fmt.format(record).split("\n")
    assert len(lines) > 1 and all(termfmt.visible_len(line) <= MAX_WIDTH for line in lines)
    assert termfmt.CYAN in lines[0] and termfmt.DIM in lines[0] and termfmt.BOLD in lines[0]
    warning = logging.LogRecord("t", logging.WARNING, __file__, 1, long_text, None, None)
    assert all(line.startswith(termfmt.YELLOW) for line in fmt.format(warning).split("\n"))


def test_summary_lines_fit_the_width():
    item = {"code": "TOP-BKT-003", "count": 2, "level": logging.WARNING, "sample": "TOP-BKT-003: " + "x " * 120}
    assert all(len(line) <= MAX_WIDTH for line in logs.format_summary([item], "log/x.log"))
