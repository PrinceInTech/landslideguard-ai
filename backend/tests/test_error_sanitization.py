"""Regression tests proving internal detail is not returned to clients.

Phase 3.10, Workstream D. Each test plants a recognisable "secret" in an
internal failure and asserts it never reaches the HTTP response.
"""
import json
from pathlib import Path

SENTINEL = "SENSITIVE-INTERNAL-DETAIL-postgres://user:pw@db-internal:5432/x"


def test_health_does_not_leak_database_error(client, monkeypatch):
    import app.main as main

    def _boom():
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(main, "SessionLocal", _boom)

    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert SENTINEL not in resp.text
    body = resp.json()
    assert body["database"] == "degraded"
    assert body["status"] == "degraded"


def test_analytics_does_not_leak_internal_error(client, monkeypatch):
    import app.api.analytics as analytics

    def _boom():
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(analytics, "get_analytics", _boom)

    resp = client.get("/api/analytics")
    assert resp.status_code == 500
    assert SENTINEL not in resp.text
    assert resp.json()["detail"] == "Analytics failed"


def test_admin_settings_hides_database_url_and_paths(client, admin_headers):
    from app.config import settings

    resp = client.get("/api/admin/settings", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    raw = json.dumps(body)

    assert settings.DATABASE_URL not in raw
    assert "://" not in raw
    assert "project_root" not in body
    assert "train_script" not in body
    assert body["database"] == "sqlite"
    assert body["model_path"] == settings.MODEL_PATH.name
    assert Path(body["model_path"]).name == body["model_path"]


def test_retrain_missing_script_does_not_leak_path(client, admin_headers, monkeypatch):
    from app.config import settings

    bogus = Path("D:/sensitive/location/train.py")
    monkeypatch.setattr(settings, "TRAIN_SCRIPT", bogus)

    resp = client.post("/api/admin/retrain", headers=admin_headers)
    assert resp.status_code == 500
    assert "sensitive" not in resp.text
    assert str(bogus) not in resp.text


def test_safe_validation_errors_are_preserved(client):
    """Sanitization must not swallow ordinary, client-actionable validation."""
    resp = client.post(
        "/api/auth/register",
        json={"name": "Bad", "email": "not-an-email", "password": "validpass123"},
    )
    assert resp.status_code == 422
    assert resp.json().get("detail")
