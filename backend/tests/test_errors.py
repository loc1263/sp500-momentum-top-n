import re
from pathlib import Path

from top3 import errors

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [*ROOT.glob("top3/*.py"), *ROOT.glob("*.py")]


def test_ids_have_the_expected_format_and_are_unique():
    ids = [c.id for c in errors.CATALOG.values()]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"TOP-[A-Z]{3}-\d{3}", i) for i in ids)
    assert all(c.level in errors.LEVELS and c.title and c.action for c in errors.CATALOG.values())


def test_msg_prefixes_the_id():
    assert errors.BKT_FEW_TICKERS.msg("hola %s") == "TOP-BKT-003: hola %s"


def test_every_code_is_used_in_the_source():
    text = "\n".join(p.read_text(encoding="utf-8") for p in SOURCES if p.name != "errors.py")
    unused = [name for name, value in vars(errors).items()
              if isinstance(value, errors.Code) and not re.search(rf"\b{name}\b", text)]
    assert unused == []


def test_every_warning_error_and_exception_log_carries_a_code():
    missing = []
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"\blog\.(warning|error|exception)\(", text):
            if ".msg(" not in text[m.end():m.end() + 60]:
                missing.append(f"{path.name}:{text.count(chr(10), 0, m.start()) + 1}")
    assert missing == []


def test_every_code_is_documented():
    doc = (ROOT.parent / "docs" / "errores.md").read_text(encoding="utf-8")
    assert [i for i in errors.CATALOG if i not in doc] == []
