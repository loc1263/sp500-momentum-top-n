"""Composición Point-in-Time del S&P 500: descarga (CSV histórico + Wikipedia) y consulta por fecha."""
import bisect
import sqlite3
from collections.abc import Iterable
from datetime import date
from io import StringIO

import pandas as pd
import requests

from . import errors as E
from .config import DataSettings
from .db import fetched_today, set_meta
from .logs import log


def parse_tickers(tickers_str) -> list[str]:
    """Lista de tickers desde el texto del CSV ("['A', 'BRK.B']"); los puntos pasan a guión (formato Yahoo)."""
    return [t.strip().replace(".", "-")
            for t in str(tickers_str).replace("[", "").replace("]", "").replace("'", "").split(",")
            if t.strip()]


def _get_text(url: str, settings: DataSettings, timeout: int | None = None) -> str:
    response = requests.get(url, headers={"User-Agent": settings.user_agent},
                            timeout=timeout or settings.http_timeout)
    log.debug("GET %s -> HTTP %s, %d bytes", url, response.status_code, len(response.content))
    response.raise_for_status()
    return response.text


def download_historical_constituents(conn: sqlite3.Connection, settings: DataSettings) -> None:
    log.info("Descargando listas históricas del S&P 500...")
    text = _get_text(settings.historical_url, settings, settings.historical_timeout)
    df = pd.read_csv(StringIO(text))
    log.debug("CSV histórico: shape=%s, columnas=%s", df.shape, list(df.columns))
    df.columns = [c.lower().strip() for c in df.columns]

    date_col = [c for c in df.columns if "date" in c][0]
    tick_cols = [c for c in df.columns if "ticker" in c or "symbol" in c or "constituent" in c]
    tick_col = tick_cols[0] if tick_cols else [c for c in df.columns if c != date_col][0]
    log.debug("Columnas usadas: fecha=%s, tickers=%s", date_col, tick_col)

    rows = [(pd.to_datetime(d).strftime("%Y-%m-%d"), ",".join(parse_tickers(t)))
            for d, t in zip(df[date_col], df[tick_col])]
    conn.execute("DELETE FROM constituents_history")
    conn.executemany("INSERT OR REPLACE INTO constituents_history (date, tickers) VALUES (?, ?)", rows)
    set_meta(conn, "constituents_history_fetched", date.today().isoformat())
    conn.commit()
    log.info("Listas históricas guardadas: %s a %s (%d filas)", rows[0][0], rows[-1][0], len(rows))


def download_current_constituents(conn: sqlite3.Connection, settings: DataSettings) -> None:
    log.info("Obteniendo lista actual del S&P 500 (Wikipedia)...")
    table = pd.read_html(StringIO(_get_text(settings.wikipedia_url, settings)))[0]
    tickers = table["Symbol"].str.replace(".", "-", regex=False).tolist()
    conn.execute("DELETE FROM constituents_current")
    conn.executemany("INSERT OR IGNORE INTO constituents_current (ticker) VALUES (?)", [(t,) for t in tickers])
    set_meta(conn, "constituents_current_fetched", date.today().isoformat())
    conn.commit()
    log.info("Lista actual guardada: %d tickers", len(tickers))


def download_index_changes(conn: sqlite3.Connection, settings: DataSettings) -> None:
    """Altas/bajas del índice según Wikipedia; completan lo que el CSV histórico no alcanza."""
    log.info("Descargando cambios del índice (Wikipedia)...")
    tables = pd.read_html(StringIO(_get_text(settings.wikipedia_changes_url, settings)))
    table = next((t for t in tables if isinstance(t.columns, pd.MultiIndex)
                  and "Added" in t.columns.get_level_values(0)), None)
    if table is None:
        raise RuntimeError(E.NET_WIKI_FORMAT.msg("No se encontró la tabla de cambios en Wikipedia (¿cambió el formato de la página?)"))
    table = table.iloc[:, :6]
    table.columns = ["date", "added", "added_name", "removed", "removed_name", "reason"]
    table["date"] = pd.to_datetime(table["date"], format="%B %d, %Y", errors="coerce")
    bad = table["date"].isna().sum()
    if bad:
        log.warning(E.DAT_BAD_DATES.msg("%d filas con fecha no interpretable, se ignoran"), bad)
    table = table.dropna(subset=["date"])

    def norm(v):
        return None if pd.isna(v) else str(v).strip().replace(".", "-")

    rows = [(r.date.strftime("%Y-%m-%d"), norm(r.added), norm(r.removed), None if pd.isna(r.reason) else str(r.reason))
            for r in table.itertuples()]
    conn.execute("DELETE FROM index_changes")
    conn.executemany("INSERT INTO index_changes (date, added, removed, reason) VALUES (?, ?, ?, ?)", rows)
    set_meta(conn, "index_changes_fetched", date.today().isoformat())
    conn.commit()
    log.info("Cambios del índice guardados: %d filas (%s a %s)", len(rows),
             min(r[0] for r in rows), max(r[0] for r in rows))


def ensure_constituents(conn: sqlite3.Connection, settings: DataSettings, use_cache: bool) -> None:
    """Descarga (o reutiliza del mismo día) el histórico (CSV), los cambios posteriores y la lista actual (Wikipedia)."""
    for key, download, label in (
        ("constituents_history_fetched", download_historical_constituents, "histórica (CSV)"),
        ("index_changes_fetched", download_index_changes, "cambios del índice (Wikipedia)"),
        ("constituents_current_fetched", download_current_constituents, "actual (Wikipedia)"),
    ):
        if use_cache and fetched_today(conn, key):
            log.info("Composición %s: usando caché SQLite (descargada hoy)", label)
            continue
        try:
            download(conn, settings)
        except Exception:
            log.exception(E.NET_COMPOSITION.msg("Error descargando composición %s"), label)
            log.warning(E.NET_FALLBACK.msg("Se usará lo que haya en SQLite para la composición %s"), label)


def _day(value) -> str:
    return pd.to_datetime(value).strftime("%Y-%m-%d")


class Constituents:
    """Composición Point-in-Time del S&P 500 leída desde SQLite."""

    def __init__(self, conn: sqlite3.Connection, aliases: dict[str, str] | None = None):
        # aliases: símbolo viejo -> símbolo actual en Yahoo (renombres de empresas)
        self.aliases = aliases or {}
        rows = conn.execute("SELECT date, tickers FROM constituents_history ORDER BY date").fetchall()
        self.dates = [r[0] for r in rows]
        self.lists = [self._canon(r[1].split(",")) if r[1] else [] for r in rows]
        self.current = self._canon(r[0] for r in conn.execute("SELECT ticker FROM constituents_current").fetchall())
        self._apply_changes(conn)
        log.debug("Constituents: %d filas históricas (%s a %s), %d actuales",
                  len(self.dates), self.dates[0] if self.dates else None,
                  self.dates[-1] if self.dates else None, len(self.current))

    def _canon(self, tickers: Iterable[str]) -> list[str]:
        """Aplica los alias y elimina duplicados (manteniendo el orden)."""
        return list(dict.fromkeys(self.aliases.get(t, t) for t in tickers))

    def _apply_changes(self, conn: sqlite3.Connection) -> None:
        """Extiende el CSV con las altas/bajas de Wikipedia posteriores a su última fecha."""
        if not self.dates:
            return
        csv_last = self.dates[-1]
        changes = conn.execute(
            "SELECT date, added, removed FROM index_changes WHERE date > ? ORDER BY date", (csv_last,)).fetchall()
        if not changes:
            log.info("Composición: el CSV llega a %s y no hay cambios posteriores en Wikipedia", csv_last)
            return
        members = set(self.lists[-1])
        by_date: dict[str, list[tuple]] = {}
        for d, added, removed in changes:
            by_date.setdefault(d, []).append((self.aliases.get(added, added), self.aliases.get(removed, removed)))
        for d in sorted(by_date):
            for added, removed in by_date[d]:
                if removed:
                    if removed in members:
                        members.discard(removed)
                    else:
                        log.debug("%s: baja %s no estaba en la lista", d, removed)
                if added:
                    members.add(added)
            self.dates.append(d)
            self.lists.append(sorted(members))
        log.info("Composición: CSV hasta %s + %d cambios de Wikipedia hasta %s (%d tickers)",
                 csv_last, len(changes), self.dates[-1], len(members))
        if self.current:
            cur = set(self.current)
            log.info("Verificación vs. lista actual de Wikipedia: faltan %d, sobran %d",
                     len(cur - members), len(members - cur))
            log.debug("Faltan: %s | Sobran: %s", sorted(cur - members), sorted(members - cur))

    def on_date(self, target) -> list[str]:
        """Tickers vigentes en `target`. Más allá del último dato histórico usa la lista actual."""
        t = _day(target)
        if not self.dates:
            log.debug("%s: sin histórico, uso lista actual", t)
            return self.current
        if t > self.dates[-1] and self.current:
            log.debug("%s: posterior al último histórico (%s), uso lista actual", t, self.dates[-1])
            return self.current
        i = bisect.bisect_right(self.dates, t) - 1
        if i < 0:
            log.warning(E.DAT_NO_HISTORY.msg("Sin datos históricos <= %s"), t)
            return []
        log.debug("%s -> fila histórica %s (%d tickers)", t, self.dates[i], len(self.lists[i]))
        return self.lists[i]

    def all_between(self, start, end) -> list[str]:
        """Unión de todos los tickers que estuvieron en el índice entre start y end."""
        s, e = _day(start), _day(end)
        tickers = set()
        if self.dates:
            i0 = max(bisect.bisect_right(self.dates, s) - 1, 0)  # fila vigente al inicio
            i1 = bisect.bisect_right(self.dates, e)
            for lst in self.lists[i0:i1]:
                tickers.update(lst)
        tickers.update(self.current)
        return sorted(tickers)
