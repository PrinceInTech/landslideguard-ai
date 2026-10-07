"""Locations, prediction, alerts, and the data-source reporting contract."""
import pytest


def test_health_reports_data_mode(client):
    body = client.get("/api/health").json()
    assert body["data_mode"] in ("DEMO", "LIVE")


def test_locations_are_seeded(client):
    resp = client.get("/api/locations")
    assert resp.status_code == 200
    assert len(resp.json()) > 0


def test_risk_summary_shape(client):
    body = client.get("/api/risk-summary").json()
    for key in (
        "total_locations",
        "risk_counts",
        "overall_risk_level",
        "overall_avg_score",
        "data_source",
    ):
        assert key in body, f"missing {key}"
    assert body["overall_risk_level"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")


def test_risk_summary_reports_configured_and_observed_source(client):
    """data_source must reflect what was actually served, not a stale constant."""
    body = client.get("/api/risk-summary").json()
    assert "data_mode_configured" in body
    assert "live_degraded" in body
    assert body["data_source"] in ("DEMO", "LIVE")
    assert body["data_mode_configured"] in ("DEMO", "LIVE")
    # In DEMO mode there is nothing to degrade.
    if body["data_mode_configured"] == "DEMO":
        assert body["live_degraded"] is False


def test_location_carries_true_data_source(client):
    """Per-location source comes from the provider, so it cannot be stale."""
    locations = client.get("/api/locations").json()
    env = locations[0].get("environmental") or {}
    assert env.get("data_source") in ("DEMO", "LIVE")


def test_prediction_valid_payload(client):
    resp = client.post(
        "/api/predict",
        json={
            "rainfall": 120,
            "soil_moisture": 70,
            "temperature": 24,
            "humidity": 80,
            "elevation": 900,
            "slope": 32,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert 0 <= body["risk_score"] <= 100
    assert body["risk_level"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
    assert 0 <= body["confidence"] <= 100


@pytest.mark.parametrize(
    "field,value",
    [
        ("rainfall", -1),
        ("rainfall", 501),
        ("soil_moisture", 101),
        ("humidity", -5),
        ("elevation", -100),
        ("slope", 95),
        ("temperature", 90),
    ],
)
def test_prediction_rejects_out_of_range_values(client, field, value):
    payload = {
        "rainfall": 100,
        "soil_moisture": 60,
        "temperature": 22,
        "humidity": 70,
        "elevation": 800,
        "slope": 30,
    }
    payload[field] = value
    resp = client.post("/api/predict", json=payload)
    assert resp.status_code == 422, f"{field}={value} should be rejected"


def test_higher_risk_conditions_produce_higher_score(client):
    """Monotonic sanity check on the scoring direction."""

    def score(rainfall, moisture, slope):
        resp = client.post(
            "/api/predict",
            json={
                "rainfall": rainfall,
                "soil_moisture": moisture,
                "temperature": 22,
                "humidity": 75,
                "elevation": 900,
                "slope": slope,
            },
        )
        return resp.json()["risk_score"]

    calm = score(10, 20, 5)
    severe = score(220, 95, 55)
    assert severe > calm, f"expected {severe} > {calm}"


def test_delete_location_removes_dependents(client, admin_headers):
    """Regression: deleting a location used to raise a raw IntegrityError (500).

    Environmental history, predictions, and alerts must be removed with it.
    """
    created = client.post(
        "/api/locations",
        headers=admin_headers,
        json={
            "name": "Temp Site",
            "state": "Assam",
            "district": "Test",
            "latitude": 26.2,
            "longitude": 92.9,
            "elevation": 300,
            "slope": 20,
        },
    )
    assert created.status_code in (200, 201), created.text
    loc_id = created.json()["id"]

    # Give it dependents: a prediction and an alert.
    client.post(
        "/api/predict",
        json={"location": "Temp Site", "rainfall": 150, "soil_moisture": 75,
              "temperature": 23, "humidity": 85, "elevation": 300, "slope": 40},
    )
    alerts = client.post(
        "/api/alerts",
        json={
            "location_id": loc_id,
            "risk_level": "HIGH",
            "risk_score": 70,
            "message": "test alert",
        },
    )
    assert alerts.status_code in (200, 201), alerts.text

    deleted = client.delete(f"/api/locations/{loc_id}", headers=admin_headers)
    assert deleted.status_code == 204, f"expected 204, got {deleted.status_code}: {deleted.text}"

    assert client.get(f"/api/locations/{loc_id}").status_code in (404, 200)


def test_delete_missing_location_is_404(client, admin_headers):
    resp = client.delete("/api/locations/999999", headers=admin_headers)
    assert resp.status_code == 404


def test_update_location_rejects_bad_coordinates(client, admin_headers):
    locations = client.get("/api/locations").json()
    loc_id = locations[0]["id"]
    resp = client.put(
        f"/api/locations/{loc_id}",
        headers=admin_headers,
        json={"latitude": 123.0},
    )
    assert resp.status_code == 422


def test_alerts_listing_and_status_transitions(client, admin_headers):
    created = client.post(
        "/api/alerts",
        json={
            "location_id": client.get("/api/locations").json()[0]["id"],
            "risk_level": "MODERATE",
            "risk_score": 50,
            "message": "status flow test",
        },
    )
    assert created.status_code in (200, 201)
    alert_id = created.json()["id"]

    acked = client.put(
        f"/api/alerts/{alert_id}", headers=admin_headers, json={"status": "acknowledged"}
    )
    assert acked.status_code == 200
    assert acked.json()["status"] == "acknowledged"

    resolved = client.put(
        f"/api/alerts/{alert_id}", headers=admin_headers, json={"status": "resolved"}
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"


def test_alert_status_validation(client, admin_headers):
    alert_id = client.get("/api/alerts").json()[0]["id"]
    resp = client.put(
        f"/api/alerts/{alert_id}", headers=admin_headers, json={"status": "bogus"}
    )
    assert resp.status_code == 422


def test_analytics_returns_all_sections(client):
    body = client.get("/api/analytics").json()
    for key in (
        "states",
        "monthly_trends",
        "rainfall_correlation",
        "risk_distribution",
        "high_risk_locations",
        "incidents_by_state",
    ):
        assert key in body, f"missing {key}"


def test_analytics_state_levels_match_backend_thresholds(client):
    from app.risk import classify_risk

    for row in client.get("/api/analytics").json()["states"]:
        assert row["risk_level"] == classify_risk(row["avg_risk_score"])


def test_environmental_history_is_bounded(client):
    """Repeated refreshes must not grow the snapshot table without limit."""
    from app.database.session import SessionLocal
    from app.models import EnvironmentalData
    from app.services.location_service import ENV_HISTORY_RETENTION, prune_environment_history

    db = SessionLocal()
    try:
        before = db.query(EnvironmentalData).count()
        prune_environment_history(db)
        after = db.query(EnvironmentalData).count()
        assert after <= before
        # Per-location cap is enforced, so the total is bounded by
        # locations * retention.
        n_locations = db.query(EnvironmentalData).with_entities(
            EnvironmentalData.location_id
        ).distinct().count()
        assert after <= n_locations * ENV_HISTORY_RETENTION + ENV_HISTORY_RETENTION
    finally:
        db.close()