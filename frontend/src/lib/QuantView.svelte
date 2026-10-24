<script>
  import TickerLink from './TickerLink.svelte';
  import { pct, share, sign } from './format.js';

  let { quant } = $props();

  const s = $derived(quant.settings);
  const cov = $derived(quant.coverage);
  const mk = $derived(quant.markowitz);
  const top = $derived(quant.ranking.slice(0, s.top_n));
  const inputs = $derived(Object.fromEntries(mk.tickers.map((t) => [t.ticker, t])));
  const weightOf = (portfolio, ticker) => portfolio.weights.find((w) => w.ticker === ticker)?.weight;
  const sectorWeightOf = (portfolio, sector) => portfolio.sectors.find((x) => x.sector === sector)?.weight;
  // sectores de la cartera principal primero, luego los demás
  const portfolioSectors = $derived(
    [...new Set(mk.portfolios.flatMap((p) => p.sectors.map((x) => x.sector)))].sort(
      (a, b) =>
        (sectorWeightOf(mk.portfolios[0], b) ?? 0) - (sectorWeightOf(mk.portfolios[0], a) ?? 0) || a.localeCompare(b, 'es'),
    ),
  );
  const score = (v) => (v == null ? 'n/d' : v.toFixed(1).replace('.', ','));
  const ratio = (v, digits = 2) => (v == null ? 'n/d' : v.toFixed(digits).replace('.', ','));
  const percent = (v, digits = 0) => (v == null ? 'n/d' : pct(v, digits));
  // yfinance entrega deuda/patrimonio como porcentaje (78 = 78%)
  const debt = (v) => (v == null ? 'n/d' : share(v / 100, 0));

  let sortKey = $state('rank');
  let descending = $state(false);
  let sector = $state('');
  let query = $state('');
  const sectors = $derived([...new Set(quant.ranking.map((r) => r.sector))].sort((a, b) => a.localeCompare(b, 'es')));

  const num = (key, label) => ({ key, label, numeric: true });
  const FIXED = [
    { key: 'rank', label: '#' },
    { key: 'ticker', label: 'Ticker' },
    { key: 'name', label: 'Empresa' },
    { key: 'sector', label: 'Sector' },
    num('score', 'Score'),
    num('momentum', 'Momentum'),
    num('health', 'Salud'),
    num('technical', 'Técnico'),
  ];
  // Qué columnas se agregan a las fijas: los indicadores de cada score o el score de cada uno de sus grupos
  const views = {
    indicadores: {
      label: 'Indicadores',
      columns: [
        num('mom_12_1', 'Mom. 12-1'), num('mom_6_1', 'Mom. 6-1'), num('roe', 'ROE'), num('operating_margin', 'Margen op.'),
        num('debt_to_equity', 'Deuda/Patr.'), num('current_ratio', 'Liq. corr.'), num('fcf_margin', 'FCF/Ventas'),
        num('fcf_yield', 'FCF/Cap.'), num('cash_conversion', 'FCF/Utilidad'), num('fcf_positive_years', 'Años FCF+'),
        num('rsi', 'RSI'), num('vs_ema50', 'vs EMA50'), num('vs_ema200', 'vs EMA200'), num('macd_hist', 'MACD'),
      ],
    },
    salud: {
      label: 'Salud: score por grupo',
      columns: [
        num('groups', 'Grupos medidos'), num('hg_rentabilidad', 'Rentabilidad'), num('hg_solvencia', 'Solvencia'),
        num('hg_liquidez', 'Liquidez'), num('hg_caja', 'Caja'),
      ],
    },
    tecnico: {
      label: 'Técnico: score por grupo',
      columns: [
        num('tg_tendencia', 'Tendencia'), num('tg_impulso', 'Impulso'), num('tg_volumen', 'Volumen'),
        num('tg_posicion', 'Posición'), num('rsi', 'RSI'), num('vs_ema50', 'vs EMA50'), num('vs_ema200', 'vs EMA200'),
        num('macd_hist', 'MACD'),
      ],
    },
  };
  let view = $state('indicadores');
  const columns = $derived([...FIXED, ...views[view].columns]);
  // Los scores por grupo viven dentro de health_groups / technical_groups
  const value = (r, key) =>
    key.startsWith('hg_') ? r.health_groups[key.slice(3)] : key.startsWith('tg_') ? r.technical_groups[key.slice(3)] : r[key];
  const withSign = (v, text) => ({ text, cls: `r ${sign(v)}` });
  const plain = (text) => ({ text, cls: 'r' });
  function cell(r, key) {
    const v = value(r, key);
    switch (key) {
      case 'rank': return { text: r.rank, cls: '' };
      case 'name': return { text: r.name, cls: '' };
      case 'sector': return { text: r.sector, cls: 'muted' };
      case 'score': return { text: score(v), cls: 'r strong' };
      case 'groups': return { ...plain(`${v}/4`), title: 'grupos de indicadores financieros medidos, de 4' };
      case 'mom_12_1': case 'mom_6_1': case 'roe': case 'operating_margin': case 'fcf_margin': case 'vs_ema50':
      case 'vs_ema200': case 'fcf_yield': case 'cash_conversion':
        return withSign(v, percent(v));
      case 'fcf_positive_years':
        return { ...plain(v == null ? 'n/d' : share(v, 0)), title: 'parte de los últimos 4 años con flujo de caja libre positivo' };
      case 'macd_hist':
        return { ...withSign(v, percent(v, 1)), title: 'histograma MACD sobre el precio: positivo = impulso alcista' };
      case 'debt_to_equity': return plain(debt(v));
      case 'current_ratio': return plain(ratio(v));
      default: return plain(score(v)); // los scores (0-100), los de cada grupo y el RSI
    }
  }
  const rows = $derived.by(() => {
    const text = query.trim().toLowerCase();
    const kept = quant.ranking.filter(
      (r) =>
        (!sector || r.sector === sector) &&
        (!text || r.ticker.toLowerCase().includes(text) || r.name.toLowerCase().includes(text)),
    );
    const direction = descending ? -1 : 1;
    return kept.toSorted((a, b) => {
      const x = value(a, sortKey);
      const y = value(b, sortKey);
      if (x == null || y == null) return (x == null) - (y == null); // sin dato, al final
      return direction * (typeof x === 'string' ? x.localeCompare(y, 'es') : x - y);
    });
  });
  function setView(next) {
    view = next;
    if (![...FIXED, ...views[next].columns].some((c) => c.key === sortKey)) {
      sortKey = 'rank';
      descending = false;
    }
  }
  function sortBy(column) {
    if (sortKey === column.key) {
      descending = !descending;
    } else {
      sortKey = column.key;
      descending = !!column.numeric && column.key !== 'rank';
    }
  }
  const ariaSort = (column) => (sortKey === column.key ? (descending ? 'descending' : 'ascending') : 'none');
</script>

<div class="cards">
  <div class="card"><div class="k">Datos al cierre del</div><div class="v">{quant.as_of}</div></div>
  <div class="card">
    <div class="k">Acciones rankeadas</div>
    <div class="v">{cov.ranked} de {cov.universe}</div>
    <div class="h">las del S&amp;P 500 con los tres scores</div>
  </div>
  <div class="card">
    <div class="k">Score final</div>
    <div class="v">0 a 100</div>
    <div class="h">promedio de los scores de momentum, de salud financiera y técnico</div>
  </div>
</div>

<h2>Cómo se calcula</h2>
<ul class="how">
  <li>
    <strong>Momentum</strong>: posición de cada acción (100 = la mejor) según el promedio de su ranking en el retorno de
    12 y de 6 meses, sin contar el último mes.
  </li>
  <li>
    <strong>Salud financiera</strong>: posición de cada empresa según cuatro grupos de indicadores de sus últimos datos
    publicados: rentabilidad (ROE, ROA, márgenes), solvencia (deuda/patrimonio, deuda neta/EBITDA, caja/deuda), liquidez
    (liquidez corriente y prueba ácida) y generación de caja (flujo libre y operativo sobre ventas y sobre la capitalización, conversión de la utilidad en caja, flujo
    operativo sobre la deuda y años con flujo libre positivo; este grupo pesa el doble: una empresa que genera caja de forma
    sostenida es más confiable). Los bancos y
    aseguradoras solo se miden con rentabilidad: en el detalle «Salud» se ve el score de cada grupo y cuántos de los 4 se pudieron medir.
  </li>
  <li>
    <strong>Técnico</strong>: posición de cada acción según cuatro grupos de indicadores calculados con sus precios y
    volumen: tendencia (medias móviles exponenciales de 20, 50 y 200 ruedas y ADX), impulso (MACD, RSI, estocástico y
    bandas de Bollinger), volumen (OBV y MFI) y posición en el rango de 52 semanas. El RSI, el estocástico y el MFI
    premian la zona alcista y penalizan la sobrecompra. El detalle «Técnico» muestra el score de cada grupo.
  </li>
  <li>
    <strong>Score final</strong>: el promedio de los tres{#if s.weights && new Set(s.weights).size > 1} (con los pesos {s.weights.join(' / ')} de
    momentum, salud y técnico){/if}. Sobre las {s.top_n} primeras se calcula Markowitz.
  </li>
</ul>

<h2>Las {s.top_n} mejores y sus pesos (Markowitz)</h2>
<p class="sub">
  Tres carteras sin posiciones cortas y con un máximo de {share(s.w_max, 0)} por acción y de {share(mk.sector_max, 0)} por sector. El retorno esperado de cada acción
  es su retorno de los últimos 12 meses con un peso de {share(s.mu_shrink, 0)}, y el resto, un retorno de largo plazo de
  {share(s.prior, 0)} (tasa libre de riesgo más prima de mercado): el retorno pasado de una acción es muy ruidoso. La
  covarianza sale de los últimos 12 meses (Ledoit-Wolf). Los pesos dependen sobre todo del riesgo; tómalos como orientativos.
</p>
{#if mk.sector_relaxed}
  <p class="best">
    Con los sectores de estas {s.top_n} acciones no se puede invertir todo con un máximo de {share(s.sector_max, 0)} por
    sector: el tope se subió a {share(mk.sector_max, 0)}.
  </p>
{/if}
{#if !mk.portfolios.some((p) => p.key === 'max_return')}
  <p class="best">
    No hay cartera de máximo retorno: con estas {s.top_n} acciones la volatilidad mínima posible es
    {share(mk.min_vol)}, por encima del tope de {share(s.vol_target, 0)}.
  </p>
{/if}
<div class="wrap">
  <table>
    <thead>
      <tr>
        <th>Ticker</th><th>Empresa</th><th>Sector</th><th class="r">Score</th><th class="r">Retorno esp.</th><th class="r">Vol. anual</th>
        {#each mk.portfolios as p (p.key)}<th class="r">{p.label}</th>{/each}
      </tr>
    </thead>
    <tbody>
      {#each top as r (r.ticker)}
        <tr>
          <td><TickerLink ticker={r.ticker} /></td>
          <td>{r.name}</td>
          <td class="muted">{r.sector}</td>
          <td class="r"><strong>{score(r.score)}</strong></td>
          <td class="r {sign(inputs[r.ticker].exp_return)}">{pct(inputs[r.ticker].exp_return)}</td>
          <td class="r">{share(inputs[r.ticker].vol)}</td>
          {#each mk.portfolios as p (p.key)}
            {@const w = weightOf(p, r.ticker)}
            <td class="r" class:main={p.key === mk.main}>{w ? share(w) : ''}</td>
          {/each}
        </tr>
      {/each}
    </tbody>
    <tfoot>
      <tr>
        <td colspan="6">Retorno esperado de la cartera</td>
        {#each mk.portfolios as p (p.key)}<td class="r {sign(p.exp_return)}">{pct(p.exp_return)}</td>{/each}
      </tr>
      <tr>
        <td colspan="6">Volatilidad anual</td>
        {#each mk.portfolios as p (p.key)}<td class="r">{share(p.vol)}</td>{/each}
      </tr>
      <tr>
        <td colspan="6">Sharpe (tasa libre de riesgo de {share(s.risk_free, 0)})</td>
        {#each mk.portfolios as p (p.key)}<td class="r">{ratio(p.sharpe)}</td>{/each}
      </tr>
    </tfoot>
  </table>
</div>
<h3>Peso por sector</h3>
<div class="wrap narrow">
  <table>
    <thead>
      <tr><th>Sector</th>{#each mk.portfolios as p (p.key)}<th class="r">{p.label}</th>{/each}</tr>
    </thead>
    <tbody>
      {#each portfolioSectors as name (name)}
        <tr>
          <td>{name}</td>
          {#each mk.portfolios as p (p.key)}
            {@const w = sectorWeightOf(p, name)}
            <td class="r" class:atcap={w >= mk.sector_max - 1e-4}>{w ? share(w) : ''}</td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>
</div>
<p class="sub note">En negrita, los sectores que llegan al tope de {share(mk.sector_max, 0)}.</p>

<h2>Ranking del S&amp;P 500</h2>
<p class="sub">
  Las {cov.ranked} acciones con los tres scores, de mejor a peor score final. ROE, márgenes, flujo de caja libre (FCF) sobre ventas,
  capitalización y utilidad, y la distancia a las EMA en porcentaje; «Deuda/Patr.» es deuda sobre patrimonio y «Años FCF+»,
  la parte de los últimos 4 años con flujo libre positivo.
  {#if cov.excluded.sin_momentum.length}Sin un año de precios (no tienen momentum): {cov.excluded.sin_momentum.join(', ')}.{/if}
  {#if cov.excluded.sin_datos_financieros.length}Sin datos financieros: {cov.excluded.sin_datos_financieros.join(', ')}.{/if}
  {#if cov.excluded.sin_datos_tecnicos.length}Sin datos técnicos: {cov.excluded.sin_datos_tecnicos.join(', ')}.{/if}
</p>
<div class="filters">
  <label>
    Buscar
    <input type="search" bind:value={query} placeholder="ticker o empresa" />
  </label>
  <label>
    Sector
    <select bind:value={sector}>
      <option value="">Todos</option>
      {#each sectors as name}<option value={name}>{name}</option>{/each}
    </select>
  </label>
  <label>
    Detalle
    <select value={view} onchange={(e) => setView(e.currentTarget.value)}>
      {#each Object.entries(views) as [key, v] (key)}<option value={key}>{v.label}</option>{/each}
    </select>
  </label>
  <span class="muted">{rows.length} de {quant.ranking.length}</span>
</div>
<div class="wrap">
  <table>
    <thead>
      <tr>
        {#each columns as column (column.key)}
          <th class:r={column.numeric} aria-sort={ariaSort(column)}>
            <button onclick={() => sortBy(column)}>
              {column.label}{#if sortKey === column.key}<span aria-hidden="true">{descending ? ' ▼' : ' ▲'}</span>{/if}
            </button>
          </th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each rows as r (r.ticker)}
        <tr class:top={r.rank <= s.top_n}>
          {#each columns as column (column.key)}
            {#if column.key === 'ticker'}
              <td><TickerLink ticker={r.ticker} /></td>
            {:else}
              {@const c = cell(r, column.key)}
              <td class={c.cls} title={c.title}>{c.text}</td>
            {/if}
          {/each}
        </tr>
      {:else}
        <tr><td colspan={columns.length} class="muted">Ninguna acción cumple el filtro.</td></tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .how { margin: var(--space-2) 0; padding-left: 20px; max-width: 90ch; }
  .how li { margin: 6px 0; }
  .filters { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; margin: 12px 0; }
  label { display: inline-flex; align-items: center; gap: 8px; color: var(--muted); font-size: .9rem; }
  input[type='search'] {
    background: var(--card); color: var(--fg); border: 1px solid var(--line); border-radius: var(--radius-sm);
    padding: 5px 10px; min-height: 32px;
  }
  th button {
    background: none; border: 0; padding: 0; font: inherit; color: inherit; cursor: pointer; white-space: nowrap;
    text-transform: inherit; letter-spacing: inherit;
  }
  th button:hover { color: var(--fg); }
  .narrow { max-width: 760px; }
  h3 { font-size: 1rem; margin: var(--space-4) 0 var(--space-2); }
  td.atcap { font-weight: 700; }
  .note { margin-top: var(--space-2); }
  td.strong { font-weight: 700; }
  td.main { font-weight: 650; background: color-mix(in srgb, var(--accent) 8%, transparent); }
  tfoot td { background: var(--th); font-variant-numeric: tabular-nums; border-top: 1px solid var(--line); }
  tr.top td:first-child { box-shadow: inset 3px 0 0 var(--accent); }
  tr.top { background: color-mix(in srgb, var(--accent) 6%, transparent); }
</style>
