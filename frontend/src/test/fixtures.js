// Datos mínimos con la forma del JSON que sirve /api/report

export const settings = { top_n: 2, months: 4, backtest_years: 5, initial_capital: 1000 };

const equity = (values) => values.map((capital, i) => ({ date: `202${i}-06-30`, capital }));

const calendar = (offset, final, cagr) => ({
  offset,
  start_date: '2020-01-31',
  end_date: '2022-12-31',
  first_rebalance: '2020-02-28',
  rebalances: 6,
  final_capital: final,
  total_return: final / 1000 - 1,
  cagr,
  equity: equity([1000, (1000 + final) / 2, final]),
  history: [
    {
      date: '2020-06-30', capital: 1000, gain: 0,
      picks: [{ ticker: 'NVDA', return: 0.5 }, { ticker: 'BRK-B', return: -0.1 }],
    },
  ],
});

const term = (months, cagrs) => ({
  months,
  summary: {
    calendars: cagrs.length,
    cagr_median: cagrs[0],
    cagr_min: Math.min(...cagrs),
    cagr_max: Math.max(...cagrs),
    capital_median: 1500,
    capital_min: 1200,
    capital_max: 1900,
  },
  calendars: cagrs.map((c, i) => calendar(i, 1000 * (1 + c) ** 3, c)),
});

export const period = (years) => ({
  years,
  start_date: `${2025 - years}-01-31`,
  end_date: '2025-01-31',
  terms: [term(3, [0.1, 0.05, 0.2]), term(4, [0.3, 0.2, 0.4])],
});

export const report = {
  run_date: '2026-10-20',
  generated_at: '2026-10-20T10:00:00',
  settings,
  actual: [
    {
      min_cap_billions: 0, label: 'Todo el índice', as_of: '2026-10-19', months: 4,
      previous_as_of: '2026-10-16', anchor: '2026-06-18', next_rebalance: '2026-10-01',
      changes: { entered: ['AMD'], exited: ['AAPL'], kept: ['NVDA'] },
      picks: [
        { rank: 1, ticker: 'NVDA', return: 0.5, market_cap: 4e12, price: 180.5 },
        { rank: 2, ticker: 'BRK-B', return: -0.02, market_cap: 1e12, price: 480 },
      ],
    },
  ],
  etf: {
    as_of: '2026-10-19', run_at: '2026-10-19T10:00:00', top_n: 2, horizons: [3, 12], risk_free: 'VUSB',
    previous_as_of: '2026-10-16', changes: { entered: ['AMD'], exited: ['VTV'], kept: ['VONV'] },
    rows: [
      { rank: 1, ticker: 'VONV', name: 'Russell 1000 Value', category: 'Acciones EE. UU. estilo', score: 1.67,
        vol: 0.111, max_dd: -0.068, sma_dist: 0.096, returns: { 3: 0.045, 12: 0.291 } },
      { rank: 2, ticker: 'VDE', name: 'Energy', category: 'Sectores', score: 1.66, vol: 0.219, max_dd: -0.15,
        sma_dist: 0.171, returns: { 3: 0.136, 12: 0.601 } },
      { rank: 3, ticker: 'BND', name: 'Total Bond Market', category: 'Bonos EE. UU.', score: -0.4, vol: 0.05,
        max_dd: -0.04, sma_dist: -0.01, returns: { 3: -0.01, 12: 0.02 } },
    ],
  },
  backtest: [
    { min_cap_billions: 0, label: 'Todo el índice', periods: [period(3), period(5)] },
  ],
};
