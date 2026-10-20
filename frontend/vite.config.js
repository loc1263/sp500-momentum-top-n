import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// El backend (backend/server.py) escucha en BACKEND_URL; en desarrollo /api se redirige hacia él
const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
  base: './',
  plugins: [svelte()],
  server: {
    port: Number(process.env.FRONTEND_PORT ?? 5173),
    strictPort: true,
    proxy: { '/api': backend },
  },
});
