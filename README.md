# LandslideGuard AI

**AI-Powered Early Warning & Landslide Risk Monitoring System for Northeast India**

Built for the **Smart India Hackathon 2026** — Problem **SIH26001**
(Ministry of Development of North Eastern Region · Theme: Disaster Management).

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

> Build an intelligent system that monitors landslide-prone areas in the North
> Eastern Region of India, analyzes environmental and geographical factors,
> predicts landslide risk using Machine Learning, provides early warnings, and
> displays everything through an interactive dashboard. — *SIH26001, MDoNER*

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

Tests are run with **pytest**, from `backend/`:

```bash
cd backend
pytest -q
```

The suite creates its own throwaway SQLite database under the system temp
directory and removes it when the run finishes; it never touches the developer's
`backend/landslideguard.db` or the Docker runtime `data/landslideguard.db`.

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
| `JWT_SECRET` | insecure dev value | **must** be overridden when `ENVIRONMENT=production` |
| `DEMO_ADMIN_PASSWORD` | `admin123` | **must** be changed when `ENVIRONMENT=production` |
| `ENVIRONMENT` | `development` | `production` enables the fail-fast checks above |
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
GET  /api/admin/stats            GET  /api/admin/alerts
POST /api/admin/upload-dataset   POST /api/admin/retrain
POST /api/admin/trigger-predict  GET  /api/admin/settings
```

That is 25 API operations plus a `GET /` service banner.

Routes under `/api/admin/*` require `Authorization: Bearer <token>` **and** the
`admin` role; other routes are public.

## Demo Credentials

```
email:    admin@landslideguard.ai
password: admin123
```

Seeded on an empty database, bcrypt-hashed, JWT-authenticated. Override with
`DEMO_ADMIN_EMAIL` / `DEMO_ADMIN_PASSWORD`.

> **Note:** `POST /api/auth/register` creates accounts with the least-privileged
> `viewer` role. Self-service signup can never mint an admin — admin accounts are
> created by the startup seed or by promoting a user in the database.

## Verifying the Install

```bash
# Backend health + model + DB status
curl http://localhost:8000/api/health
```

The Docker stack has been validated end-to-end with an automated suite
(auth, role enforcement, risk summary, alerts workflow, analytics, prediction
monotonicity across LOW→CRITICAL, admin retrain, restart-safe seeding,
read-path write elimination, and CORS).

## Screenshots

> Add `docs/screenshots/*.png` here. Quick reference for judges:
> Landing → Dashboard → Risk Map → Prediction → Alerts → Analytics → Admin.

*(Screenshots placeholder — capture from the running app.)*

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

*Project for Smart India Hackathon 2026 · SIH26001 · MDoNER.*