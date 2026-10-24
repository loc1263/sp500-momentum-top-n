<script>
  import { int, share } from './format.js';

  let { settings } = $props();

  const sections = [
    {
      tab: 'Top actual',
      text: 'Las acciones del S&P 500 que hoy lideran el ranking de momentum (modelo N-0): las que más subieron en la ventana de los últimos N meses. Incluye los suplentes (los puestos siguientes), qué entra y qué sale respecto de la corrida anterior, el próximo rebalanceo y cómo le fue a cada selección guardada desde que se eligió.',
    },
    {
      tab: 'Backtest',
      text: 'Qué habría pasado con la estrategia en el pasado: la curva de capital, el historial de selecciones en cada rebalanceo y el resultado de cada fecha de arranque posible. Se puede elegir el plazo, el período y el universo.',
    },
    {
      tab: 'Plazos y sensibilidad',
      text: 'Compara los plazos entre sí (cada cuántos meses se rebalancea) y mide cuánto del resultado depende del mes en que se hubiera empezado. Muestra el resultado típico (mediana), el peor y el mejor arranque.',
    },
    {
      tab: 'N-0 vs N-1',
      text: 'Compara el modelo de siempre (N-0) con una variante que ignora el último mes al armar el ranking (N-1, «skip-month»), plazo por plazo y en las dos mitades del período, para ver si una ventaja se sostiene en el tiempo o depende de un solo tramo del mercado.',
    },
    {
      tab: 'ETFs Vanguard',
      text: 'Un ranking aparte, sin backtest: los ETFs de Vanguard ordenados por cuánto subieron por unidad de riesgo (retorno ajustado por volatilidad en 3, 6 y 12 meses, descontando la referencia libre de riesgo), con su tendencia y caída máxima. Los ETFs de tipo efectivo (letras del Tesoro, bonos ultracortos) no entran al ranking.',
    },
  ];

  const sources = [
    ['Precios', 'Yahoo Finance (precios ajustados por dividendos y splits).'],
    ['Composición del S&P 500', 'CSV histórico del repositorio hanshof/sp500_constituents y las altas y bajas de Wikipedia: en cada fecha del backtest solo compiten las empresas que estaban en el índice ese día (Point-in-Time).'],
    ['Lista de ETFs de Vanguard', 'La página de productos de Vanguard; los ETFs nuevos se agregan solos a la lista.'],
  ];

  const limits = [
    'Sesgo de supervivencia: las empresas que ya no cotizan no tienen precios en Yahoo y quedan fuera, así que los retornos probablemente están inflados.',
    'La capitalización de los universos large-cap y mega-cap se aproxima con las acciones en circulación de hoy, lo que adelanta la entrada de empresas que hoy son grandes.',
    'Pocas decisiones: en 5 años hay entre 5 y 20 rebalanceos por plazo, y el resultado depende de unas pocas rachas.',
    'No incluye impuestos ni deslizamiento (la diferencia entre el precio de cierre y el que realmente se obtiene).',
  ];
</script>

<div class="about">
  <h2>Qué es esta aplicación</h2>
  <p>
    Evalúa una estrategia de <strong>momentum</strong> sobre el S&amp;P 500: cada <em>N</em> meses se compran, con
    ponderación igual, las {settings.top_n} acciones que más subieron en los últimos <em>N</em> meses, y se mantienen
    hasta el siguiente rebalanceo. La aplicación muestra qué habría pasado con esa estrategia en el pasado (backtest) y
    qué seleccionaría hoy. El plazo de referencia es de {settings.months} meses y el capital inicial de los
    backtests, US$ {int(settings.initial_capital)}.
  </p>
  <p class="muted">
    Es una herramienta de análisis personal y educativa. <strong>No es una recomendación de inversión.</strong>
  </p>

  <h2>Qué muestra cada sección</h2>
  <dl>
    {#each sections as s (s.tab)}
      <dt>{s.tab}</dt>
      <dd>{s.text}</dd>
    {/each}
  </dl>

  <h2>Los filtros</h2>
  <p>
    <strong>Universo</strong>: el índice completo, solo las empresas large-cap + mega-cap (capitalización de al
    menos US$ 10.000 millones) o solo las mega-cap (al menos US$ 200.000 millones).
    <strong>Período</strong>: cuántos años hacia atrás se simulan (los backtests terminan en la fecha de la corrida).
  </p>

  <h2>De dónde salen los datos</h2>
  <dl>
    {#each sources as [name, text] (name)}
      <dt>{name}</dt>
      <dd>{text}</dd>
    {/each}
  </dl>

  <h2>Qué incluyen los resultados</h2>
  <p>
    Los backtests cobran una comisión de {share(settings.commission ?? 0, 2)} por lado al armar la cartera y por las
    posiciones que cambian en cada rebalanceo. Los resultados de cada plazo se miden con todas las fechas de arranque
    posibles, y se informa el resultado típico (la mediana) y no un solo número.
  </p>
  <p>Límites que conviene tener presentes al leer los números:</p>
  <ul>
    {#each limits as text}
      <li>{text}</li>
    {/each}
  </ul>

  <h2>Cómo se actualiza</h2>
  <p>
    Los datos se generan fuera de la página, al ejecutar <code>python run_pipeline.py</code> en la carpeta
    <code>backend</code>. La fecha de «Corrida» que aparece arriba es la de la última vez que se hizo; para refrescar,
    se vuelve a ejecutar y se recarga la página.
  </p>
</div>

<style>
  .about { max-width: 860px; }
  .about h2:first-child { margin-top: 16px; }
  p { margin: 8px 0; }
  dl { margin: 8px 0; display: grid; grid-template-columns: max-content 1fr; gap: 8px 20px; }
  dt { font-weight: 600; }
  dd { margin: 0; color: var(--muted); }
  ul { margin: 4px 0 8px; padding-left: 20px; color: var(--muted); }
  li { margin: 4px 0; }
  code { background: var(--card); border: 1px solid var(--line); border-radius: 4px; padding: 0 5px; font-size: .85em; }
  @media (max-width: 640px) {
    dl { grid-template-columns: 1fr; gap: 2px; }
    dd { margin-bottom: 8px; }
  }
</style>
