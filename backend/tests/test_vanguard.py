import logging

import pytest

from top3 import etf, vanguard


def profile(ticker, long_name, is_etf=True, style="Stock Funds", kind="Domestic Stock - General", closed=False):
    return {"profile": {"ticker": ticker, "longName": long_name, "isETF": is_etf, "style": style, "type": kind,
                        "fundFact": {"isClosed": closed}}}


def response(extra=()):
    base = [profile(f"E{i:02d}", f"Vanguard Fund {i} ETF") for i in range(25)]
    return {"fund": {"entity": base + list(extra)}}


def test_parse_keeps_only_open_etfs_and_cleans_names():
    data = response([
        profile("VTI", "Vanguard Total Stock Market ETF Shares"),
        profile("VTSAX", "Vanguard Total Stock Market Index Fund Admiral Shares", is_etf=False),
        profile("OLD", "Vanguard Old ETF", closed=True),
    ])
    etfs = {e["ticker"]: e for e in vanguard.parse_etfs(data)}
    assert "VTSAX" not in etfs and "OLD" not in etfs
    assert etfs["VTI"] == {"ticker": "VTI", "name": "Total Stock Market", "category": "Acciones EE. UU. amplio"}


@pytest.mark.parametrize("name, style, kind, expected", [
    ("Vanguard Core Bond ETF", "Bond Funds", "Intermediate-Term Bond", "Bonos EE. UU."),
    ("Vanguard Total International Bond ETF", "Bond Funds", "Taxable Bond", "Bonos internacionales"),
    ("Vanguard Emerging Markets ex-China ETF", "Stock Funds", "International/Global Stock", "Acciones internacionales"),
    ("Vanguard Energy ETF", "Stock Funds", "Domestic Stock - Sector-Specific", "Sectores"),
    ("Vanguard Mid-Cap ETF", "Stock Funds", "Domestic Stock - More Aggressive", "Acciones EE. UU. amplio"),
])
def test_category_from_the_style_vanguard_reports(name, style, kind, expected):
    assert vanguard.category({"longName": name, "style": style, "type": kind}) == expected


def test_a_response_with_the_wrong_shape_or_too_few_etfs_is_rejected():
    with pytest.raises(ValueError, match="forma esperada"):
        vanguard.parse_etfs({"algo": []})
    with pytest.raises(ValueError, match="solo 2 ETFs"):
        vanguard.parse_etfs({"fund": {"entity": [profile("A", "Vanguard A ETF"), profile("B", "Vanguard B ETF")]}})


def test_update_list_appends_only_new_tickers_and_never_edits_existing_rows(tmp_path):
    path = tmp_path / "e.csv"
    path.write_bytes("ticker,name,category\r\nVTI,Mi nombre,Mi categoría\r\nGONE,Cerrado,Cat\r\n".encode("utf-8"))
    etfs = [{"ticker": "VTI", "name": "Total Stock Market", "category": "Otra"},
            {"ticker": "ZZZ", "name": "Zeta, con coma", "category": "Sectores"},
            {"ticker": "AAA", "name": "Alfa", "category": "Sectores"}]
    added, gone = vanguard.update_list(path, etfs)
    assert added == ["AAA", "ZZZ"] and gone == ["GONE"]
    text = path.read_text(encoding="utf-8", newline="")
    assert text.startswith("ticker,name,category\r\nVTI,Mi nombre,Mi categoría\r\nGONE,Cerrado,Cat\r\n")
    assert text.endswith('AAA,Alfa,Sectores\r\nZZZ,"Zeta, con coma",Sectores\r\n')
    assert vanguard.update_list(path, etfs) == ([], ["GONE"])          # idempotente
    assert path.read_text(encoding="utf-8", newline="") == text


def test_update_list_adds_the_missing_final_newline(tmp_path):
    path = tmp_path / "e.csv"
    path.write_text("ticker,name,category\nVTI,Total,Cat", encoding="utf-8")
    vanguard.update_list(path, [{"ticker": "VTI", "name": "x", "category": "y"},
                                {"ticker": "NEW", "name": "Nuevo", "category": "Sectores"}])
    assert path.read_text(encoding="utf-8") == "ticker,name,category\nVTI,Total,Cat\nNEW,Nuevo,Sectores\n"


class FakeResponse:
    status_code = 200
    content = b"{}"

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_refresh_list_adds_new_etfs(cfg, tmp_path, monkeypatch, caplog):
    path = tmp_path / "e.csv"
    path.write_text("ticker,name,category\nE00,Fund 0,Cat\n", encoding="utf-8")
    cfg["etf"]["csv"] = str(path)
    monkeypatch.setattr(vanguard.requests, "get", lambda *a, **k: FakeResponse(response()))
    with caplog.at_level(logging.INFO):
        etf.refresh_list(cfg)
    assert path.read_text(encoding="utf-8").count("\n") == 26           # encabezado + los 25 de la respuesta
    assert "se agregaron 24" in caplog.text


def test_refresh_list_survives_a_failed_download_with_a_warning(cfg, tmp_path, monkeypatch, caplog):
    path = tmp_path / "e.csv"
    path.write_text("ticker,name,category\nE00,Fund 0,Cat\n", encoding="utf-8")
    cfg["etf"]["csv"] = str(path)

    def boom(*a, **k):
        raise ConnectionError("sin red")
    monkeypatch.setattr(vanguard.requests, "get", boom)
    etf.refresh_list(cfg)
    assert path.read_text(encoding="utf-8") == "ticker,name,category\nE00,Fund 0,Cat\n"      # sin cambios
    assert "TOP-ETF-006" in caplog.text and "sin red" in caplog.text


def test_run_etf_only_updates_the_configured_list(cfg, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(etf, "refresh_list", lambda c: calls.append(1))
    monkeypatch.setattr(etf, "load_universe", lambda path: (_ for _ in ()).throw(SystemExit("corte")))
    for kwargs in ({}, {"csv_path": "otra.csv"}, {"update_list": False}):
        with pytest.raises(SystemExit):
            etf.run_etf(cfg, **kwargs)
    assert calls == [1]                  # solo con la lista del config y sin --no-update
    cfg["etf"]["update_list"] = False
    with pytest.raises(SystemExit):
        etf.run_etf(cfg)
    assert calls == [1]
