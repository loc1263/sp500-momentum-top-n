# Desarrollo

## Estructura

```
start.ps1      # levanta backend + frontend
backend/       # Python: backtest, Top actual, base SQLite y API HTTP
frontend/      # SPA en Svelte 5 + Vite con los resultados del día y del backtest
docs/          # documentación
```

| Archivo | Para qué sirve |
|---|---|
| `start.ps1` | Levanta los dos servidores (`.\start.ps1`; Ctrl+C los detiene) |
| `backend/top3_backtest.py` | Backtest Point-in-Time, comparación de plazos y sensibilidad al calendario de arranque |
| `backend/top3_actual.py` | Top N de hoy: las acciones del S&P 500 con mejor retorno en el plazo configurado |
| `backend/top3_etf.py` | Ranking de momentum ajustado por riesgo de los ETFs de Vanguard (sin backtest) |
| `backend/vanguard_etfs.csv` | Lista de ETFs de Vanguard (se mantiene a mano) |
| `backend/run_pipeline.py` | Pipeline completo: backtest (todos los períodos y universos) + Top actual de cada universo + JSON del frontend |
| `backend/server.py` | API HTTP: `GET /api/report` (JSON con Top actual y backtest, leído de SQLite) |
| `backend/prune_db.py` | Limpia a mano las corridas viejas de SQLite (se hace sola en cada backtest) |
| `backend/export_frontend.py` | Escribe ese mismo JSON en `frontend/public/data/report.json` (lo hacen solos los dos scripts al terminar) |
| `backend/top3/` | Paquete con la lógica (ver abajo); los scripts de arriba son solo la línea de comandos |
| `backend/config.toml` | Configuración (ver [configuracion.md](configuracion.md)) |
| `backend/data/top3.db` | Base SQLite con los datos descargados y los resultados (se crea sola) |
| `backend/output/` | Reportes HTML (`backtest/` y `actual/`); se crea sola |
| `backend/log/` | Logs de la última ejecución (nivel DEBUG) |
| `frontend/` | SPA: pestañas Top actual, Backtest y Plazos/sensibilidad, con selector de universo |

## Paquete `backend/top3/`

| Módulo | Responsabilidad |
|---|---|
| `config.py` | Valores por defecto, lectura de `config.toml` y `DataSettings` (parámetros de descarga) |
| `db.py`, `logs.py` | Esquema y conexión SQLite; logging |
| `constituents.py` | Composición Point-in-Time (CSV histórico + Wikipedia) |
| `prices.py`, `shares.py` | Precios (descarga completa e incremental, con reintento ante rate limit) y acciones en circulación |
| `yahoo.py` | Clasifica los errores que yfinance escribe en su logger y captura los tickers rechazados para reintentarlos |
| `universe.py` | Universos por capitalización: filtro y etiquetas |
| `engine.py` | Motor del backtest (`run_backtest`) |
| `analysis.py` | Calendarios de arranque, resumen por plazo y guardado de corridas |
| `tables.py` | Tablas de resultados (texto) que comparten la consola y el HTML |
| `console.py`, `html_report.py` | Salida por consola y reportes HTML |
| `etf.py` | Ranking de ETFs: lista, score ajustado por riesgo, guardado en `etf_scores` y reportes |
| `rotation.py` | Top actual: cambios contra la corrida anterior y próximo rebalanceo |
| `workflow.py`, `actual.py` | Flujos completos: backtest normal / sweep / offsets y Top actual |
| `report_data.py`, `api.py` | JSON del frontend y API HTTP |

## Frontend (`frontend/src/`)

| Archivo | Responsabilidad |
|---|---|
| `App.svelte` | Carga de datos (API y luego JSON estático), pestañas, filtros de universo y período, tema |
| `lib/ActualView.svelte` | Top actual |
| `lib/BacktestView.svelte` | Tarjetas, curva de capital, historial de selecciones y calendarios |
| `lib/SweepView.svelte` | Comparación de plazos y sensibilidad al arranque |
| `lib/Chart.svelte`, `Range.svelte`, `TickerLink.svelte`, `Glossary.svelte` | Componentes compartidos |
| `lib/format.js` | Formato de porcentajes, dinero y signos |
| `test/` | Configuración de los tests y datos de ejemplo (`fixtures.js`) |

## Tests

Backend (`backend/tests/`, un archivo por módulo de `top3/`, más la línea de comandos y el pipeline). No usan
red: los datos son sintéticos y las descargas se reemplazan por dobles de prueba.

```
cd backend && python -m pytest
```

Frontend (Vitest + Testing Library sobre jsdom, junto a cada componente como `*.test.js`). La carga de datos se
prueba reemplazando `fetch`.

```
cd frontend && npm test
```
