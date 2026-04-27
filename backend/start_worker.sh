#!/usr/bin/env bash
#
# Pharos Unified Edge Worker launcher.
#
# Guarantees:
#   - cwd is backend/
#   - .env is loaded (so DATABASE_URL, UPSTASH_*, EDGE_EMBED_PORT etc. are set)
#   - MODE=EDGE (override-safe: forced even if .env says CLOUD)
#   - Banner prints active queues + 30s BLPOP timeout
#
# Usage:
#   bash start_worker.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="$SCRIPT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
else
    echo "[WARN] $ENV_FILE not found; relying on shell environment"
fi

# Force EDGE mode regardless of what .env said.
export MODE=EDGE
export PYTHONUNBUFFERED=1

PYTHON_BIN="${PYTHON_BIN:-python}"
EMBED_PORT="${EDGE_EMBED_PORT:-8001}"

cat <<BANNER
================================================================
  Pharos Unified Edge Worker
================================================================
  Mode             : EDGE
  Queues (BLPOP)   : pharos:tasks, ingest_queue
  BLPOP timeout    : 30s  (~2,880 idle cmds/day, Upstash-safe)
  Embed endpoint   : http://127.0.0.1:${EMBED_PORT}/embed
  Working dir      : $(pwd)
  Python           : $($PYTHON_BIN --version 2>&1)
================================================================
BANNER

exec "$PYTHON_BIN" -m app.workers.main_worker
