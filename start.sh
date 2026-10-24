#!/usr/bin/env bash
# Levanta el frontend (Svelte + Vite). La página lee frontend/public/data/report.json, que dejan los scripts de
# Python (backend/run_pipeline.py); no necesita el backend en marcha. Ctrl+C lo detiene.
# Equivalente de start.ps1 para macOS y Linux.
#
#   ./start.sh
#   FRONTEND_PORT=3000 ./start.sh
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export FRONTEND_PORT="${FRONTEND_PORT:-5173}"

command -v npm >/dev/null || { echo "No se encontró npm en el PATH." >&2; exit 1; }

if [ ! -d "$root/frontend/node_modules" ]; then
    echo "Instalando dependencias del frontend..."
    (cd "$root/frontend" && npm install)
fi

if [ ! -f "$root/frontend/public/data/report.json" ]; then
    echo "Aviso: falta frontend/public/data/report.json. Ejecute 'python run_pipeline.py' en backend/ para generarlo." >&2
fi

echo "Frontend -> http://localhost:${FRONTEND_PORT}   (Ctrl+C para detener)"
cd "$root/frontend" && exec npm run dev
