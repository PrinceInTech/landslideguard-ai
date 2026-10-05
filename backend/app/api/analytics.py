"""Analytics + weather + misc routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import EnvironmentalData, Location
from app.services.analytics_service import get_analytics, incidents_by_state, monthly_trends, rainfall_correlation
from app.services.data_provider import weather_provider

router = APIRouter(tags=["analytics"])


@router.get("/api/analytics")
def analytics():
    try:
        return get_analytics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analytics failed: {e}")


@router.get("/api/weather/{location_name}")
def weather(location_name: str, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.name.ilike(f"%{location_name}%")).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    env = weather_provider.get_conditions({
        "latitude": loc.latitude, "longitude": loc.longitude,
        "name": loc.name, "state": loc.state,
        "elevation": loc.elevation, "slope": loc.slope,
    })
    return {"location": loc.name, "state": loc.state, **env}


@router.get("/api/environmental/{location_id}")
def environmental_history(location_id: int, limit: int = 30, db: Session = Depends(get_db)):
    rows = (
        db.query(EnvironmentalData)
        .filter(EnvironmentalData.location_id == location_id)
        .order_by(EnvironmentalData.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [{
        "timestamp": r.timestamp,
        "rainfall": r.rainfall,
        "soil_moisture": r.soil_moisture,
        "temperature": r.temperature,
        "humidity": r.humidity,
        "wind_speed": r.wind_speed,
    } for r in rows]