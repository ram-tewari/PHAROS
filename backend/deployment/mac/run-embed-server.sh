#!/bin/sh
# Serve query embeddings for production from this Mac (launchd keeps it running).
#
# Loopback only (127.0.0.1:8790); `tailscale funnel --bg --https=8443 http://127.0.0.1:8790`
# publishes just this port. Reads EDGE_EMBED_TOKEN from $PHAROS_ENV_FILE
# (default ~/.pharos-deploy.env). Production uses it with
# EMBEDDING_BACKEND=edge-onnx and falls back to its own model when this Mac is off.
set -eu
BACKEND="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${PHAROS_ENV_FILE:-$HOME/.pharos-deploy.env}"
PYTHON="${PHAROS_PYTHON:-$BACKEND/.venv-local/bin/python}"

EDGE_EMBED_TOKEN="$(sed -n "s/^EDGE_EMBED_TOKEN='\{0,1\}\([^']*\)'\{0,1\}$/\1/p" "$ENV_FILE")"
export EDGE_EMBED_TOKEN
export EMBEDDING_ONNX_DIR="${EMBEDDING_ONNX_DIR:-$BACKEND/models/granite-embedding-english-r2-int8}"
export EMBEDDING_MODEL_ID="${EMBEDDING_MODEL_ID:-granite-embedding-english-r2-int8}"
export EMBEDDING_ONNX_THREADS="${EMBEDDING_ONNX_THREADS:-4}"

cd "$BACKEND"
"$PYTHON" scripts/fetch_onnx_model.py --model "$EMBEDDING_MODEL_ID" "$EMBEDDING_ONNX_DIR" >/dev/null
exec "$PYTHON" -m app.codeintel.edge_server
