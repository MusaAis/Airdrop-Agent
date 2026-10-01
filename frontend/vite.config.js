import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth': 'http://localhost:8002',
      '/agent': 'http://localhost:8002',
      '/chains': 'http://localhost:8002',
      '/wallets': 'http://localhost:8002',
      '/projects': 'http://localhost:8002',
      '/faucets': 'http://localhost:8002',
      '/ai': 'http://localhost:8002',
      '/autonomy': 'http://localhost:8002',
      '/reports': 'http://localhost:8002',
      '/ops': 'http://localhost:8002',
      '/stats': 'http://localhost:8002',
      '/proxies': 'http://localhost:8002',
      '/autonomy': 'http://localhost:8002',
      '/ws': {
        target: 'ws://localhost:8002',
        ws: true
      }
    }
  }
})
