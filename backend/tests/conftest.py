"""Shared pytest fixtures.

Isolation contract
------------------
The database the suite uses is decided **once, at conftest import time**,
before any `app` module is imported. `app.config.Settings` reads `DATABASE_URL`
when the class body executes, i.e. on first import of `app.config`, so the
variable has to be correct by then. Setting it later (inside a fixture) is too
late as soon as a test module imports `app.*` at module level during collection
-- which is exactly the failure this file previously had: the purge-list
approach left `app.config` bound to the developer's real database, so pytest
dropped and recreated tables in `backend/landslideguard.db`.

Nothing here ever points at a repository database; `_TEST_DB_PATH` lives under
the system temp directory and is checked against the repo before use, and the
directory is deleted again when the session finishes (see `pytest_sessionfinish`
below).
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

# Importing `app` requires backend/ on sys.path.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Must be set before app.config is imported: production mode refuses to start
# with the default signing key and admin password.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-used-in-production-0123456789")
os.environ.setdefault("DEMO_ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("DATA_MODE", "DEMO")

# --- Test database -----------------------------------------------------------
# Created here, not in a fixture, so it is in place before `app.config` loads.
_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="lg-tests-"))
_TEST_DB_PATH = _TEST_DB_DIR / "test.db"
_TEST_DB_URL = f"sqlite:///{_TEST_DB_PATH.as_posix()}"

# Safety net: the suite must never be able to reach a database inside the
# repository (the development DB at backend/landslideguard.db or the Docker
# bind-mount DB at data/landslideguard.db).
assert _TEST_DB_PATH.parent == _TEST_DB_DIR, "test database must live in its own temp dir"
assert not _TEST_DB_PATH.is_relative_to(PROJECT_ROOT), (
    f"test database {_TEST_DB_PATH} would be created inside the project; "
    "refusing to run tests against a repository database"
)
assert not _TEST_DB_PATH.is_relative_to(BACKEND_DIR), (
    f"test database {_TEST_DB_PATH} would be created inside backend/"
)
assert _TEST_DB_PATH.name != "landslideguard.db", "test database must not reuse the dev filename"
assert _TEST_DB_URL.startswith("sqlite:///"), "tests require a file-backed SQLite URL"

os.environ["DATABASE_URL"] = _TEST_DB_URL

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


# --- Temp directory cleanup -------------------------------------------------
# The directory created above is removed as soon as the session ends, pass or
# fail, so repeated runs do not pile SQLite files up in the system temp folder.
# The pooled connections have to be closed first: on Windows SQLite keeps the
# file open, and an open file cannot be deleted.


def _remove_test_db_dir() -> bool:
    """Close the engine and delete this session's temporary directory.

    Only a `lg-tests-*` directory outside the project can ever be removed, so a
    future rename cannot turn this helper into a way to delete the wrong thing.
    Returns True when nothing is left behind.
    """
    assert _TEST_DB_DIR.name.startswith("lg-tests-"), (
        f"refusing to delete {_TEST_DB_DIR}: not a pytest temp directory"
    )
    assert not _TEST_DB_DIR.is_relative_to(PROJECT_ROOT), (
        f"refusing to delete {_TEST_DB_DIR}: it is inside the project"
    )
    try:
        from app.database.session import engine

        engine.dispose()
    except Exception:
        pass  # the engine was never imported, so nothing holds the file open
    if not _TEST_DB_DIR.is_dir():
        return True
    shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)
    return not _TEST_DB_DIR.is_dir()


def pytest_sessionfinish(session, exitstatus):
    """Delete the temporary database once the run is over.

    pytest always calls this hook before exiting, including when tests failed,
    so a red run does not leave a stale directory behind either. A directory
    that cannot be removed is reported but never changes the exit status.
    """
    if not _remove_test_db_dir():
        print(
            f"warning: could not remove temp test directory {_TEST_DB_DIR}",
            file=sys.stderr,
        )


@pytest.fixture(scope="session")
def _test_db_url() -> str:
    """The isolated database every test runs against."""
    return _TEST_DB_URL


@pytest.fixture()
def client(_test_db_url, monkeypatch):
    """A TestClient bound to the isolated temporary database."""
    from app.config import settings

    # Re-assert isolation at use time so a future refactor cannot silently
    # repoint the suite at a repository file.
    assert settings.DATABASE_URL == _test_db_url, (
        f"app.config bound to {settings.DATABASE_URL!r}, expected the temp test "
        f"database {_test_db_url!r}"
    )

    from app.database.session import engine
    from app.main import app
    from app.models import Base

    resolved = engine.url.database
    assert resolved, "engine has no database path"
    resolved_path = Path(resolved)
    assert resolved_path.name == "test.db", f"unexpected test database {resolved_path}"
    assert not resolved_path.is_relative_to(PROJECT_ROOT), (
        f"engine is bound to repository database {resolved_path}; refusing to run"
    )

    # Clean schema for this test, on the temp database only.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def admin_token(client):
    """Token for the seeded demo admin."""
    resp = client.post(
        "/api/auth/login",
        json={
            "email": "admin@landslideguard.ai",
            "password": os.environ["DEMO_ADMIN_PASSWORD"],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture()
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture()
def viewer(client):
    """A registered (non-admin) user. Returns the login response body."""
    resp = client.post(
        "/api/auth/register",
        json={"name": "Viewer", "email": "viewer@example.com", "password": "viewerpass123"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()
