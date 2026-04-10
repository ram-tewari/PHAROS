# Pharos 2.0 - Backend Dockerfile
# Multi-stage build for optimized production image

# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# Configure pip globally with longer timeout and retries
RUN pip config set global.timeout 600 && \
    pip config set global.retries 10 && \
    pip config set global.index-url https://pypi.org/simple

# Copy and install dependencies in layers for better caching
# Layer 1: Base dependencies (fast)
COPY requirements-base.txt .
RUN pip install --no-cache-dir --user -r requirements-base.txt

# Layer 2: Processing dependencies (medium)
COPY requirements-processing.txt .
RUN pip install --no-cache-dir --user -r requirements-processing.txt

# Layer 3: ML dependencies (slow - install with extra patience)
COPY requirements-ml.txt .
RUN pip install --no-cache-dir --user -r requirements-ml.txt || \
    (echo "First attempt failed, retrying with individual packages..." && \
     pip install --no-cache-dir --user torch>=2.0.0 && \
     pip install --no-cache-dir --user transformers==4.43.3 && \
     pip install --no-cache-dir --user sentence-transformers==2.2.2 && \
     pip install --no-cache-dir --user "numpy<2.0,>=1.17.3" && \
     pip install --no-cache-dir --user scikit-learn==1.3.2 && \
     pip install --no-cache-dir --user "gensim>=4.3.3" && \
     pip install --no-cache-dir --user "spacy>=3.8.0" && \
     pip install --no-cache-dir --user "arxiv>=1.4.0" && \
     pip install --no-cache-dir --user "optuna>=3.0.0" && \
     pip install --no-cache-dir --user "tensorboard>=2.14.0")

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/storage /app/data /app/logs

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run database migrations and start server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
