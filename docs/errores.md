# Códigos de error y aviso

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
| `TOP-BKT-003` | Aviso | Pocos tickers disponibles en la fecha de rebalanceo | Se omite ese rebalanceo (menos de 10 candidatos). Frecuente en mega-cap con períodos largos. |
| `TOP-BKT-004` | Aviso | Ventana de precios insuficiente para rankear | Se omite ese rebalanceo. |
| `TOP-BKT-005` | Aviso | Sin precios para mantener la selección durante el período | El retorno de ese período no se computa. |
| `TOP-BKT-006` | Aviso | Un plazo/calendario de arranque no produjo resultado | Se omite ese calendario; el resto continúa. |
| `TOP-ACT-001` | Error | No hay ruedas de precios suficientes | Descarga más historia (--no-cache) o reduce el plazo en meses. |
| `TOP-ACT-002` | Aviso | Tickers con huecos en la ventana quedan fuera del ranking | Misma regla que el backtest. Revisa si Yahoo falló para esos tickers y reintenta. |
| `TOP-API-001` | Error | Error armando /api/report | Revisa que exista la base SQLite y que se haya corrido el pipeline al menos una vez. |
| `TOP-SYS-001` | Aviso | Aviso de Python (pandas, yfinance u otra librería) | El mensaje original trae el archivo y la línea. |

## Mantenimiento

El catálogo está en `backend/top3/errors.py`. Reglas: los IDs no se reutilizan ni se renumeran; todo
`log.warning` / `log.error` / `log.exception` y todo `raise` de usuario usa `CODIGO.msg("texto")`; y cada código
nuevo se documenta aquí. Los tests (`tests/test_errors.py`) verifican las tres cosas.
