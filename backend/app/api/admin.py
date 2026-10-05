"""Admin routes - location CRUD, dataset upload, model retrain trigger, stats."""
import os
import subprocess
import sys

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.auth import get_current_admin
from app.database.session import get_db, SessionLocal
from app.ml import predictor
from app.models import Alert, Location, Prediction, User
from app.services.alert_engine import alert_to_dict
from app.config import PROJECT_ROOT, settings

router = APIRouter(prefix="/api/admin", tags=["admin"])

UPLOAD_DIR = settings.DATA_DIR
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.get("/stats")
def admin_stats(db: Session = Depends(get_db), _: object = Depends(get_current_admin)):
    n_locations = db.query(Location).count()
    n_alerts = db.query(Alert).count()
    n_predictions = db.query(Prediction).count()
    n_users = db.query(User).count()
    model, _bundle = predictor.get_model()
    return {
        "total_locations": n_locations,
        "total_alerts": n_alerts,
        "total_predictions": n_predictions,
        "total_users": n_users,
        "model_loaded": model is not None,
        "data_mode": settings.DATA_MODE,
    }


@router.get("/alerts")
def admin_alerts(db: Session = Depends(get_db), _: object = Depends(get_current_admin)):
    alerts = db.query(Alert).order_by(Alert.created_at.desc()).limit(200).all()
    return [alert_to_dict(a, db) for a in alerts]


@router.post("/upload-dataset")
async def upload_dataset(file: UploadFile = File(...), _: object = Depends(get_current_admin)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV datasets are supported")
    dest = settings.HISTORICAL_DATA
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)
    return {"message": f"Dataset uploaded to {dest.name}", "rows": content.count(b"\n")}


@router.post("/retrain")
def retrain_model(_: object = Depends(get_current_admin)):
    train_script = settings.TRAIN_SCRIPT
    if not train_script.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Training script not found at {train_script}. "
                   "The ml/ directory must be deployed alongside the backend "
                   "(set TRAIN_SCRIPT to override).",
        )
    env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT)}
    try:
        proc = subprocess.run(
            [sys.executable, str(train_script)],
            capture_output=True, text=True, timeout=900, env=env,
            cwd=str(PROJECT_ROOT),
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Training timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {e}")

    if proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Training failed (exit {proc.returncode}): {(proc.stderr or proc.stdout)[-2000:]}",
        )

    # Clear the model cache so the newly trained model is picked up on next call.
    predictor._model_cache["loaded"] = False
    model, _bundle = predictor.get_model()
    if model is None:
        raise HTTPException(
            status_code=500,
            detail="Training completed but the resulting model could not be loaded.",
        )
    return {"message": "Model retrained successfully", "output": proc.stdout[-500:]}


@router.post("/trigger-predict")
def trigger_prediction(_: object = Depends(get_current_admin), db: Session = Depends(get_db)):
    from app.services.location_service import refresh_risks
    # Explicit refresh: recompute every location and append history snapshots.
    locations, alerts = refresh_risks(db, persist_history=True)
    return {
        "message": f"Prediction triggered for {len(locations)} locations",
        "alerts_created": len(alerts),
    }


@router.get("/settings")
def admin_settings(_: object = Depends(get_current_admin)):
    return {
        "data_mode": settings.DATA_MODE,
        "weather_api_configured": bool(settings.OPENWEATHER_API_KEY),
        "database": settings.DATABASE_URL,
        "model_path": str(settings.MODEL_PATH),
        "model_present": settings.MODEL_PATH.exists(),
        "project_root": str(PROJECT_ROOT),
        "train_script": str(settings.TRAIN_SCRIPT),
        "train_script_present": settings.TRAIN_SCRIPT.exists(),
        "environment": settings.ENVIRONMENT,
    }