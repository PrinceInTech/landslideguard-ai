# Demo Guide

A practical, repository-grounded guide to running and presenting LandslideGuard AI
locally, aimed at judges and reviewers.

> **Scope:** this guide documents what the repository actually supports. It does
> **not** claim the app, the Docker stack, the frontend build/tests, or remote CI
> were executed as part of writing it. See the
> [command verification status](#command-verification-status) for exactly what
> has and has not been verified.

## Verification legend

Used throughout this file:

- **Documented** — described by repository code/config/docs; not necessarily run
  while this guide was written.
- **Previously verified** — recorded as passing in an earlier project phase
  (backend pytest suite; frontend `npm test` / `npm run build`).
- **Not yet verified** — no recorded run in this repository (e.g. Docker,
  cloud deployment, remote CI).

## 1. Prerequisites

| Requirement | Detail |
| ----------- | ------ |
| Python | 3.10+ (tested on 3.12 and 3.14) |
| Node.js | 18+ |
| Committed model | `ml/model/landslide_model.joblib`, `preprocessors.joblib`, `model_meta.json` are committed — no training needed before first run |
| `.env` | **Not required.** With no `.env` the app boots on safe local defaults (`DATA_MODE=DEMO`, deterministic simulated weather) |

No API key is needed for the DEMO flow. `LIVE` weather additionally needs
`OPENWEATHER_API_KEY` and `DATA_MODE=LIVE` (see [README → Environment Variables](../README.md#environment-variables)).

## 2. Launch options (documented)

Pick **one**. The first two are local-process launches; the third is containerised.

### Option A — `run.ps1` (Windows helper)

```powershell
.\run.ps1
# or custom ports (the Vite proxy follows):
.\run.ps1 -BackendPort 8123 -VitePort 5180
```

Starts the backend on `:8000` and Vite on `:5173`, waits for `/api/health` to
report healthy, then prints the URLs and the demo login. Requires
`backend\.venv` and `frontend\node_modules` to already exist (the script exits
with instructions otherwise).

### Option B — two terminals

```bash
# Terminal 1 — backend
cd backend
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — frontend
cd frontend
npm run dev
```

- API docs: http://127.0.0.1:8000/docs
- App: http://localhost:5173 (Vite proxies `/api` to the backend; override with
  `VITE_PROXY_TARGET`)

### Option C — Docker Compose (not yet verified)

```bash
docker compose up --build
# frontend http://localhost:5173  ·  backend http://localhost:8000/docs
```

The frontend is served by nginx, which reverse-proxies `/api`, so the browser
talks to a single origin. **This stack has not been run/validated end-to-end in
this repository's evidence** — treat it as a documented setup path.

> **Port note:** on Windows a reserved TCP range (commonly 8002–8101) can make an
> apparently-free port fail to bind. Check with
> `netsh interface ipv4 show excludedportrange protocol=tcp` and choose a port
> outside the excluded ranges.

## 3. Startup & login checklist

- [ ] Backend process started (Option A or B).
- [ ] `GET /api/health` returns `"status": "ok"` and `"model": "ok"`
      (documented) — a `"model": "missing"` value means only the rule-based
      fallback is active.
- [ ] Frontend dev server reachable at http://localhost:5173.
- [ ] Landing page loads at `/`.
- [ ] Sign in at `/login` with the demo credentials below and land on `/dashboard`.

> **Dashboard routes require authentication.** Opening `/dashboard` or any other
> app page while signed out redirects to `/login`
> (`frontend/src/layouts/DashboardLayout.jsx`).

**Demo credentials (local demo use only):**

```
email:    admin@landslideguard.ai
password: admin123
```

Seeded on an empty database by the startup seed, bcrypt-hashed, JWT-authenticated.
These defaults are published in the repo for local/judge demos. On the login
form the email is prefilled, the password is left empty, and the plaintext
demo-credential hint is rendered **only in Vite development mode**
(`import.meta.env.DEV`) — it is absent from production builds. They **must** be
overridden before any non-local deployment (see
[README → Demo Credentials](../README.md#demo-credentials)).

## 4. Route-by-route walkthrough

Routes are defined in `frontend/src/App.jsx`; the signed-in shell groups them in
`frontend/src/layouts/Sidebar.jsx` (Monitor / Intelligence / Manage).

### `/` — Landing
Public marketing/overview page. Hero, "how it works", capability cards, tech
stack, and CTAs. Buttons link into the app (which then requires sign-in).

> The landing page states the SIH framing and an impact statistic in the UI.
> The official SIH problem statement is **not** in this repository — verify the
> problem number/title/ministry and any external statistics independently.

### `/login` — Login
Email prefilled, password left empty, a sign-in button, and an offline notice.
The demo-credential hint below the form is shown only in Vite development mode
(`import.meta.env.DEV`) and is not present in production builds. Login is
disabled while the browser is offline (sign-in needs the backend).

### `/dashboard` — Disaster Monitoring Dashboard
Summary cards (monitored locations, overall risk, active alerts, average model
certainty), a risk-distribution bar chart, the highest-risk location, an
environmental snapshot, and recent alerts. The header shows a `DEMO DATA` /
`LIVE DATA` / `LIVE UNAVAILABLE — DEMO DATA` source badge and an Online/Offline
indicator. Data is polled (20–30 s) with pause/resume and manual refresh.

### `/map` — Risk Map
Leaflet map of the Northeast with risk markers plus a detail panel for the
selected site (model output, per-location risk bands, terrain/weather values,
recorded trigger factors) and a searchable list of all monitored locations.

### `/prediction` — AI Risk Prediction
Form over the model inputs; choose a monitoring site to **write the result to
that site's record**, or leave **"None — ad-hoc input"** for a **read-only
preview** that changes nothing. Results show score, level, model certainty,
probability, top contributing factors and recommended actions, plus read-only
stored history.

> **Write-back disclosure:** the form warns before running when a site is
> selected — it updates that site's stored risk and may raise or resolve alerts.
> Prefer the "None" preview during a demo unless you intend the write.

### `/alerts` — Alerts
Early-warning list with status workflow (`active → acknowledged → resolved`),
filters and search, expandable rows, and a per-alert lifecycle view. Only real
API timestamps are shown — an unrecorded step is labelled as such, never
invented.

### `/analytics` — Historical Analytics
Charts and summaries over the historical incident dataset (monthly trends,
rainfall correlation, risk distribution, state-wise summary, highest-risk
locations). Data is historical/DEMO.

### `/ai-insights` — AI Insights
Model card (algorithm, version, training samples, features, metrics) and global
feature importance, plus an explicit "what these explanations are — and are not"
panel. The metrics shown are demo-data results and are labelled as such.

### `/locations` — Monitoring Locations
Table of monitored sites (coordinates, terrain, current risk, last updated) with
admin-style add/edit/delete controls.

> **Destructive:** Deleting a location also removes its dependent environmental
> history, predictions and alerts (see [Do not do this during a demo](#7-do-not-do-this-during-a-demo)).

### `/admin` — Admin  *(admin-only)*
Admin statistics, a prominent `DATA MODE:` badge, the full alert list
(issued/resolved timestamps), and admin actions (upload dataset, retrain,
trigger prediction, location CRUD). Hidden from `viewer` accounts.

### `/settings` — Settings  *(admin-only)*
Application status (from `/api/health`) and data/model configuration (data mode,
database, model path, whether a weather key is configured). Non-admin accounts
see an "Admin access required" state instead of a raw 403.

## 5. Screenshot checklist

The 11 captures below are already saved under `docs/screenshots/` and referenced
from the [README Screenshots section](../README.md#screenshots). They were taken
at a 1440×900 desktop viewport against a locally-running stack in DEMO data
mode.

| # | Page | Route | File | Notes |
| - | ---- | ----- | ---- | ----- |
| 1 | Landing | `/` | `docs/screenshots/landing.png` | Public hero + framing |
| 2 | Login | `/login` | `docs/screenshots/login.png` | Password field cleared; demo hint hidden — credentials not visible |
| 3 | Dashboard | `/dashboard` | `docs/screenshots/dashboard.png` | Source badge + summary cards |
| 4 | Risk Map | `/map` | `docs/screenshots/risk-map.png` | A site selected to show the detail panel |
| 5 | Prediction | `/prediction` | `docs/screenshots/prediction.png` | A completed result (preview mode) |
| 6 | Alerts | `/alerts` | `docs/screenshots/alerts.png` | Expand one alert to show the lifecycle |
| 7 | Analytics | `/analytics` | `docs/screenshots/analytics.png` | Charts visible |
| 8 | AI Insights | `/ai-insights` | `docs/screenshots/ai-insights.png` | Model card + importance |
| 9 | Locations | `/locations` | `docs/screenshots/locations.png` | Table populated |
| 10 | Admin | `/admin` | `docs/screenshots/admin.png` | DATA MODE badge visible (admin login) |
| 11 | Settings | `/settings` | `docs/screenshots/settings.png` | Admin status/config (admin login) |

Tips: use a desktop viewport (the layout is `lg`-oriented), wait for data to
load before capturing, and keep the DEMO/LIVE badge in frame so the data source
is unambiguous.

## 6. DEMO & model limitations

State these plainly when presenting — the UI already does:

- The model is a **Random Forest trained on synthetic DEMO data**
  (`data/historical_landslide_data.csv`), not on observed landslide inventory.
- The DEMO dataset has **label leakage**: the label is a thresholded linear
  score over seven of the model's own features
  (`ml/data/generate_data.py`). The reported metrics
  (accuracy ≈ 0.823 and friends) measure how well the forest **recovers that
  rule**, not real-world predictive skill, and are described in
  [`docs/model.md`](model.md) as an inflated upper bound.
- **Do not claim real-world model performance.** Meaningful accuracy requires
  real labelled inventories and a geographically held-out validation split.
- "Model certainty" is a distance-from-0.5 heuristic (range 55–95), **not**
  calibrated statistical confidence, and the per-run factor bars are a
  rule-based contribution score, **not** SHAP/LIME or causal attribution.
- The REAL-data feature path (`/api/extract`, `/api/provenance/validate`) is a
  **contract + reader foundation**, not a trained model; with the currently
  acquired single-day/single-hour artifacts, rolling-window features report
  `insufficient_temporal_coverage` and provenance validation returns
  `production_readiness = "NO-GO"`.
- **Production readiness remains `NO-GO`.** The demo is not a validated
  early-warning deployment.
- The landing-page impact claim **"2,300+ landslides a year" is an unverified
  statistic** — this repository contains no traceable supporting source for it,
  so treat it as framing copy, not a cited figure.

Related: [`docs/model.md`](model.md), [`docs/features.md`](features.md),
[`docs/provenance.md`](provenance.md).

## 7. Do not do this during a demo

These actions **overwrite or delete existing data or artifacts**. Avoid them
unless you intend the change and have a backup:

- **Upload dataset** (`POST /api/admin/upload-dataset`, Admin page) — replaces
  the training CSV (`data/historical_landslide_data.csv`).
- **Retrain model** (`POST /api/admin/retrain`, Admin page) — rewrites the model
  artifacts (`ml/model/*`); takes around a minute.
- **Regenerate dataset** (`python ml/data/generate_data.py`) — overwrites the
  demo dataset; the committed `dataset_sha256` no longer matches until retrained.
- **Delete a location** (Locations page) — cascades to that location's
  environmental history, predictions and alerts.
- **Trigger prediction for a site** (`POST /api/admin/trigger-predict`, or running
  Prediction with a site selected) — recomputes stored risk and may raise/resolve
  alerts.
- **`docker compose down -v`** — deletes the `lg_ml_model` named volume; it is
  reseeded from the image on the next `up`, but any retrained model is lost.

Safe for a demo: viewing any page, the read-only Prediction **preview**
("None" site), filtering/searching alerts, and refreshing data.

## 8. Offline behaviour

- The header **Online/Offline** badge reflects the **browser's** network state
  only; backend availability is confirmed per request. "Online" does not
  guarantee the API is reachable.
- After a successful dashboard load, a **sanitized aggregate snapshot** is saved
  to `localStorage` (`frontend/src/services/offlineCache.js`). It never stores
  tokens, user data, alerts, the location list or predictions. Offline, that
  snapshot is shown as a read-only view headed `OFFLINE — STALE / LAST UPDATED …`.
- **Backend-dependent writes are disabled offline** (refresh, predictions, alert
  changes, sign-in, admin operations) and re-enable on reconnect.
- The **app-shell service worker** (`frontend/public/sw.js`) caches same-origin
  GET navigations and static `/assets/` **in production builds only**; it never
  caches `/api/` responses or non-GET requests. `npm run dev` does not register
  it. See [`docs/architecture.md`](architecture.md#frontend-layers).

To try the offline view: load the dashboard, then toggle the browser/DevTools to
"Offline". The stale snapshot (if one was cached) and the disabled-action state
appear; toggle back online and the live endpoints take over.

## 9. Troubleshooting

Drawn from existing repository documentation and observed implementation:

| Symptom | Likely cause / fix |
| ------- | ------------------ |
| Backend exits with `[winerror 10013]` / "access permissions" | Windows reserved TCP port range — pick a port outside it (`netsh interface ipv4 show excludedportrange protocol=tcp`) |
| Frontend blank page / "Cannot GET /src/main.jsx" | `npm install` was not run in `frontend/`, or `frontend/src/` is missing |
| `/api/health` reports `"model": "missing"` | Model artifacts absent — confirm `ml/model/landslide_model.joblib` and `preprocessors.joblib` exist (they are committed), or regenerate with `python ml/train.py` |
| First request to the Vite dev server hangs a few seconds | Vite is pre-bundling dependencies on first load — retry |
| Signed-out user bounced from `/dashboard` to `/login` | Expected: app routes are auth-gated; sign in with the demo credentials |
| Viewer account sees no Admin/Settings in the sidebar | Expected: those routes are admin-only |

See also [README → Troubleshooting](../README.md#troubleshooting).

## Command verification status

This guide was written without running these commands. Status reflects the
repository's recorded evidence, not a run during this writing:

| Command | Status |
| ------- | ------ |
| `cd backend; pytest -q` | Previously verified (backend suite) |
| `cd frontend; npm test` | Previously verified (Vitest suite) |
| `cd frontend; npm run build` | Previously verified |
| `npm install` (frontend) | Documented |
| `.\run.ps1` | Documented (not run here) |
| `docker compose up --build` | **Not yet verified** |
| `curl http://localhost:8000/api/health` | Documented endpoint (not run here) |
| `python ml/train.py` / `ml/evaluate.py` / `ml/data/generate_data.py` | Documented (not run here) |
| Remote CI (GitHub Actions) | **Not verified remotely** |

## Related documentation

- [README](../README.md) — install, run, API summary, deployment
- [`docs/architecture.md`](architecture.md) — system layers and data-mode flow
- [`docs/model.md`](model.md) — ML methodology, metrics and the leakage caveat
- [`docs/api.md`](api.md) — full API reference and authorization model
- [`docs/features.md`](features.md) — REAL-data feature contract and statuses
