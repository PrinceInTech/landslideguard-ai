"""Alert engine.

Converts risk escalations into structured alerts (warning / emergency) and
provides a notification abstraction that can later be wired to SMS/WhatsApp.
"""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Alert, Location

ACTIONS = {
    "MODERATE": "Increase monitoring frequency to every 6 hours.",
    "HIGH": "Issue warning to district disaster management authority; pre-position response teams.",
    "CRITICAL": "EVACUATE vulnerable zones and initiate emergency monitoring immediately.",
}


def build_message(location: Location, result: dict) -> str:
    level = result["risk_level"]
    factors = ", ".join(c["factor"] for c in result["contributing_factors"][:4])
    if level == "CRITICAL":
        return (
            f"CRITICAL LANDSLIDE WARNING - {location.name}, {location.state}. "
            f"Risk score {result['risk_score']:.0f}%. Main factors: {factors}. "
            f"Action: {ACTIONS['CRITICAL']}"
        )
    if level == "HIGH":
        return (
            f"HIGH RISK ALERT - {location.name}, {location.state}. "
            f"Risk score {result['risk_score']:.0f}%. Main factors: {factors}. "
            f"Action: {ACTIONS['HIGH']}"
        )
    return (
        f"MODERATE RISK at {location.name}, {location.state}. "
        f"Risk score {result['risk_score']:.0f}%. Action: {ACTIONS['MODERATE']}"
    )


def create_alert(db: Session, location: Location, result: dict) -> Alert:
    trigger_factors = [
        f"{c['factor']} ({c['contribution']:.0f}%)"
        for c in result["contributing_factors"][:4]
    ]
    alert = Alert(
        location_id=location.id,
        risk_level=result["risk_level"],
        risk_score=result["risk_score"],
        message=build_message(location, result),
        trigger_factors=json.dumps(trigger_factors),
        status="active",
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def alert_to_dict(alert: Alert, db: Session = None) -> dict:
    loc = None
    if db:
        loc = db.query(Location).filter(Location.id == alert.location_id).first()
    return {
        "id": alert.id,
        "location_id": alert.location_id,
        "location_name": loc.name if loc else None,
        "location_state": loc.state if loc else None,
        "risk_level": alert.risk_level,
        "risk_score": alert.risk_score,
        "message": alert.message,
        "trigger_factors": json.loads(alert.trigger_factors or "[]"),
        "status": alert.status,
        "created_at": alert.created_at,
        "resolved_at": alert.resolved_at,
    }


# ---------- Notification abstraction ----------
class NotificationChannel:
    """Base notification interface - extend for SMS/WhatsApp/Email later."""

    def send(self, recipient, subject, body) -> bool:
        raise NotImplementedError


class InAppNotification(NotificationChannel):
    """Prototype in-app/browser notification (console + returns for frontend)."""

    def send(self, recipient, subject, body) -> bool:
        # In production this would push via websocket/SSE or store for polling.
        return True


def notify_alert(alert: dict, channels=None):
    channels = channels or [InAppNotification()]
    subject = f"LandslideGuard {alert['risk_level']} Alert - {alert['location_name']}"
    body = alert["message"]
    for ch in channels:
        try:
            ch.send(recipient="authority", subject=subject, body=body)
        except Exception:
            continue
