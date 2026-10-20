# Configuración (`backend/config.toml`)

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
| | `runs_keep_days` | `7` | Días con corridas del backtest que se conservan en SQLite (mínimo 1); ver [Limpieza](salidas.md#limpieza-de-la-base) |
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
| | `backtest_subdir`, `actual_subdir`, `etf_subdir` | `"backtest"`, `"actual"`, `"etf"` | Subcarpetas dentro de `dir` |
| | `backtest_prefix`, `sweep_prefix`, `offsets_prefix`, `actual_prefix`, `etf_prefix` | `top3_*` | Prefijos de los archivos HTML |
| | `log_dir` | `"log"` | Carpeta de los logs |
| | `backtest_log`, `actual_log`, `etf_log` | `top3_*.log` | Nombres de los archivos de log |
| `[etf]` | `csv` | `"vanguard_etfs.csv"` | Lista de ETFs de Vanguard (columnas `ticker`, `name`, `category`) |
| | `horizons_months` | `[3, 6, 12]` | Plazos del retorno ajustado por riesgo; el score es el promedio de sus cocientes |
| | `top_n` | `15` | Cuántos ETFs se muestran en la consola (el HTML trae todos) |
| | `risk_free_ticker` | `"VUSB"` | ETF cuyo retorno se resta al de cada ETF (referencia libre de riesgo); `""` = no restar |
| `[simulation]` | `months` | `[3, 4, 6, 8, 12]` | Plazos que comparan `--sweep` y `--offsets` |
