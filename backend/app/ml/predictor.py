"""ML prediction service.

Loads the trained Random Forest model + preprocessors and provides:
    - risk prediction (score 0-100)
    - risk classification
    - explainability (feature contributions)
    - recommended actions derived from risk level + trigger factors

If the model is unavailable, a deterministic rule-based fallback is used so the
application never crashes.
"""
import json
import os

import joblib
import numpy as np

from app.config import settings

_RISK_BUCKETS = {
    "LOW": (0, 30, 10),
    "MODERATE": (31, 60, 20),
    "HIGH": (61, 80, 30),
    "CRITICAL": (81, 100, 40),
}


def _load_model():
    """Load model + preprocessors. Returns (model, bundle) or (None, None)."""
    model_path = settings.MODEL_PATH
    preproc_path = settings.PREPROCESSOR_PATH
    if not (os.path.exists(model_path) and os.path.exists(preproc_path)):
        return None, None
    try:
        model = joblib.load(model_path)
        bundle = joblib.load(preproc_path)
        return model, bundle
    except Exception:
        return None, None


_model_cache = {"model": None, "bundle": None, "loaded": False}


def get_model():
    if not _model_cache["loaded"]:
        _model_cache["model"], _model_cache["bundle"] = _load_model()
        _model_cache["loaded"] = True
    return _model_cache["model"], _model_cache["bundle"]


def _encode_categoricals(bundle, row):
    """Encode categorical columns using saved LabelEncoders; fallback 0 on unseen."""
    result = {}
    encoders = bundle["encoders"]
    for col, enc in encoders.items():
        val = row.get(col, "Unknown")
        try:
            result[f"{col}_enc"] = int(enc.transform([str(val)])[0])
        except Exception:
            result[f"{col}_enc"] = 0
    return result


def _f(features, key, default=0):
    """Return features[key] or default, treating None as missing."""
    val = features.get(key, default)
    return default if val is None else val


def predict(features: dict, location_data: dict = None):
    """Run inference and return a full prediction result dict.

    features: dict of required feature values.
    """
    model, bundle = get_model()

    if model is None:
        result = _rule_based_predict(features)
        result["model"] = "Rule-based fallback (model not loaded)"
        return result

    # Build feature vector in the order the model was trained on.
    rainfall = _f(features, "rainfall")
    base_features = {
        "rainfall": rainfall,
        "rainfall_intensity": _f(features, "rainfall_intensity", rainfall * 0.2),
        "soil_moisture": _f(features, "soil_moisture"),
        "temperature": _f(features, "temperature"),
        "humidity": _f(features, "humidity"),
        "elevation": _f(features, "elevation"),
        "slope": _f(features, "slope"),
        "historical_occurrence": int(_f(features, "historical_occurrence")),
        "distance_to_drain": _f(features, "distance_to_drain", 2.0),
    }

    feature_columns = bundle.get("feature_columns", [])
    categoricals = _encode_categoricals(bundle, features)

    all_features = {**base_features, **categoricals}
    import pandas as pd
    df = pd.DataFrame([all_features])[feature_columns]
    proba = float(model.predict_proba(df)[0][1])
    # Monotonic squashing so moderate conditions map to moderate risk bands
    # and only extreme conditions reach CRITICAL.
    risk_score = float(np.clip(100 * (proba ** 1.6), 0, 100))
    risk_level = classify_risk(risk_score)

    # Explainability: derive contributions from feature importances weighted by
    # how far each risky feature is from its "safe" baseline.
    contributions = _explain(features, base_features)

    result = {
        "risk_score": round(risk_score, 1),
        "risk_level": risk_level,
        "probability": round(proba, 4),
        "confidence": round(_confidence(proba, risk_level), 1),
        "contributing_factors": contributions,
        "recommended_actions": recommended_actions(risk_level, contributions),
        "model": "RandomForestClassifier (trained on DEMO data)",
        "data_source": settings.DATA_MODE,
    }
    return result


def classify_risk(score: float) -> str:
    score = max(0.0, min(100.0, score))
    if score <= 30:
        return "LOW"
    if score <= 60:
        return "MODERATE"
    if score <= 80:
        return "HIGH"
    return "CRITICAL"


def _confidence(proba, risk_level):
    # Confidence reflects model certainty: distance from 0.5 threshold and
    # proportion toward the hard boundaries of the bucket.
    certainty = abs(proba - 0.5) * 2  # 0..1
    return float(np.clip(55 + certainty * 40, 55, 95))


def _explain(features, base):
    """Compute human-readable factor contributions (0-100)."""
    contributions = []
    # Define risky thresholds for each factor.
    checks = [
        ("Rainfall", base["rainfall"], 80, 180),
        ("Rainfall Intensity", base["rainfall_intensity"], 15, 40),
        ("Soil Moisture", base["soil_moisture"], 55, 85),
        ("Humidity", base["humidity"], 65, 95),
        ("Slope", base["slope"], 25, 45),
        ("Elevation", base["elevation"], 800, 2000),
        ("Historical Occurrence", float(base["historical_occurrence"]), 0.5, 1.0),
    ]
    for label, value, low, high in checks:
        if high <= low:
            continue
        factor = float(np.clip((value - low) / (high - low), 0, 1))
        contributions.append({"factor": label, "value": value, "contribution": round(factor * 100, 1)})

    # Sort descending by contribution
    contributions.sort(key=lambda x: x["contribution"], reverse=True)
    return contributions


def recommended_actions(risk_level, contributions):
    top_factors = ", ".join(c["factor"].lower() for c in contributions[:3]) or "environmental conditions"
    actions = {
        "LOW": [
            "No immediate action required.",
            "Continue routine monitoring.",
            "Maintain baseline surveillance.",
        ],
        "MODERATE": [
            "Increase monitoring frequency to every 6 hours.",
            "Alert local field officers to stay vigilant.",
            "Review drainage and slope stability at this location.",
        ],
        "HIGH": [
            "Issue warning to district disaster management authority.",
            "Pre-position rescue and response teams.",
            "Restrict access to vulnerable slope areas.",
            "Increase monitoring frequency to every 1-2 hours.",
        ],
        "CRITICAL": [
            "ISSUE EMERGENCY ALERT - initiate evacuation of vulnerable zones.",
            "Deploy emergency response teams immediately.",
            "Establish emergency communication with affected communities.",
            "Continuously monitor until conditions stabilize.",
        ],
    }
    return actions.get(risk_level, actions["LOW"])


def _rule_based_predict(features):
    """Deterministic fallback when the ML model is unavailable."""
    rainfall = _f(features, "rainfall")
    soil_moisture = _f(features, "soil_moisture")
    slope = _f(features, "slope")
    humidity = _f(features, "humidity")

    score = (
        min(rainfall, 250) / 250 * 35
        + soil_moisture / 100 * 25
        + slope / 60 * 20
        + humidity / 100 * 20
    )
    score = float(np.clip(score, 0, 100))
    risk_level = classify_risk(score)
    contributions = _explain(features, {
        "rainfall": rainfall,
        "rainfall_intensity": _f(features, "rainfall_intensity", rainfall * 0.2),
        "soil_moisture": soil_moisture,
        "temperature": _f(features, "temperature"),
        "humidity": humidity,
        "elevation": _f(features, "elevation"),
        "slope": slope,
        "historical_occurrence": int(_f(features, "historical_occurrence")),
    })
    return {
        "risk_score": round(score, 1),
        "risk_level": risk_level,
        "probability": round(score / 100, 4),
        "confidence": 70.0,
        "contributing_factors": contributions,
        "recommended_actions": recommended_actions(risk_level, contributions),
        "model": "Rule-based fallback",
        "data_source": settings.DATA_MODE,
    }
