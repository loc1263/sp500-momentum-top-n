# Modelo Octubre - Top N del S&P 500

Estrategia de momentum: cada N meses se compran, con ponderación igual, las N acciones del S&P 500
que más subieron en los últimos N meses. Este proyecto la prueba con datos históricos (backtest),
mide cuánto del resultado depende del azar del calendario y genera reportes en consola y HTML.

> **Aviso:** es una herramienta de análisis, no una recomendación de inversión. El backtest no incluye
> comisiones ni impuestos y tiene sesgos de datos (ver [Limitaciones](#limitaciones)).

## Estructura

```
start.ps1      # levanta backend + frontend
backend/       # Python: backtest, Top actual, base SQLite y API HTTP
frontend/      # SPA en Svelte 5 + Vite con los resultados del día y del backtest
```

| Archivo | Para qué sirve |
|---|---|
| `start.ps1` | Levanta los dos servidores (`.\start.ps1`; Ctrl+C los detiene) |
| `backend/top3_backtest.py` | Backtest Point-in-Time, comparación de plazos y sensibilidad al calendario de arranque |
| `backend/top3_actual.py` | Top N de hoy: las acciones del S&P 500 con mejor retorno en el plazo configurado |
| `backend/run_pipeline.py` | Pipeline completo: backtest (todos los períodos y universos) + Top actual de cada universo + JSON del frontend |
| `backend/server.py` | API HTTP: `GET /api/report` (JSON con Top actual y backtest, leído de SQLite) |
| `backend/export_frontend.py` | Escribe ese mismo JSON en `frontend/public/data/report.json` (lo hacen solos los dos scripts al terminar) |
| `backend/top3/` | Paquete con la lógica (ver abajo); los scripts de arriba son solo la línea de comandos |
| `backend/config.toml` | Configuración (histórico, plazo, universo, salida, servidor) |
| `backend/data/top3.db` | Base SQLite con los datos descargados y los resultados (se crea sola) |
| `backend/output/` | Reportes HTML (`backtest/` y `actual/`); se crea sola |
| `backend/log/` | Logs de la última ejecución (nivel DEBUG) |
| `frontend/` | SPA: pestañas Top actual, Backtest y Plazos/sensibilidad, con selector de universo |

Los comandos de Python se corren desde `backend/` (las rutas del config son relativas a esa carpeta).

### Paquete `backend/top3/`

| Módulo | Responsabilidad |
|---|---|
| `config.py` | Valores por defecto, lectura de `config.toml` y `DataSettings` (parámetros de descarga) |
| `db.py`, `logs.py` | Esquema y conexión SQLite; logging |
| `constituents.py` | Composición Point-in-Time (CSV histórico + Wikipedia) |
| `prices.py`, `shares.py` | Precios (descarga completa e incremental) y acciones en circulación |
| `universe.py` | Universos por capitalización: filtro y etiquetas |
| `engine.py` | Motor del backtest (`run_backtest`) |
| `analysis.py` | Calendarios de arranque, resumen por plazo y guardado de corridas |
| `tables.py` | Tablas de resultados (texto) que comparten la consola y el HTML |
| `console.py`, `html_report.py` | Salida por consola y reportes HTML |
| `workflow.py`, `actual.py` | Flujos completos: backtest normal / sweep / offsets y Top actual |
| `report_data.py`, `api.py` | JSON del frontend y API HTTP |

## Pipeline completo

```
cd backend
python run_pipeline.py                  # todo: actualiza datos, backtest, Top actual y JSON del frontend
python run_pipeline.py --tests          # corre antes los tests
python run_pipeline.py --no-cache       # descarga todo de nuevo
python run_pipeline.py --years 7        # backtest de un único período
python run_pipeline.py --skip-backtest  # solo Top actual + JSON (rápido)
```

Cada paso corre en su propio proceso y, si uno falla, se corta. Al final imprime el tiempo de cada paso.

## Levantar todo

```
.\start.ps1                                   # backend en :8000, frontend en http://localhost:5173
.\start.ps1 -BackendPort 9000 -FrontendPort 3000
```

El frontend pide `/api/report` al backend (en desarrollo Vite lo redirige) y, si el backend no está, usa
`data/report.json`. Primero hay que haber corrido el backtest y el Top actual al menos una vez (ver Uso).
`npm run build` en `frontend/` genera la versión estática en `frontend/dist/`.

## Instalación

Requiere Python 3.11 o superior (usa `tomllib`).

```
cd backend
pip install -r requirements.txt          # o requirements-dev.txt para correr también los tests
```

`lxml` lo necesita `pandas.read_html` para leer las tablas de Wikipedia.

## Uso (desde `backend/`)

```
python top3_backtest.py                       # backtest normal (plazo de config.toml)
python top3_backtest.py --months 3            # backtest normal con otro plazo
python top3_backtest.py --sweep               # todo: 3 universos x (sweep + offsets) = 6 HTML
python top3_backtest.py --sweep --large-cap   # solo ese universo (sweep + offsets)
python top3_backtest.py --offsets             # solo el detalle de calendarios de arranque (universo completo)
python top3_backtest.py --no-cache            # vuelve a descargar todo
python top3_backtest.py --large-cap           # solo large-cap + mega-cap (>= 10 B)
python top3_backtest.py --min-cap-billions 200  # solo mega-cap (>= 200 B)
python top3_backtest.py --config otro.toml    # otro archivo de configuración
python top3_actual.py                         # Top N de hoy (plazo y top_n del config)
python top3_actual.py --months 6 --top-n 3    # otro plazo / otra cantidad
python top3_actual.py --min-cap-billions 200  # solo mega-cap
```

### Top actual (`top3_actual.py`)

Aplica a hoy la misma lógica del backtest: toma la lista actual del S&P 500 (con los alias de tickers),
calcula el retorno de las últimas N x 21 ruedas y muestra las `top_n` mejores con ponderación igual.
Usa `[backtest] months` y `top_n` del `config.toml`, y acepta `--months`, `--top-n`, `--large-cap`,
`--min-cap-billions`, `--no-cache` y `--config`. Por defecto: 4 meses y 4 acciones.

Reutiliza la base `data/top3.db`: si el backtest ya descargó los precios hoy, los lee de ahí y solo baja lo que
falte; si no, descarga la ventana reciente sin tocar el histórico guardado. Cada resultado se guarda en la tabla
`actual_picks` y se genera `output/actual/top3_actual_YYYYMMDD.html` (con sufijo `_largecap` / `_megacap` si
se filtra el universo). El último dato de la ventana es el precio más reciente disponible, que durante la
rueda puede ser intradía.

Las opciones de universo (`--large-cap`, `--min-cap-billions`) se combinan con `--sweep`, `--offsets`
o el backtest normal.

**`--sweep` solo** corre todas las opciones paramétricas: los universos de `[universe] sweep_min_cap_billions`
(por defecto índice completo, large-cap + mega-cap y mega-cap) y, para cada uno, el sweep y la sensibilidad
al arranque. Genera 6 HTML y al final lista las rutas. Si se pasa un filtro explícito
(`--large-cap` o `--min-cap-billions N`), corre solo ese universo.

### Qué muestra cada modo

- **Normal:** el calendario base (arranque en el primer mes), la tabla de selecciones con capital y
  ganancia/pérdida acumulada, la mediana y el rango de CAGR de todos los calendarios posibles del plazo,
  y una tabla con cada calendario.
- **`--sweep`:** una tabla que compara los plazos (3, 4, 6, 8 y 12 meses por defecto), con el resultado
  del calendario base y la mediana y el rango de CAGR. Ordenado por CAGR mediano. Incluye las selecciones
  de cada plazo. Se repite para cada universo y se acompaña del reporte de sensibilidad al arranque.
- **`--offsets`:** el resumen por plazo (mediana, mínimo y máximo de CAGR y de capital final) y el detalle de
  cada calendario. Dentro de `--sweep` reutiliza los calendarios ya calculados.

## Cómo funciona

1. **Composición del índice (Point-in-Time).** Se descarga el CSV histórico del repositorio
   [`hanshof/sp500_constituents`](https://github.com/hanshof/sp500_constituents), que llega hasta cierta
   fecha. Lo posterior se completa con las altas y bajas de la tabla de cambios de Wikipedia
   ([Historical components of the S&P 500](https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500)).
   La lista actual de Wikipedia se usa para verificar y para fechas posteriores al último cambio.
2. **Alias de tickers.** Las tablas usan símbolos distintos tras un renombre (por ejemplo `BK` y `BNY`);
   `[tickers.aliases]` los unifica con el símbolo vigente en Yahoo.
3. **Precios.** Se bajan con `yfinance` (precios ajustados) para todos los tickers que estuvieron en el índice
   durante el histórico, en lotes de 100.
4. **Backtest.** En cada fecha de rebalanceo se rankean las acciones del índice vigentes ese día por retorno
   de los últimos N meses (N x 21 ruedas), se eligen las `top_n` y se mantienen N meses. El retorno del
   período es el promedio simple de las acciones elegidas.
5. **Calendarios de arranque.** Un plazo de N meses se puede empezar en N meses distintos. Se prueban todos
   y se informa el calendario base (primer mes), la mediana y el rango, para medir cuánto del resultado
   depende de la fecha de arranque.
6. **Caché.** Todo se guarda en SQLite. Si se vuelve a correr el mismo día se reutiliza lo descargado;
   `--no-cache` fuerza una descarga nueva.
   Si es otro día, los precios se actualizan de forma incremental: solo se baja lo que falta desde la última
   descarga (tickers nuevos completos; un ticker que pagó dividendo o hizo split desde entonces se vuelve a bajar
   entero, porque su precio ajustado cambió). Una descarga completa solo ocurre con `--no-cache`, sin datos
   guardados o si se pide más histórico que el guardado (`history_years` mayor).

## Configuración (`config.toml`)

| Sección | Clave | Por defecto | Descripción |
|---|---|---|---|
| `[data]` | `history_years` | `12` | Años de histórico a descargar (composición y precios); debe superar el mayor período + 1 año de ranking |
| | `db_path` | `"data/top3.db"` | Base SQLite |
| | `historical_url` | CSV de `hanshof` | Composición histórica del S&P 500 |
| | `wikipedia_url`, `wikipedia_changes_url` | páginas de Wikipedia | Lista actual y altas/bajas del índice |
| | `user_agent` | `"Mozilla/5.0"` | User-Agent de las descargas a Wikipedia |
| | `http_timeout`, `historical_timeout` | `30`, `60` | Timeouts HTTP en segundos (Wikipedia / CSV histórico) |
| | `batch_size` | `100` | Tickers por lote al pedir precios a Yahoo |
| | `shares_workers` | `8` | Hilos en paralelo para las acciones en circulación |
| | `price_overlap_days`, `stale_days`, `price_drift_tolerance` | `7`, `30`, `0.0001` | Actualización incremental: días de solape, días sin cotizar para dar un ticker de baja y diferencia que fuerza a rebajarlo completo |
| `[backtest]` | `start_date`, `end_date` | `""` | Período a evaluar (`"YYYY-MM-DD"`); vacío = automático |
| | `backtest_years` | `5` | Años hacia atrás desde `end_date` si `start_date` está vacío |
| | `periods_years` | `[3, 5, 10]` | Períodos (años) que se simulan; el frontend deja elegir entre ellos. `--years N` corre uno solo |
| | `months` | `4` | Plazo del backtest normal: ranking de N meses y rebalanceo cada N meses |
| | `initial_capital` | `1000` | Capital inicial (US$) |
| | `top_n` | `4` | Cantidad de acciones por rebalanceo |
| | `trading_days_per_month` | `21` | Ruedas por mes para convertir meses en ventana de ranking |
| `[tickers.aliases]` | `VIEJO = "NUEVO"` | 6 renombres | Unifica símbolos renombrados |
| `[universe]` | `min_cap_billions` | `10` | Umbral de `--large-cap` (miles de millones de US$) |
| | `sweep_min_cap_billions` | `[0, 10, 200]` | Universos que corre `--sweep` por defecto (0 = índice completo) |
| `[server]` | `host`, `port`, `cors_origin` | `127.0.0.1`, `8000`, `*` | API HTTP de `server.py` |
| `[output]` | `dir` | `"output"` | Carpeta de los reportes HTML |
| | `frontend_data` | `"../frontend/public/data/report.json"` | JSON estático para el frontend |
| | `backtest_subdir`, `actual_subdir` | `"backtest"`, `"actual"` | Subcarpetas dentro de `dir` |
| | `backtest_prefix`, `sweep_prefix`, `offsets_prefix`, `actual_prefix` | `top3_*` | Prefijos de los archivos HTML |
| | `log_dir` | `"log"` | Carpeta de los logs |
| | `backtest_log`, `actual_log` | `top3_*.log` | Nombres de los archivos de log |
| `[simulation]` | `months` | `[3, 4, 6, 8, 12]` | Plazos que comparan `--sweep` y `--offsets` |

## Salidas

### HTML (`backend/output/`)

El nombre lleva la fecha de la corrida (`YYYYMMDD`); si se corre dos veces el mismo día se sobrescribe.

| Modo | Archivo |
|---|---|
| Normal | `output/backtest/top3_backtest_Ny_YYYYMMDD.html` |
| `--sweep` | `output/backtest/top3_sweep_Ny_YYYYMMDD.html` |
| `--offsets` | `output/backtest/top3_offsets_Ny_YYYYMMDD.html` |

Con filtro de universo el nombre suma un sufijo: `_largecap` (>= 10 B), `_megacap` (>= 200 B) o `_capXB`
para otro umbral. `Ny` es el período en años (`_3y`, `_5y`, `_10y`). Por ejemplo `top3_sweep_megacap_5y_20261020.html`.

### Consola

Las tablas de selecciones tienen una fila por rebalanceo: `Fecha`, los tickers `#1`..`#N` con su retorno,
`Cap. aprox. (US$ B)` (informativa), `Capital (US$)` (valor al entrar a esa fila) y `Gan/Pérd` (acumulado
vs. el capital inicial, en verde si es positivo). Se puede desactivar el color con la variable `NO_COLOR=1`.

### SQLite (`backend/data/top3.db`)

| Tabla | Contenido |
|---|---|
| `constituents_history` | Composición histórica (CSV) |
| `index_changes` | Altas y bajas de Wikipedia |
| `constituents_current` | Lista actual de Wikipedia |
| `prices` | Precios ajustados por ticker y fecha |
| `shares` | Acciones en circulación actuales (para la capitalización aproximada) |
| `meta` | Fechas de descarga y rango de precios (control del caché) |
| `runs`, `selections`, `equity` | Cada corrida: parámetros, selecciones y curva de capital |
| `actual_picks` | Resultados de `top3_actual.py` (fecha de datos, plazo, ticker, retorno, precio, capitalización) |

## Universo y capitalización

Por defecto compite todo el índice. Con `--large-cap` o `--min-cap-billions N` solo compiten las empresas con
capitalización aproximada de al menos N miles de millones de US$ (10 = large-cap + mega-cap, 200 = mega-cap).
La capitalización se aproxima con **precio de esa fecha x acciones en circulación actuales**, porque Yahoo
no entrega la serie histórica de acciones gratis. La columna `Cap. aprox.` de las tablas es solo informativa
cuando no se filtra.

## Limitaciones

- **Sesgo de supervivencia.** Los tickers que ya no cotizan (adquiridos o eliminados) no tienen precios en
  Yahoo y quedan fuera del backtest. Los retornos probablemente están inflados.
- **Look-ahead en el filtro de capitalización.** Usar las acciones de hoy hace que empresas que hoy son
  grandes entren al universo antes de tiempo. Pesa mucho más en mega-cap que en large-cap.
- **Pocas decisiones.** Con 5 años hay entre 5 y 20 rebalanceos por plazo, y el resultado depende de unas
  pocas rachas. Por eso se informa la mediana y el rango de los calendarios y no un solo número.
- **Sin costos.** No incluye comisiones, impuestos ni deslizamiento (slippage), y asume ponderación igual.
- **Dependencias externas.** Los datos vienen de Yahoo Finance, un repositorio de GitHub y Wikipedia. Si
  cambia el formato de alguna fuente, el script avisa en el log y sigue con lo que tenga guardado en SQLite.
- Un rebalanceo se decide con precios hasta esa misma fecha de rebalanceo.

## Depuración

Cada ejecución escribe `log/top3_backtest.log` (o `log/top3_actual.log`) con nivel DEBUG: respuestas HTTP, forma de las
tablas, tickers sin datos, filtros de capitalización y retornos por período. El log se sobrescribe en cada
corrida; la consola muestra solo el nivel INFO.

## Tests

```
cd backend && python -m pytest
```

Los tests están en `backend/tests/` (un archivo por módulo de `top3/`, más la línea de comandos y el pipeline). No usan red: los datos son sintéticos y las descargas se reemplazan por dobles de prueba.
