"""FastAPI application entrypoint."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import admin, alerts, analytics, auth, locations, prediction
from app.config import settings
from app.database.session import init_db, SessionLocal
from app.services.location_service import refresh_risks, seed_locations
from app.services.auth_service import seed_default_admin
from app.ml import predictor


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        # Seed demo locations from CSV if the DB is empty
        seed_locations(db)
        # Seed the demo admin account (idempotent)
        seed_default_admin(db)
        # Refresh risks with current demo/live weather and create escalation alerts
        locations, escalations = refresh_risks(db)
        model, _bundle = predictor.get_model()
        print(
            f"[startup] {len(locations)} locations refreshed, "
            f"{len(escalations)} escalations detected, "
            f"ML model {'loaded' if model is not None else 'MISSING (rule-based fallback active)'}"
        )
    except Exception as e:
        print(f"[startup] warning: {e}")
    finally:
        db.close()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Powered Early Warning & Landslide Risk Monitoring System for Northeast India",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(locations.router)
app.include_router(prediction.router)
app.include_router(alerts.router)
app.include_router(analytics.router)
app.include_router(admin.router)


@app.get("/")
def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "message": "AI-Powered Early Warning & Landslide Risk Monitoring System for NER",
        "docs": "/docs",
    }


@app.get("/api/health")
def health():
    """Liveness/readiness probe.

    Reports real component status so orchestrators (and deploy platforms) can
    tell whether the database and ML model are actually usable.
    """
    db_status = "ok"
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception as e:
        db_status = f"degraded: {e}"

    model, _bundle = predictor.get_model()
    model_status = "ok" if model is not None else "missing"

    status = "ok" if db_status == "ok" else "degraded"
    return {
        "status": status,
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": db_status,
        "model": model_status,
        "data_mode": settings.DATA_MODE,
        "time": datetime.now(timezone.utc).isoformat(),
    }