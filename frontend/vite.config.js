import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const API = 'http://localhost:8002'

// Several API prefixes (/wallets, /projects, /chains, /reports…) are also page routes.
// Without this, reloading the browser on /wallets was proxied to the backend instead of
// serving the app. Browser navigations (Accept: text/html) get index.html; fetch/XHR still proxy.
const api = {
  target: API,
  bypass: req => (req.headers.accept?.includes('text/html') ? '/index.html' : undefined),
}

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth': api,
      '/agent': api,
      '/chains': api,
      '/wallets': api,
      '/projects': api,
      '/faucets': api,
      '/ai': api,
      '/autonomy': api,
      '/reports': api,
      '/ops': api,
      '/stats': api,
      '/proxies': api,
      '/claims': api,
      '/ws': { target: 'ws://localhost:8002', ws: true },
    },
  },
})
