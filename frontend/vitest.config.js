import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Dedicated Vitest config so the product `vite.config.js` (dev proxy + build
// chunking) is left untouched. Tests run in jsdom with the same React plugin
// the app is built with. Dependencies are declared in package.json; if they
// are not installed yet, run `npm install` in `frontend/` first.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
    css: false,
  },
})
