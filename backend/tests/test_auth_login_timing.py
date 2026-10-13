"""Login timing side-channel mitigation (Phase 3.15).

The login flow must spend comparable bcrypt work whether or not the submitted
email is registered, so a missing account cannot be distinguished from a wrong
password by how long the response takes. These tests pin the mechanism (a fixed
dummy hash is used for absent or empty stored hashes) and the public API contract
(identical ``401`` for unknown user and wrong password). They deliberately avoid
wall-clock assertions: the evidence is *which* hash verification is performed,
not a measured number of seconds. No password hash or secret is ever printed.
"""
import os

from app.services import auth_service


def _login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_unknown_user_verifies_against_the_dummy_hash(client, monkeypatch):
    seen = []
    real = auth_service.verify_password

    def spy(plain, hashed):
        seen.append(hashed)
        return real(plain, hashed)

    monkeypatch.setattr(auth_service, "verify_password", spy)

    resp = _login(client, "does-not-exist@example.com", "some-password-123")

    assert resp.status_code == 401
    # Exactly one verification ran, against the fixed dummy hash.
    assert seen == [auth_service._DUMMY_PASSWORD_HASH]


def test_wrong_password_existing_user_uses_the_stored_hash(client, monkeypatch):
    seen = []
    real = auth_service.verify_password

    def spy(plain, hashed):
        seen.append(hashed)
        return real(plain, hashed)

    monkeypatch.setattr(auth_service, "verify_password", spy)

    resp = _login(client, "admin@landslideguard.ai", "definitely-wrong-password")

    assert resp.status_code == 401
    assert len(seen) == 1
    # The real stored hash is used (never the dummy); assert its shape without
    # ever echoing its value.
    assert seen[0] != auth_service._DUMMY_PASSWORD_HASH
    assert seen[0].startswith("$2b$")


def test_correct_password_still_succeeds(client):
    resp = _login(client, "admin@landslideguard.ai", os.environ["DEMO_ADMIN_PASSWORD"])
    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "admin"


def test_unknown_user_and_wrong_password_are_indistinguishable(client):
    unknown = _login(client, "nobody@example.com", "any-password-123")
    wrong = _login(client, "admin@landslideguard.ai", "any-password-123")

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json() == {"detail": "Invalid credentials"}
    assert unknown.headers.get("content-type") == wrong.headers.get("content-type")


def test_verify_password_or_dummy_never_authenticates_without_hash(monkeypatch):
    calls = []

    def always_match(plain, hashed):
        calls.append(hashed)
        return True

    monkeypatch.setattr(auth_service, "verify_password", always_match)

    # Even though the (stubbed) comparison reports a match, a missing stored hash
    # must never authenticate: the result is discarded and the work still runs.
    assert auth_service.verify_password_or_dummy("anything", None) is False
    assert calls == [auth_service._DUMMY_PASSWORD_HASH]


def test_verify_password_or_dummy_uses_real_hash_when_present(monkeypatch):
    calls = []
    monkeypatch.setattr(
        auth_service,
        "verify_password",
        lambda plain, hashed: calls.append(hashed) or False,
    )

    assert auth_service.verify_password_or_dummy("anything", "$2b$placeholder") is False
    assert calls == ["$2b$placeholder"]


def test_empty_and_malformed_stored_hashes_fail_generically(client):
    from app.database.session import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        db.add(
            User(
                name="Empty",
                email="empty-hash@example.com",
                password_hash="",
                role="viewer",
            )
        )
        db.add(
            User(
                name="Malformed",
                email="malformed-hash@example.com",
                password_hash="not-a-bcrypt-hash",
                role="viewer",
            )
        )
        db.commit()
    finally:
        db.close()

    for email in ("empty-hash@example.com", "malformed-hash@example.com"):
        resp = _login(client, email, "whatever-123456")
        assert resp.status_code == 401
        # A broken stored hash must not surface an internal error or a different
        # body than any other failed login.
        assert resp.json() == {"detail": "Invalid credentials"}
