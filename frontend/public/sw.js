/*
 * LandslideGuard AI — service worker (app-shell caching only).
 *
 * Hard rules:
 *   - NEVER cache anything under /api/ (auth, predictions, alerts, admin,
 *     locations, risk-summary). Those requests are handed straight to the
 *     network and their responses are never written to a cache.
 *   - Only same-origin, GET, static asset / navigation responses are cached.
 *   - The cache is versioned (CACHE_NAME); old caches are deleted on activate.
 *
 * Unregistering / clearing during local development:
 *   - DevTools ▸ Application ▸ Service Workers ▸ Unregister, or delete the
 *     "landslideguard-shell-*" entries under Cache Storage. Or run in the
 *     console:
 *       navigator.serviceWorker.getRegistrations().then(rs => rs.forEach(r => r.unregister()))
 *   - The app never registers this worker outside production builds, so
 *     `npm run dev` does not install it at all (see src/main.jsx).
 */

const CACHE_NAME = 'landslideguard-shell-v1'
const SHELL_FALLBACK = '/index.html'
const PRECACHE_URLS = ['/', '/index.html']

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      try {
        const cache = await caches.open(CACHE_NAME)
        await cache.addAll(PRECACHE_URLS)
      } catch {
        // A failed pre-cache must not block installation; the app still works.
      }
      await self.skipWaiting()
    })()
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys()
      await Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
      await self.clients.claim()
    })()
  )
})

const isApiRequest = (url) => url.pathname.startsWith('/api/')

const isStaticAsset = (url) =>
  url.pathname.startsWith('/assets/') ||
  /\.(?:js|mjs|css|png|jpe?g|gif|svg|ico|webp|woff2?|ttf|eot)$/i.test(url.pathname)

self.addEventListener('fetch', (event) => {
  const { request } = event

  // Only GET is eligible for caching; mutations always go to the network.
  if (request.method !== 'GET') return

  const url = new URL(request.url)

  // Ignore cross-origin and, critically, all API traffic.
  if (url.origin !== self.location.origin) return
  if (isApiRequest(url)) return

  // Navigations: network-first, falling back to the cached shell when offline.
  if (request.mode === 'navigate') {
    event.respondWith(
      (async () => {
        try {
          const fresh = await fetch(request)
          const cache = await caches.open(CACHE_NAME)
          cache.put(SHELL_FALLBACK, fresh.clone())
          return fresh
        } catch {
          const cache = await caches.open(CACHE_NAME)
          const cached =
            (await cache.match(SHELL_FALLBACK)) || (await cache.match('/'))
          return cached || Response.error()
        }
      })()
    )
    return
  }

  // Versioned static assets: cache-first with a background refresh.
  if (isStaticAsset(url)) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(CACHE_NAME)
        const cached = await cache.match(request)
        const network = fetch(request)
          .then((response) => {
            if (response && response.ok && response.type === 'basic') {
              cache.put(request, response.clone())
            }
            return response
          })
          .catch(() => cached)
        return cached || network
      })()
    )
  }
})
