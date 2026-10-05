# LandslideGuard AI — Frontend

React + Vite + Tailwind dashboard for landslide risk monitoring in Northeast India.

## Stack

- React 18, Vite 5, Tailwind CSS 3
- React Router (SPA navigation)
- Recharts (analytics charts)
- Leaflet + react-leaflet (interactive GIS risk map)
- Lucide React (icons)

## Quick Start

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to the backend (default `http://127.0.0.1:8001`, override
with the `VITE_PROXY_TARGET` env var or edit `vite.config.js`). The app then
behaves like a single origin — no CORS problems in development.

Open http://localhost:5173 (see Vite output for the actual port).

## Pages

| Route          | Purpose                                          |
| -------------- | ------------------------------------------------ |
| `/`            | Landing page                                     |
| `/dashboard`   | Overall risk overview + alerts + environment     |
| `/map`         | Interactive GIS map of NER risk                  |
| `/prediction`  | ML prediction form + gauge + explainability      |
| `/alerts`      | Alert management (acks, resolve, filters)        |
| `/analytics`   | Historical charts and state-wise summaries       |
| `/locations`   | Monitoring location CRUD                         |
| `/ai-insights` | Model explainability and future scope            |
| `/admin`       | Admin panel (upload dataset, retrain, trigger)   |
| `/settings`    | System configuration status                      |

## Production build

```bash
npm run build     # outputs to dist/
npm run preview   # serve the build locally
```