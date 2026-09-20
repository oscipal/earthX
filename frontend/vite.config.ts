import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The dev server proxies /stac to the earthx STAC API so the frontend can use
// same-origin relative URLs (no CORS). Override the backend target via
// VITE_API_PROXY if needed. /collections goes to the `tiler` process instead
// (a separate process/port, architekturplan.md 3.2) — its tile and statistics
// routes are rooted at /collections/{dataset}/items/{item}/... (adr/0006).
// Override with VITE_TILER_PROXY.
const apiTarget = process.env.VITE_API_PROXY ?? 'http://localhost:8000'
const tilerTarget = process.env.VITE_TILER_PROXY ?? 'http://localhost:8001'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/stac': { target: apiTarget, changeOrigin: true },
      '/collections': { target: tilerTarget, changeOrigin: true },
    },
  },
  test: {
    include: ['src/**/*.test.ts'],
  },
})
