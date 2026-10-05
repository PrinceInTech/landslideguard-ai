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
  "data_source": "DEMO"
}
```
Counts are weather-dependent (DEMO weather is deterministic per 15-minute
window), so the numbers above will differ from yours.

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
  "data_source": "DEMO"
}
```
Numeric inputs are range-validated; out-of-range values return `422`.

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

## Location CRUD

`POST /api/locations`, `PUT /api/locations/{location_id}`,
`DELETE /api/locations/{location_id}` — same shape as the location object,
validated with Pydantic.

## Error handling

Standard FastAPI semantics:

- `400` duplicate email on register
- `401` invalid/expired token, or bad credentials
- `403` authenticated but not an admin
- `404` missing resource
- `422` Pydantic validation failure (e.g. out-of-range features, bad alert status)
- `500` unexpected failure, with a readable `detail`
- Missing model / weather API never crash — the app falls back to a deterministic
  rule-based predictor or DEMO weather and reports `data_source` and `model`.