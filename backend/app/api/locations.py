"""Location routes + risk summary."""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Alert, EnvironmentalData, Location, Prediction
from app.schemas import LocationCreate, LocationOut, LocationUpdate
from app.services.data_provider import weather_provider
from app.services.location_service import location_to_dict, refresh_risks
from app.ml import predictor
from app.risk import RISK_LEVELS

router = APIRouter(prefix="/api", tags=["locations"])

logger = logging.getLogger(__name__)


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

    # Dependent rows (environmental history, predictions, alerts) carry a
    # `location_id` column referencing this row. SQLite here runs with
    # `PRAGMA foreign_keys` OFF — SQLAlchemy does not enable it and the models
    # define no ORM relationships — so nothing raises today: a bare
    # `db.delete(loc)` would succeed and silently leave orphaned dependents.
    # Remove them explicitly so the deletion is consistent rather than leaving
    # rows that point at a location that no longer exists.
    name = loc.name
    db.query(EnvironmentalData).filter(EnvironmentalData.location_id == loc.id).delete(
        synchronize_session=False
    )
    db.query(Prediction).filter(Prediction.location_id == loc.id).delete(
        synchronize_session=False
    )
    db.query(Alert).filter(Alert.location_id == loc.id).delete(synchronize_session=False)
    db.delete(loc)
    # Defensive: with SQLite FK enforcement off this branch is not reachable
    # via a foreign key today, but a UNIQUE/NOT NULL violation, a future
    # enabled `PRAGMA foreign_keys`, or another engine must not surface as a
    # bare 500.
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.exception("Failed to delete location id=%s name=%r", location_id, name)
        raise HTTPException(
            status_code=409,
            detail="The location could not be deleted because other records depend on it",
        ) from exc


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
        "data_mode_configured": weather_provider.configured_source,
        "live_degraded": weather_provider.degraded,
    }


def _overall(counts):
    """Roll individual locations up to the worst severity present."""
    for level, _upper in reversed(RISK_LEVELS):
        if counts.get(level, 0) > 0:
            return level
    return RISK_LEVELS[0][0]
