"""Resultado guardado del modelo por score (quant_runs): solo se conserva el último."""
import json
import sqlite3


def save_latest(conn: sqlite3.Connection, run_at: str, as_of: str, payload: dict) -> None:
    conn.execute("DELETE FROM quant_runs")
    conn.execute("INSERT INTO quant_runs (run_at, as_of, payload) VALUES (?, ?, ?)",
                 (run_at, as_of, json.dumps(payload, ensure_ascii=False)))
    conn.commit()


def latest(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute("SELECT payload FROM quant_runs ORDER BY run_at DESC LIMIT 1").fetchone()
    return json.loads(row[0]) if row else None
