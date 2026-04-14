# Gunicorn Configuration for Render Deployment
# Optimized for Render Starter Tier (512MB RAM)
#
# This configuration is production-hardened for memory-constrained environments
# and works with serverless databases (NeonDB, Upstash Redis).
#
# Key Features:
# - Conservative worker count to prevent OOM on 512MB instances
# - Graceful shutdown handling for serverless database connections
# - Request timeout handling for long-running operations
# - Health check endpoint support
# - Structured logging for production monitoring

import multiprocessing
import os

# ============================================================================
# WORKER CONFIGURATION
# ============================================================================

# Worker class: Use Uvicorn workers for ASGI support
worker_class = "uvicorn.workers.UvicornWorker"

# Number of workers: Conservative for Render Starter (512MB RAM)
# Formula: (2 × CPU cores) + 1, but capped at 2 for memory constraints
#
# Render Starter: 0.5 CPU → 2 workers (recommended)
# Render Standard: 1 CPU → 3 workers (recommended)
# Render Pro: 2 CPU → 4 workers (safe)
#
# Each worker uses ~150-200MB RAM:
# - 2 workers = ~400MB (safe for 512MB with ~100MB headroom)
# - 3 workers = ~600MB (risky for 512MB, safe for 1GB)
# - 4 workers = ~800MB (requires 1GB+ RAM)

workers = int(os.getenv("WEB_CONCURRENCY", "2"))

# Threads per worker: 1 (async workers don't benefit from threads)
threads = 1

# Worker connections: Maximum concurrent requests per worker
# For async workers, this can be higher than sync workers
worker_connections = 1000

# ============================================================================
# BINDING & NETWORKING
# ============================================================================

# Bind address: Render provides PORT environment variable
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# Backlog: Maximum number of pending connections
backlog = 2048

# ============================================================================
# TIMEOUTS & GRACEFUL SHUTDOWN
# ============================================================================

# Timeout: Maximum time for a request to complete (seconds)
# Set to 60s to handle:
# - NeonDB cold start (up to 10s)
# - Complex queries (up to 30s)
# - Embedding generation (up to 20s)
timeout = 60

# Graceful timeout: Time to wait for workers to finish during shutdown
# Important for serverless databases to close connections cleanly
graceful_timeout = 30

# Keep-alive: Time to wait for requests on a Keep-Alive connection
keepalive = 5

# ============================================================================
# WORKER LIFECYCLE
# ============================================================================

# Max requests: Restart worker after N requests (prevents memory leaks)
# Set to 1000 for production stability
max_requests = 1000

# Max requests jitter: Add randomness to prevent all workers restarting at once
max_requests_jitter = 100

# Worker restart: Restart workers gracefully when code changes (dev only)
reload = os.getenv("ENVIRONMENT", "production") == "development"

# ============================================================================
# LOGGING
# ============================================================================

# Access log: Log all requests (use "-" for stdout)
accesslog = "-"

# Error log: Log errors and warnings (use "-" for stderr)
errorlog = "-"

# Log level: info (production), debug (development)
loglevel = os.getenv("LOG_LEVEL", "info")

# Access log format: Structured logging for production monitoring
# Includes: timestamp, method, path, status, duration, user-agent
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
)

# ============================================================================
# PROCESS NAMING
# ============================================================================

# Process name: Helps identify Gunicorn processes in monitoring tools
proc_name = "pharos-api"

# ============================================================================
# SECURITY
# ============================================================================

# Limit request line size (prevents header injection attacks)
limit_request_line = 4096

# Limit request header field size
limit_request_field_size = 8190

# Limit request header fields count
limit_request_fields = 100

# ============================================================================
# HOOKS (Lifecycle Events)
# ============================================================================


def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Pharos API starting...")
    server.log.info(f"Workers: {workers}")
    server.log.info(f"Worker class: {worker_class}")
    server.log.info(f"Timeout: {timeout}s")
    server.log.info(f"Bind: {bind}")


def on_reload(server):
    """Called when a worker is reloaded (code change detected)."""
    server.log.info("Code change detected, reloading workers...")


def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Pharos API ready to accept connections")


def worker_int(worker):
    """Called when a worker receives SIGINT or SIGQUIT signal."""
    worker.log.info(f"Worker {worker.pid} received shutdown signal")


def worker_abort(worker):
    """Called when a worker is aborted (timeout or error)."""
    worker.log.error(f"Worker {worker.pid} aborted (timeout or error)")


def pre_fork(server, worker):
    """Called just before a worker is forked."""
    pass


def post_fork(server, worker):
    """Called just after a worker is forked."""
    worker.log.info(f"Worker {worker.pid} spawned")


def pre_exec(server):
    """Called just before a new master process is forked."""
    server.log.info("Forking new master process...")


def pre_request(worker, req):
    """Called just before a worker processes a request."""
    # Log slow requests (useful for debugging)
    worker.log.debug(f"{req.method} {req.path}")


def post_request(worker, req, environ, resp):
    """Called after a worker processes a request."""
    pass


def child_exit(server, worker):
    """Called just after a worker has been exited."""
    server.log.info(f"Worker {worker.pid} exited")


def worker_exit(server, worker):
    """Called just after a worker has been exited."""
    server.log.info(f"Worker {worker.pid} shutdown complete")


def nworkers_changed(server, new_value, old_value):
    """Called when the number of workers changes."""
    server.log.info(f"Workers changed: {old_value} → {new_value}")


def on_exit(server):
    """Called just before the master process exits."""
    server.log.info("Pharos API shutting down...")


# ============================================================================
# SERVERLESS DATABASE NOTES
# ============================================================================

# NeonDB (PostgreSQL):
# - Connection pooling handled by SQLAlchemy (see app/shared/database.py)
# - Pool size: 3 base + 7 overflow = 10 connections per worker
# - Total connections: 10 × 2 workers = 20 (safe for Render Starter: 22 max)
# - Pool pre-ping enabled to handle dropped connections
# - Statement timeout: 30s to prevent runaway queries
# - Graceful shutdown ensures connections close cleanly

# Upstash Redis:
# - Serverless Redis with per-request pricing
# - SSL/TLS required (rediss:// protocol)
# - Automatic retry logic in app/shared/cache.py
# - Free tier: 10,000 requests/day (sufficient for solo dev)

# ============================================================================
# MEMORY OPTIMIZATION NOTES
# ============================================================================

# Render Starter (512MB RAM):
# - 2 workers × 150MB = 300MB (worker processes)
# - ~100MB for OS and overhead
# - ~100MB headroom for request spikes
# - Total: ~500MB (safe)

# If you see OOM errors:
# 1. Reduce workers to 1: WEB_CONCURRENCY=1
# 2. Reduce max_requests to 500 (restart workers more frequently)
# 3. Upgrade to Render Standard (1GB RAM) for 3 workers

# ============================================================================
# MONITORING & DEBUGGING
# ============================================================================

# To monitor worker memory usage:
# 1. SSH into Render instance: render ssh
# 2. Run: ps aux | grep gunicorn
# 3. Check RSS (resident set size) column for memory usage

# To test configuration locally:
# gunicorn -c gunicorn_conf.py app.main:app

# To test with specific worker count:
# WEB_CONCURRENCY=1 gunicorn -c gunicorn_conf.py app.main:app
