import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En local apunta a localhost:8000; en Docker se sobreescribe con VITE_PROXY_TARGET
const coreTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    include: ['html5-qrcode']
  },
  server: {
    watch: {
      usePolling: true,
    },
    host: true, // needed for docker
    proxy: {
      '/api': {
        target: coreTarget,
        changeOrigin: true
      },
      '/auth': {
        target: coreTarget,
        changeOrigin: true
      },
      '/core': {
        target: coreTarget,
        changeOrigin: true
      },
      '/ws': {
        target: coreTarget,
        changeOrigin: true,
        ws: true
      }
    }
  }
})
