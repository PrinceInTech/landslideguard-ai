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
 ├─ components/ → reusable UI (map, gauge, badges, charts, states)
 ├─ hooks/      → API fetching / polling / auth
 ├─ services/   → axios instance with JWT interceptor
 └─ utils/      → risk level metadata + formatting
```

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