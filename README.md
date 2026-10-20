# sp500-momentum-top-n - Top N del S&P 500

Estrategia de momentum: cada N meses se compran, con ponderación igual, las N acciones del S&P 500
que más subieron en los últimos N meses. Este proyecto la prueba con datos históricos (backtest),
mide cuánto del resultado depende del azar del calendario y genera reportes en consola y HTML.

Además calcula el **Top actual** (qué comprar hoy, con los cambios respecto de la corrida anterior y el próximo
rebalanceo) y un **ranking de momentum de los ETFs de Vanguard** ajustado por riesgo, sin backtest.

> **Aviso:** es una herramienta de análisis, no una recomendación de inversión. El backtest no incluye
> comisiones ni impuestos y tiene sesgos de datos (ver [Limitaciones](docs/como-funciona.md#limitaciones)).

## Qué incluye

| Qué | Dónde se ve |
|---|---|
| **Backtest** Point-in-Time del S&P 500: comparación de plazos y sensibilidad al mes de arranque, por universo (índice completo, large-cap, mega-cap) y por período | Pestañas *Backtest* y *Plazos y sensibilidad* |
| **Top actual**: las N acciones con mejor retorno hoy, qué entra y qué sale, próximo rebalanceo | Pestaña *Top actual* |
| **ETFs de Vanguard**: ranking global por retorno ajustado por riesgo (exceso sobre un ETF de bonos ultracortos, dividido por la volatilidad), con tendencia y caída máxima | Pestaña *ETFs Vanguard* (ordenable y con filtros) |
| Reportes por consola (avisos en amarillo, errores en rojo, resumen final) y en HTML | `backend/output/` |
| Códigos de error y aviso estables (`TOP-BKT-003`...) en el log y en el resumen final | [docs/errores.md](docs/errores.md) |

## Inicio rápido

Requiere Python 3.11 o superior y Node.js.

```
cd backend
pip install -r requirements.txt          # o requirements-dev.txt para correr también los tests
python run_pipeline.py                   # descarga datos; backtest, Top actual, ETFs de Vanguard y JSON del frontend
cd ../frontend
npm install
cd ..
.\start.ps1                              # backend en :8000, frontend en http://localhost:5173
```

`lxml` lo necesita `pandas.read_html` para leer las tablas de Wikipedia.

Comandos sueltos más usados (desde `backend/`):

```
python top3_backtest.py --sweep          # backtest de todos los plazos y universos
python top3_actual.py                    # Top N de hoy
python top3_etf.py                       # ranking de ETFs de Vanguard (--as-of 2025-06-30 para una fecha pasada)
python run_pipeline.py --no-cache        # descarga todo de nuevo (solo el primer paso; los demás reutilizan)
python prune_db.py                       # limpia corridas viejas de SQLite (también se hace sola en cada backtest)
python -m pytest                         # tests del backend (en frontend/: npm test)
```

Con `--no-cache` el backtest completo tarda del orden de un minuto y medio, casi todo en la descarga de precios; el
Top actual y los ETFs, segundos. Todas las opciones están en [docs/uso.md](docs/uso.md).

## Estructura

```
start.ps1             # levanta backend + frontend
backend/              # Python: backtest, Top actual, ranking de ETFs, base SQLite y API HTTP
  config.toml         # configuración
  vanguard_etfs.csv   # lista de ETFs de Vanguard (se mantiene a mano)
frontend/             # SPA en Svelte 5 + Vite: Top actual, backtest, plazos y ETFs
docs/                 # documentación
```

## Documentación

| Documento | Contenido |
|---|---|
| [docs/uso.md](docs/uso.md) | Comandos, pipeline completo, modos del backtest, Top actual y ranking de ETFs de Vanguard |
| [docs/como-funciona.md](docs/como-funciona.md) | Metodología, universo y capitalización, caché, limitaciones |
| [docs/configuracion.md](docs/configuracion.md) | Todas las claves de `config.toml` |
| [docs/salidas.md](docs/salidas.md) | Reportes HTML, consola, tablas SQLite, logs y limpieza de la base |
| [docs/errores.md](docs/errores.md) | Códigos de error y aviso (`TOP-BKT-003`...) y qué hacer con cada uno |
| [docs/desarrollo.md](docs/desarrollo.md) | Módulos del backend y del frontend, tests |
