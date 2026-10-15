"""Regression tests for the ``app.config`` environment-security guard.

``app/config.py`` evaluates its guards once, at import time: outside an
explicitly local environment it refuses to load while the built-in demo JWT
secret or the default admin password is still in place. Because that logic runs
on first import, each scenario is exercised in a fresh subprocess rather than by
reloading the module -- this keeps the check honest (no monkeypatched state) and
never touches a database, a model or the network.

The probe neutralises ``.env`` loading so the result reflects only the injected
environment; the guard under test is the environment-variable logic, not dotenv
parsing.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent

DEMO_JWT_SECRET = "change-me-landslideguard-demo-secret"
DEMO_ADMIN_PASSWORD = "admin123"
STRONG_SECRET = "config-test-secret-0123456789abcdef"
STRONG_PASSWORD = "config-test-admin-password"

LOCAL_ENVIRONMENTS = ("development", "dev", "local", "test")

# Keys the parent test process sets for its own suite; dropped so the probe sees
# only what each case injects.
_INHERITED_KEYS = (
    "ENVIRONMENT",
    "JWT_SECRET",
    "JWT_SECRET_KEY",
    "DEMO_ADMIN_PASSWORD",
    "DATABASE_URL",
)

_PROBE = (
    "import json, sys, types\n"
    "fake = types.ModuleType('dotenv')\n"
    "fake.load_dotenv = lambda *a, **k: False\n"
    "sys.modules['dotenv'] = fake\n"
    "result = {'environment': None, 'loaded': False, 'error': None}\n"
    "try:\n"
    "    import app.config as c\n"
    "    result['loaded'] = True\n"
    "    result['environment'] = c.settings.ENVIRONMENT\n"
    "except RuntimeError:\n"
    "    result['error'] = 'RuntimeError'\n"
    "except Exception as exc:\n"
    "    result['error'] = type(exc).__name__\n"
    "print(json.dumps(result))\n"
)


def _probe(environment, *, secret=DEMO_JWT_SECRET, password=DEMO_ADMIN_PASSWORD):
    """Import ``app.config`` in a clean subprocess and report the outcome.

    ``environment=None`` leaves ``ENVIRONMENT`` unset so the default is used.
    Returns the parsed probe result plus the process return code.
    """
    env = {k: v for k, v in os.environ.items() if k not in _INHERITED_KEYS}
    env["PYTHONPATH"] = str(BACKEND_DIR)
    if environment is not None:
        env["ENVIRONMENT"] = environment
    if secret is not None:
        env["JWT_SECRET"] = secret
    if password is not None:
        env["DEMO_ADMIN_PASSWORD"] = password

    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(
    "value",
    [
        *LOCAL_ENVIRONMENTS,
        *(v.upper() for v in LOCAL_ENVIRONMENTS),
        "Development",
        "  development  ",
        " Test ",
    ],
)
def test_local_environments_accept_demo_defaults(value):
    result = _probe(value)
    assert result["loaded"] is True
    assert result["error"] is None
    assert result["environment"] == value.strip().lower()


@pytest.mark.parametrize(
    "value",
    [
        "production",
        "prod",
        "staging",
        "production ",
        "  staging",
        "Production",
        "PROD",
        "qa",
        "prodution",
        "",
    ],
)
def test_non_local_environments_reject_demo_defaults(value):
    result = _probe(value)
    assert result["loaded"] is False
    assert result["error"] == "RuntimeError"


def test_unset_environment_defaults_to_local_development():
    result = _probe(None)
    assert result["loaded"] is True
    assert result["environment"] == "development"


def test_explicit_credentials_allowed_in_non_local_environment():
    result = _probe("staging", secret=STRONG_SECRET, password=STRONG_PASSWORD)
    assert result["loaded"] is True
    assert result["error"] is None
    assert result["environment"] == "staging"


def test_non_local_rejects_default_admin_password_only():
    result = _probe("staging", secret=STRONG_SECRET, password=DEMO_ADMIN_PASSWORD)
    assert result["loaded"] is False
    assert result["error"] == "RuntimeError"


def test_non_local_rejects_demo_jwt_secret_only():
    result = _probe("staging", secret=DEMO_JWT_SECRET, password=STRONG_PASSWORD)
    assert result["loaded"] is False
    assert result["error"] == "RuntimeError"


def test_short_jwt_secret_is_rejected_even_when_local():
    result = _probe("development", secret="short")
    assert result["loaded"] is False
    assert result["error"] == "RuntimeError"


def test_suite_uses_a_non_default_jwt_secret():
    """The suite must not silently run on the built-in demo signing key.

    Guards the conftest variable name: setting ``JWT_SECRET_KEY`` instead of
    ``JWT_SECRET`` would leave the demo default in force and fail here, without
    ever exposing the value.
    """
    from app.config import settings

    assert settings.JWT_SECRET != DEMO_JWT_SECRET
    assert settings.JWT_SECRET == os.environ.get("JWT_SECRET")
