# LandslideGuard AI

**AI-Powered Early Warning & Landslide Risk Monitoring System for Northeast India**

Built for the **Smart India Hackathon 2026**, framed around landslide risk
monitoring for the Ministry of Development of North Eastern Region (MDoNER).

> **Attribution note:** the problem identifier and ministry above are this
> project's own framing, not independently verified here. The **official SIH
> problem statement is not included in this repository**, so the exact problem
> number, title and sponsoring ministry must be checked against the official SIH
> source separately.

---

## Project Overview

LandslideGuard AI is a working, end-to-end AI platform that monitors
landslide-prone areas across the **8 North Eastern states of India**, ingests
environmental data, predicts landslide risk with a **real trained machine
learning model**, explains **why** each location is risky, issues **graded early
warnings**, and visualizes everything on an **interactive GIS map**.

> Every major feature is functional — not a static mock. The React dashboard
> talks to FastAPI; prediction calls the actual Random Forest model; the map
> loads real backend data; alerts start from the database.

## SIH Problem Statement

The project is aimed at this framing: *build an intelligent system that monitors
landslide-prone areas in the North Eastern Region of India, analyzes
environmental and geographical factors, predicts landslide risk using machine
learning, provides early warnings, and displays everything through an
interactive dashboard.*

> The wording above is this repository's own paraphrase. The **official SIH
> problem statement is not present in this repository and has not been verified
> here** — check the official SIH source for the authoritative problem number,
> title and sponsoring ministry before quoting any of them.

## Solution

| Layer            | What it does                                             |
| ---------------- | -------------------------------------------------------- |
| Data ingestion   | Demo (deterministic simulated) or LIVE weather (OpenWeatherMap), with automatic fallback |
| ML engine        | Random Forest trained on environmental + geological features |
| Risk assessment  | 0–100 score, LOW / MODERATE / HIGH / CRITICAL, confidence |
| Explainability   | Per-prediction contributing factors (rainfall, slope, soil moisture, …) |
| Early warning    | Alerts auto-created on escalation, with recommended actions |
| GIS dashboard    | Leaflet map of NER with live risk markers + location details |
| Analytics        | Monthly trends, rainfall correlation, state summaries, risk distribution |
| Admin            | Dataset upload, model re-train trigger, location CRUD, stats |

## Features

- Interactive monitoring dashboard (overall risk, counts, alerts, environment, confidence)
- Risk map of all NER states with 30 monitoring locations
- Real ML prediction (Random Forest, honest metrics on demo data)
- Explainable AI — factor contribution bars for every prediction
- Early warning engine with actionable alerts & status workflow
- Historical analytics with charts (trends, correlation, distributions)
- State-wise monitoring for all 8 NER states
- Alert management (view / acknowledge / resolve, filters, search)
- Admin panel (auth, upload, retrain, trigger, CRUD)
- Weather service abstraction — LIVE vs DEMO clearly labelled
- Loading / error / empty / retry states throughout the UI
- Responsive government-style dark UI

## Architecture

```
Environmental Data → Data Ingestion → Processing → Feature Engineering
        → AI/ML Prediction Engine → Risk Assessment → Early Warning Engine
              → GIS Dashboard → Authorities
              → Alerts       → Users
```
See **[docs/architecture.md](docs/architecture.md)** for the full diagram.

## AI/ML Methodology

- **Dataset:** `data/historical_landslide_data.csv` (1,470 rows, labelled).
  **This is demo/sample data** — the README and UI say so explicitly.
- **Features (12):** rainfall, rainfall intensity, soil moisture, temperature,
  humidity, elevation, slope, historical occurrence, distance to drain, land
  cover, soil type, rock type.
- **Algorithm:** Random Forest Classifier (`class_weight=balanced`, 200 trees).
- **Split:** 80/20 stratified.
- **Metrics (demo data):** Accuracy **0.823**, Precision **0.884**, Recall **0.848**,
  F1 **0.866** — reported honestly, never inflated. These are reproduced exactly
  by re-running `python ml/train.py`.
- **Score:** `100 × probability^1.6`, bucketed LOW ≤30 / MODERATE ≤60 /
  HIGH ≤80 / CRITICAL ≤100.
- **Explainability:** factor contributions derived from feature importances.

See **[docs/model.md](docs/model.md)**.

## Dataset

```
data/
  historical_landslide_data.csv   # 1,470 labeled rows (DEMO)
  monitoring_locations.csv        # 30 locations across NER states
  sample_realtime_data.json       # example realtime payload
```

Regenerate with:
```bash
python ml/data/generate_data.py
```
In production, replace these files with real observations (see Future Scope).

> **Data contract & provenance (Phase 2.2):** see
> **[docs/provenance.md](docs/provenance.md)** for the typed contract that will
> govern future REAL data — per-record provenance, source-level provenance, and
> the committed manifest at `data/provenance/manifest.json`, which registers
> DEMO artifacts by SHA-256 and will reference raw REAL files by checksum only
> (raw files are git-ignored under `data/raw/`).

## Tech Stack

- **Frontend:** React · Vite · Tailwind CSS · React Router · Recharts · Leaflet/react-leaflet · Lucide
- **Backend:** Python · FastAPI · Pydantic · Uvicorn · SQLAlchemy
- **ML:** Pandas · NumPy · Scikit-learn · Joblib
- **Database:** SQLite via SQLAlchemy (the only engine with a declared driver)
- **Weather:** OpenWeatherMap (optional, free) with DEMO fallback

## Installation

Prerequisites: Python 3.10+ (tested on 3.12 and 3.14), Node 18+.

```bash
# 1. Clone / enter the project
cd landslideguard-ai

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows:  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cd ..

# 3. Frontend
cd frontend
npm install
cd ..
```

The trained model is committed to the repo, so nothing needs to be generated
before first run.

### Dependencies

- **Runtime:** [`backend/requirements.txt`](backend/requirements.txt) — what the
  application needs to serve requests. Install this everywhere, including
  deployment.
- **Test:** [`backend/requirements-dev.txt`](backend/requirements-dev.txt) —
  `pytest` and `httpx`, used only by the test suite. Install it in development
  and CI, not in production:

  ```bash
  pip install -r backend/requirements.txt -r backend/requirements-dev.txt
  ```

### Running the tests

**Backend** — with **pytest**, from `backend/`:

```bash
cd backend
pytest -q
```

The suite creates its own throwaway SQLite database under the system temp
directory and removes it when the run finishes; it never touches the developer's
`backend/landslideguard.db` or the Docker runtime `data/landslideguard.db`.

**Frontend** — with **Vitest**, from `frontend/`:

```bash
cd frontend
npm test            # single run (vitest run)
npm run test:watch  # watch mode
```

The frontend tests run in `jsdom` (config in `frontend/vitest.config.js`) and
stub `fetch`, so they never make real network calls. They cover the router shell,
loading/error/empty states, the risk helpers, and the DEMO/LIVE and offline
surfaces.

### Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on pushes to `main`
and on pull requests:

- **Backend job** — installs `backend/requirements.txt` + `requirements-dev.txt`
  on Python 3.12, runs `python -m pytest -q`, then a whitespace/conflict-marker
  check and the protected-file verifier.
- **Frontend job** — installs from `frontend/package-lock.json` with `npm ci` and
  runs `npm run build`.

> **Note:** CI builds the frontend but does **not** execute the Vitest suite
> (`npm test`) in the current workflow. Run the frontend tests locally as above.
> Remote CI status is **not verified** from this repository.

## Environment Variables

All variables are optional — with no `.env` the app boots on safe local
defaults. See **[.env.example](.env.example)** for the annotated list.

```bash
cp .env.example .env
```

The ones that matter most:

| Variable | Default | Notes |
| -------- | ------- | ----- |
| `DATA_MODE` | `DEMO` | `LIVE` requires `OPENWEATHER_API_KEY` |
| `JWT_SECRET` | insecure dev value | **must** be overridden outside local dev (`ENVIRONMENT` not `development`/`dev`/`local`/`test`) |
| `DEMO_ADMIN_PASSWORD` | `admin123` | **must** be changed outside local dev |
| `ENVIRONMENT` | `development` | any value other than `development`/`dev`/`local`/`test` enables the fail-fast secret checks |
| `OPENWEATHER_API_KEY` | _(empty)_ | unset ⇒ deterministic DEMO weather |
| `CORS_ORIGINS` | localhost:5173,127.0.0.1:5173,localhost:8080 | only needed for cross-origin browser calls |
| `VITE_API_URL` | _(empty)_ | build-time; set only if the API is on a different origin |

> Do **not** set `DATABASE_URL` to a relative path. SQLite resolves relative
> paths against the process working directory, which differs between a local run
> and the container. Leave it unset for the default, or give an absolute path.

## Running Locally

Two terminals:

```bash
# Terminal 1 — backend on :8000
cd backend
.venv\Scripts\activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- API docs: http://127.0.0.1:8000/docs
- On startup the server seeds 30 locations + the demo admin, computes risks,
  and creates escalation alerts. The SQLite DB (`backend/landslideguard.db`) is
  created automatically.

```bash
# Terminal 2 — frontend on :5173
cd frontend
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api` to
`http://127.0.0.1:8000`; override with `VITE_PROXY_TARGET`.

> **Authentication required:** the dashboard and all other app pages
> (`/dashboard`, `/map`, `/prediction`, `/alerts`, `/analytics`, `/locations`,
> `/ai-insights`, `/admin`, `/settings`) are auth-gated. Opening them while
> signed out redirects to `/login` (`frontend/src/layouts/DashboardLayout.jsx`),
> so sign in first with the demo credentials below.

> **Port watch:** if Vite auto-selects another port because 5173 is busy, open
> that port instead — the proxy still works. If you use a non-default port, add
> it to `CORS_ORIGINS` when talking to the backend cross-origin.

On Windows you can also run `.\run.ps1` to start both. It waits for the backend
to report healthy before printing the URLs, and stops both processes on Ctrl+C.

```powershell
.\run.ps1                                  # backend :8000, frontend :5173
.\run.ps1 -BackendPort 8123 -VitePort 5180 # custom ports (proxy follows)
```

## Troubleshooting

**Backend exits immediately with `[winerror 10013]` / "access permissions".**
Windows reserves a block of TCP ports that cannot be bound even when they look
free. Check what is excluded on your machine:

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```

On a typical Windows install this excludes **8002–8101**, so `-BackendPort 8010`
or `8080` will fail while appearing free. Pick a port outside the excluded
ranges (e.g. `8000`, or anything `>= 8102`).

**Frontend shows a blank page / "Cannot GET /src/main.jsx".**
`frontend/src/` is missing or was never restored, or `npm install` was not run
in `frontend/`. The dev server logs a proxy error for the same reason.

**`/api/health` reports `model: "missing"`.**
The trained artifacts are committed to the repo; confirm
`ml/model/landslide_model.joblib` and `preprocessors.joblib` exist. If you
deleted them, regenerate with `python ml/train.py`, or point `MODEL_PATH` /
`PREPROCESSOR_PATH` at them.

**First request to the Vite dev server hangs for a few seconds.**
Vite is optimizing and pre-bundling dependencies on first load, then reloads.
This is normal — retry.

## Running with Docker

```bash
docker compose up --build
# frontend http://localhost:5173  ·  backend http://localhost:8000/docs
```

- The frontend is served by nginx, which also reverse-proxies `/api`, so the
  browser talks to a single origin and CORS is not needed.
- `./data` is bind-mounted (the SQLite DB survives restarts).
- The model directory is a **named volume** (`lg_ml_model`) seeded from the
  image, so a model trained via the admin retrain endpoint survives restarts.
- `docker compose down -v` deletes the model volume and reseeds it from the image
  on the next `up`.

## Training the ML Model

```bash
# From the project root
python ml/data/generate_data.py     # regenerate demo dataset (optional)
python ml/train.py                  # train + save model + print metrics
python ml/evaluate.py               # evaluate saved model
```

Artifacts: `ml/model/landslide_model.joblib`, `ml/model/preprocessors.joblib`,
`ml/model/model_meta.json`. The backend loads these automatically at startup and
can re-run this pipeline through `POST /api/admin/retrain`.

## Demo Mode

- The app runs fully offline with **DEMO data** immediately after install.
- Demo weather is **deterministic within 15-minute windows** so judges can
  reproduce results while conditions still evolve over time.
- Every page shows a **DEMO DATA** badge. Set a weather API key + `DATA_MODE=LIVE`
  to switch to live conditions — the UI badge flips to **LIVE DATA**.
- Fallbacks mean the app never crashes without a model, API key, or DB.

## Offline & Poor Connectivity

The UI degrades gracefully when the browser loses connectivity:

- **Browser connectivity is not the same as backend availability.** The
  Online/Offline badge reflects the *browser's* network state only. Backend
  reachability is confirmed per request (error states and the DEMO/LIVE source
  badge), so "Online" does not guarantee the API is reachable.
- **Cached dashboard summary, always labelled stale.** After a successful load
  the dashboard stores a **sanitized, non-sensitive** aggregate snapshot in
  `localStorage` (`frontend/src/services/offlineCache.js`). It deliberately
  never stores tokens, user data, the alert list, monitored locations or
  predictions. Offline, that snapshot is shown as a read-only view headed
  `OFFLINE — STALE / LAST UPDATED …`.
- **Backend-dependent writes are disabled offline.** Refresh, predictions,
  alert changes, sign-in and admin operations are disabled while offline and
  re-enable automatically when connectivity returns.
- **The app shell is cached in production builds only.** A service worker
  (`frontend/public/sw.js`) caches same-origin GET navigations and static
  `/assets/` so the app can load offline. It **never** caches `/api/` responses
  or non-GET requests. It is registered only in production builds
  (`import.meta.env.PROD` in `frontend/src/main.jsx`), so `npm run dev` does not
  install it.

## API Documentation

Full reference in **[docs/api.md](docs/api.md)**. Summary:

```
GET  /api/health                 GET  /api/locations
GET  /api/locations/{location_id}         POST /api/locations
PUT  /api/locations/{location_id}         DELETE /api/locations/{location_id}
GET  /api/environmental/{location_id}     POST /api/predict
POST /api/predict/location/{location_id}  GET  /api/predictions
GET  /api/risk-summary           GET  /api/alerts
POST /api/alerts                 PUT  /api/alerts/{alert_id}
GET  /api/analytics              GET  /api/weather/{location_name}
POST /api/auth/login             POST /api/auth/register
GET  /api/auth/me
POST /api/extract                POST /api/provenance/validate
GET  /api/admin/stats            GET  /api/admin/alerts
POST /api/admin/upload-dataset   POST /api/admin/retrain
POST /api/admin/trigger-predict  GET  /api/admin/settings
```

That is 27 API operations plus a `GET /` service banner.

Read endpoints (`GET /api/locations`, `/risk-summary`, `/analytics`, `/alerts`,
`/predictions`) are public. Write endpoints — `POST`/`PUT`/`DELETE` on locations
and alerts, `POST /api/predict`, `POST /api/predict/location/{id}`,
`POST /api/extract` and `POST /api/provenance/validate` — require a valid
`Authorization: Bearer <token>` (any authenticated role). Routes under
`/api/admin/*` additionally require the
`admin` role. See **[docs/api.md](docs/api.md)** for the full authorization
model.

## Demo Credentials

```
email:    admin@landslideguard.ai
password: admin123
```

Seeded on an empty database, bcrypt-hashed, JWT-authenticated. Override with
`DEMO_ADMIN_EMAIL` / `DEMO_ADMIN_PASSWORD`.

> **Local demo use only.** These default credentials are published in this
> repository and the login page (`frontend/src/pages/Login.jsx`) for convenient
> local/judge demos. They **must** be overridden (a non-default
> `DEMO_ADMIN_PASSWORD` and a real `JWT_SECRET`) before any non-local deployment;
> with `ENVIRONMENT` set outside the local values the backend refuses to boot on
> the insecure defaults.

> **Note:** `POST /api/auth/register` creates accounts with the least-privileged
> `viewer` role. Self-service signup can never mint an admin — admin accounts are
> created by the startup seed or by promoting a user in the database.

## Verifying the Install

```bash
# Backend health + model + DB status
curl http://localhost:8000/api/health
```

The behaviours above (auth, role enforcement, risk summary, the alerts workflow,
analytics, prediction monotonicity across LOW→CRITICAL, admin retrain,
restart-safe seeding, read-path write elimination and CORS) are exercised by the
**in-process backend test suite** using `httpx.TestClient` (`backend/tests/`) —
not by a running Docker stack.

> **Not verified here:** the `docker compose` stack has **not** been run and
> validated end-to-end in this repository's recorded evidence. Treat the Docker
> and cloud deployment sections below as documented setup steps, not as tested
> end-to-end guarantees.

## Screenshots

Real captures from a running instance are stored under **`docs/screenshots/`**.
They were taken at a 1440×900 desktop viewport against a locally-running stack
in DEMO data mode (see **[docs/demo.md](docs/demo.md)** for the demo login and
route walkthrough):

| Page | Route | File |
| ---- | ----- | ---- |
| Landing | `/` | [`docs/screenshots/landing.png`](docs/screenshots/landing.png) |
| Login | `/login` | [`docs/screenshots/login.png`](docs/screenshots/login.png) |
| Dashboard | `/dashboard` | [`docs/screenshots/dashboard.png`](docs/screenshots/dashboard.png) |
| Risk Map | `/map` | [`docs/screenshots/risk-map.png`](docs/screenshots/risk-map.png) |
| Prediction | `/prediction` | [`docs/screenshots/prediction.png`](docs/screenshots/prediction.png) |
| Alerts | `/alerts` | [`docs/screenshots/alerts.png`](docs/screenshots/alerts.png) |
| Analytics | `/analytics` | [`docs/screenshots/analytics.png`](docs/screenshots/analytics.png) |
| AI Insights | `/ai-insights` | [`docs/screenshots/ai-insights.png`](docs/screenshots/ai-insights.png) |
| Locations | `/locations` | [`docs/screenshots/locations.png`](docs/screenshots/locations.png) |
| Admin | `/admin` | [`docs/screenshots/admin.png`](docs/screenshots/admin.png) |
| Settings | `/settings` | [`docs/screenshots/settings.png`](docs/screenshots/settings.png) |

The `login.png` capture shows the login form with the password field cleared
and the plaintext demo-credential hint hidden (the demo email remains prefilled).
It was re-captured on 2026-10-15 from a **production build preview** and verified
programmatically; it is byte-identical to the previously reviewed image, so the
recorded human review still applies and no separate human inspection of the
re-capture was performed. The linked
[`docs/screenshots/visual-review-log.md`](docs/screenshots/visual-review-log.md)
currently records 11 screenshots as `REVIEWED` and 0 as `NOT REVIEWED`; these are
human-recorded review statuses and do not independently establish visual QA
verification. Overall screenshot visual QA remains `NOT VERIFIED`, and any row
still marked `NOT REVIEWED` must be treated as unreviewed. Make sure these files
are committed before relying on any submission-generated link. The suggested
page set and exact routes originate in
**[docs/demo.md → Screenshot checklist](docs/demo.md#5-screenshot-checklist)**.

## Deployment

### Docker (full stack, single host)
```bash
docker compose up --build -d
```

### Backend — Render / Railway
[`render.yaml`](render.yaml) is a ready Render Blueprint (Deploy → New → Blueprint).

1. The service root is the **repository root**, not `backend/` — the backend needs
   the sibling `ml/` and `data/` directories to load the model, seed locations and
   re-train on demand.
2. Build: `pip install -r backend/requirements.txt`
3. Start: `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT`
4. Health check path: `/api/health`
5. Set env vars: `ENVIRONMENT=production`, `JWT_SECRET` (random 48+ chars),
   `DEMO_ADMIN_PASSWORD` (non-default), `DATA_MODE`, `OPENWEATHER_API_KEY`.
6. Render's filesystem is ephemeral, so by default the SQLite DB and any retrained
   model are lost on each redeploy. Attach a disk (see the `disk:` block in
   `render.yaml`) and point `DATABASE_URL`, `DATA_DIR` and `MODEL_DIR` at it.
7. Only SQLite is supported — no other driver is declared in `requirements.txt`.

### Frontend — Vercel / Netlify
[`frontend/vercel.json`](frontend/vercel.json) carries the SPA rewrite, so client
routes like `/dashboard` resolve to `index.html` instead of 404ing.

1. Root directory: **`frontend`** · Build: `npm run build` · Output: `dist`.
2. Set `VITE_API_URL` to the deployed backend origin (e.g.
   `https://your-api.onrender.com`) in the project's environment variables. When
   set, the frontend calls the backend directly instead of using the dev proxy —
   set the backend `CORS_ORIGINS` to the frontend origin to match.
3. `VITE_API_URL` is inlined at **build** time, so redeploy the frontend after
   changing the backend URL.

### Auth rate limiting and reverse proxies

`POST /api/auth/login` and `POST /api/auth/register` are guarded by an
**in-process, per-client-address** fixed-window limiter
([`backend/app/services/rate_limit.py`](backend/app/services/rate_limit.py);
defaults 10 requests/60 s for login and 5/300 s for registration, overridable
with the `AUTH_*` environment variables). A blocked attempt returns `429` with a
`Retry-After` header and a generic body that does not reveal whether an account
exists. Client identity is the transport peer address only — forwarding headers
such as `X-Forwarded-For` are deliberately ignored so a caller cannot forge new
buckets by rotating a header.

This is a **best-effort, per-process** control, **not** a distributed one:

- Counters live in the process memory, reset on restart, and are **not shared
  across workers or replicas** — with N workers the effective limit is roughly N×
  the configured value.
- Behind the bundled nginx (or any proxy that terminates the connection) every
  caller can share the proxy's address and therefore a **single bucket**, so
  legitimate users may be throttled together.
- Storage is bounded (4096 keys); a flood of distinct source addresses can evict
  existing buckets.

For any multi-worker, multi-replica or public deployment, add a **shared or
edge-level** limit at the proxy/gateway or a central store, covering both login
and registration and returning the same generic `429`. If per-client identity is
required, enable proxy-header trust (uvicorn `--proxy-headers` /
`--forwarded-allow-ips`) **only for known trusted proxies** — never trust
forwarded headers from arbitrary clients. The current single-process deployments
(`uvicorn` without `--workers` in `backend/Dockerfile` and `render.yaml`) do not
need proxy headers for the limiter to work, and none of this changes the app's
authentication behavior.

## Future Scope

- ISRO / NRSC satellite & remote-sensing feeds
- IoT rain gauges and soil moisture sensors
- Time-series forecasting (LSTM/transformers)
- SHAP-based per-prediction explanations
- SMS / WhatsApp / Email notification channels
- Public alerting portal + mobile app
- PostgreSQL/MongoDB persistence behind a repository abstraction
- Regional model calibration per state

## Team Contribution

| Role | Responsibility |
| ---- | -------------- |
| ML Engineer | Dataset pipeline, model training, evaluation, explainability |
| Backend Dev | FastAPI, database, prediction & alert services, auth |
| Frontend Dev | React dashboard, GIS map, charts, responsive UI |
| UI/UX Designer | Landing page, information architecture, risk visual language |
| Data/GIS Analyst | NER monitoring locations & geological feature curation |
| DevOps | Docker, deployment guides, environment configuration |

---

*Framed for Smart India Hackathon 2026 around landslide risk monitoring for
the North Eastern Region. The problem identifier and sponsoring ministry are
this project's own framing — see the attribution note at the top of this file
and verify against the official SIH source.*