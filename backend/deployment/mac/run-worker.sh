#!/bin/sh
# Drain queued ingestion jobs on this Mac, then exit (launchd runs it hourly).
#
# Production (Render free, 512 MB) only embeds queries; repositories are
# indexed here with the same embedding model, straight into the production
# database. Reads DATABASE_URL from $PHAROS_ENV_FILE (default
# ~/.pharos-deploy.env, KEY='value' lines). Nothing is listened on.
set -eu
BACKEND="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${PHAROS_ENV_FILE:-$HOME/.pharos-deploy.env}"
PYTHON="${PHAROS_PYTHON:-$BACKEND/.venv-local/bin/python}"

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
export MODE=CLOUD ENV=prod EMBEDDING_BACKEND=onnx
export EMBEDDING_ONNX_DIR="${EMBEDDING_ONNX_DIR:-$BACKEND/models/granite-embedding-english-r2-int8}"
export EMBEDDING_MODEL_ID="${EMBEDDING_MODEL_ID:-granite-embedding-english-r2-int8}"
export EMBEDDING_ONNX_BATCH_SIZE="${EMBEDDING_ONNX_BATCH_SIZE:-32}"

cd "$BACKEND"
"$PYTHON" scripts/fetch_onnx_model.py --model "$EMBEDDING_MODEL_ID" "$EMBEDDING_ONNX_DIR" >/dev/null
exec "$PYTHON" -m app.cli worker --once
