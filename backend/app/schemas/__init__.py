"""Pydantic request/response schemas with validation."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------- Risk helpers ----------
def classify_risk(score: float) -> str:
    score = max(0.0, min(100.0, score))
    if score <= 30:
        return "LOW"
    if score <= 60:
        return "MODERATE"
    if score <= 80:
        return "HIGH"
    return "CRITICAL"


# ---------- Auth ----------
class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Locations ----------
class LocationBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    state: str = Field(min_length=1, max_length=60)
    district: str = Field(min_length=1, max_length=60)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    elevation: float = Field(default=0, ge=0, le=9000)
    slope: float = Field(default=0, ge=0, le=90)


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    elevation: Optional[float] = None
    slope: Optional[float] = None


class LocationOut(LocationBase):
    id: int
    risk_score: float
    risk_level: str
    confidence: float
    last_updated: Optional[datetime] = None
    environmental: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


# ---------- Prediction ----------
class PredictionRequest(BaseModel):
    location: Optional[str] = None
    rainfall: float = Field(ge=0, le=500)
    soil_moisture: float = Field(ge=0, le=100)
    temperature: float = Field(ge=-20, le=50)
    humidity: float = Field(ge=0, le=100)
    elevation: float = Field(ge=0, le=9000)
    slope: float = Field(ge=0, le=90)
    rainfall_intensity: Optional[float] = Field(default=None, ge=0, le=200)
    land_cover: Optional[str] = Field(default="Dense Forest")
    soil_type: Optional[str] = Field(default="Clay Loam")
    rock_type: Optional[str] = Field(default="Mixed")
    historical_occurrence: Optional[int] = Field(default=0, ge=0, le=1)
    distance_to_drain: Optional[float] = Field(default=2.0, ge=0)

    @field_validator("land_cover", "soil_type", "rock_type", mode="before")
    @classmethod
    def stringify(cls, v):
        return str(v) if v is not None else v


class PredictionResponse(BaseModel):
    risk_score: float
    risk_level: str
    probability: float
    confidence: float
    contributing_factors: List[dict]
    recommended_actions: List[str]
    model: str
    data_source: str


# ---------- Alerts ----------
class AlertCreate(BaseModel):
    location_id: int
    risk_level: str
    risk_score: float = 0
    message: str
    trigger_factors: List[str] = Field(default_factory=list)
    status: str = Field(default="active")


class AlertUpdate(BaseModel):
    status: Optional[str] = Field(default=None, pattern="^(active|acknowledged|resolved)$")


class AlertOut(BaseModel):
    id: int
    location_id: int
    location_name: Optional[str] = None
    location_state: Optional[str] = None
    risk_level: str
    risk_score: float
    message: str
    trigger_factors: List[str] = Field(default_factory=list)
    status: str
    created_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- Analytics ----------
class AnalyticsOut(BaseModel):
    states: List[dict]
    monthly_trends: List[dict]
    rainfall_correlation: float
    risk_distribution: List[dict]
    high_risk_locations: List[dict]
    incidents_by_state: List[dict]
