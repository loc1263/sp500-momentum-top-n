# Uso

Los comandos de Python se corren desde `backend/` (las rutas del config son relativas a esa carpeta).

## Levantar todo

```
.\start.ps1                                   # backend en :8000, frontend en http://localhost:5173
.\start.ps1 -BackendPort 9000 -FrontendPort 3000
```

El frontend pide `/api/report` al backend (en desarrollo Vite lo redirige) y, si el backend no está, usa
`data/report.json`. Primero hay que haber corrido el backtest y el Top actual al menos una vez.
`npm run build` en `frontend/` genera la versión estática en `frontend/dist/`.

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

## Scripts sueltos

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

Las opciones de universo (`--large-cap`, `--min-cap-billions`) se combinan con `--sweep`, `--offsets`
o el backtest normal.

**`--sweep` solo** corre todas las opciones paramétricas: los universos de `[universe] sweep_min_cap_billions`
(por defecto índice completo, large-cap + mega-cap y mega-cap) y, para cada uno, el sweep y la sensibilidad
al arranque. Genera 6 HTML y al final lista las rutas. Si se pasa un filtro explícito
(`--large-cap` o `--min-cap-billions N`), corre solo ese universo.

## Qué muestra cada modo

- **Normal:** el calendario base (arranque en el primer mes), la tabla de selecciones con capital y
  ganancia/pérdida acumulada, la mediana y el rango de CAGR de todos los calendarios posibles del plazo,
  y una tabla con cada calendario.
- **`--sweep`:** una tabla que compara los plazos (3, 4, 6, 8 y 12 meses por defecto), con el resultado
  del calendario base y la mediana y el rango de CAGR. Ordenado por CAGR mediano. Incluye las selecciones
  de cada plazo. Se repite para cada universo y se acompaña del reporte de sensibilidad al arranque.
- **`--offsets`:** el resumen por plazo (mediana, mínimo y máximo de CAGR y de capital final) y el detalle de
  cada calendario. Dentro de `--sweep` reutiliza los calendarios ya calculados.

## Top actual (`top3_actual.py`)

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

- **Cambios vs. la corrida anterior:** qué tickers entran, salen y se mantienen respecto de la última selección
  guardada en `actual_picks` (mismo plazo y universo).
- **Próximo rebalanceo:** el primer inicio de mes de la grilla "cada N meses" contada desde la primera corrida
  guardada. Es una referencia: el backtest no tiene un ancla fija para el Top de hoy.
- **Tickers excluidos:** los que tienen huecos de precios en la ventana no se pueden rankear (igual que en el
  backtest) y quedan listados como advertencia en la consola y en el log.

Correr el script dos veces con los mismos datos reemplaza el resultado en lugar de duplicarlo.
