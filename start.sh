#!/usr/bin/env bash
# Levanta el backend (Python, API en /api/report) y el frontend (Svelte + Vite) a la vez.
# Equivalente de start.ps1 para macOS y Linux. Ctrl+C detiene los dos servidores.
#
#   ./start.sh
#   BACKEND_PORT=9000 FRONTEND_PORT=3000 ./start.sh
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
backend_host="${BACKEND_HOST:-127.0.0.1}"
backend_port="${BACKEND_PORT:-8000}"
frontend_port="${FRONTEND_PORT:-5173}"

# Se usa el primer intérprete que realmente funcione (en Windows python3 puede ser un acceso directo vacío)
python_bin=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null && "$candidate" -c "import sys" 2>/dev/null; then
        python_bin="$candidate"; break
    fi
done
[ -n "$python_bin" ] || { echo "No se encontró Python 3.11 o superior en el PATH." >&2; exit 1; }
command -v npm >/dev/null || { echo "No se encontró npm en el PATH." >&2; exit 1; }

if [ ! -d "$root/frontend/node_modules" ]; then
    echo "Instalando dependencias del frontend..."
    (cd "$root/frontend" && npm install)
fi

# El frontend redirige /api al backend
export BACKEND_URL="http://${backend_host}:${backend_port}"
export FRONTEND_PORT="$frontend_port"

pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "Backend  -> http://${backend_host}:${backend_port}/api/report"
(cd "$root/backend" && exec "$python_bin" server.py --host "$backend_host" --port "$backend_port") &
pids+=($!)

echo "Frontend -> http://localhost:${frontend_port}"
(cd "$root/frontend" && exec npm run dev) &
pids+=($!)

echo "Ctrl+C para detener ambos."
# Si uno de los dos termina, se detiene el otro
wait -n
echo "Uno de los servidores terminó; se detiene el otro." >&2
