"""Authentication, RBAC, and the viewer-registration regression test."""
import os


def test_health_is_public(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert "status" in resp.json()


def test_register_grants_viewer_never_admin(client):
    """Regression: self-registration must not create an admin.

    This is the exact privilege-escalation path that was fixed; keep it pinned.
    """
    resp = client.post(
        "/api/auth/register",
        json={"name": "Asc", "email": "asc@example.com", "password": "hunter2hunter2"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["role"] == "viewer"
    assert body["user"]["role"] != "admin"


def test_registered_viewer_is_forbidden_from_admin_routes(client, viewer):
    """A viewer token must receive 403 from every admin endpoint."""
    token = viewer["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    for method, path in (
        ("get", "/api/admin/stats"),
        ("get", "/api/admin/alerts"),
        ("get", "/api/admin/settings"),
        ("post", "/api/admin/retrain"),
    ):
        resp = getattr(client, method)(path, headers=headers)
        assert resp.status_code == 403, f"{method.upper()} {path} returned {resp.status_code}"
        assert "admin" in resp.json()["detail"].lower()


def test_admin_token_is_allowed(client, admin_headers):
    resp = client.get("/api/admin/stats", headers=admin_headers)
    assert resp.status_code == 200
    assert "total_locations" in resp.json()


def test_protected_routes_require_a_token(client):
    assert client.get("/api/admin/stats").status_code == 401
    assert client.get("/api/admin/alerts").status_code == 401


def test_invalid_token_is_rejected(client):
    resp = client.get("/api/admin/stats", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


def test_login_with_wrong_password_fails(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@landslideguard.ai", "password": "wrong-password"},
    )
    assert resp.status_code == 401


def test_me_returns_the_token_subject(client, admin_token):
    resp = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


def test_duplicate_email_is_rejected(client, viewer):
    resp = client.post(
        "/api/auth/register",
        json={"name": "Dup", "email": "viewer@example.com", "password": "another12345"},
    )
    assert resp.status_code in (400, 409)


def test_short_password_is_rejected(client):
    resp = client.post(
        "/api/auth/register",
        json={"name": "Short", "email": "short@example.com", "password": "abc"},
    )
    assert resp.status_code == 422


def test_invalid_email_is_rejected(client):
    resp = client.post(
        "/api/auth/register",
        json={"name": "Bad", "email": "not-an-email", "password": "validpass123"},
    )
    assert resp.status_code == 422


def test_seeded_admin_uses_configured_password(client):
    """The seed must honour DEMO_ADMIN_PASSWORD rather than a hardcoded value."""
    resp = client.post(
        "/api/auth/login",
        json={
            "email": "admin@landslideguard.ai",
            "password": os.environ["DEMO_ADMIN_PASSWORD"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "admin"


# --- Phase 3.8: write endpoints require an authenticated user --------------
#
# Established policy (matches the documented authorization model and the
# frontend, whose dashboard pages are auth-gated but not admin-gated): every
# in-scope mutation requires a valid bearer token. Any authenticated role
# (`viewer` or `admin`) may mutate; only `/api/admin/**` additionally requires
# `admin`. Bodies are valid so that, for an anonymous or bad-token request, the
# only possible failure is the authorization check -- never request validation.

_MUTATING_ENDPOINTS = [
    (
        "post",
        "/api/locations",
        {
            "name": "Auth Probe",
            "state": "Assam",
            "district": "Probe",
            "latitude": 26.1,
            "longitude": 92.8,
            "elevation": 300,
            "slope": 20,
        },
    ),
    ("put", "/api/locations/1", {"name": "Auth Probe"}),
    ("delete", "/api/locations/1", None),
    (
        "post",
        "/api/alerts",
        {
            "location_id": 1,
            "risk_level": "HIGH",
            "risk_score": 70,
            "message": "auth probe",
        },
    ),
    ("put", "/api/alerts/1", {"status": "acknowledged"}),
    (
        "post",
        "/api/predict",
        {
            "rainfall": 120,
            "soil_moisture": 70,
            "temperature": 24,
            "humidity": 80,
            "elevation": 900,
            "slope": 32,
        },
    ),
    ("post", "/api/predict/location/1", None),
]


def _call(client, method, path, body, headers=None):
    kwargs = {}
    if headers is not None:
        kwargs["headers"] = headers
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(path, **kwargs)


def test_mutating_endpoints_require_authentication(client):
    """Anonymous requests must not be able to mutate any in-scope resource."""
    for method, path, body in _MUTATING_ENDPOINTS:
        resp = _call(client, method, path, body)
        assert resp.status_code == 401, f"{method.upper()} {path} returned {resp.status_code}"


def test_mutating_endpoints_reject_invalid_token(client):
    """A syntactically present but invalid token must not authorize a mutation."""
    for method, path, body in _MUTATING_ENDPOINTS:
        resp = _call(client, method, path, body, {"Authorization": "Bearer not-a-jwt"})
        assert resp.status_code == 401, f"{method.upper()} {path} returned {resp.status_code}"


def test_authenticated_viewer_can_mutate(client, viewer):
    """The chosen minimal policy keeps the existing workflow: any signed-in user
    (the `viewer` role) may manage locations, alerts and predictions."""
    headers = {"Authorization": f"Bearer {viewer['access_token']}"}

    created = _call(
        client,
        "post",
        "/api/locations",
        {
            "name": "Auth Probe Site",
            "state": "Assam",
            "district": "Probe",
            "latitude": 26.15,
            "longitude": 92.85,
            "elevation": 300,
            "slope": 20,
        },
        headers,
    )
    assert created.status_code in (200, 201), created.text
    loc_id = created.json()["id"]

    updated = _call(client, "put", f"/api/locations/{loc_id}", {"slope": 25}, headers)
    assert updated.status_code == 200, updated.text

    predicted = _call(
        client,
        "post",
        "/api/predict",
        {
            "location": "Auth Probe Site",
            "rainfall": 120,
            "soil_moisture": 70,
            "temperature": 24,
            "humidity": 80,
            "elevation": 300,
            "slope": 25,
        },
        headers,
    )
    assert predicted.status_code == 200, predicted.text

    alert = _call(
        client,
        "post",
        "/api/alerts",
        {
            "location_id": loc_id,
            "risk_level": "HIGH",
            "risk_score": 70,
            "message": "auth probe",
        },
        headers,
    )
    assert alert.status_code in (200, 201), alert.text
    alert_id = alert.json()["id"]

    acked = _call(client, "put", f"/api/alerts/{alert_id}", {"status": "acknowledged"}, headers)
    assert acked.status_code == 200, acked.text

    deleted = _call(client, "delete", f"/api/locations/{loc_id}", None, headers)
    assert deleted.status_code == 204, deleted.text