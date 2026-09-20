import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The dev server proxies /stac to the earthx STAC API so the frontend can use
// same-origin relative URLs (no CORS). Override the backend target via
// VITE_API_PROXY if needed.
const apiTarget = process.env.VITE_API_PROXY ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/stac': { target: apiTarget, changeOrigin: true },
    },
  },
  test: {
    include: ['src/**/*.test.ts'],
  },
})
