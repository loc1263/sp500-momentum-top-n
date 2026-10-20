# Salidas y depuración

## HTML (`backend/output/`)

El nombre lleva la fecha de la corrida (`YYYYMMDD`); si se corre dos veces el mismo día se sobrescribe.

| Modo | Archivo |
|---|---|
| Normal | `output/backtest/top3_backtest_Ny_YYYYMMDD.html` |
| `--sweep` | `output/backtest/top3_sweep_Ny_YYYYMMDD.html` |
| `--offsets` | `output/backtest/top3_offsets_Ny_YYYYMMDD.html` |
| Top actual | `output/actual/top3_actual_YYYYMMDD.html` |

Con filtro de universo el nombre suma un sufijo: `_largecap` (>= 10 B), `_megacap` (>= 200 B) o `_capXB`
para otro umbral. `Ny` es el período en años (`_3y`, `_5y`, `_10y`). Por ejemplo `top3_sweep_megacap_5y_20261020.html`.

## Consola

Las tablas de selecciones tienen una fila por rebalanceo: `Fecha`, los tickers `#1`..`#N` con su retorno,
`Cap. aprox. (US$ B)` (informativa), `Capital (US$)` (valor al entrar a esa fila) y `Gan/Pérd` (acumulado
vs. el capital inicial, en verde si es positivo). Se puede desactivar el color con la variable `NO_COLOR=1`.

Los avisos del log salen en **amarillo** y los errores en **rojo** (incluidos los mensajes que cortan un script y los
tracebacks sin capturar). Solo si la salida es una terminal: al redirigir a archivo o pipe, o con `NO_COLOR=1`, va sin
color. El archivo de log nunca lleva códigos de color.

Al terminar cada script (y `run_pipeline.py`, con los de todos sus pasos juntos) se imprime un **resumen de avisos y
errores** agrupado por código, con cuántas veces ocurrió, un ejemplo y qué hacer según
[errores.md](errores.md); los errores van primero. Si no hubo ninguno, no se imprime nada.

## SQLite (`backend/data/top3.db`)

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

## Limpieza de la base

Cada backtest guarda cientos de corridas (parámetros, selecciones y curva de capital) y el informe solo usa la última de
cada combinación del día más reciente. Para que la base no crezca sin límite:

- Al terminar `top3_backtest.py` (y por lo tanto `run_pipeline.py`) se borran, **una vez por día**, las corridas de
  más de `[data] runs_keep_days` días (contados desde el último día con corridas) y las repetidas del mismo día con
  los mismos parámetros. Después se compacta el archivo.
- Para forzarlo a mano: `python prune_db.py` (o `--keep-days N`).
- No se toca `actual_picks` (historial del Top actual, que usa la comparación con la corrida anterior) ni los precios.

## Depuración

Cada ejecución escribe `log/top3_backtest.log` (o `log/top3_actual.log`) con nivel DEBUG: respuestas HTTP, forma de las
tablas, tickers sin datos, filtros de capitalización y retornos por período. El log se sobrescribe en cada
corrida; la consola muestra solo el nivel INFO. Los avisos y errores llevan un ID estable (`TOP-BKT-003: ...`);
el catálogo está en [errores.md](errores.md).
