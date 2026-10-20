"""Servidor HTTP del backend (GET /api/report y /api/health) para el frontend.

    python server.py [--host H] [--port P] [--config config.toml]
"""
import argparse
import threading
from http.server import ThreadingHTTPServer

from top3.api import make_handler
from top3.config import load_config
from top3.logs import log, log_config, setup_logging


def main() -> None:
    ap = argparse.ArgumentParser(description="Servidor HTTP con los resultados del backtest y el Top actual")
    ap.add_argument("--config", default="config.toml", help="Archivo de configuración (default: config.toml)")
    ap.add_argument("--host", default=None, help="Host (default: [server] host del config)")
    ap.add_argument("--port", type=int, default=None, help="Puerto (default: [server] port del config)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg["output"]["server_log"], cfg["output"]["log_dir"])
    log_config(cfg, args.config)
    host = args.host or cfg["server"]["host"]
    port = args.port or int(cfg["server"]["port"])
    handler = make_handler(cfg)
    # Se precalcula en segundo plano para que el primer pedido del frontend no espere
    threading.Thread(target=handler.cache.get, daemon=True).start()
    httpd = ThreadingHTTPServer((host, port), handler)
    log.info("Backend escuchando en http://%s:%d (GET /api/report)", host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("Backend detenido")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
