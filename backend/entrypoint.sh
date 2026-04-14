#!/bin/bash
# ============================================================================
# Pharos Backend - Container Entrypoint Script
# ============================================================================
# Handles startup sequence for Koyeb deployment:
# 1. Run database migrations (Alembic)
# 2. Start web server (Gunicorn + Uvicorn workers)
#
# Exit codes:
# - 0: Success
# - 1: Migration failure
# - 2: Server startup failure
# ============================================================================

set -e  # Exit immediately if any command fails
set -u  # Exit if undefined variable is used
set -o pipefail  # Exit if any command in a pipeline fails

# ============================================================================
# CONFIGURATION
# ============================================================================

# Port: Koyeb injects $PORT environment variable (defaults to 8000)
PORT="${PORT:-8000}"

# Worker count: Conservative for 512MB RAM (2 workers = ~400MB)
# Override with WEB_CONCURRENCY environment variable if needed
WEB_CONCURRENCY="${WEB_CONCURRENCY:-2}"

# Log level: info (production), debug (development)
LOG_LEVEL="${LOG_LEVEL:-info}"

# Environment: production (default), development, staging
ENVIRONMENT="${ENVIRONMENT:-production}"

# ============================================================================
# LOGGING HELPERS
# ============================================================================

log_info() {
    echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

log_success() {
    echo "[SUCCESS] $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# ============================================================================
# ENVIRONMENT VALIDATION
# ============================================================================

log_info "Starting Pharos API..."
log_info "Environment: $ENVIRONMENT"
log_info "Port: $PORT"
log_info "Workers: $WEB_CONCURRENCY"
log_info "Log Level: $LOG_LEVEL"

# Validate required environment variables
if [ -z "${DATABASE_URL:-}" ]; then
    log_error "DATABASE_URL environment variable is not set"
    log_error "Please configure DATABASE_URL in Koyeb Secrets"
    exit 1
fi

if [ -z "${REDIS_URL:-}" ]; then
    log_error "REDIS_URL environment variable is not set"
    log_error "Please configure REDIS_URL in Koyeb Secrets"
    exit 1
fi

log_success "Environment validation passed"

# ============================================================================
# DATABASE MIGRATIONS
# ============================================================================

log_info "Running database migrations..."

# Change to backend directory (where alembic.ini is located)
cd /app

# Run Alembic migrations
# -c: Path to alembic.ini configuration file
# upgrade head: Apply all pending migrations
if alembic -c config/alembic.ini upgrade head; then
    log_success "Database migrations completed successfully"
else
    log_error "Database migrations failed"
    log_error "Check DATABASE_URL and database connectivity"
    exit 1
fi

# ============================================================================
# SERVER STARTUP
# ============================================================================

log_info "Starting Gunicorn web server..."
log_info "Binding to 0.0.0.0:$PORT"

# Start Gunicorn with Uvicorn workers
# -c: Path to gunicorn configuration file
# --bind: Bind to all interfaces on $PORT
# --workers: Number of worker processes (from $WEB_CONCURRENCY)
# --worker-class: Use Uvicorn workers for ASGI support
# --timeout: Request timeout (60s for NeonDB cold start + complex queries)
# --graceful-timeout: Time to wait for workers to finish during shutdown
# --log-level: Logging verbosity
# app.main:app: FastAPI application instance

exec gunicorn \
    -c gunicorn_conf.py \
    --bind "0.0.0.0:$PORT" \
    --workers "$WEB_CONCURRENCY" \
    --worker-class uvicorn.workers.UvicornWorker \
    --timeout 60 \
    --graceful-timeout 30 \
    --log-level "$LOG_LEVEL" \
    --access-logfile - \
    --error-logfile - \
    app.main:app

# Note: exec replaces the shell process with Gunicorn, so this line is never reached
# If we reach here, something went wrong
log_error "Server startup failed"
exit 2
