import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The dev server proxies /api to the FastAPI backend so the frontend can use
// same-origin relative URLs (no CORS, and the MAAP token never touches the
// browser). Override the backend target via VITE_API_PROXY if needed.
const apiTarget = process.env.VITE_API_PROXY ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
    },
  },
  test: {
    include: ['src/**/*.test.ts'],
  },
})
