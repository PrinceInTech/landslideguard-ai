"""Prediction routes - calls the real ML model."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.ml import predictor
from app.models import Location, Prediction
from app.schemas import PredictionRequest, PredictionResponse
from app.services.data_provider import weather_provider
import json as _json

router = APIRouter(prefix="/api", tags=["prediction"])


@router.post("/predict", response_model=PredictionResponse)
def predict(payload: PredictionRequest, db: Session = Depends(get_db)):
    features = payload.model_dump()
    result = predictor.predict(features)

    # Persist prediction if a location matches
    loc = None
    if payload.location:
        loc = db.query(Location).filter(Location.name.ilike(f"%{payload.location}%")).first()
    if loc:
        db.add(Prediction(
            location_id=loc.id,
            risk_score=result["risk_score"],
            risk_level=result["risk_level"],
            probability=result["probability"],
            confidence=result["confidence"],
            features=_json.dumps(features),
            factor_contributions=_json.dumps(result["contributing_factors"]),
        ))
        loc.risk_score = result["risk_score"]
        loc.risk_level = result["risk_level"]
        loc.confidence = result["confidence"]
        db.commit()

    return PredictionResponse(**result)


@router.get("/predictions")
def list_predictions(db: Session = Depends(get_db)):
    rows = db.query(Prediction).order_by(Prediction.timestamp.desc()).limit(50).all()
    return [{
        "id": r.id,
        "location_id": r.location_id,
        "risk_score": r.risk_score,
        "risk_level": r.risk_level,
        "probability": r.probability,
        "confidence": r.confidence,
        "timestamp": r.timestamp,
    } for r in rows]


@router.post("/predict/location/{location_id}")
def predict_location(location_id: int, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    env = weather_provider.get_conditions({
        "latitude": loc.latitude, "longitude": loc.longitude,
        "name": loc.name, "state": loc.state,
        "elevation": loc.elevation, "slope": loc.slope,
    })
    features = {
        "location": loc.name,
        "rainfall": env.get("rainfall", 0),
        "rainfall_intensity": env.get("rainfall_intensity", env.get("rainfall", 0) * 0.2),
        "soil_moisture": env.get("soil_moisture", 0),
        "temperature": env.get("temperature", 20),
        "humidity": env.get("humidity", 60),
        "elevation": loc.elevation,
        "slope": loc.slope,
        "historical_occurrence": 1 if (loc.slope >= 32 or loc.elevation >= 1500) else 0,
    }
    return predict(PredictionRequest(**features), db)