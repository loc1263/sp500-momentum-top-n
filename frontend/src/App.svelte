<script>
  import ActualView from './lib/ActualView.svelte';
  import BacktestView from './lib/BacktestView.svelte';
  import SweepView from './lib/SweepView.svelte';
  import EtfView from './lib/EtfView.svelte';
  import Glossary from './lib/Glossary.svelte';
  import Bunny from './lib/Bunny.svelte';

  const tabs = [
    { id: 'actual', label: 'Top actual' },
    { id: 'backtest', label: 'Backtest' },
    { id: 'sweep', label: 'Plazos y sensibilidad' },
    { id: 'etf', label: 'ETFs Vanguard' },
  ];

  const initialTab = () => (tabs.some((t) => t.id === location.hash.slice(1)) ? location.hash.slice(1) : 'actual');

  let tab = $state(initialTab());
  let capKey = $state('0');
  let chosenYears = $state(null); // null = período por defecto del config
  let report = $state(null);
  let error = $state(null);
  let dark = $state(document.documentElement.dataset.theme === 'dark');

  function toggleTheme() {
    dark = !dark;
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    try {
      localStorage.setItem('theme', dark ? 'dark' : 'light');
    } catch {
      /* el tema vale solo para esta sesión */
    }
  }

  // Primero la API del backend; si no está levantada, el JSON estático exportado
  async function load() {
    for (const url of ['api/report', 'data/report.json']) {
      try {
        const res = await fetch(url);
        if (res.ok && (res.headers.get('content-type') ?? '').includes('json')) return await res.json();
      } catch {
        /* se prueba la siguiente fuente */
      }
    }
    throw new Error('No se pudo cargar api/report ni data/report.json. ¿Está levantado el backend?');
  }

  $effect(() => {
    load().then((r) => (report = r), (e) => (error = e.message));
  });

  $effect(() => {
    history.replaceState(null, '', `#${tab}`);
  });

  const key = (u) => String(u.min_cap_billions ?? 0);
  const universes = $derived(
    report ? [...new Map([...report.actual, ...report.backtest].map((u) => [key(u), u])).values()] : [],
  );
  const actual = $derived(report?.actual.find((a) => key(a) === capKey));
  const universeData = $derived(report?.backtest.find((u) => key(u) === capKey));
  const periods = $derived(universeData?.periods ?? []);
  const period = $derived(
    periods.find((p) => p.years === (chosenYears ?? report?.settings.backtest_years)) ?? periods.at(-1),
  );
  // Lo que reciben las vistas: el universo con el período elegido
  const universe = $derived(
    universeData && period ? { label: universeData.label, ...period } : null,
  );
  const label = $derived(universes.find((u) => key(u) === capKey)?.label ?? '');
</script>

<main>
  <header>
    <button class="theme" onclick={toggleTheme} aria-label="Cambiar tema claro/oscuro" title="Cambiar tema">
      {dark ? '☀️ Claro' : '🌙 Oscuro'}
    </button>
    <h1>Top {report?.settings.top_n ?? 'N'} del S&amp;P 500</h1>
    <p class="sub">
      Momentum: cada N meses se compran, con ponderación igual, las acciones que más subieron en los últimos N meses.
      {#if report}
        Corrida del {report.run_date ?? 'sin datos'}.
      {/if}
    </p>
  </header>

  {#if error}
    <p class="best error">{error}</p>
  {:else if !report}
    <p class="muted">Cargando…</p>
  {:else}
    <nav>
      <div class="tabs" role="tablist">
        {#each tabs as t}
          <button role="tab" aria-selected={tab === t.id} class:active={tab === t.id} onclick={() => (tab = t.id)}>
            {t.label}
          </button>
        {/each}
      </div>
      <div class="filters">
        {#if tab !== 'actual' && tab !== 'etf' && periods.length}
          <label>
            Período
            <select value={period?.years} onchange={(e) => (chosenYears = Number(e.currentTarget.value))}>
              {#each periods as p (p.years)}
                <option value={p.years}>
                  {p.years} años ({p.start_date.slice(0, 4)}–{p.end_date.slice(0, 4)})
                </option>
              {/each}
            </select>
          </label>
        {/if}
        {#if tab !== 'etf'}
          <label>
            Universo
            <select bind:value={capKey}>
              {#each universes as u (key(u))}
                <option value={key(u)}>{u.label}</option>
              {/each}
            </select>
          </label>
        {/if}
      </div>
    </nav>

    {#if tab === 'backtest' || tab === 'sweep'}<Glossary />{/if}

    {#if tab === 'etf'}
      {#if report.etf}
        <EtfView etf={report.etf} />
      {:else}
        <p class="muted">Sin ranking de ETFs. Corré top3_etf.py.</p>
      {/if}
    {:else if tab === 'actual'}
      {#if actual}
        <ActualView {actual} />
      {:else}
        <p class="muted">Sin Top actual para «{label}». Corré top3_actual.py.</p>
      {/if}
    {:else if !universe}
      <p class="muted">Sin backtest para «{label}». Corré top3_backtest.py --sweep.</p>
    {:else if tab === 'backtest'}
      {#key `${capKey}-${period.years}`}<BacktestView {universe} settings={report.settings} />{/key}
    {:else}
      <SweepView {universe} settings={report.settings} />
    {/if}

    <footer>
      Generado el {report.generated_at.replace('T', ' ')}. Backtest sin comisiones ni impuestos, ponderación igual
      entre los tickers seleccionados. Excluye tickers sin datos en Yahoo (sesgo de supervivencia). Herramienta de
      análisis, no una recomendación de inversión.
    </footer>
  {/if}
</main>

<Bunny />

<style>
  main { max-width: 1280px; margin: 0 auto; padding: 24px 16px 48px; }
  header { position: relative; }
  .theme {
    position: absolute; top: 0; right: 0; background: var(--card); color: var(--fg); border: 1px solid var(--line);
    border-radius: 6px; padding: 4px 10px; font: inherit; font-size: .85rem; cursor: pointer;
  }
  nav { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px 16px; margin: 16px 0 8px; }
  .tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); flex: 1 1 auto; }
  .tabs button {
    background: none; border: 0; border-bottom: 2px solid transparent; color: var(--muted); cursor: pointer;
    font: inherit; padding: 8px 14px; margin-bottom: -1px;
  }
  .tabs button.active { color: var(--fg); border-bottom-color: var(--accent); font-weight: 600; }
  .filters { display: flex; flex-wrap: wrap; gap: 8px 16px; }
  nav label { display: inline-flex; align-items: center; gap: 8px; color: var(--muted); font-size: .9rem; }
  .error { border-left-color: var(--neg); }
  footer { margin-top: 32px; color: var(--muted); font-size: .8rem; }
</style>
