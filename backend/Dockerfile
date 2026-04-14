# ============================================================================
# Pharos Backend - Production Dockerfile for Koyeb Free Tier
# ============================================================================
# Optimized for Koyeb's 512MB RAM "nano" instance with 24/7 serverless hosting
#
# Architecture:
# - Multi-stage build to minimize final image size
# - Slim Python 3.11 base for reduced memory footprint
# - Cloud-optimized dependencies (no ML libraries)
# - Serverless database support (NeonDB PostgreSQL, Upstash Redis)
#
# Build: docker build -t pharos-api -f backend/Dockerfile backend/
# Run:   docker run -p 8000:8000 --env-file .env pharos-api
# ============================================================================

# ============================================================================
# STAGE 1: Builder - Install dependencies
# ============================================================================
FROM python:3.11-slim AS builder

# Set working directory
WORKDIR /build

# Install system dependencies required for Python packages
# - gcc, g++: Compile C extensions (psycopg2, etc.)
# - libpq-dev: PostgreSQL client library headers
# - curl: Health checks and debugging
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements files
COPY config/requirements-cloud.txt config/requirements-base.txt ./

# Install Python dependencies to /install directory
# --prefix=/install: Install to custom location for copying to final stage
# --no-cache-dir: Don't cache packages (reduces image size)
# --no-warn-script-location: Suppress pip warnings about script locations
RUN pip install --no-cache-dir --prefix=/install \
    -r requirements-cloud.txt

# ============================================================================
# STAGE 2: Runtime - Minimal production image
# ============================================================================
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/usr/local/bin:$PATH" \
    PORT=8000

# Install runtime dependencies only
# - libpq5: PostgreSQL client library (runtime, not dev headers)
# - curl: Health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
# Koyeb runs containers as non-root by default
RUN useradd -m -u 1000 -s /bin/bash pharos

# Set working directory
WORKDIR /app

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=pharos:pharos . .

# Copy entrypoint script
COPY --chown=pharos:pharos entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Switch to non-root user
USER pharos

# Expose port (Koyeb injects $PORT, defaults to 8000)
EXPOSE 8000

# Health check endpoint
# Koyeb will use this to determine if the service is healthy
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Entrypoint: Run migrations then start server
ENTRYPOINT ["/app/entrypoint.sh"]
