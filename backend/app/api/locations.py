"""Location routes + risk summary."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Location
from app.schemas import LocationCreate, LocationOut, LocationUpdate
from app.services.data_provider import weather_provider
from app.services.location_service import location_to_dict, refresh_risks
from app.ml import predictor

router = APIRouter(prefix="/api", tags=["locations"])


def _with_env(loc: Location, db: Session) -> dict:
    base = {
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "name": loc.name,
        "state": loc.state,
        "elevation": loc.elevation,
        "slope": loc.slope,
    }
    env = weather_provider.get_conditions(base)
    return location_to_dict(loc, env)


@router.get("/locations")
def list_locations(db: Session = Depends(get_db)):
    # Recompute risks from current (demo/live) conditions so the UI always shows
    # live values, but do NOT append environmental history rows on a read.
    results, _alerts = refresh_risks(db, persist_history=False)
    return [location_to_dict(loc, env) for loc, env in results]


@router.get("/locations/{location_id}", response_model=LocationOut)
def get_location(location_id: int, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    return LocationOut(**location_to_dict(loc, {
        **weather_provider.get_conditions({
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "name": loc.name,
            "state": loc.state,
            "elevation": loc.elevation,
            "slope": loc.slope,
        })
    }))


@router.post("/locations", response_model=LocationOut)
def create_location(payload: LocationCreate, db: Session = Depends(get_db)):
    loc = Location(**payload.model_dump())
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return LocationOut(**location_to_dict(loc, weather_provider.get_conditions({
        "latitude": loc.latitude, "longitude": loc.longitude, "name": loc.name,
        "state": loc.state, "elevation": loc.elevation, "slope": loc.slope,
    })))


@router.put("/locations/{location_id}", response_model=LocationOut)
def update_location(location_id: int, payload: LocationUpdate, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(loc, field, value)
    db.commit()
    db.refresh(loc)
    return LocationOut(**location_to_dict(loc, weather_provider.get_conditions({
        "latitude": loc.latitude, "longitude": loc.longitude, "name": loc.name,
        "state": loc.state, "elevation": loc.elevation, "slope": loc.slope,
    })))


@router.delete("/locations/{location_id}", status_code=204)
def delete_location(location_id: int, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    db.delete(loc)
    db.commit()


@router.get("/risk-summary")
def risk_summary(db: Session = Depends(get_db)):
    locations = db.query(Location).all()
    counts = {"LOW": 0, "MODERATE": 0, "HIGH": 0, "CRITICAL": 0}
    max_score = 0
    max_loc = None
    total_conf = 0
    for loc in locations:
        counts[loc.risk_level] = counts.get(loc.risk_level, 0) + 1
        if loc.risk_score > max_score:
            max_score = loc.risk_score
            max_loc = loc
        total_conf += loc.confidence
    n = len(locations) or 1
    return {
        "total_locations": len(locations),
        "risk_counts": counts,
        "overall_risk_level": _overall(counts),
        "overall_avg_score": round(sum(l.risk_score for l in locations) / n, 1) if locations else 0,
        "avg_confidence": round(total_conf / n, 1) if locations else 0,
        "highest_risk_location": {
            "name": max_loc.name, "state": max_loc.state,
            "risk_score": max_loc.risk_score, "risk_level": max_loc.risk_level,
        } if max_loc else None,
        "data_source": weather_provider.source,
    }


def _overall(counts):
    if counts.get("CRITICAL", 0) > 0:
        return "CRITICAL"
    if counts.get("HIGH", 0) > 0:
        return "HIGH"
    if counts.get("MODERATE", 0) > 0:
        return "MODERATE"
    return "LOW"