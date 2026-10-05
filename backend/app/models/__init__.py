"""SQLAlchemy ORM models.

Schema follows the SIH design:
    Users, Locations, EnvironmentalData, Predictions, Alerts
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)

from app.database.session import Base


def utcnow():
    """Naive UTC timestamp.

    All DateTime columns are timezone-naive, so every writer must use this
    helper to keep values comparable (mixing aware and naive datetimes breaks
    ordering and filtering on some backends).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    # Least privilege: a row must be *explicitly* promoted to admin. A default of
    # "admin" here would silently escalate any user created without a role.
    role = Column(String, default="viewer", nullable=False)
    created_at = Column(DateTime, default=utcnow)


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    state = Column(String, nullable=False)
    district = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    elevation = Column(Float, default=0)
    slope = Column(Float, default=0)
    risk_score = Column(Float, default=0)
    risk_level = Column(String, default="LOW")
    confidence = Column(Float, default=0)
    last_updated = Column(DateTime, default=utcnow)


class EnvironmentalData(Base):
    __tablename__ = "environmental_data"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), index=True)
    rainfall = Column(Float, default=0)
    soil_moisture = Column(Float, default=0)
    temperature = Column(Float, default=0)
    humidity = Column(Float, default=0)
    wind_speed = Column(Float, default=0)
    pressure = Column(Float, default=0)
    timestamp = Column(DateTime, default=utcnow)


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), index=True)
    risk_score = Column(Float, default=0)
    risk_level = Column(String, default="LOW")
    probability = Column(Float, default=0)
    confidence = Column(Float, default=0)
    features = Column(Text, default="{}")  # JSON string of input features
    factor_contributions = Column(Text, default="{}")
    timestamp = Column(DateTime, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), index=True)
    risk_level = Column(String, nullable=False)
    risk_score = Column(Float, default=0)
    message = Column(Text, nullable=False)
    trigger_factors = Column(Text, default="[]")  # JSON list
    status = Column(String, default="active")  # active | acknowledged | resolved
    created_at = Column(DateTime, default=utcnow)
    resolved_at = Column(DateTime, nullable=True)
