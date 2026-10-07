"""Weather provider source reporting, uploads, and model metadata integrity."""
import json
import os
from pathlib import Path

import pytest

from app.services.data_provider import WeatherProvider

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
MODEL_META = PROJECT_ROOT / "ml" / "model" / "model_meta.json"
MODEL_FILE = PROJECT_ROOT / "ml" / "model" / "landslide_model.joblib"
DATASET = PROJECT_ROOT / "data" / "historical_landslide_data.csv"

LOCATION = {
    "name": "Kohima",
    "state": "Nagaland",
    "latitude": 25.67,
    "longitude": 94.11,
    "elevation": 1444,
    "slope": 30,
}


def test_configured_source_requires_both_mode_and_key(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "DATA_MODE", "DEMO")
    assert WeatherProvider().configured_source == "DEMO"

    monkeypatch.setattr(settings, "DATA_MODE", "LIVE")
    # LIVE mode with no key must not claim LIVE.
    assert WeatherProvider().configured_source == "DEMO"


def test_configured_source_is_live_when_mode_and_key_present(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "DATA_MODE", "LIVE")
    provider = WeatherProvider()
    provider.api_key = "test-key"
    assert provider.configured_source == "LIVE"


def test_demo_read_updates_source(client):
    """Regression: `source` used to be set once in __init__ and never updated."""
    provider = WeatherProvider()
    provider.last_source = None
    conditions = provider.get_conditions(LOCATION)
    assert conditions["data_source"] == "DEMO"
    assert provider.source == "DEMO"


def test_degraded_flag_when_live_fetch_fails(client, monkeypatch):
    """LIVE configured but unreachable must be reported, not silently DEMO.

    Hermetic: `_fetch_live` is replaced with a raiser so no request leaves the
    process. The suite must pass offline and in CI.
    """
    from app.config import settings

    def _raise(self, location):
        raise RuntimeError("simulated OpenWeather outage (test double)")

    monkeypatch.setattr(WeatherProvider, "_fetch_live", _raise)
    monkeypatch.setattr(settings, "DATA_MODE", "LIVE")
    provider = WeatherProvider()
    provider.api_key = "test-key-never-sent"

    conditions = provider.get_conditions(LOCATION)

    assert provider.configured_source == "LIVE"
    assert provider.source == "DEMO", "failed fetch should report the source actually served"
    assert provider.degraded is True
    assert provider.last_error, "the failure reason should be retained for diagnostics"
    assert "simulated OpenWeather outage" in provider.last_error
    assert conditions["data_source"] == "DEMO"


def test_not_degraded_in_demo_mode(client):
    provider = WeatherProvider()
    provider.get_conditions(LOCATION)
    assert provider.degraded is False


def test_health_exposes_provider_state(client):
    body = client.get("/api/health").json()
    assert "data_mode" in body


def test_upload_rejects_non_csv(client, admin_headers):
    resp = client.post(
        "/api/admin/upload-dataset",
        headers=admin_headers,
        files={"file": ("data.txt", b"not a csv", "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_rejects_empty_file(client, admin_headers):
    resp = client.post(
        "/api/admin/upload-dataset",
        headers=admin_headers,
        files={"file": ("empty.csv", b"   ", "text/csv")},
    )
    assert resp.status_code == 400


def test_upload_enforces_size_limit(client, admin_headers, monkeypatch):
    """An oversized upload must be refused with 413 before it is written.

    The real dataset is never touched: DATA_DIR is redirected to a temp copy.
    """
    import shutil
    import tempfile
    from pathlib import Path as P

    tmp = Path(tempfile.mkdtemp(prefix="lg-upload-"))
    (tmp / "historical_landslide_data.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    from app.config import settings

    monkeypatch.setattr(settings, "DATA_DIR", tmp)
    monkeypatch.setattr(settings, "HISTORICAL_DATA", tmp / "historical_landslide_data.csv")
    # 1 KB limit; send 4 KB.
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1024)

    resp = client.post(
        "/api/admin/upload-dataset",
        headers=admin_headers,
        files={"file": ("big.csv", b"a,b\n" * 2048, "text/csv")},
    )
    assert resp.status_code == 413, resp.text
    # The previous file must survive an aborted upload.
    assert (tmp / "historical_landslide_data.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"
    # No partial temp file left behind.
    assert not list(tmp.glob("*.tmp"))
    shutil.rmtree(tmp, ignore_errors=True)


def test_upload_accepts_valid_csv(client, admin_headers, monkeypatch):
    import shutil
    import tempfile
    from pathlib import Path as P

    tmp = Path(tempfile.mkdtemp(prefix="lg-upload-"))
    (tmp / "historical_landslide_data.csv").write_text("old\n", encoding="utf-8")

    from app.config import settings

    monkeypatch.setattr(settings, "DATA_DIR", tmp)
    monkeypatch.setattr(settings, "HISTORICAL_DATA", tmp / "historical_landslide_data.csv")

    resp = client.post(
        "/api/admin/upload-dataset",
        headers=admin_headers,
        files={"file": ("ok.csv", b"a,b\n1,2\n3,4\n", "text/csv")},
    )
    assert resp.status_code == 200
    body = (tmp / "historical_landslide_data.csv").read_text(encoding="utf-8")
    assert body == "a,b\n1,2\n3,4\n"
    assert not list(tmp.glob("*.tmp"))
    shutil.rmtree(tmp, ignore_errors=True)


def test_upload_requires_admin(client, viewer):
    resp = client.post(
        "/api/admin/upload-dataset",
        headers={"Authorization": f"Bearer {viewer['access_token']}"},
        files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")},
    )
    assert resp.status_code == 403


def test_model_metadata_records_provenance():
    """Metadata must identify the model and the exact data it was trained on."""
    meta = json.loads(MODEL_META.read_text(encoding="utf-8"))

    assert meta["model_version"]
    assert meta["trained_at_utc"]

    versions = meta["library_versions"]
    for pkg in ("scikit-learn", "numpy", "pandas", "joblib", "python"):
        assert versions.get(pkg), f"missing library version for {pkg}"

    hp = meta["hyperparameters"]
    assert hp["n_estimators"] > 0
    assert "random_state" in hp
    assert "test_size" in hp["train_test_split"]

    # The dataset digest must match the file actually present.
    import hashlib

    digest = hashlib.sha256(DATASET.read_bytes()).hexdigest()
    assert meta["dataset_sha256"] == digest, "dataset changed since training"

    # Split sizes must add up to the dataset.
    assert meta["n_samples_train"] + meta["n_samples_test"] == meta["n_samples"]
    assert meta["class_balance"]["positive"] + meta["class_balance"]["negative"] == meta["n_samples"]


def test_model_metadata_does_not_leak_absolute_paths():
    meta_text = MODEL_META.read_text(encoding="utf-8")
    assert ":\\" not in meta_text, "absolute Windows path leaked into metadata"
    assert "/home/" not in meta_text and "/Users/" not in meta_text
    assert meta_text.count("D:\\") == 0


def test_model_metadata_records_leakage_caveat():
    """The structural label leakage must be recorded, not quietly omitted."""
    meta = json.loads(MODEL_META.read_text(encoding="utf-8"))
    leakage = meta["label_leakage"]
    assert leakage["present_in_demo_data"] is True
    assert leakage["note"], "a human-readable explanation is required"


def test_model_artifacts_exist():
    assert MODEL_FILE.exists()
    assert MODEL_FILE.stat().st_size > 0


def test_model_loads_and_predicts(client):
    """The shipped artifact must load in this environment."""
    resp = client.post(
        "/api/predict",
        json={
            "rainfall": 150,
            "soil_moisture": 80,
            "temperature": 23,
            "humidity": 85,
            "elevation": 1200,
            "slope": 38,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["model"].startswith("RandomForestClassifier")