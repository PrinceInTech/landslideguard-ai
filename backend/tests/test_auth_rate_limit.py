"""Focused tests for the offline auth rate limiter (Phase 3.10, Workstream C)."""
import os

import pytest

from app.api import auth


@pytest.fixture()
def login_limiter():
    return auth.login_rate_limit.limiter


@pytest.fixture()
def register_limiter():
    return auth.register_rate_limit.limiter


def test_login_is_rate_limited_with_generic_response(client, login_limiter, monkeypatch):
    monkeypatch.setattr(login_limiter, "limit", 3)
    login_limiter.reset()

    payload = {"email": "admin@landslideguard.ai", "password": "wrong-password"}
    for _ in range(3):
        assert client.post("/api/auth/login", json=payload).status_code == 401

    blocked = client.post("/api/auth/login", json=payload)
    assert blocked.status_code == 429
    # The response must not reveal whether the account exists.
    assert blocked.json()["detail"] == "Too many attempts. Please try again later."
    assert int(blocked.headers["Retry-After"]) >= 1


def test_register_and_login_use_separate_buckets(
    client, register_limiter, login_limiter, monkeypatch
):
    monkeypatch.setattr(register_limiter, "limit", 2)
    register_limiter.reset()
    login_limiter.reset()

    for index in range(2):
        resp = client.post(
            "/api/auth/register",
            json={
                "name": f"Rl {index}",
                "email": f"rl-user-{index}@example.com",
                "password": "validpass123",
            },
        )
        assert resp.status_code == 200, resp.text

    blocked = client.post(
        "/api/auth/register",
        json={
            "name": "Rl X",
            "email": "rl-user-x@example.com",
            "password": "validpass123",
        },
    )
    assert blocked.status_code == 429

    # Exhausting the registration bucket must not consume the login bucket.
    login = client.post(
        "/api/auth/login",
        json={
            "email": "admin@landslideguard.ai",
            "password": os.environ["DEMO_ADMIN_PASSWORD"],
        },
    )
    assert login.status_code == 200, login.text


def test_successful_login_still_works_within_the_limit(client):
    resp = client.post(
        "/api/auth/login",
        json={
            "email": "admin@landslideguard.ai",
            "password": os.environ["DEMO_ADMIN_PASSWORD"],
        },
    )
    assert resp.status_code == 200


def test_fixed_window_limiter_resets_after_the_window():
    from app.services.rate_limit import FixedWindowLimiter

    now = [0.0]
    limiter = FixedWindowLimiter(limit=2, window_seconds=10, clock=lambda: now[0])

    assert limiter.hit("client") == (True, 0)
    assert limiter.hit("client") == (True, 0)
    allowed, retry_after = limiter.hit("client")
    assert allowed is False and retry_after >= 1

    now[0] = 11.0
    assert limiter.hit("client") == (True, 0)


def test_fixed_window_limiter_keys_are_independent():
    from app.services.rate_limit import FixedWindowLimiter

    limiter = FixedWindowLimiter(limit=1, window_seconds=60, clock=lambda: 0.0)
    assert limiter.hit("a")[0] is True
    assert limiter.hit("b")[0] is True
    assert limiter.hit("a")[0] is False


def test_client_identity_ignores_spoofable_forwarding_headers():
    """A rotating X-Forwarded-For must not create new buckets."""
    from app.services.rate_limit import _client_key

    class _FakeRequest:
        client = type("_Peer", (), {"host": "10.0.0.5"})()
        headers = {"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"}

    assert _client_key(_FakeRequest()) == "10.0.0.5"
