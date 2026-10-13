import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
// Bundled so the production CSP (style-src 'self') can serve it; index.html
// must not link it from a CDN. Imported before index.css so the local
// .leaflet-container overrides above win.
import 'leaflet/dist/leaflet.css'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
)

// Register the app-shell service worker in production only. In development it
// is never registered so a stale cache can never shadow HMR. A failed
// registration is non-fatal: the app simply runs without offline shell caching.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((error) => {
      console.warn('Service worker registration failed; continuing without it.', error)
    })
  })
}