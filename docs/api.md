# API Reference

Base URL: `http://127.0.0.1:8000` (interactive docs live at `/docs` via Swagger UI).

All responses are JSON. Admin endpoints require **both**
`Authorization: Bearer <token>` **and** the `admin` role.

The full machine-readable contract is always available at `/openapi.json`.

## Public endpoints

### `GET /api/health`
System health, database and model status, and the active data mode.
```json
{
  "status": "ok",
  "app": "LandslideGuard AI",
  "version": "1.0.0",
  "database": "ok",
  "model": "ok",
  "data_mode": "DEMO",
  "time": "2026-10-05T11:28:00.545074+00:00"
}
```
`model` reports `ok` only when the trained model is loaded in memory;
`status` degrades to `degraded` when the database is unreachable.

### `GET /api/locations`
All monitored locations with current risk + environmental snapshot.
```json
[{
  "id": 1,
  "name": "Yuksom", "state": "Sikkim", "district": "West Sikkim",
  "latitude": 27.3745, "longitude": 88.2238,
  "elevation": 1780.0, "slope": 36.2,
  "risk_score": 93.0, "risk_level": "CRITICAL", "confidence": 94.3,
  "last_updated": "2026-10-05T11:28:00+00:00",
  "environmental": {
    "temperature": 18.4, "humidity": 88.1, "pressure": 1004.2,
    "wind_speed": 9.3, "rainfall": 50.6, "rainfall_intensity": 12.7,
    "soil_moisture": 47.9, "weather_main": "Rain",
    "season": "monsoon", "data_source": "DEMO"
  }
}]
```

Reading this endpoint refreshes in-memory risk display data but does **not**
insert new environmental snapshots or predictions.

### `GET /api/locations/{location_id}`
Single location, `404` if missing.

### `GET /api/environmental/{location_id}`
Just the environmental block for one location (no risk fields).

### `GET /api/risk-summary`
Aggregated risk overview.
```json
{
  "total_locations": 30,
  "risk_counts": { "LOW": 9, "MODERATE": 8, "HIGH": 5, "CRITICAL": 8 },
  "overall_risk_level": "CRITICAL",
  "overall_avg_score": 50.2,
  "avg_confidence": 75.6,
  "highest_risk_location": {
    "name": "Cherrapunji", "state": "Meghalaya",
    "risk_score": 89.3, "risk_level": "CRITICAL"
  },
  "data_source": "DEMO",
  "data_mode_configured": "LIVE",
  "live_degraded": true
}
```
Counts are weather-dependent (DEMO weather is deterministic per 15-minute
window), so the numbers above will differ from yours.

The three source fields are deliberately distinct:

| Field | Meaning |
| ----- | ------- |
| `data_mode_configured` | what `DATA_MODE` + the API key imply (`LIVE` only if both are set) |
| `data_source` | the source actually served for the most recent readings |
| `live_degraded` | `true` when `LIVE` is configured but the provider fell back to DEMO |

`live_degraded` is the field to check before trusting a `LIVE` deployment: a
network or quota failure at OpenWeatherMap silently degrades to simulated
readings, and this flag is how that state becomes visible instead of a stale
`DEMO` string. The UI renders it as `LIVE UNAVAILABLE — DEMO DATA`.

### `POST /api/predict`
Run the ML model on given environmental features. Returns score, level,
probability, confidence, contributing factors and recommended actions.
```json
{
  "location": "Yuksom", "rainfall": 200, "soil_moisture": 92,
  "temperature": 20, "humidity": 95, "elevation": 1780, "slope": 36,
  "land_cover": "Dense Forest", "soil_type": "Clay Loam",
  "rock_type": "Mixed", "historical_occurrence": 1
}
```
Response:
```json
{
  "risk_score": 99.6, "risk_level": "CRITICAL", "probability": 0.96,
  "confidence": 94.8,
  "contributing_factors": [ { "factor": "Rainfall", "value": 200, "contribution": 100.0 } ],
  "recommended_actions": ["ISSUE EMERGENCY ALERT — initiate evacuation..."],
  "model": "RandomForestClassifier (trained on DEMO data)",
  "data_source": "DEMO",
  "prediction_mode": "demo"
}
```
Numeric inputs are range-validated; out-of-range values return `422`.

`prediction_mode` is `"demo"` on every response from this route, matching the
DEMO-trained model; it never indicates production readiness.

### `POST /api/predict/location/{location_id}`
Predict using the stored location + live/demo environmental data. Also persists
a prediction row when the location is known.

### `GET /api/predictions`
Recent prediction history.

### `GET /api/alerts`
List alerts. Query params: `state`, `risk_level`, `status`, `search`.

### `POST /api/alerts`
Create an alert manually.

### `PUT /api/alerts/{alert_id}`
Update the alert status workflow: `active` → `acknowledged` → `resolved`.
Setting `resolved` stamps `resolved_at`. An unknown status returns `422`.

### `GET /api/analytics`
Historical + current analytics:
`states`, `monthly_trends`, `rainfall_correlation`, `risk_distribution`,
`high_risk_locations`, `incidents_by_state`.

### `GET /api/weather/{location_name}`
Current conditions for a location (LIVE or DEMO, reported in `data_source`).

### `POST /api/extract`
Run evidence-gated temporal feature extraction over a **committed** real
acquisition (see `docs/features.md`). Requires a valid JWT. The request names a
source, a point, a prediction cutoff, the features to compute and an
availability policy; the service resolves the matching acquisition record from
the committed manifest and evaluates it — it never downloads data.

```json
{
  "source": "chirps",
  "position": { "latitude": 28.02, "longitude": 90.03 },
  "prediction_cutoff_utc": "2026-10-08T12:00:00Z",
  "requested_features": ["precipitation_daily_mm"],
  "availability_policy": "research_replay"
}
```

The response is a `FeatureExtractionResult` (`contract_version`, resolved
`artifact_sha256`, `acquisition_record_id`, and one entry per requested
feature). Each feature carries a status — `valid`, `missing`,
`insufficient_temporal_coverage` or `rejected_leakage` — plus provenance. A
policy rejection is **not** an error: it returns `200` with the honest status
and a `null` value, so callers can tell "the evidence does not permit this
value" from "the request was malformed".

Failure mapping:
- `401` — missing or invalid token.
- `409` — the resolved artifact is absent or unreadable, or no real acquisition
  exists for the source. The detail never includes a server path.
- `422` — a contract violation (unsupported source, point outside the study
  region, unknown feature name, unrecognised `artifact_sha256`, or a malformed
  artifact). Absolute paths are redacted.

### `POST /api/provenance/validate`
Provenance-gated **prediction-input validation**. Requires a valid JWT (any
role). It takes the **same request** as `POST /api/extract` (source, position,
`prediction_cutoff_utc`, `requested_features`, `availability_policy`) and reuses
the same protected extraction pipeline unchanged, but returns an explicit
*validation report* instead of a prediction.

```json
{
  "source": "chirps",
  "position": { "latitude": 28.02, "longitude": 90.03 },
  "prediction_cutoff_utc": "2026-10-08T12:00:00Z",
  "requested_features": ["precipitation_daily_mm"],
  "availability_policy": "research_replay"
}
```

The response is a `ProvenanceGateResponse`. It is **never** a prediction — the
DEMO model is deliberately not invoked:

- `prediction_mode` = `"provenance_gated_validation"`, `is_prediction` = `false`,
  `model_invoked` = `false`, `model` = `"none (DEMO model deliberately not invoked)"`.
- `model_compatibility` = `"incompatible"` with a `model_compatibility_reason`;
  the REAL feature vocabulary cannot feed the DEMO model.
- `disclaimer` states that provenance-valid inputs are not evidence of accuracy.
- `production_readiness` = `"NO-GO"` (the frozen subsystem stance, independent of
  the per-request `availability_policy`).

Gate decision fields:

| Field | Meaning |
| ----- | ------- |
| `availability_policy` | echo of the requested policy |
| `verdict` | `accepted_for_research`, `accepted_for_production`, or `rejected` |
| `verdict_reason` | why that verdict was reached |
| `checksum_verification` | always `"verified"` for the resolved artifact |
| `temporal_eligibility` | `eligible` or `rejected` for the cutoff |
| `accepted_features` | names of features that passed every gate |
| `rejected_features` | `ProvenanceGateFeatureDecision` entries with honest reasons |
| `feature_decisions` | every requested feature's decision + traceability |
| `result` | the full `FeatureExtractionResult`, unchanged (see `/api/extract`) |

A rejection is **not** an error: it returns `200` with the per-feature reasons and
a `null` value for each rejected feature. No value is ever fabricated. Failure
mapping matches `/api/extract`:
- `401` — missing or invalid token.
- `409` — the resolved artifact is absent or unreadable, or no real acquisition
  exists for the source. The detail never includes a server path.
- `422` — a contract violation (unsupported source, point outside the study
  region, unknown feature name, unrecognised `artifact_sha256`, or a malformed
  artifact). Absolute paths are redacted.

### `GET /`
Service banner (name + version).

## Auth

### `POST /api/auth/register`
`{ name, email, password }` → `{ access_token, user }`

New accounts are always created with the **`viewer`** role — public signup can
never mint an administrator. Admin accounts come from the startup seed or a
manual promotion in the database. Re-registering an existing email returns `400`.

### `POST /api/auth/login`
`{ email, password }` → `{ access_token, user }`
Demo admin: `admin@landslideguard.ai` / `admin123`
Wrong email or password returns `401`.

### `GET /api/auth/me`
Returns the current user from a valid bearer token. Missing, invalid or expired
token → `401`.

## Admin (JWT + `admin` role required)

Anonymous → `401`; authenticated non-admin → `403`.

| Method | Route                        | Purpose                            |
| ------ | ---------------------------- | ---------------------------------- |
| GET    | `/api/admin/stats`           | System statistics + model status   |
| GET    | `/api/admin/alerts`          | All alerts (admin view)            |
| GET    | `/api/admin/settings`        | Config + resolved paths, model/train presence |
| POST   | `/api/admin/upload-dataset`  | Upload CSV dataset (multipart)     |
| POST   | `/api/admin/retrain`         | Re-run `ml/train.py`, then hot-reload the model |
| POST   | `/api/admin/trigger-predict` | Recompute risk for all locations   |

`retrain` runs the training pipeline in a subprocess, so it can take around a
minute; it returns `500` with a readable `detail` if the `ml/` directory was not
deployed alongside the backend.

`upload-dataset` accepts `.csv` only, rejects empty files with `400`, and caps
the body at `MAX_UPLOAD_MB` (default 50) with `413`. The body is read in 1 MB
chunks and the new file is written to a temporary path then swapped in, so an
aborted upload cannot truncate the last known-good dataset. nginx enforces the
same ceiling via `client_max_body_size` so oversized bodies are refused at the
proxy instead of reaching the app.

## Location CRUD

`POST /api/locations`, `PUT /api/locations/{location_id}`,
`DELETE /api/locations/{location_id}` — same shape as the location object,
validated with Pydantic. `PUT` accepts partial updates and applies the same
bounds as create, so an out-of-range latitude or a negative slope returns `422`.

`DELETE` removes the location's dependent environmental history, predictions,
and alerts in the same transaction, then returns `204`. The cleanup is
explicit because SQLite here runs with `PRAGMA foreign_keys` **off** —
SQLAlchemy does not enable it and the models define no ORM relationships. With
enforcement off the bare `DELETE` would still succeed, so the real risk is not
an error but silent orphans: rows in `environmental_data`, `predictions` and
`alerts` left pointing at a location that no longer exists. A delete the
database rejects for any other reason returns `409` with a readable `detail`
rather than a stack trace; that branch is defensive and is not reachable via a
foreign key in the current configuration.

## Error handling

Standard FastAPI semantics:

- `400` duplicate email on register
- `401` invalid/expired token, or bad credentials
- `403` authenticated but not an admin
- `404` missing resource
- `409` delete rejected by the database (defensive branch; see Location CRUD)
- `413` upload exceeds `MAX_UPLOAD_MB`
- `422` Pydantic validation failure (e.g. out-of-range features, bad alert status)
- `500` unexpected failure, with a readable `detail`
- Missing model / weather API never crash — the app falls back to a deterministic
  rule-based predictor or DEMO weather and reports `data_source` and `model`.

## Authorization model

| Surface | Requirement |
| ------- | ----------- |
| Read endpoints (`GET /api/locations`, `/risk-summary`, `/analytics`, `/alerts`, `/predictions`) | none |
| Write endpoints (`POST`/`PUT`/`DELETE` on locations and alerts; `POST /api/predict` and `POST /api/predict/location/{id}`; `POST /api/extract` and `POST /api/provenance/validate`) | valid JWT (any role) |
| `/api/admin/**` | valid JWT **and** `role == "admin"` |
| Self-registration | always creates `role == "viewer"` |

Anonymous or invalid-token requests to a write endpoint return `401`. Any
authenticated user — `viewer` or `admin` — may perform these writes, matching
the UI, which shows the location/alert/prediction controls to every signed-in
user and only hides the Admin area from non-admins. The seeded demo admin
(`DEMO_ADMIN_EMAIL`) is the only account that starts as an admin; `viewer`
cannot reach `/api/admin/**`.

*Previously* (through Phase 3.7) location, alert and prediction writes were
unauthenticated; Phase 3.8 added a `get_current_user` dependency to every
mutating route.
