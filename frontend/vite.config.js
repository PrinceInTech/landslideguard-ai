import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The backend listens on 8000 by default. Both the dev server and `npm run
// preview` proxy /api to it so the frontend can always use same-origin
// relative URLs (see src/services/api.js, which defaults VITE_API_URL to '').
const BACKEND_ORIGIN =
  process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_PROXY_TARGET || BACKEND_ORIGIN

  const proxy = {
    '/api': {
      target,
      changeOrigin: true,
      secure: false,
    },
  }

  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: false,
      proxy,
    },
    preview: {
      port: 4173,
      strictPort: false,
      proxy,
    },
    build: {
      chunkSizeWarningLimit: 1100,
      rollupOptions: {
        output: {
          manualChunks: {
            react: ['react', 'react-dom', 'react-router-dom'],
            charts: ['recharts'],
            map: ['leaflet', 'react-leaflet'],
          },
        },
      },
    },
  }
})