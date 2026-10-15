"""Phase 3.8: route tests for the feature-extraction API.

Covers the three things the endpoint must guarantee:

* **Authorization** -- anonymous and bad-token callers cannot reach the
  pipeline (``401``), while any authenticated user can.
* **Contract behavior** -- a valid request over the committed REAL artifacts
  returns the honest result, including ``rejected_leakage`` for a policy that
  the record cannot clear, and never a fabricated value.
* **Safe errors** -- contract violations map to ``422`` and reader/decoder
  failures to ``409``, and no response ever exposes a server filesystem path.

Real-artifact tests are skip-guarded on local file presence (nothing is
downloaded).
"""
from pathlib import Path

import pytest

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

# After the CHIRPS record's available_utc (2026-09-11T21:10:59Z) and the
# ERA5-Land record's available_utc (2026-09-15T00:00:00Z), so only the
# availability-evidence policy -- not the time rule -- can reject.
CUTOFF_AFTER_AVAILABILITY = "2026-10-08T12:00:00Z"


def _chirps_body(**overrides):
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


def test_extract_requires_authentication(client):
    resp = client.post("/api/extract", json=_chirps_body())
    assert resp.status_code == 401


def test_extract_rejects_invalid_token(client):
    resp = client.post(
        "/api/extract",
        headers={"Authorization": "Bearer not-a-jwt"},
        json=_chirps_body(),
    )
    assert resp.status_code == 401


# --- Contract violations (no artifact bytes needed) ------------------------


def test_extract_rejects_unsupported_source(client, admin_headers):
    resp = client.post(
        "/api/extract", headers=admin_headers, json=_chirps_body(source="nasa-coolr")
    )
    assert resp.status_code == 422
    assert "nasa-coolr" in resp.json()["detail"]


def test_extract_rejects_position_outside_study_region(client, admin_headers):
    resp = client.post(
        "/api/extract",
        headers=admin_headers,
        json=_chirps_body(position={"latitude": 0.0, "longitude": 0.0}),
    )
    assert resp.status_code == 422


def test_extract_rejects_unknown_artifact_pin(client, admin_headers):
    resp = client.post(
        "/api/extract", headers=admin_headers, json=_chirps_body(artifact_sha256="0" * 64)
    )
    assert resp.status_code == 422
    assert "artifact_sha256" in resp.json()["detail"]


# --- Honest success / honest refusal over the committed artifacts ----------


@CHIRPS_MISSING
def test_extract_returns_valid_chirps_feature(client, admin_headers):
    resp = client.post("/api/extract", headers=admin_headers, json=_chirps_body())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["contract_version"] == "1.1.0"
    assert body["source"] == "chirps"
    assert body["acquisition_record_id"] == "REAL-chirps-v2.0-2026-08-31"
    feature = body["features"][0]
    assert feature["feature_name"] == "precipitation_daily_mm"
    assert feature["status"] == "valid"
    assert feature["value"] is not None
    assert feature["provenance"]["prediction_cutoff_utc"].startswith("2026-10-08")


@ERA5_MISSING
def test_extract_production_policy_refuses_unverified_record(client, admin_headers):
    """ERA5-Land's committed record is unclassified, so the production gate must
    return an honest ``rejected_leakage`` -- never a fabricated value."""
    resp = client.post(
        "/api/extract",
        headers=admin_headers,
        json=_chirps_body(
            source="era5-land",
            position={"latitude": 26.0, "longitude": 94.0},
            requested_features=["temperature_2m_K"],
            availability_policy="production",
        ),
    )
    assert resp.status_code == 200, resp.text
    feature = resp.json()["features"][0]
    assert feature["feature_name"] == "temperature_2m_K"
    assert feature["status"] == "rejected_leakage"
    assert feature["value"] is None
    assert feature["note"]


# --- Safe error mapping (path never leaked) --------------------------------


def test_extract_maps_reader_failure_to_409_without_path(client, admin_headers, monkeypatch):
    from app.api import features as features_api

    leaky_path = (
        r"D:\PROJECTS\landslideguard-ai\data\raw\real\chirps"
        r"\chirps__v2.x__2026-08-31.tif.gz"
    )

    def boom(_request):
        raise features_api.ArtifactReadError(f"{leaky_path}: truncated TIFF header")

    monkeypatch.setattr(features_api, "run_extraction", boom)
    resp = client.post("/api/extract", headers=admin_headers, json=_chirps_body())
    assert resp.status_code == 409
    assert "PROJECTS" not in resp.text
    assert "tif.gz" not in resp.text


def test_extract_maps_contract_error_to_422_with_path_redacted(
    client, admin_headers, monkeypatch
):
    from app.api import features as features_api

    leaky_path = (
        r"D:\PROJECTS\landslideguard-ai\data\raw\real\chirps"
        r"\chirps__v2.x__2026-08-31.tif.gz"
    )

    def boom(_request):
        raise features_api.FeatureContractError(
            f"CHIRPS artifact {leaky_path} has no ModelPixelScale"
        )

    monkeypatch.setattr(features_api, "run_extraction", boom)
    resp = client.post("/api/extract", headers=admin_headers, json=_chirps_body())
    assert resp.status_code == 422
    assert "PROJECTS" not in resp.text
    assert "<path>" in resp.json()["detail"]
