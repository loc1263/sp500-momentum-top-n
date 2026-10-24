# sp500-momentum-top-n

Estrategia de momentum sobre el S&P 500: cada N meses se compran, con ponderación igual, las N acciones que más
subieron en los últimos N meses. El proyecto la evalúa con datos históricos (backtest), mide cuánto del resultado
depende del mes de arranque y muestra los resultados en una aplicación web local.

Además calcula el **Top actual** (qué acciones lidera hoy el ranking, con sus suplentes, los cambios respecto de la
corrida anterior y el próximo rebalanceo) y un **ranking de momentum de los ETFs de Vanguard** ajustado por riesgo.

> **Aviso:** es una herramienta de análisis, no una recomendación de inversión. El backtest cobra solo una comisión
> de 0,05% por lado, sin impuestos, y tiene sesgos de datos (ver [Limitaciones](#limitaciones)).

## Qué incluye

| Funcionalidad | Dónde se ve |
|---|---|
| **Backtest** Point-in-Time: comparación de plazos y sensibilidad al mes de arranque, por universo (índice completo, large-cap, mega-cap) y por período | Pestañas *Backtest* y *Plazos y sensibilidad* |
| **Comparación N-0 vs. N-1**: el modelo de siempre frente a una variante *skip-month* que ignora el último mes al rankear, plazo por plazo | Pestaña *N-0 vs N-1* |
| **Top actual**: las N acciones con mejor retorno hoy, cuatro suplentes, qué entra y qué sale, próximo rebalanceo | Pestaña *Top actual* |
| **ETFs de Vanguard**: ranking por retorno ajustado por riesgo, con tendencia y caída máxima | Pestaña *ETFs Vanguard* |
| **About**: qué se muestra en cada pestaña, de dónde salen los datos, qué incluyen los resultados y sus límites | Pestaña *About* |
| Reportes por consola y en HTML, con códigos de error estables (`TOP-BKT-003`, ...) | `backend/output/` y [Códigos de error](#códigos-de-error-y-aviso) |

## Requisitos

| Herramienta | Versión | Para qué |
|---|---|---|
| [Python](https://www.python.org/downloads/) | 3.11 o superior | Descarga de datos, cálculos y API |
| [Node.js](https://nodejs.org/) (incluye `npm`) | 20.19 o superior | Interfaz web |
| Conexión a internet | | Descarga de precios y listas del índice |

## Cómo ejecutarlo

El proceso tiene tres pasos: **instalar**, **generar los datos** y **abrir la web**. Los comandos se escriben en
una terminal (en Windows, PowerShell; en macOS y Linux, Terminal). Primero se descarga el proyecto:

```
git clone https://github.com/loc1263/sp500-momentum-top-n.git
cd sp500-momentum-top-n
```

### 1. Instalar las dependencias

```
cd backend
pip install -r requirements.txt
cd ../frontend
npm install
cd ..
```

En macOS y Linux, si `pip` no existe, use `pip3` (y `python3` en lugar de `python` en los pasos siguientes).

### 2. Generar los datos (backend)

```
cd backend
python run_pipeline.py
cd ..
```

Este comando descarga los precios, ejecuta el backtest y el Top actual, calcula el ranking de ETFs y deja todo
guardado en una base SQLite local (`backend/data/`). **La primera vez tarda varios minutos** (descarga más de diez
años de precios); las siguientes ejecuciones son mucho más rápidas porque solo actualizan lo que falta.

Al terminar imprime un resumen con el tiempo de cada paso y los avisos que hayan aparecido.

### 3. Levantar la web

Desde la carpeta raíz del proyecto:

| Sistema | Comando |
|---|---|
| Windows (PowerShell) | `.\start.ps1` |
| macOS / Linux | `./start.sh` |

Esto inicia el frontend (puerto 5173). La página **no consulta ningún servidor**: lee el archivo estático
`frontend/public/data/report.json`, que el paso 2 deja actualizado. Cuando aparezca el mensaje
`Local: http://localhost:5173/`, abra esa dirección en el navegador:

**http://localhost:5173**

Para detenerlo, presione `Ctrl+C` en la terminal.

<details>
<summary>Levantar el frontend a mano (alternativa a los scripts)</summary>

```
cd frontend
npm run dev
```

</details>

### Actualizar los resultados

Para refrescar los datos (por ejemplo, otro día), vuelva a ejecutar el paso 2 y recargue la página. El servidor
puede seguir en marcha.

### Problemas frecuentes

| Síntoma | Solución |
|---|---|
| PowerShell indica que la ejecución de scripts está deshabilitada | Ejecute `powershell -ExecutionPolicy Bypass -File .\start.ps1` o use la alternativa manual |
| La página muestra «No se pudo cargar data/report.json» | Falta el paso 2. Ejecute `python run_pipeline.py` en `backend/` y recargue |
| La pestaña indica «Sin Top actual» o «Sin backtest» | Ejecute `python run_pipeline.py` en `backend/` |
| Error por puerto en uso | Cierre el programa que lo ocupa o cambie el puerto: `.\start.ps1 -FrontendPort 3000` (Windows) o `FRONTEND_PORT=3000 ./start.sh` |
| Avisos o errores durante la descarga (`TOP-NET-...`) | Suelen ser problemas de red o límites de Yahoo Finance; vuelva a intentarlo más tarde. Ver [Códigos de error](#códigos-de-error-y-aviso) |

## Cómo funciona

1. **Composición del índice (Point-in-Time).** Se descarga el CSV histórico del repositorio
   [`hanshof/sp500_constituents`](https://github.com/hanshof/sp500_constituents), que llega hasta cierta
   fecha. Lo posterior se completa con las altas y bajas de la tabla de cambios de Wikipedia
   ([Historical components of the S&P 500](https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500)).
   La lista actual de Wikipedia se usa para verificar y para fechas posteriores al último cambio.
2. **Alias de tickers.** Las tablas usan símbolos distintos tras un renombre (por ejemplo `BK` y `BNY`);
   `[tickers.aliases]` los unifica con el símbolo vigente en Yahoo.
3. **Precios.** Se bajan con `yfinance` (precios ajustados) para todos los tickers que estuvieron en el índice
   durante el histórico, en lotes de 100. Si Yahoo rechaza tickers por rate limit, se reintentan hasta 3 veces
   esperando 10, 20 y 40 s (`TOP-NET-006`); si siguen rechazados quedan sin datos y se informa como error
   (`TOP-NET-005`). Los tickers dados de baja (esperables) solo quedan en el log a nivel DEBUG y se anotan en
   `no_data_tickers`: no se vuelven a pedir hasta pasados `[data] no_data_ttl_days` días (30), ni siquiera con
   `--no-cache`.
4. **Backtest.** En cada fecha de rebalanceo se rankean las acciones del índice vigentes ese día por retorno
   de los últimos N meses (N x 21 ruedas), se eligen las `top_n` y se mantienen N meses. El retorno del
   período es el promedio simple de las acciones elegidas. Se cobra una comisión por lado
   (`[backtest] commission`, 0,05%) al armar la cartera y por las posiciones que cambian en cada rebalanceo.
5. **Calendarios de arranque.** Un plazo de N meses se puede empezar en N meses distintos. Se prueban todos
   y se informa el calendario base (primer mes), la mediana y el rango, para medir cuánto del resultado
   depende de la fecha de arranque.
6. **Comparación con skip-month (N-1).** En cada sweep se corre además una variante que arma el ranking con los
   N meses que terminan un mes (21 ruedas) antes de la fecha de rebalanceo, para no premiar rebotes de corto
   plazo. Las compras y el rendimiento siguen contándose desde la fecha de rebalanceo. Usa los mismos precios,
   universos, períodos y fechas de arranque que el modelo de siempre (N-0), que es el que se usa en el Top
   actual. En las corridas de prueba N-0 rindió más que N-1 con el plazo de 4 meses; N-1 solo ganó en plazos
   cortos. El Top actual no calcula la variante N-1. Para ver si una ventaja depende de un solo tramo del
   mercado, la pestaña *N-0 vs N-1* parte cada período en dos mitades (por fecha) y muestra el CAGR mediano de
   cada modelo en cada una, a partir de las curvas de capital ya guardadas (sin simulaciones nuevas): si un modelo
   gana en las dos mitades, su ventaja se sostiene. Con períodos cortos cada mitad tiene muy pocos rebalanceos.
7. **Caché.** Todo se guarda en SQLite. Si se vuelve a correr el mismo día se reutiliza lo descargado;
   `--no-cache` fuerza una descarga nueva, pero no repite dentro de la misma corrida lo que ya bajó (p. ej. las
   acciones en circulación), y `run_pipeline.py` lo aplica solo al primer paso que descarga: los siguientes leen de
   SQLite lo que ese paso acaba de guardar. Las acciones en circulación cambian por trimestre, así que se
   reutilizan hasta `[data] shares_ttl_days` días (30 por defecto) aunque sean de otro día. Si es otro día, los
   precios se actualizan de forma incremental: solo se baja lo que falta desde la última descarga (tickers
   nuevos completos; un ticker que pagó dividendo o hizo split desde entonces se vuelve a bajar entero, porque su
   precio ajustado cambió). Una descarga completa solo ocurre con `--no-cache`, sin datos guardados o si se pide
   más histórico que el guardado (`history_years` mayor).

### Universo y capitalización

Por defecto compite todo el índice. Con `--large-cap` o `--min-cap-billions N` solo compiten las empresas con
capitalización aproximada de al menos N miles de millones de US$ (10 = large-cap + mega-cap, 200 = mega-cap).
La capitalización se aproxima con **precio de esa fecha x acciones en circulación actuales**, porque Yahoo
no entrega la serie histórica de acciones gratis. La columna `Cap. aprox.` de las tablas es solo informativa
cuando no se filtra.

### Limitaciones

- **Sesgo de supervivencia.** Los tickers que ya no cotizan (adquiridos o eliminados) no tienen precios en
  Yahoo y quedan fuera del backtest. Los retornos probablemente están inflados.
- **Look-ahead en el filtro de capitalización.** Usar las acciones de hoy hace que empresas que hoy son
  grandes entren al universo antes de tiempo. Pesa mucho más en mega-cap que en large-cap.
- **Pocas decisiones.** Con 5 años hay entre 5 y 20 rebalanceos por plazo, y el resultado depende de unas
  pocas rachas. Por eso se informa la mediana y el rango de los calendarios y no un solo número.
- **Costos parciales.** Cobra una comisión por lado (`[backtest] commission`, 0,05%) al armar la cartera y por las
  posiciones que cambian en cada rebalanceo; no incluye impuestos ni deslizamiento (slippage), no cobra el
  reequilibrio de pesos de las que se mantienen y asume ponderación igual.
- **Dependencias externas.** Los datos vienen de Yahoo Finance, un repositorio de GitHub y Wikipedia. Si
  cambia el formato de alguna fuente, el script avisa en el log y sigue con lo que tenga guardado en SQLite.
- Un rebalanceo se decide con precios hasta esa misma fecha de rebalanceo.

## Uso

Los comandos de Python se corren desde `backend/` (las rutas del config son relativas a esa carpeta).

### Levantar todo

```
.\start.ps1                                   # Windows: frontend en http://localhost:5173
.\start.ps1 -FrontendPort 3000
./start.sh                                    # macOS / Linux
FRONTEND_PORT=3000 ./start.sh
```

La página no pide nada al backend: lee `data/report.json`, el archivo estático que dejan al terminar
`run_pipeline.py`, `top3_backtest.py`, `top3_actual.py` y `top3_etf.py` (también `export_frontend.py` a mano). Primero
hay que haber corrido el pipeline al menos una vez. `npm run build` en `frontend/` genera la versión estática en
`frontend/dist/`, que se puede publicar en cualquier hosting estático con el JSON de ese momento.

`backend/server.py` sigue disponible como API opcional (`GET /api/report`), pero la web no la usa.

### Pipeline completo

```
cd backend
python run_pipeline.py                  # todo: actualiza datos, backtest, Top actual y JSON del frontend
python run_pipeline.py --tests          # corre antes los tests
python run_pipeline.py --no-cache       # descarga todo de nuevo (solo el primer paso que descarga; los demás leen lo que acaba de guardar)
python run_pipeline.py --years 7        # backtest de un único período
python run_pipeline.py --skip-backtest  # solo Top actual + JSON (rápido)
python run_pipeline.py --skip-actual    # omite el Top actual
python run_pipeline.py --skip-etf       # omite el ranking de ETFs
```

Cada paso corre en su propio proceso y, si uno falla, se corta. Al final imprime el tiempo de cada paso.

### Scripts sueltos

```
python top3_backtest.py                       # backtest normal (plazo de config.toml)
python top3_backtest.py --months 3            # backtest normal con otro plazo
python top3_backtest.py --sweep               # todo: 3 universos x (sweep + offsets) = 6 HTML
python top3_backtest.py --sweep --large-cap   # solo ese universo (sweep + offsets)
python top3_backtest.py --offsets             # solo el detalle de calendarios de arranque (universo completo)
python top3_backtest.py --no-cache            # vuelve a descargar todo
python top3_backtest.py --large-cap           # solo large-cap + mega-cap (>= 10 B)
python top3_backtest.py --min-cap-billions 200  # solo mega-cap (>= 200 B)
python top3_backtest.py --years 5             # un único período de 5 años
python top3_backtest.py --config otro.toml    # otro archivo de configuración
python top3_actual.py                         # Top N de hoy (plazo y top_n del config)
python top3_actual.py --months 6 --top-n 3    # otro plazo / otra cantidad
python top3_actual.py --min-cap-billions 200  # solo mega-cap
python top3_etf.py                            # ranking de ETFs de Vanguard
python prune_db.py                            # limpia a mano las corridas viejas de SQLite
python -m pytest                              # tests del backend (requiere requirements-dev.txt)
```

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
- **`--sweep`:** una tabla que compara los plazos (los de `[simulation] months`), con el resultado
  del calendario base y la mediana y el rango de CAGR. Ordenado por CAGR mediano. Incluye las selecciones
  de cada plazo. Se repite para cada universo y se acompaña del reporte de sensibilidad al arranque.
- **`--offsets`:** el resumen por plazo (mediana, mínimo y máximo de CAGR y de capital final) y el detalle de
  cada calendario. Dentro de `--sweep` reutiliza los calendarios ya calculados.
- **Comparación N-0 vs. N-1 (dentro de `--sweep`):** después de la sensibilidad al arranque, una tabla por universo
  con el CAGR y el capital final típicos (mediana de los calendarios) del modelo de siempre (N-0) y del skip-month
  (N-1), la diferencia en puntos porcentuales y cuál gana en cada plazo. Las corridas del N-1 se guardan en SQLite
  con `skip_months = 1` y se ven en la pestaña *N-0 vs N-1*.

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

Además del Top, muestra:

- **Suplentes:** los `[backtest] alternates` puestos siguientes al `top_n` (4 por defecto), con el mismo criterio
  de ranking, para evaluar el reemplazo de alguna acción del top. No tienen peso asignado y no afectan el backtest
  ni la comparación con la corrida anterior. Se guardan en la tabla `actual_alternates`.
- **Cambios vs. la corrida anterior:** qué tickers entran, salen y se mantienen respecto de la última selección
  guardada en `actual_picks` (mismo plazo y universo).
- **Próximo rebalanceo:** el primer inicio de mes de la grilla "cada N meses" contada desde la primera corrida
  guardada. Es una referencia: el backtest no tiene un ancla fija para el Top de hoy.
- **Tickers excluidos:** los que tienen huecos de precios en la ventana no se pueden rankear (igual que en el
  backtest) y quedan listados como advertencia en la consola y en el log.
- **Seguimiento de selecciones anteriores (solo en la web):** para cada selección guardada en `actual_picks`, el
  retorno de ponderación igual entre el precio de cuando se eligió y el último precio disponible en la base,
  sin pasar de los N meses que dura la tenencia. Pasado ese plazo figura como *cerrada*. Es una verificación fuera
  del backtest, pero hace falta acumular selecciones (una por corrida con datos de un día nuevo) antes de que diga algo.

Correr el script dos veces con los mismos datos reemplaza el resultado en lugar de duplicarlo.

### ETFs de Vanguard (`top3_etf.py`)

Ranking global de momentum de los ETFs de Vanguard, **sin backtest**: qué ETFs tienen hoy (o a una fecha dada) más
retorno por unidad de riesgo.

```
python top3_etf.py                       # ranking de hoy; muestra el top de [etf] top_n
python top3_etf.py --top-n 30            # más filas en la consola (el HTML siempre trae todos)
python top3_etf.py --as-of 2025-06-30    # ranking con los datos hasta esa fecha
python top3_etf.py --csv otra_lista.csv  # otra lista de ETFs (esa lista no se actualiza sola)
python top3_etf.py --no-update           # no agrega los ETFs nuevos de Vanguard a la lista
python run_pipeline.py --skip-etf        # el pipeline lo incluye salvo que se omita
```

**Score.** Para cada plazo de `[etf] horizons_months` (3, 6 y 12 meses por defecto):
`(retorno del plazo - retorno de la referencia libre de riesgo) / (volatilidad anual x raíz(meses/12))`. El score es el
promedio de esos cocientes. La referencia es `[etf] risk_free_ticker` (VUSB, bonos ultracortos): sin restarla, un ETF
casi sin riesgo ganaría siempre. Los ETFs de tipo efectivo (volatilidad anual menor a `[etf] min_vol`, como VBIL, VGUS y la propia VUSB) no entran al ranking: con tan poco riesgo cualquier exceso mínimo sobre la referencia daría un score enorme sin ser una señal de momentum; se listan aparte en la consola y el HTML. Además del score la tabla muestra el retorno de cada plazo, la volatilidad anual y la
caída máxima del plazo más largo, y la distancia del precio a su media de 200 ruedas (positivo = tendencia alcista).

**La lista** está en `backend/vanguard_etfs.csv` (`ticker,name,category`). Cada vez que se corre el ranking se
consulta el servicio que alimenta la página de productos de Vanguard y se **agregan al final del archivo los ETFs que
falten** (con la categoría que se deduce del estilo que informa Vanguard); las filas que ya existen no se tocan, así
que nombres y categorías se pueden corregir a mano, y nunca se borra ninguna. Si Vanguard ya no lista un ETF de la
lista, se informa en el log para que se quite a mano. Si la consulta falla (sin red, formato distinto) se usa la lista
guardada y se avisa con `TOP-ETF-006`. Es un servicio no documentado de la web de Vanguard, de uso personal. Un ticker sin precios en Yahoo avisa con `TOP-ETF-002`; los ETFs sin historia suficiente para el
plazo más largo quedan fuera del ranking y se listan (`TOP-ETF-003`).

**`--as-of`** usa la lista actual, así que no incluye los ETFs lanzados después de esa fecha ni los cerrados: sirve
para ver cómo se veía el ranking, no como backtest, y no se guarda. Cada corrida normal se guarda en la tabla
`etf_scores` y se compara el top con el de la corrida anterior (entran / salen). Reporte HTML en `output/etf/`.

## Configuración (`backend/config.toml`)

Los valores de la columna «Por defecto» son los que se usan si la clave no está en el archivo; el `config.toml`
incluido puede traer otros (por ejemplo más períodos y plazos en `[simulation]`).

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
| | `shares_ttl_days` | `30` | Días que se reutilizan las acciones en circulación guardadas (cambian por trimestre); `--no-cache` las vuelve a pedir |
| | `no_data_ttl_days` | `30` | Días que no se vuelve a pedir un ticker que Yahoo dijo que no existe o está dado de baja (`0` = pedirlos siempre) |
| | `runs_keep_days` | `7` | Días con corridas del backtest que se conservan en SQLite (mínimo 1); ver [Limpieza de la base](#limpieza-de-la-base) |
| `[backtest]` | `start_date`, `end_date` | `""` | Período a evaluar (`"YYYY-MM-DD"`); vacío = automático |
| | `backtest_years` | `5` | Años hacia atrás desde `end_date` si `start_date` está vacío |
| | `periods_years` | `[3, 5, 10]` | Períodos (años) que se simulan; el frontend deja elegir entre ellos. `--years N` corre uno solo |
| | `months` | `4` | Plazo del backtest normal: ranking de N meses y rebalanceo cada N meses |
| | `initial_capital` | `1000` | Capital inicial (US$) |
| | `top_n` | `4` | Cantidad de acciones por rebalanceo |
| | `commission` | `0.0005` | Comisión por lado (0,05%): se cobra al armar la cartera y por las posiciones que cambian en cada rebalanceo |
| | `alternates` | `4` | Suplentes del Top actual: puestos posteriores al `top_n` que se muestran como reemplazo posible (`0` = ninguno) |
| | `trading_days_per_month` | `21` | Ruedas por mes para convertir meses en ventana de ranking |
| `[tickers.aliases]` | `VIEJO = "NUEVO"` | 6 renombres | Unifica símbolos renombrados |
| `[universe]` | `min_cap_billions` | `10` | Umbral de `--large-cap` (miles de millones de US$) |
| | `sweep_min_cap_billions` | `[0, 10, 200]` | Universos que corre `--sweep` por defecto (0 = índice completo) |
| `[server]` | `host`, `port`, `cors_origin` | `127.0.0.1`, `8000`, `*` | API HTTP de `server.py` |
| `[output]` | `dir` | `"output"` | Carpeta de los reportes HTML |
| | `frontend_data` | `"../frontend/public/data/report.json"` | JSON estático para el frontend |
| | `backtest_subdir`, `actual_subdir`, `etf_subdir` | `"backtest"`, `"actual"`, `"etf"` | Subcarpetas dentro de `dir` |
| | `backtest_prefix`, `sweep_prefix`, `offsets_prefix`, `actual_prefix`, `etf_prefix` | `top3_*` | Prefijos de los archivos HTML |
| | `log_dir` | `"log"` | Carpeta de los logs |
| | `backtest_log`, `actual_log`, `etf_log` | `top3_*.log` | Nombres de los archivos de log |
| `[etf]` | `update_list` | `true` | Al correr el ranking de ETFs, agrega a la lista los ETFs nuevos que Vanguard publica (nunca borra ni edita filas) |
| | `list_url` | página de productos de Vanguard | Servicio del que se baja la lista de ETFs de Vanguard |
| | `csv` | `"vanguard_etfs.csv"` | Lista de ETFs de Vanguard (columnas `ticker`, `name`, `category`) |
| | `horizons_months` | `[3, 6, 12]` | Plazos del retorno ajustado por riesgo; el score es el promedio de sus cocientes |
| | `top_n` | `15` | Cuántos ETFs se muestran en la consola (el HTML trae todos) |
| | `min_vol` | `0.01` | Volatilidad anual mínima para entrar al ranking (1%): los ETFs por debajo son de tipo efectivo (letras del Tesoro, bonos ultracortos) y quedan fuera; `0` = rankear todos |
| | `risk_free_ticker` | `"VUSB"` | ETF cuyo retorno se resta al de cada ETF (referencia libre de riesgo); `""` = no restar |
| `[simulation]` | `months` | `[3, 4, 6, 8, 12]` | Plazos que comparan `--sweep` y `--offsets` |

## Salidas y depuración

### HTML (`backend/output/`)

El nombre lleva la fecha de la corrida (`YYYYMMDD`); si se corre dos veces el mismo día se sobrescribe.

| Modo | Archivo |
|---|---|
| Normal | `output/backtest/top3_backtest_Ny_YYYYMMDD.html` |
| `--sweep` | `output/backtest/top3_sweep_Ny_YYYYMMDD.html` |
| `--offsets` | `output/backtest/top3_offsets_Ny_YYYYMMDD.html` |
| Top actual | `output/actual/top3_actual_YYYYMMDD.html` |
| ETFs de Vanguard | `output/etf/top3_etf_YYYYMMDD.html` (con `--as-of`: `top3_etf_asof_<fecha>_YYYYMMDD.html`) |

Con filtro de universo el nombre suma un sufijo: `_largecap` (>= 10 B), `_megacap` (>= 200 B) o `_capXB`
para otro umbral. `Ny` es el período en años (`_3y`, `_5y`, `_10y`). Por ejemplo `top3_sweep_megacap_5y_20261020.html`.

### Consola

Las tablas de selecciones tienen una fila por rebalanceo: `Fecha`, los tickers `#1`..`#N` con su retorno,
`Cap. aprox. (US$ B)` (informativa), `Capital (US$)` (valor al entrar a esa fila) y `Gan/Pérd` (acumulado
vs. el capital inicial, en verde si es positivo). Se puede desactivar el color con la variable `NO_COLOR=1`.

Los títulos y marcos de los resúmenes (cada paso del pipeline, `RESUMEN` y `RESUMEN DE AVISOS Y ERRORES`) salen en
**verde**. Los avisos del log salen en **amarillo** y los errores en **rojo** (incluidos los mensajes que cortan un
script y los tracebacks sin capturar). Solo si la salida es una terminal: al redirigir a archivo o pipe, o con
`NO_COLOR=1`, va sin color. El archivo de log nunca lleva códigos de color.

Al terminar cada script (y `run_pipeline.py`, con los de todos sus pasos juntos) se imprime un **resumen de avisos y
errores** agrupado por código, con cuántas veces ocurrió, un ejemplo y qué hacer según la tabla de
[códigos de error](#códigos-de-error-y-aviso); los errores van primero. Si no hubo ninguno, no se imprime nada.

### SQLite (`backend/data/top3.db`)

| Tabla | Contenido |
|---|---|
| `constituents_history` | Composición histórica (CSV) |
| `index_changes` | Altas y bajas de Wikipedia |
| `constituents_current` | Lista actual de Wikipedia |
| `prices` | Precios ajustados por ticker y fecha |
| `no_data_tickers` | Tickers que Yahoo dijo que no existen o están dados de baja y la fecha de consulta (no se vuelven a pedir durante `no_data_ttl_days`) |
| `shares` | Acciones en circulación actuales (para la capitalización aproximada) |
| `meta` | Fechas de descarga y rango de precios (control del caché) |
| `runs`, `selections`, `equity` | Cada corrida: parámetros, selecciones y curva de capital |
| `etf_scores` | Ranking de ETFs de Vanguard por corrida (fecha de datos, posición, score, volatilidad, caída máxima, distancia a la SMA200, retornos por plazo) |
| `actual_picks`, `actual_alternates` | Resultados de `top3_actual.py` (fecha de datos, plazo, ticker, retorno, precio, capitalización) y sus suplentes |

### Limpieza de la base

Cada backtest guarda cientos de corridas (parámetros, selecciones y curva de capital) y el informe solo usa la última de
cada combinación del día más reciente. Para que la base no crezca sin límite:

- Al terminar `top3_backtest.py` (y por lo tanto `run_pipeline.py`) se borran las corridas de más de
  `[data] runs_keep_days` días (contados desde el último día con corridas) y las que otra corrida del mismo día
  reemplaza: las que tienen el mismo universo, período, plazo, desfase y modelo (N-0 o N-1), que es lo que
  identifica una corrida en el informe. Es rápido, así que se hace en cada ejecución. Compactar el archivo
  (`VACUUM`) es lo lento: se hace como mucho una vez por día.
- Para forzarlo a mano: `python prune_db.py` (o `--keep-days N`).
- No se toca `actual_picks` (historial del Top actual, que usa la comparación con la corrida anterior) ni los precios.

### Depuración

Cada ejecución escribe `log/top3_backtest.log` (o `log/top3_actual.log`) con nivel DEBUG: respuestas HTTP, forma de las
tablas, tickers sin datos, filtros de capitalización y retornos por período. El log se sobrescribe en cada
corrida; la consola muestra solo el nivel INFO. Los avisos y errores llevan un ID estable (`TOP-BKT-003: ...`).

## Códigos de error y aviso

Cada aviso, error y excepción del proyecto lleva un ID estable al principio del mensaje, al estilo de Oracle
(`ORA-00942`):

```
2026-10-20 15:31:22,327 [WARNING] TOP-BKT-003: Pocos tickers disponibles en 2016-11-01
```

Formato: `TOP-<ÁREA>-<NNN>`.

| Área | Qué cubre |
|---|---|
| `CFG` | Configuración y fechas |
| `NET` | Descargas (Yahoo, GitHub, Wikipedia) |
| `DAT` | Calidad y faltantes de datos |
| `BKT` | Backtest |
| `ACT` | Top actual |
| `ETF` | Ranking de ETFs de Vanguard |
| `API` | Servidor HTTP (también viaja como `code` en la respuesta 500 de `/api/report`) |
| `SYS` | Avisos de Python capturados (pandas, yfinance...) |

**Aviso** = se continúa con lo que haya. **Error** = la operación se corta o falla.

Para buscar en el log: `grep TOP-BKT backend/log/top3_backtest.log`.

| ID | Nivel | Qué significa | Qué hacer |
|---|---|---|---|
| `TOP-CFG-001` | Aviso | No existe el archivo de configuración | Se usan los valores por defecto. Crea config.toml o pasa --config con la ruta correcta. |
| `TOP-CFG-002` | Error | start_date no es anterior a end_date | Corrige [backtest] start_date / end_date o backtest_years en config.toml. |
| `TOP-CFG-003` | Aviso | El período del backtest empieza antes del histórico descargado | Sube [data] history_years (debe superar el mayor período + 1 año). |
| `TOP-NET-001` | Error | Falló la descarga de la composición del índice | Revisa la conexión; se usa lo guardado en SQLite. Reintenta o usa --no-cache. |
| `TOP-NET-002` | Aviso | Se usa la composición guardada en SQLite | Los datos pueden estar desactualizados; vuelve a correr cuando haya conexión. |
| `TOP-NET-003` | Error | Falló la descarga de la lista actual del S&P 500 | Se usa la guardada en SQLite (puede ser vieja). Revisa la conexión. |
| `TOP-NET-004` | Error | No se encontró la tabla de cambios en Wikipedia | Es probable que Wikipedia cambiara el formato de la página; hay que ajustar el lector. |
| `TOP-NET-005` | Error | Yahoo limitó las solicitudes (rate limit) y quedaron tickers sin datos | Ya se reintentó con espera. Vuelve a correr más tarde; los tickers afectados no entran en el ranking. |
| `TOP-NET-006` | Aviso | Yahoo limitó las solicitudes; se reintenta tras una espera | No requiere acción: si el reintento funciona no se pierde nada. |
| `TOP-NET-007` | Aviso | yfinance informó un error al descargar precios | Revisa el mensaje original; los tickers afectados pueden quedar sin datos. |
| `TOP-DAT-001` | Aviso | Filas con fecha no interpretable en la tabla de cambios | Se ignoran. Si son muchas, el formato de la fuente cambió. |
| `TOP-DAT-002` | Aviso | Sin composición histórica para esa fecha | Esa fecha queda sin constituyentes; revisa history_years y el CSV histórico. |
| `TOP-DAT-003` | Aviso | Sin dato de acciones en circulación para algunos tickers | Su capitalización queda en n/d y no entran en un universo filtrado por capitalización. |
| `TOP-DAT-004` | Error | No hay lista actual del S&P 500 | No se descargó ni existe en SQLite. Corre con conexión a internet. |
| `TOP-BKT-001` | Error | El backtest no generó ningún rebalanceo | Revisa las fechas, el histórico descargado y que el universo no sea demasiado chico. |
| `TOP-BKT-002` | Aviso | Sin constituyentes en la fecha de rebalanceo | Se omite ese rebalanceo. |
| `TOP-BKT-003` | Aviso | Pocos tickers disponibles en la fecha de rebalanceo | Se omiten esos rebalanceos (menos de 10 candidatos); se avisa una vez por universo y período con el rango de fechas. Frecuente en mega-cap con períodos largos. |
| `TOP-BKT-004` | Aviso | Ventana de precios insuficiente para rankear | Se omite ese rebalanceo. |
| `TOP-BKT-005` | Aviso | Sin precios para mantener la selección durante el período | El retorno de ese período no se computa. |
| `TOP-BKT-006` | Aviso | Un plazo/calendario de arranque no produjo resultado | Se omite ese calendario; el resto continúa. |
| `TOP-ACT-001` | Error | No hay ruedas de precios suficientes | Descarga más historia (--no-cache) o reduce el plazo en meses. |
| `TOP-ACT-002` | Aviso | Tickers con huecos en la ventana quedan fuera del ranking | Misma regla que el backtest. Revisa si Yahoo falló para esos tickers y reintenta. |
| `TOP-ETF-001` | Error | No hay lista de ETFs utilizable | Revisa [etf] csv en config.toml: el archivo debe existir y tener las columnas ticker, name, category. |
| `TOP-ETF-002` | Aviso | ETFs de la lista sin precios en Yahoo | Pueden estar dados de baja o con el ticker mal escrito; quítalos o corrígelos en el CSV. |
| `TOP-ETF-003` | Aviso | ETFs fuera del ranking por huecos de precios o poca historia | Los ETFs nuevos entran cuando acumulan historia para el plazo más largo. |
| `TOP-ETF-004` | Error | Ningún ETF se pudo rankear | Descarga más historia o reduce [etf] horizons_months. |
| `TOP-ETF-005` | Aviso | La referencia libre de riesgo no está disponible | El score se calcula sin restarla (los ETFs casi sin riesgo quedan arriba). Revisa [etf] risk_free_ticker: debe estar en la lista y tener historia completa. |
| `TOP-ETF-006` | Aviso | No se pudo actualizar la lista de ETFs de Vanguard | Se usa la lista guardada en el CSV. Revisa la conexión; si Vanguard cambió el formato de su respuesta hay que ajustar `top3/vanguard.py`. Con `--no-update` o `[etf] update_list = false` no se intenta. |
| `TOP-API-001` | Error | Error armando /api/report | Revisa que exista la base SQLite y que se haya corrido el pipeline al menos una vez. |
| `TOP-SYS-001` | Aviso | Aviso de Python (pandas, yfinance u otra librería) | El mensaje original trae el archivo y la línea. |

## Estructura y desarrollo

```
start.ps1 / start.sh  # levantan backend + frontend (Windows / macOS y Linux)
backend/              # Python: backtest, Top actual, ranking de ETFs, base SQLite y API HTTP
  config.toml         # configuración
  vanguard_etfs.csv   # lista de ETFs de Vanguard (se mantiene a mano)
  top3/               # paquete con la lógica; los scripts de la raíz de backend/ son solo la línea de comandos
  tests/              # tests (pytest)
frontend/             # Aplicación web en Svelte 5 + Vite
```

| Archivo | Para qué sirve |
|---|---|
| `backend/top3_backtest.py` | Backtest Point-in-Time, comparación de plazos y sensibilidad al calendario de arranque |
| `backend/top3_actual.py` | Top N de hoy: las acciones del S&P 500 con mejor retorno en el plazo configurado |
| `backend/top3_etf.py` | Ranking de momentum ajustado por riesgo de los ETFs de Vanguard (sin backtest) |
| `backend/run_pipeline.py` | Pipeline completo: backtest (todos los períodos y universos) + Top actual de cada universo + JSON del frontend |
| `backend/server.py` | API HTTP opcional: `GET /api/report` (el mismo JSON, leído de SQLite). La web no la usa |
| `backend/prune_db.py` | Limpia a mano las corridas viejas de SQLite (se hace sola en cada backtest) |
| `backend/export_frontend.py` | Escribe ese mismo JSON en `frontend/public/data/report.json` (lo hacen solos los scripts al terminar) |
| `backend/data/`, `backend/output/`, `backend/log/` | Base SQLite, reportes HTML y logs; se crean solos |

**Paquete `backend/top3/`**

| Módulo | Responsabilidad |
|---|---|
| `config.py` | Valores por defecto, lectura de `config.toml` y `DataSettings` (parámetros de descarga) |
| `db.py`, `logs.py` | Esquema y conexión SQLite; logging |
| `constituents.py` | Composición Point-in-Time (CSV histórico + Wikipedia) |
| `prices.py`, `shares.py` | Precios (descarga completa e incremental, con reintento ante rate limit) y acciones en circulación |
| `yahoo.py` | Clasifica los errores que yfinance escribe en su logger y captura los tickers rechazados para reintentarlos |
| `universe.py` | Universos por capitalización: filtro y etiquetas |
| `engine.py` | Motor del backtest (`run_backtest`), con comisión y skip-month |
| `pricematrix.py` | Precios como matriz numpy con NaN acumulados: consultas de ventana y de retorno sin copiar historia |
| `analysis.py` | Calendarios de arranque, resumen por plazo y guardado de corridas |
| `tables.py` | Tablas de resultados (texto) que comparten la consola y el HTML |
| `console.py`, `html_report.py` | Salida por consola y reportes HTML |
| `etf.py` | Ranking de ETFs: lista, score ajustado por riesgo, guardado en `etf_scores` y reportes |
| `vanguard.py` | Baja la lista de ETFs de Vanguard y agrega al CSV los que falten |
| `rotation.py` | Top actual: cambios contra la corrida anterior y próximo rebalanceo |
| `workflow.py`, `actual.py` | Flujos completos: backtest normal / sweep / offsets y Top actual |
| `report_data.py`, `api.py` | JSON del frontend y API HTTP |
| `errors.py` | Catálogo de códigos de error y aviso |

**Frontend (`frontend/src/`)**

| Archivo | Responsabilidad |
|---|---|
| `App.svelte` | Carga de datos (API y luego JSON estático), pestañas, filtros de universo y período, tema |
| `lib/ActualView.svelte` | Top actual, suplentes y seguimiento de selecciones anteriores |
| `lib/BacktestView.svelte` | Tarjetas, curva de capital, historial de selecciones y calendarios |
| `lib/SweepView.svelte` | Comparación de plazos y sensibilidad al arranque |
| `lib/CompareView.svelte` | Modelo de siempre (N-0) frente al skip-month (N-1), plazo por plazo y por mitades del período |
| `lib/EtfView.svelte` | Ranking de ETFs de Vanguard |
| `lib/AboutView.svelte` | Pestaña About: qué se muestra en la aplicación, fuentes de datos y límites |
| `lib/Chart.svelte`, `Range.svelte`, `TickerLink.svelte`, `Glossary.svelte` | Componentes compartidos |
| `lib/Bunny.svelte` | Detalle decorativo: un conejo que pasea por el pie de la pantalla, se aleja del cursor y saluda al hacer clic (se desactiva con «reducir movimiento» del sistema) |
| `lib/format.js` | Formato de porcentajes, dinero y signos |

**Tests.** Backend (`backend/tests/`, un archivo por módulo de `top3/`, más la línea de comandos y el pipeline): no
usan red, los datos son sintéticos y las descargas se reemplazan por dobles de prueba.

```
cd backend && python -m pytest
cd frontend && npm test
```

**Mantenimiento de los códigos de error.** El catálogo está en `backend/top3/errors.py`. Los IDs no se reutilizan ni
se renumeran; todo `log.warning` / `log.error` / `log.exception` y todo `raise` de usuario usa
`CODIGO.msg("texto")`; y cada código nuevo se documenta en la tabla de arriba. Los tests
(`tests/test_errors.py`) verifican las tres cosas.

## Fuentes de datos

Los precios se obtienen de Yahoo Finance mediante [`yfinance`](https://github.com/ranaroussi/yfinance); la
composición del índice, del repositorio [`hanshof/sp500_constituents`](https://github.com/hanshof/sp500_constituents)
y de Wikipedia. Su disponibilidad y exactitud no están garantizadas, y su uso queda sujeto a los términos de cada
proveedor. Este proyecto está pensado para uso personal y educativo.

## Licencia

Distribuido bajo la licencia [MIT](LICENSE).
