#!/bin/sh
# LandslideGuard AI - backend entrypoint
#
# The container starts as root only long enough to make the writable paths
# usable, then drops to an unprivileged user for the lifetime of the process.
#
# Why this is necessary: /app/data is a bind mount from the host. A database
# file created by an earlier root-run container is owned by root with mode 644,
# so the unprivileged user cannot open it and SQLite reports "attempt to write a
# readonly database". Chowning at startup repairs that and keeps any host-
# supplied files writable, without ever running the application as root.
set -e

DATA_DIR="${DATA_DIR:-/app/data}"
MODEL_DIR="${MODEL_DIR:-/app/ml/model}"

mkdir -p "$DATA_DIR" "$MODEL_DIR"

# Best effort: a read-only mount or a foreign ownership model should not stop
# the service from booting, because the app degrades gracefully.
chown -R appuser:appuser "$DATA_DIR" "$MODEL_DIR" 2>/dev/null || \
    echo "warning: could not chown $DATA_DIR / $MODEL_DIR; continuing" >&2

exec setpriv --reuid=appuser --regid=appuser --init-groups "$@"