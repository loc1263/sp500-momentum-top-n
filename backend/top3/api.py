"""API HTTP de solo lectura: expone al frontend los resultados guardados en SQLite.

GET /api/report  -> JSON con el Top actual y el backtest (ver report_data.build_report)
GET /api/health  -> {"status": "ok"}
"""
import json
import threading
from http.server import BaseHTTPRequestHandler

from .db import open_db
from .logs import log
from .report_data import build_report


class ReportCache:
    """Guarda el JSON del reporte y solo lo reconstruye cuando cambian los resultados en SQLite.

    Armarlo lee miles de filas; la huella (últimas corridas guardadas) es instantánea.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._lock = threading.Lock()
        self._fingerprint = None
        self._body: bytes | None = None

    @staticmethod
    def _fingerprint_of(conn) -> tuple:
        runs = conn.execute("SELECT COUNT(*), MAX(id) FROM runs").fetchone()
        actual = conn.execute("SELECT COUNT(*), MAX(run_at) FROM actual_picks").fetchone()
        return runs, actual

    def get(self) -> bytes:
        conn = open_db(self.cfg["data"]["db_path"])
        try:
            fingerprint = self._fingerprint_of(conn)
            with self._lock:
                if fingerprint != self._fingerprint or self._body is None:
                    log.info("Reconstruyendo el reporte (cambiaron los resultados guardados)")
                    report = build_report(conn, self.cfg)
                    self._body = json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    self._fingerprint = fingerprint
                return self._body
        finally:
            conn.close()


def make_handler(cfg: dict) -> type[BaseHTTPRequestHandler]:
    cache = ReportCache(cfg)

    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload) -> None:
            body = payload if isinstance(payload, bytes) else json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", cfg["server"]["cors_origin"])
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0].rstrip("/")
            if path == "/api/health":
                return self._send_json(200, {"status": "ok"})
            if path == "/api/report":
                try:
                    return self._send_json(200, cache.get())
                except Exception:
                    log.exception("Error armando /api/report")
                    return self._send_json(500, {"error": "No se pudo leer la base de datos"})
            self._send_json(404, {"error": "No existe"})

        def log_message(self, fmt, *args) -> None:
            log.info("%s - %s", self.address_string(), fmt % args)

    Handler.cache = cache
    return Handler
