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