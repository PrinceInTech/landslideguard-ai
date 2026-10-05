"""Application configuration via environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Directory containing this file -> the `app` package directory -> its parent.
# This is the directory that holds the application package, whatever the layout:
#   local:  <repo>/backend/app/config.py   -> <repo>/backend
#   docker: /app/app/config.py             -> /app
BACKEND_DIR = Path(__file__).resolve().parent.parent


def _detect_project_root(backend_dir: Path) -> Path:
    """Walk up from the backend directory looking for the repository root.

    The project root is the closest ancestor that contains the ``data`` and
    ``ml`` directories. Relying on a fixed number of ``.parent`` hops breaks as
    soon as the image layout differs from the local checkout (for example the
    Docker image puts the app package directly in /app, which would otherwise
    resolve the root to "/").
    """
    for candidate in (backend_dir, *backend_dir.parents):
        if (candidate / "data").is_dir() and (candidate / "ml").is_dir():
            return candidate
    # Fall back to the conventional layout (backend/ inside the repo).
    return backend_dir.parent


PROJECT_ROOT = _detect_project_root(BACKEND_DIR)

# Backwards-compatible alias used elsewhere in the codebase.
BASE_DIR = BACKEND_DIR


def _load_env():
    # Priority: project .env -> backend-local .env
    root_env = PROJECT_ROOT / ".env"
    local_env = BACKEND_DIR / ".env"
    for env_file in (root_env, local_env):
        if env_file.exists():
            load_dotenv(env_file)


_load_env()

# A hardcoded fallback signing key means anybody who reads the repo can forge
# admin tokens. Outside development we require an explicitly configured secret.
_INSECURE_JWT_SECRET = "change-me-landslideguard-demo-secret"
_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
_IS_PRODUCTION = _ENVIRONMENT in ("production", "prod")
_JWT_SECRET_RAW = os.getenv("JWT_SECRET", _INSECURE_JWT_SECRET)

if _IS_PRODUCTION and _JWT_SECRET_RAW == _INSECURE_JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET must be set to a unique value when ENVIRONMENT=production. "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )
if len(_JWT_SECRET_RAW) < 16:
    raise RuntimeError("JWT_SECRET must be at least 16 characters long.")


class Settings:
    APP_NAME = "LandslideGuard AI"
    APP_VERSION = "1.0.0"
    ENVIRONMENT = _ENVIRONMENT
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    # Security
    JWT_SECRET = _JWT_SECRET_RAW
    JWT_ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

    # Demo admin account (seeded on fresh DB)
    DEMO_ADMIN_EMAIL = os.getenv("DEMO_ADMIN_EMAIL", "admin@landslideguard.ai")
    DEMO_ADMIN_PASSWORD = os.getenv("DEMO_ADMIN_PASSWORD", "admin123")

    if _IS_PRODUCTION and DEMO_ADMIN_PASSWORD == "admin123":
        raise RuntimeError(
            "DEMO_ADMIN_PASSWORD must be changed from the default when ENVIRONMENT=production."
        )

    # Database. SQLite is the only engine actually supported: no other driver
    # (psycopg, pymongo, ...) is declared in requirements.txt, so pointing this
    # at another backend will fail at create_engine time.
    DATABASE_URL = os.getenv(
        "DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'landslideguard.db'}"
    )

    # Data source mode
    DATA_MODE = os.getenv("DATA_MODE", "DEMO")  # DEMO or LIVE

    # Weather API (optional). Leave blank to force demo weather fallback.
    OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
    OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"

    # Paths. Every one of these can be overridden by environment variable so
    # the same code runs unchanged from a checkout, a container, or a PaaS
    # filesystem that is read-only outside /tmp.
    DATA_DIR = Path(os.getenv("DATA_DIR") or (PROJECT_ROOT / "data"))
    HISTORICAL_DATA = DATA_DIR / "historical_landslide_data.csv"
    LOCATIONS_DATA = DATA_DIR / "monitoring_locations.csv"
    REALTIME_DATA = DATA_DIR / "sample_realtime_data.json"
    MODEL_DIR = Path(os.getenv("MODEL_DIR") or (PROJECT_ROOT / "ml" / "model"))
    MODEL_PATH = Path(os.getenv("MODEL_PATH") or (MODEL_DIR / "landslide_model.joblib"))
    PREPROCESSOR_PATH = Path(
        os.getenv("PREPROCESSOR_PATH") or (MODEL_DIR / "preprocessors.joblib")
    )
    # Training pipeline, invoked by the admin retrain endpoint.
    TRAIN_SCRIPT = Path(os.getenv("TRAIN_SCRIPT") or (PROJECT_ROOT / "ml" / "train.py"))

    # CORS. "*" is rejected by the browser when credentials are used, so
    # production must list explicit origins.
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080",
        ).split(",")
        if origin.strip()
    ]


settings = Settings()
