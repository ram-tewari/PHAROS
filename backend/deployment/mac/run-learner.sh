#!/bin/sh
# Learn every indexed repository whose current commit has no memory yet, then exit.
# Runs against the production database (DATABASE_URL in ~/.pharos-deploy.env), on this Mac:
# it needs full git mirrors (LEARNING_MIRROR_DIR, default ~/.cache/pharos/git) and, from L2 on,
# Codex. Production never learns. Nightly under launchd (com.pharos.learner.plist).
set -eu
BACKEND="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${PHAROS_ENV_FILE:-$HOME/.pharos-deploy.env}"
PYTHON="${PHAROS_PYTHON:-$BACKEND/.venv-local/bin/python}"

set -a
. "$ENV_FILE"
set +a
export MODE=CLOUD ENV=prod EMBEDDING_BACKEND=onnx
export EMBEDDING_ONNX_DIR="${EMBEDDING_ONNX_DIR:-$BACKEND/models/granite-embedding-english-r2-int8}"
export EMBEDDING_MODEL_ID="${EMBEDDING_MODEL_ID:-granite-embedding-english-r2-int8}"
export LEARNING_MIRROR_DIR="${LEARNING_MIRROR_DIR:-$HOME/.cache/pharos/git}"

cd "$BACKEND"
"$PYTHON" scripts/fetch_onnx_model.py --model "$EMBEDDING_MODEL_ID" "$EMBEDDING_ONNX_DIR" >/dev/null
# caffeinate keeps the Mac from idle-sleeping mid-run (a sleeping Mac stalls Codex and drops the
# database connection); it ends with the worker.
exec /usr/bin/caffeinate -i "$PYTHON" -m app.workers.learning_worker --once
