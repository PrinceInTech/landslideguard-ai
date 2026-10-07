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

# The dataset upload target lives under DATA_DIR; make sure it exists before
# the first upload rather than relying on the repo shipping it.
os.makedirs(settings.DATA_DIR, exist_ok=True)

_UPLOAD_CHUNK_BYTES = 1024 * 1024


def _row_count(content: bytes) -> int:
    """Number of data rows (every line after the header) in a CSV body.

    `content.count(b"\\n") - 1` under-reports when the file has no trailing
    newline and returns -1 for a header-only body, so count lines explicitly.
    """
    if not content:
        return 0
    lines = content.count(b"\n") + (0 if content.endswith(b"\n") else 1)
    return max(0, lines - 1)


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

    # Read in bounded chunks and abort as soon as the limit is exceeded, so a
    # large upload cannot exhaust memory before the size check runs.
    limit = settings.MAX_UPLOAD_BYTES
    size = 0
    chunks = []
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise HTTPException(
                status_code=413,
                detail=f"Dataset exceeds the {limit // (1024 * 1024)} MB limit",
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    if not content.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    dest = settings.HISTORICAL_DATA
    # Write to a temporary file then swap, so a failure mid-write cannot leave a
    # truncated dataset in place of the last known-good one.
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        tmp.write_bytes(content)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)

    return {"message": f"Dataset uploaded to {dest.name}", "rows": _row_count(content)}


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
