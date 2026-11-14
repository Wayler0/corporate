import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dashboard calls /api/... and Vite passes those calls on to Django,
// so the browser only ever talks to one address (no CORS set-up needed).
// Point it at another machine with:  FARE_SERVER=http://192.168.1.20:8000 npm run dev
const server = process.env.FARE_SERVER || 'http://127.0.0.1:8000'

const api = {
  target: server,
  changeOrigin: true,   // Django sees its own address as the Host...
  configure(proxy) {
    // ...so the Origin must match it too, or Django's CSRF check refuses
    // every POST (the browser's Origin is this dev server, e.g. a phone on
    // http://192.168.1.20:5173).
    proxy.on('proxyReq', (request) => {
      if (request.getHeader('origin')) request.setHeader('origin', server)
    })
  },
}

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': api } },
  preview: { proxy: { '/api': api } },
})
