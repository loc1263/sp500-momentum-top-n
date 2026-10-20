import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App.svelte';
import { report } from './test/fixtures.js';

const json = (body) => ({
  ok: true,
  headers: { get: () => 'application/json' },
  json: async () => body,
});
const fail = () => ({ ok: false, headers: { get: () => '' } });

beforeEach(() => {
  location.hash = '';
  delete document.documentElement.dataset.theme;
});
afterEach(() => vi.unstubAllGlobals());

describe('App', () => {
  it('carga api/report y muestra el Top actual', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(report)));
    render(App);
    expect(await screen.findByText('NVDA')).toBeInTheDocument();
    expect(screen.getByText(/Corrida del 2026-10-20/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith('api/report');
  });

  it('cae al JSON estático si la API no responde', async () => {
    const f = vi.fn(async (url) => (url === 'api/report' ? fail() : json(report)));
    vi.stubGlobal('fetch', f);
    render(App);
    expect(await screen.findByText('NVDA')).toBeInTheDocument();
    expect(f).toHaveBeenLastCalledWith('data/report.json');
  });

  it('ignora respuestas que no son JSON', async () => {
    const html = { ok: true, headers: { get: () => 'text/html' }, json: async () => ({}) };
    vi.stubGlobal('fetch', vi.fn(async (url) => (url === 'api/report' ? html : json(report))));
    render(App);
    expect(await screen.findByText('NVDA')).toBeInTheDocument();
  });

  it('muestra un error si no hay ninguna fuente', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('red'); }));
    render(App);
    expect(await screen.findByText(/No se pudo cargar/)).toBeInTheDocument();
  });

  it('cambia de pestaña y actualiza el hash', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(report)));
    render(App);
    await screen.findByText('NVDA');
    await fireEvent.click(screen.getByRole('tab', { name: 'Plazos y sensibilidad' }));
    expect(await screen.findByText('Comparación de plazos')).toBeInTheDocument();
    await waitFor(() => expect(location.hash).toBe('#sweep'));
  });

  it('abre la pestaña indicada en el hash', async () => {
    location.hash = '#backtest';
    vi.stubGlobal('fetch', vi.fn(async () => json(report)));
    render(App);
    expect(await screen.findByText('Curva de capital')).toBeInTheDocument();
  });

  it('alterna el tema', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(report)));
    render(App);
    await fireEvent.click(screen.getByRole('button', { name: /tema/i }));
    expect(document.documentElement.dataset.theme).toBe('dark');
    await fireEvent.click(screen.getByRole('button', { name: /tema/i }));
    expect(document.documentElement.dataset.theme).toBe('light');
  });
});
