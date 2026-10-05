"""Alert routes - list, create, update status."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Alert, Location, utcnow
from app.schemas import AlertCreate, AlertOut, AlertUpdate
from app.services.alert_engine import alert_to_dict, notify_alert

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
def list_alerts(
    state: str = None,
    risk_level: str = None,
    status: str = None,
    search: str = None,
    db: Session = Depends(get_db),
):
    query = db.query(Alert, Location).join(Location, Alert.location_id == Location.id)
    if state:
        query = query.filter(Location.state == state)
    if risk_level:
        query = query.filter(Alert.risk_level == risk_level)
    if status:
        query = query.filter(Alert.status == status)
    if search:
        query = query.filter(Location.name.ilike(f"%{search}%"))
    rows = query.order_by(Alert.created_at.desc()).limit(200).all()
    return [{
        **alert_to_dict(alert, db),
        "location_name": loc.name,
        "location_state": loc.state,
    } for alert, loc in rows]


@router.post("")
def create_alert(payload: AlertCreate, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.id == payload.location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    alert = Alert(
        location_id=payload.location_id,
        risk_level=payload.risk_level,
        risk_score=payload.risk_score,
        message=payload.message,
        trigger_factors=_json(payload.trigger_factors),
        status=payload.status,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    out = alert_to_dict(alert, db)
    notify_alert(out)
    return out


@router.put("/{alert_id}")
def update_alert(alert_id: int, payload: AlertUpdate, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if payload.status == "resolved" and alert.status != "resolved":
        alert.resolved_at = utcnow()
    alert.status = payload.status
    db.commit()
    db.refresh(alert)
    return alert_to_dict(alert, db)


def _json(items):
    from json import dumps
    return dumps(list(items))