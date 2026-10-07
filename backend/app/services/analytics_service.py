"""Analytics service - generates statistics from historical data + current DB state."""
import pandas as pd

from app.config import settings
from app.database.session import SessionLocal
from app.models import Location
from app.risk import classify_risk

STATES = [
    "Arunachal Pradesh", "Assam", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Sikkim", "Tripura",
]


def _load_history() -> pd.DataFrame:
    path = settings.HISTORICAL_DATA
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def monthly_trends(df: pd.DataFrame) -> list:
    if df.empty:
        return []
    df = df.copy()
    df["month"] = df["timestamp"].dt.month
    grouped = df.groupby("month").agg(
        incidents=("landslide", "sum"),
        avg_rainfall=("rainfall", "mean"),
    ).reset_index()
    month_names = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
    }
    return [
        {
            "month": month_names.get(int(r.month), str(int(r.month))),
            "incidents": int(r.incidents),
            "avg_rainfall": round(float(r.avg_rainfall), 1),
        }
        for r in grouped.itertuples()
    ]


def rainfall_correlation(df: pd.DataFrame) -> float:
    if df.empty or len(df) < 5:
        return 0.0
    corr = df["rainfall"].corr(df["landslide"])
    return round(float(corr), 3)


def incidents_by_state(df: pd.DataFrame) -> list:
    if df.empty:
        return []
    grouped = df.groupby("state")["landslide"].sum().reset_index()
    return [{"state": r.state, "incidents": int(r.landslide)} for r in grouped.itertuples()]


def state_risk_summary():
    db = SessionLocal()
    locs = db.query(Location).all()
    db.close()
    summary = []
    for state in STATES:
        state_locs = [l for l in locs if l.state == state]
        if not state_locs:
            avg_score = 0
        else:
            avg_score = sum(l.risk_score for l in state_locs) / len(state_locs)
        max_loc = max(state_locs, key=lambda x: x.risk_score) if state_locs else None
        summary.append({
            "state": state,
            "avg_risk_score": round(avg_score, 1),
            "risk_level": classify_risk(avg_score),
            "locations": len(state_locs),
            "highest_risk_location": max_loc.name if max_loc else None,
            "highest_risk_score": round(max_loc.risk_score, 1) if max_loc else 0,
        })
    return summary


def risk_distribution():
    db = SessionLocal()
    locs = db.query(Location).all()
    db.close()
    counts = {"LOW": 0, "MODERATE": 0, "HIGH": 0, "CRITICAL": 0}
    for l in locs:
        counts[l.risk_level] = counts.get(l.risk_level, 0) + 1
    return [{"level": k, "count": v} for k, v in counts.items()]


def high_risk_locations():
    db = SessionLocal()
    locs = db.query(Location).order_by(Location.risk_score.desc()).limit(10).all()
    db.close()
    return [
        {
            "name": l.name,
            "state": l.state,
            "district": l.district,
            "risk_score": l.risk_score,
            "risk_level": l.risk_level,
            "latitude": l.latitude,
            "longitude": l.longitude,
        }
        for l in locs
    ]


def get_analytics() -> dict:
    df = _load_history()
    return {
        "states": state_risk_summary(),
        "monthly_trends": monthly_trends(df),
        "rainfall_correlation": rainfall_correlation(df),
        "risk_distribution": risk_distribution(),
        "high_risk_locations": high_risk_locations(),
        "incidents_by_state": incidents_by_state(df),
    }