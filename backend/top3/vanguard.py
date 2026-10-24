"""Lista de ETFs de Vanguard: se baja del servicio que alimenta la página de productos de Vanguard y se agrega a
`vanguard_etfs.csv` lo que falte.

El archivo se mantiene a mano en lo que ya tiene (nombres y categorías en español no se tocan): acá solo se agregan
los ETFs nuevos y nunca se borra ninguno. Los que Vanguard ya no lista se informan para que se quiten a mano.
"""
import csv
import io
import os
import re
import tempfile
from pathlib import Path

import requests

from .logs import log

MIN_ETFS = 20  # una respuesta con menos ETFs que esto no es la lista completa: no se toca el archivo


def fetch_etfs(url: str, user_agent: str, timeout: int) -> list[dict[str, str]]:
    """ETFs de la respuesta de Vanguard como [{ticker, name, category}]. Lanza ValueError si la respuesta no tiene
    la forma esperada o trae demasiado pocos ETFs."""
    response = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
    log.debug("GET %s -> HTTP %s, %d bytes", url, response.status_code, len(response.content))
    response.raise_for_status()
    return parse_etfs(response.json())


def parse_etfs(data: dict) -> list[dict[str, str]]:
    try:
        entities = data["fund"]["entity"]
        profiles = [e["profile"] for e in entities]
    except (KeyError, TypeError) as e:
        raise ValueError(f"la respuesta de Vanguard no tiene la forma esperada ({e!r})") from e
    etfs = [{"ticker": p["ticker"].strip().upper(), "name": short_name(p["longName"]), "category": category(p)}
            for p in profiles if p.get("isETF") and p.get("ticker") and not p.get("fundFact", {}).get("isClosed")]
    if len(etfs) < MIN_ETFS:
        raise ValueError(f"solo {len(etfs)} ETFs en la respuesta de Vanguard (se esperaban al menos {MIN_ETFS})")
    return etfs


def short_name(long_name: str) -> str:
    """'Vanguard Total Stock Market ETF' -> 'Total Stock Market'."""
    return re.sub(r"\s+ETF( Shares)?$", "", re.sub(r"^Vanguard\s+", "", long_name.strip())).strip()


def category(profile: dict) -> str:
    """Categoría (las del archivo) para un ETF nuevo, según el estilo que informa Vanguard."""
    name, style, kind = profile["longName"], profile.get("style", ""), profile.get("type", "")
    if style == "Bond Funds":
        return "Bonos internacionales" if re.search(r"International|Emerging|World|Global", name) else "Bonos EE. UU."
    if kind == "International/Global Stock":
        return "Acciones internacionales"
    if kind == "Domestic Stock - Sector-Specific":
        return "Sectores"
    return "Acciones EE. UU. amplio"


def update_list(path: str | Path, etfs: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    """Agrega al CSV los ETFs que no están. Devuelve (tickers agregados, tickers del CSV que Vanguard ya no lista)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", newline="")
    newline = "\r\n" if "\r\n" in text else "\n"
    rows = list(csv.DictReader(text.splitlines()))
    known = {r["ticker"].strip().upper() for r in rows}
    theirs = {e["ticker"] for e in etfs}
    new = sorted((e for e in etfs if e["ticker"] not in known), key=lambda e: e["ticker"])
    gone = sorted(known - theirs)
    if new:
        body = text if text.endswith(("\n", "\r")) else text + newline
        buffer = io.StringIO()
        csv.writer(buffer, lineterminator=newline).writerows([e["ticker"], e["name"], e["category"]] for e in new)
        extra = buffer.getvalue()
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(body + extra)
        os.replace(tmp, path)  # el archivo nunca queda a medio escribir
    return [e["ticker"] for e in new], gone
