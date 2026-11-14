import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dashboard calls /api/... and Vite passes those calls on to Django,
// so the browser only ever talks to one address (no CORS set-up needed).
// Point it at another machine with:  FARE_SERVER=http://192.168.1.20:8000 npm run dev
const server = process.env.FARE_SERVER || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': server } },
  preview: { proxy: { '/api': server } },
})
