<script>
  import { pct, share, usd, billions, sign } from './format.js';

  let { actual } = $props();

  const weight = $derived(actual.picks.length ? 1 / actual.picks.length : 0);
  const from = $derived.by(() => {
    const d = new Date(`${actual.as_of}T00:00:00Z`);
    d.setUTCMonth(d.getUTCMonth() - actual.months);
    return d.toISOString().slice(0, 10);
  });
</script>

<div class="cards">
  <div class="card"><div class="k">Datos al cierre del</div><div class="v">{actual.as_of}</div></div>
  <div class="card"><div class="k">Plazo</div><div class="v">{actual.months} meses</div></div>
  <div class="card"><div class="k">Acciones</div><div class="v">{actual.picks.length}</div></div>
  <div class="card"><div class="k">Peso por acción</div><div class="v">{share(weight)}</div></div>
</div>

<h2>Top {actual.picks.length} de los últimos {actual.months} meses</h2>
<p class="range">
  <strong>Ventana de retorno:</strong> {from} a {actual.as_of}
  <span class="muted">({actual.months} meses)</span>
</p>
<p class="sub">
  Ponderación igual; se rebalancea cada {actual.months} meses. Cap. aprox. = precio × acciones en circulación
  actuales, informativa.
</p>
<div class="wrap">
  <table>
    <thead>
      <tr>
        <th>#</th><th>Ticker</th><th class="r">Retorno {actual.months} meses</th>
        <th class="r">Cap. aprox. (US$ B)</th><th class="r">Precio (US$)</th><th class="r">Peso</th>
      </tr>
    </thead>
    <tbody>
      {#each actual.picks as p (p.ticker)}
        <tr>
          <td>{p.rank}</td>
          <td><strong>{p.ticker}</strong></td>
          <td class="r {sign(p.return)}">{pct(p.return)}</td>
          <td class="r">{billions(p.market_cap)}</td>
          <td class="r">{usd(p.price)}</td>
          <td class="r">{share(weight)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
