import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The dev server proxies /stac to the earthx STAC API so the frontend can use
// same-origin relative URLs (no CORS). Override the backend target via
// VITE_API_PROXY if needed. /collections goes to the `tiler` process instead
// (a separate process/port, architekturplan.md 3.2) — its tile and statistics
// routes are rooted at /collections/{dataset}/items/{item}/... (adr/0006).
// Override with VITE_TILER_PROXY. /coverage (M2-05b), /aoi (M3-06a/b) and
// /geocode (M3-07a/b) all sit on the `api` process's base app, outside /stac,
// so they share apiTarget.
const apiTarget = process.env.VITE_API_PROXY ?? 'http://localhost:8000'
const tilerTarget = process.env.VITE_TILER_PROXY ?? 'http://localhost:8001'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/stac': { target: apiTarget, changeOrigin: true },
      '/coverage': { target: apiTarget, changeOrigin: true },
      '/aoi': { target: apiTarget, changeOrigin: true },
      '/geocode': { target: apiTarget, changeOrigin: true },
      '/collections': { target: tilerTarget, changeOrigin: true },
    },
  },
  test: {
    // `.tsx` as well since M2-10: the hint below a dataset's lowest released
    // level was invisible not because its rule was wrong but because it was
    // mounted inside a panel that slides away, and only rendering a component
    // catches that.
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
