# syntax=docker/dockerfile:1
#
# LandslideGuard AI - backend image
#
# Build context is the PROJECT ROOT (see docker-compose.yml) because the image
# needs ../ml and ../data, which Docker cannot COPY from outside its context.
#
# Layout note: WORKDIR is /app and the app package is copied to /app/app, so
# app/config.py resolves BASE_DIR=/app and PROJECT_ROOT=/app. That makes the
# derived paths line up with the runtime mounts:
#     PROJECT_ROOT/data       -> /app/data
#     PROJECT_ROOT/ml/model   -> /app/ml/model
# Keeping these consistent is what lets the ML model and seed CSVs be found
# inside the container.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so application edits do not invalidate the pip layer.
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code, the full ML pipeline (train.py is invoked by the admin
# retrain endpoint) and the seed datasets.
COPY backend/app ./app
COPY ml ./ml
COPY data ./data

# Run as an unprivileged user. /app is chowned because the retrain endpoint
# writes model artifacts and the dataset upload writes into data/.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

# Entrypoint chowns the writable mounts and then drops privileges via setpriv,
# so the server itself never runs as root. See docker-entrypoint.sh.
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Defaults; overridden by docker-compose / real environment variables.
ENV DATA_MODE=DEMO \
    DATABASE_URL=sqlite:////app/data/landslideguard.db \
    DATA_DIR=/app/data \
    MODEL_DIR=/app/ml/model \
    ENVIRONMENT=development

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# The app needs /app/data and /app/ml/model to be writable, so it cannot be a
# fully read-only container. It still drops to a non-root user at startup.
