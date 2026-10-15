# System Architecture

## Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                          DATA SOURCES                                  │
│  OpenWeatherMap (optional) · Monitoring Locations CSV · Sample Data     │
└───────────────────────────────┬────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       DATA INGESTION                                   │
│  WeatherProvider (data_provider.py)                                    │
│  • LIVE mode: OpenWeatherMap REST calls                                │
│  • DEMO mode: deterministic simulated weather (15-min windows)         │
│  • Automatic fallback → never breaks                                   │
└───────────────────────────────┬────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  DATA PROCESSING + PERSISTENCE                          │
│  SQLite via SQLAlchemy (users, locations, environmental_data,           │
│  predictions, alerts). Service functions own the queries; SQLite is the   │
│  only engine with a declared driver                                        │
└───────────────────────────────┬────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     FEATURE ENGINEERING                                 │
│  rainfall, rainfall intensity, soil moisture, temperature, humidity,    │
│  elevation, slope, historical occurrence, distance to drain,            │
│  land cover / soil / rock type (label-encoded)                          │
└───────────────────────────────┬────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       AI/ML PREDICTION ENGINE                           │
│  RandomForestClassifier (joblib) trained in ml/train.py                 │
│  Score 0–100 (probability rescaled): LOW ≤30 · MODERATE ≤60             │
│           HIGH ≤80 · CRITICAL ≤100                                      │
└───────────────────────────────┬────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        RISK ASSESSMENT                                  │
│  risk score + level + confidence + explainable factor contributions     │
│  (per-factor bars shown in the UI)                                      │
└───────────────────────────────┬────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        EARLY WARNING ENGINE                             │
│  Escalation to HIGH/CRITICAL → Alert row + notification abstraction      │
│  (in-app now; SMS / WhatsApp / Email pluggable later)                   │
└───────────────┬───────────────────────────────┬─────────────────────────┘
                │                               │
                ▼                               ▼
┌──────────────────────────┐        ┌──────────────────────────┐
│       GIS DASHBOARD       │        │         ALERTS           │
│  React + Leaflet map,     │        │  status workflow:        │
│  dashboard, prediction,   │        │  active → acknowledged   │
│  analytics, admin         │        │  → resolved              │
└──────────────────────────┘        └──────────────────────────┘
                │                               │
                ▼                               ▼
         Authorities                    Users / Communities
         (district DMAs)                (in-app + future SMS)
```

## Backend layers

```
FastAPI (app/) 
 ├─ api/        → HTTP routes, validation (Pydantic), error handling
 ├─ services/   → business logic, providers (data, weather, analytics, auth, alerts)
 ├─ ml/         → model loading + inference + explainability
 ├─ models/     → SQLAlchemy ORM (Users, Locations, EnvironmentalData, Predictions, Alerts)
 ├─ schemas/    → request/response models
 └─ database/   → engine + session
```

## Frontend layers

```
React SPA (frontend/src/)
 ├─ pages/      → one component per route
 ├─ layouts/    → authenticated app shell + sidebar
 ├─ components/ → reusable UI (map, gauge, badges, charts, states, offline)
 ├─ hooks/      → API fetching / polling / auth / online status
 ├─ services/   → axios instance with JWT interceptor, offline summary cache
 └─ utils/      → risk level metadata + formatting
frontend/public/
 └─ sw.js       → app-shell service worker (production builds only)
```

## Offline behaviour

The app degrades safely when the browser is offline. There are two independent
pieces, and neither one silently substitutes live data:

**1. App-shell service worker (`frontend/public/sw.js`).** In **production
builds only** (`import.meta.env.PROD` in `frontend/src/main.jsx`; `npm run dev`
never registers it), a service worker caches a versioned app shell
(`landslideguard-shell-v1`) so the SPA can load offline:

- It caches **same-origin, GET** navigations and static `/assets/` files only.
- It **never** caches anything under `/api/` and **never** caches non-GET
  requests — those go straight to the network (see the guard in `sw.js`).
- Navigations are network-first with a cached-shell fallback; static assets are
  cache-first with a background refresh. Old caches are deleted on activate.

**2. Allowlisted dashboard-summary cache (`frontend/src/services/offlineCache.js`).**
After each successful `GET /api/risk-summary`, the dashboard stores a
**sanitized, non-sensitive** aggregate snapshot in `localStorage` under
`lg_offline_risk_summary` (schema version 1). It whitelists fields and
deliberately **never** stores credentials, JWTs, user profiles, alerts, the
monitored-location list or predictions. Malformed/old/invalid payloads are
purged. Offline, and only offline, that snapshot renders as a read-only
`OfflineDashboard` headed `OFFLINE — STALE / LAST UPDATED …`, so a cached value
can never be mistaken for live data. Coming back online drops the cache view and
the live endpoints take over.

**Writes are not queued or replayed.** While offline, `useApi`/`usePolling` skip
the doomed request and surface an offline error without discarding already-loaded
data; refresh, predictions, alert changes, sign-in and admin actions are
disabled in the UI. Nothing is buffered for later submission — there is **no**
offline write queue, background sync or replay, so returning online never
silently re-issues a mutation the user made while disconnected.

**Connectivity vs availability.** The `ConnectionStatus` badge reflects the
*browser's* `navigator.onLine` state only. It does **not** assert that the
backend API is reachable; that is confirmed per request via error states and the
DEMO/LIVE source badge below.

## Data-mode distinctions (DEMO vs LIVE)

Source labelling is layered, and the two terms are not interchangeable:

- **Provider configured source** — `LIVE` only when `DATA_MODE=LIVE` **and** an
  OpenWeatherMap key is configured; otherwise `DEMO` (deterministic simulated
  weather, stable within 15-minute windows).
- **Source actually served** — the provider may fall back to DEMO mid-flight;
  `GET /api/risk-summary` reports this as `data_source` alongside
  `data_mode_configured` and `live_degraded`. `live_degraded = true` is how a
  `LIVE` deployment that has silently fallen back to simulated readings becomes
  visible; the UI renders it as `LIVE UNAVAILABLE — DEMO DATA`.
- **Model provenance** — predictions carry `data_source` + `prediction_mode`
  (`"demo"`), matching the DEMO-trained model; this never implies production
  readiness.

See [`docs/api.md`](api.md) for the exact fields and the DEMO/model caveats in
[`docs/model.md`](model.md).

## Key design decisions

1. **SQLite via SQLAlchemy.** All DB access sits in `services/` and
   `api/` modules rather than being scattered through routes, which keeps the
   query surface small and reviewable. Be aware this is *not* a formal
   repository pattern: there is no ORM/DB abstraction interface, and no driver
   other than SQLite's is declared in `requirements.txt`, so swapping engines
   today would mean writing that abstraction first.
2. **Demo/LIVE transparency.** Every response includes `data_source` so the UI
   clearly labels DEMO vs LIVE.
3. **No crash on missing pieces.** Model missing → rule fallback. Weather API
   down → demo fallback. Database down → HTTP 503 with message.
4. **Deterministic demo.** 15-minute time buckets give reproducible demonstrations.
5. **Explainability first.** Risk is never a black box — contributing factors are
   returned with each prediction.

## Dependency reproducibility & locking

Runtime dependencies are declared as **minimum versions** in
[`backend/requirements.txt`](../backend/requirements.txt); test-only
dependencies live in
[`backend/requirements-dev.txt`](../backend/requirements-dev.txt). `ml/` has
its own [`requirements.txt`](../ml/requirements.txt) for the training pipeline.
No fully pinned lockfile is committed, so two installs resolved at different
times can produce different transitive versions.

The trained artifact is version-sensitive: `ml/model/model_meta.json` records
the exact `library_versions` used to fit it (including `scikit-learn`). Loading
a pickled model under a *different* scikit-learn build is supported but emits a
benign `InconsistentVersionWarning`; the runtime interpreter and the training
interpreter should be kept in step. **Known skew:** the committed model was
pickled with a newer scikit-learn than a fresh floor-based install may resolve,
so the warning is expected until the runtime is aligned (below).

**Locking plan (not yet executed — no lockfile is fabricated here):**

1. In an environment that matches the deployment target, install the declared
   requirements, then capture exact versions with
   `python -m pip freeze > backend/requirements.lock` (and equivalently for the
   frontend via the committed `frontend/package-lock.json`, which is already
   pinned).
2. Retrain the model (`python ml/train.py`) **in that same environment** so
   `model_meta.json.library_versions` matches the locked runtime exactly, and
   the `InconsistentVersionWarning` disappears.
3. Install from the lockfile in CI and in the image so the tested environment
   and the shipped environment are identical.

Until step 2 runs, the existing model continues to load and predict; the skew
is a reproducibility gap, not a functional failure.