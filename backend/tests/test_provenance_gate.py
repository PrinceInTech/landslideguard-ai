"""Phase 3.20: tests for the provenance-gated prediction-input validation route.

The gate must guarantee:

* **Authorization** -- anonymous/bad-token callers cannot reach it (``401``).
* **No model** -- a successful report is explicitly *not* a prediction
  (``prediction_mode``/``is_prediction``/``model_invoked``), and the REAL feature
  vocabulary is proven disjoint from the DEMO model's inputs.
* **Reuse of the real gates** -- a valid request over the committed REAL
  artifacts returns the honest verdict (``accepted_for_research``); a policy the
  record cannot clear returns ``rejected`` with a ``rejected_leakage`` decision;
  a rolling window without coverage returns ``insufficient_temporal_coverage``;
  a future cutoff rejects; and no value is ever fabricated.
* **Safe errors** -- contract violations map to ``422`` and reader failures to
  ``409``, with no server filesystem path in any response.

Real-artifact tests are skip-guarded on local file presence (nothing is
downloaded).
"""
from pathlib import Path

import pytest

from app.ml import predictor
from app.schemas.features import FEATURE_SPECS
from app.services.provenance_gate import (
    DEMO_MODEL_FEATURE_COLUMNS,
    assess_demo_model_compatibility,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
REAL_CHIRPS = (
    PROJECT_ROOT / "data" / "raw" / "real" / "chirps" / "chirps__v2.x__2026-08-31.tif.gz"
)
REAL_ERA5 = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "real"
    / "era5-land"
    / "era5-land__operational-consolidated-2-months-era5-land-t-5-days__2026-07-15t0000.nc"
)

CHIRPS_MISSING = pytest.mark.skipif(
    not REAL_CHIRPS.is_file(), reason="real CHIRPS artifact not present"
)
ERA5_MISSING = pytest.mark.skipif(
    not REAL_ERA5.is_file(), reason="real ERA5-Land artifact not present"
)

# After both committed REAL records' available_utc values, so only the
# availability-evidence policy (not the time rule) can reject.
CUTOFF_AFTER_AVAILABILITY = "2026-10-08T12:00:00Z"
# Before the CHIRPS observation window (2026-08-31 .. 2026-09-01): future data.
CUTOFF_BEFORE_OBSERVATION = "2026-08-30T00:00:00Z"

ROUTE = "/api/provenance/validate"


def _body(**overrides):
    body = {
        "source": "chirps",
        "position": {"latitude": 28.02, "longitude": 90.03},
        "prediction_cutoff_utc": CUTOFF_AFTER_AVAILABILITY,
        "requested_features": ["precipitation_daily_mm"],
        "availability_policy": "research_replay",
    }
    body.update(overrides)
    return body


# --- Authorization ---------------------------------------------------------


def test_gate_requires_authentication(client):
    assert client.post(ROUTE, json=_body()).status_code == 401


def test_gate_rejects_invalid_token(client):
    resp = client.post(ROUTE, headers={"Authorization": "Bearer not-a-jwt"}, json=_body())
    assert resp.status_code == 401


# --- Contract violations (no artifact bytes needed) ------------------------


def test_gate_rejects_unsupported_source(client, admin_headers):
    resp = client.post(ROUTE, headers=admin_headers, json=_body(source="nasa-coolr"))
    assert resp.status_code == 422
    assert "nasa-coolr" in resp.json()["detail"]


def test_gate_rejects_unknown_artifact_pin(client, admin_headers):
    resp = client.post(ROUTE, headers=admin_headers, json=_body(artifact_sha256="0" * 64))
    assert resp.status_code == 422
    assert "artifact_sha256" in resp.json()["detail"]


def test_gate_rejects_position_outside_study_region(client, admin_headers):
    resp = client.post(
        ROUTE, headers=admin_headers, json=_body(position={"latitude": 0.0, "longitude": 0.0})
    )
    assert resp.status_code == 422


# --- Honest success / honest refusal over the committed artifacts ----------


@CHIRPS_MISSING
def test_gate_accepts_valid_chirps_for_research(client, admin_headers):
    resp = client.post(ROUTE, headers=admin_headers, json=_body())
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["prediction_mode"] == "provenance_gated_validation"
    assert body["is_prediction"] is False
    assert body["model_invoked"] is False
    assert "not a landslide prediction" in body["disclaimer"]
    assert body["production_readiness"] == "NO-GO"
    assert body["model_compatibility"] == "incompatible"

    assert body["verdict"] == "accepted_for_research"
    assert body["availability_policy"] == "research_replay"
    assert body["temporal_eligibility"] == "eligible"
    assert body["checksum_verification"] == "verified"
    assert "precipitation_daily_mm" in body["accepted_features"]
    assert body["rejected_features"] == []
    assert "risk_score" not in body

    feature = body["result"]["features"][0]
    assert feature["status"] == "valid"
    assert feature["value"] is not None


@ERA5_MISSING
def test_gate_production_policy_rejects_unverified_record(client, admin_headers):
    """The ERA5-Land committed record is unclassified, so the production policy
    must return an honest rejection -- never a fabricated value."""
    resp = client.post(
        ROUTE,
        headers=admin_headers,
        json=_body(
            source="era5-land",
            position={"latitude": 26.0, "longitude": 94.0},
            requested_features=["temperature_2m_K"],
            availability_policy="production",
        ),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verdict"] == "rejected"
    assert body["availability_policy"] == "production"
    assert body["temporal_eligibility"] == "rejected"
    assert body["accepted_features"] == []
    rejected = body["rejected_features"][0]
    assert rejected["feature_name"] == "temperature_2m_K"
    assert rejected["status"] == "rejected_leakage"
    assert rejected["value"] is None
    assert rejected["reason"]


@CHIRPS_MISSING
def test_gate_rejects_future_data_leakage(client, admin_headers):
    """A cutoff before the observation window must reject, not use future data."""
    resp = client.post(
        ROUTE,
        headers=admin_headers,
        json=_body(prediction_cutoff_utc=CUTOFF_BEFORE_OBSERVATION),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verdict"] == "rejected"
    assert body["temporal_eligibility"] == "rejected"
    assert body["result"]["features"][0]["status"] == "rejected_leakage"


@CHIRPS_MISSING
def test_gate_rejects_rolling_window_without_coverage(client, admin_headers):
    """A 30-day window over a single committed day is insufficient, not zero."""
    resp = client.post(
        ROUTE,
        headers=admin_headers,
        json=_body(requested_features=["precipitation_30d_mm"]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verdict"] == "rejected"
    feature = body["result"]["features"][0]
    assert feature["status"] == "insufficient_temporal_coverage"
    assert feature["value"] is None


# --- DEMO / REAL separation (proven in code) -------------------------------


def test_demo_model_vocabulary_is_disjoint_from_real_features():
    model, bundle = predictor.get_model()
    if model is None:
        pytest.skip("shipped DEMO model artifact not loadable in this environment")
    model_columns = set(bundle.get("feature_columns", []))
    assert model_columns, "model bundle declares no feature_columns"
    assert model_columns == set(DEMO_MODEL_FEATURE_COLUMNS), (
        "the reviewed DEMO feature vocabulary drifted from the shipped model"
    )
    assert model_columns & set(FEATURE_SPECS) == set(), (
        "a REAL feature name unexpectedly matches a DEMO model input"
    )

    assessment = assess_demo_model_compatibility()
    assert assessment["compatible"] is False
    assert assessment["shared_feature_names"] == []
    assert "without inventing a mapping" in assessment["reason"]


def test_demo_predict_labels_its_mode(client, admin_headers):
    """The DEMO prediction response must declare its (distinct) mode."""
    resp = client.post(
        "/api/predict",
        headers=admin_headers,
        json={
            "rainfall": 120,
            "soil_moisture": 70,
            "temperature": 24,
            "humidity": 80,
            "elevation": 900,
            "slope": 32,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prediction_mode"] == "demo"
    # The DEMO path still returns a prediction-shaped payload.
    assert "risk_score" in body


# --- Safe error mapping (path never leaked) --------------------------------


def test_gate_maps_reader_failure_to_409_without_path(client, admin_headers, monkeypatch):
    from app.api import provenance_gate as gate_api

    leaky_path = (
        r"D:\PROJECTS\landslideguard-ai\data\raw\real\chirps"
        r"\chirps__v2.x__2026-08-31.tif.gz"
    )

    def boom(_request):
        raise gate_api.ArtifactReadError(f"{leaky_path}: truncated TIFF header")

    monkeypatch.setattr(gate_api, "run_provenance_gate", boom)
    resp = client.post(ROUTE, headers=admin_headers, json=_body())
    assert resp.status_code == 409
    assert "PROJECTS" not in resp.text
    assert "tif.gz" not in resp.text


def test_gate_maps_contract_error_to_422_with_path_redacted(client, admin_headers, monkeypatch):
    from app.api import provenance_gate as gate_api

    leaky_path = (
        r"D:\PROJECTS\landslideguard-ai\data\raw\real\chirps"
        r"\chirps__v2.x__2026-08-31.tif.gz"
    )

    def boom(_request):
        raise gate_api.FeatureContractError(
            f"CHIRPS artifact {leaky_path} has no ModelPixelScale"
        )

    monkeypatch.setattr(gate_api, "run_provenance_gate", boom)
    resp = client.post(ROUTE, headers=admin_headers, json=_body())
    assert resp.status_code == 422
    assert "PROJECTS" not in resp.text
    assert "<path>" in resp.json()["detail"]
