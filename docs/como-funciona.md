# Cómo funciona

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
   `--no-cache` (eran 126 de 738, el 17% de los pedidos, y fallan siempre).
4. **Backtest.** En cada fecha de rebalanceo se rankean las acciones del índice vigentes ese día por retorno
   de los últimos N meses (N x 21 ruedas), se eligen las `top_n` y se mantienen N meses. El retorno del
   período es el promedio simple de las acciones elegidas.
5. **Calendarios de arranque.** Un plazo de N meses se puede empezar en N meses distintos. Se prueban todos
   y se informa el calendario base (primer mes), la mediana y el rango, para medir cuánto del resultado
   depende de la fecha de arranque.
6. **Comparación con skip-month (N-1).** En cada sweep se corre además una variante que arma el ranking con los
   N meses que terminan un mes (21 ruedas) antes de la fecha de rebalanceo, para no premiar rebotes de corto
   plazo. Las compras y el rendimiento siguen contándose desde la fecha de rebalanceo. Usa los mismos precios,
   universos, períodos y fechas de arranque que el modelo de siempre (N-0), que es el que se usa en el Top
   actual. En las corridas de prueba N-0 rindió más que N-1 con el plazo de 4 meses; N-1 solo ganó en plazos
   cortos. El Top actual no calcula la variante N-1.
7. **Caché.** Todo se guarda en SQLite. Si se vuelve a correr el mismo día se reutiliza lo descargado;
   `--no-cache` fuerza una descarga nueva, pero no repite dentro de la misma corrida lo que ya bajó (p. ej. las acciones
   en circulación), y `run_pipeline.py` lo aplica solo al primer paso que descarga: los siguientes leen de SQLite lo que
   ese paso acaba de guardar. Las acciones en circulación cambian por trimestre, así que se reutilizan hasta
   `[data] shares_ttl_days` días (30 por defecto) aunque sean de otro día.
   Si es otro día, los precios se actualizan de forma incremental: solo se baja lo que falta desde la última
   descarga (tickers nuevos completos; un ticker que pagó dividendo o hizo split desde entonces se vuelve a bajar
   entero, porque su precio ajustado cambió). Una descarga completa solo ocurre con `--no-cache`, sin datos
   guardados o si se pide más histórico que el guardado (`history_years` mayor).

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
- **Costos parciales.** Cobra una comisión por lado (`[backtest] commission`, 0,05%) al armar la cartera y por las
  posiciones que cambian en cada rebalanceo; no incluye impuestos ni deslizamiento (slippage), no cobra el
  reequilibrio de pesos de las que se mantienen y asume ponderación igual.
- **Dependencias externas.** Los datos vienen de Yahoo Finance, un repositorio de GitHub y Wikipedia. Si
  cambia el formato de alguna fuente, el script avisa en el log y sigue con lo que tenga guardado en SQLite.
- Un rebalanceo se decide con precios hasta esa misma fecha de rebalanceo.
