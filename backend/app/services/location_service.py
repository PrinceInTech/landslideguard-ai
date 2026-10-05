"""Location + environmental data service.

Combines monitoring locations, demo/live weather, and the ML model to compute
live risk levels for every monitored location.
"""
import csv
import json

from sqlalchemy.orm import Session

from app.config import settings
from app.models import EnvironmentalData, Location, utcnow
from app.ml import predictor
from app.services.alert_engine import create_alert, notify_alert
from app.services.data_provider import weather_provider


def load_monitoring_locations():
    """Load seed monitoring locations from CSV (returns list of dicts)."""
    rows = []
    path = settings.LOCATIONS_DATA
    if not path.exists():
        return rows
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "name": row["name"],
                "state": row["state"],
                "district": row["district"],
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "elevation": float(row["elevation"]),
                "slope": float(row["slope"]),
            })
    return rows


def seed_locations(db: Session):
    """Create DB rows for any monitoring locations not yet present."""
    if db.query(Location).count() > 0:
        return
    for loc in load_monitoring_locations():
        db.add(Location(**loc, risk_score=0, risk_level="LOW", confidence=0))
    db.commit()


def refresh_risks(db: Session, persist_history: bool = True):
    """Recompute weather + risk for all locations and persist current state.

    Args:
        persist_history: when True, append an EnvironmentalData snapshot per
            location (used at startup and on explicit "trigger prediction").
            Read endpoints pass False so that simply loading the page does not
            grow the database on every request.

    Returns (locations_with_env, alerts_created).
    """
    locations = db.query(Location).all()
    alerts_created = []
    result_locations = []

    for loc in locations:
        base = {
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "name": loc.name,
            "state": loc.state,
            "elevation": loc.elevation,
            "slope": loc.slope,
        }
        env = weather_provider.get_conditions(base)

        # Persist environmental snapshot (only on explicit refreshes)
        if persist_history:
            db.add(EnvironmentalData(
                location_id=loc.id,
                rainfall=env.get("rainfall", 0),
                soil_moisture=env.get("soil_moisture", 0),
                temperature=env.get("temperature", 0),
                humidity=env.get("humidity", 0),
                wind_speed=env.get("wind_speed", 0),
                pressure=env.get("pressure", 0),
            ))

        features = {
            "rainfall": env.get("rainfall", 0),
            "rainfall_intensity": env.get("rainfall_intensity", env.get("rainfall", 0) * 0.2),
            "soil_moisture": env.get("soil_moisture", 0),
            "temperature": env.get("temperature", 20),
            "humidity": env.get("humidity", 60),
            "elevation": loc.elevation,
            "slope": loc.slope,
            "historical_occurrence": 1 if (loc.slope >= 32 or loc.elevation >= 1500) else 0,
            "distance_to_drain": 2.0,
        }
        result = predictor.predict(features)
        env["risk_score"] = result["risk_score"]
        env["risk_level"] = result["risk_level"]
        env["confidence"] = result["confidence"]

        prev_level = loc.risk_level
        loc.risk_score = result["risk_score"]
        loc.risk_level = result["risk_level"]
        loc.confidence = result["confidence"]
        loc.last_updated = utcnow()

        # Generate alert if there is an escalation to HIGH/CRITICAL
        if result["risk_level"] in ("HIGH", "CRITICAL") and prev_level not in ("HIGH", "CRITICAL"):
            alert = create_alert(db, loc, result)
            alerts_created.append(alert)

        result_locations.append((loc, env))

    db.commit()

    if persist_history:
        prune_environment_history(db)

    return result_locations, alerts_created


# Keep the environmental history table bounded so long-running deployments do
# not grow without limit.
ENV_HISTORY_RETENTION = 240


def prune_environment_history(db: Session, keep: int = ENV_HISTORY_RETENTION):
    """Delete environmental snapshots beyond the newest `keep` rows per location."""
    location_ids = [row[0] for row in db.query(EnvironmentalData.location_id)
                    .distinct().all()]
    for location_id in location_ids:
        total = db.query(EnvironmentalData)\
            .filter(EnvironmentalData.location_id == location_id).count()
        if total <= keep:
            continue
        cutoff = (db.query(EnvironmentalData.id)
                  .filter(EnvironmentalData.location_id == location_id)
                  .order_by(EnvironmentalData.timestamp.desc(), EnvironmentalData.id.desc())
                  .offset(keep).limit(1)
                  .scalar())
        if cutoff is None:
            continue
        stale = (db.query(EnvironmentalData)
                 .filter(EnvironmentalData.location_id == location_id,
                         EnvironmentalData.id <= cutoff)
                 .delete(synchronize_session=False))
    db.commit()


def location_to_dict(loc: Location, env: dict = None) -> dict:
    data = {
        "id": loc.id,
        "name": loc.name,
        "state": loc.state,
        "district": loc.district,
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "elevation": loc.elevation,
        "slope": loc.slope,
        "risk_score": loc.risk_score,
        "risk_level": loc.risk_level,
        "confidence": loc.confidence,
        "last_updated": loc.last_updated,
    }
    if env:
        data["environmental"] = env
    return data
