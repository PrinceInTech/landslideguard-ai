# LandslideGuard AI — Backend

FastAPI backend for the AI-based early warning and landslide risk monitoring system.

## Quick Start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# From the project root (landslideguard-ai/) so paths resolve:
cd ..
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
```

The server auto-seeds 30 monitoring locations and computes initial risk levels
on startup. API docs: http://127.0.0.1:8001/docs

## Structure

```
backend/app/
  api/        FastAPI routers (auth, locations, prediction, alerts, analytics, admin)
  models/     SQLAlchemy ORM models
  schemas/    Pydantic validation schemas
  services/   business logic (auth, data provider, location service, alert engine, analytics)
  ml/         ML prediction service (loads trained model, explainability)
  database/   SQLAlchemy session + engine
  config.py   environment-based configuration
  main.py     application entrypoint
```

## Data provider abstraction

`services/data_provider.py` serves weather two ways:

- **DEMO** (default): deterministic per 15-minute window, so judges can reproduce
  results while conditions still evolve over time. Clearly labelled `data_source=DEMO`.
- **LIVE**: if `OPENWEATHER_API_KEY` is set and `DATA_MODE=LIVE`, real weather is used.
  On any error the app **falls back to DEMO** and never crashes.

Switch demo vs live per endpoint response with `data_source`.

## Keys / environment

All config via `.env` at the project root (see `.env.example`). No secrets are
hardcoded.