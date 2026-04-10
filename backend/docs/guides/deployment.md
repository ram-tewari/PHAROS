# Deployment Guide

## Overview

Pharos uses a hybrid edge-cloud architecture (Phase 19) that splits the backend into two complementary components:

- **Cloud API (Render)**: Lightweight control plane for orchestration
- **Edge Worker (Local)**: GPU-accelerated compute plane for ML operations

## Quick Start

### Cloud Deployment (Render)

1. **Prerequisites**:
   - GitHub repository connected to Render
   - Environment variables configured in Render dashboard
   - Neon Postgres, Qdrant Cloud, Upstash Redis accounts

2. **Deploy**:
   ```bash
   git push origin master
   # Render auto-deploys from master branch
   ```

3. **Verify**:
   ```bash
   curl https://pharos.onrender.com/health
   ```

### Edge Worker (Local)

1. **Setup**:
   ```bash
   cd backend
   pip install -r requirements-edge.txt
   cp .env.edge.template .env
   # Edit .env with your credentials
   ```

2. **Run**:
   ```bash
   python worker.py
   ```

3. **Verify**:
   - Check for "Edge Worker Online" message
   - Verify GPU detection: "Hardware: NVIDIA GeForce RTX 4070"

## Configuration

### Environment Variables

**Cloud API** (`.env.cloud.template`):
```bash
MODE=CLOUD
DATABASE_URL=postgresql://...  # Neon Postgres
QDRANT_URL=https://...         # Qdrant Cloud
QDRANT_API_KEY=...
UPSTASH_REDIS_REST_URL=...
UPSTASH_REDIS_REST_TOKEN=...
PHAROS_ADMIN_TOKEN=...         # For ingestion auth
```

**Edge Worker** (`.env.edge.template`):
```bash
MODE=EDGE
UPSTASH_REDIS_REST_URL=...
UPSTASH_REDIS_REST_TOKEN=...
QDRANT_URL=https://...
QDRANT_API_KEY=...
```

### Deployment Modes

The application uses `MODE` environment variable to determine which modules to load:

- **CLOUD**: Lightweight API, skips torch-dependent modules (recommendations)
- **EDGE**: Full ML stack with torch, transformers, and graph neural networks

## Architecture

### Cloud API (Render Free Tier)

**Resources**:
- 512MB RAM
- 0.1 CPU
- PostgreSQL (Neon)
- Vector DB (Qdrant Cloud)
- Redis (Upstash)

**Modules Loaded**:
- ✓ Core: collections, resources, search
- ✓ Features: annotations, scholarly, authority, curation
- ✓ ML: quality, taxonomy, graph
- ✓ Auth: JWT authentication
- ✓ Ingestion: Task dispatch
- ✗ Recommendations: Requires torch (skipped)

**Endpoints**:
- `GET /health` - Health check
- `GET /docs` - API documentation
- `POST /api/v1/ingestion/ingest/{repo_url}` - Dispatch ingestion task
- `GET /api/v1/ingestion/worker/status` - Worker status
- All other module endpoints

### Edge Worker (Local GPU)

**Resources**:
- GPU: NVIDIA RTX 4070 (or any CUDA-capable GPU)
- RAM: 8GB+ recommended
- Storage: 10GB+ for models

**Capabilities**:
- Repository cloning and parsing
- Dependency graph construction
- Node2Vec training on GPU
- Structural embedding generation
- Batch upload to Qdrant

**Task Flow**:
1. Poll Redis queue every 2 seconds
2. Clone repository
3. Parse source files with Tree-sitter
4. Build dependency graph
5. Train Node2Vec on GPU
6. Upload embeddings to Qdrant
7. Update job status

## Deployment Fixes (January 2026)

### Issue: Missing Dependencies

**Problem**: Cloud deployment failed with:
```
ModuleNotFoundError: No module named 'torch'
ModuleNotFoundError: No module named 'redis'
```

**Root Cause**: Application tried to load ALL modules including torch-dependent ones in cloud environment.

**Solution**:
1. Made redis imports optional with graceful degradation
2. Added `redis==5.2.1` to `requirements-base.txt`
3. Made torch imports optional in recommendations module
4. Implemented conditional module loading based on MODE

**Files Modified**:
- `app/shared/cache.py` - Optional redis import
- `app/__init__.py` - MODE-based module loading
- `app/modules/recommendations/collaborative.py` - Optional torch
- `requirements-base.txt` - Added redis dependency

## Monitoring

### Health Checks

**Cloud API**:
```bash
# Basic health
curl https://pharos.onrender.com/health

# Worker status
curl https://pharos.onrender.com/api/v1/ingestion/worker/status
```

**Edge Worker**:
- Check console output for status messages
- Monitor Redis `worker_status` key
- Check `job_history` list for completed jobs

### Logs

**Cloud API**:
- View in Render dashboard: https://dashboard.render.com/
- Look for: "Deployment mode: CLOUD"
- Verify: No torch import errors

**Edge Worker**:
- Console output shows real-time progress
- Status updates: "Training Graph on {repo_url}"
- Completion: "Job Complete (X.XXs)"

## Troubleshooting

### Cloud API Won't Start

1. Check Render logs for import errors
2. Verify MODE=CLOUD in environment variables
3. Ensure all cloud services (Neon, Qdrant, Upstash) are accessible
4. Check that torch-dependent modules are being skipped

### Edge Worker Can't Connect

1. Verify Redis credentials in `.env`
2. Check network connectivity to Upstash
3. Ensure CUDA is available: `python -c "import torch; print(torch.cuda.is_available())"`
4. Verify Qdrant credentials

### Tasks Not Processing

1. Check Redis queue: `redis-cli LLEN ingest_queue`
2. Verify worker is running and polling
3. Check worker status: `GET /api/v1/ingestion/worker/status`
4. Review job history: `GET /api/v1/ingestion/jobs/history`

### GPU Not Detected

1. Install CUDA toolkit: https://developer.nvidia.com/cuda-downloads
2. Install PyTorch with CUDA: `pip install torch --index-url https://download.pytorch.org/whl/cu118`
3. Verify: `nvidia-smi` shows GPU
4. Test: `python -c "import torch; print(torch.cuda.get_device_name(0))"`

## Security

### Required Secrets

**Critical Security Configuration**:

The following environment variables must be set in production:

| Variable | Description | Requirements |
|----------|-------------|--------------|
| `JWT_SECRET_KEY` | JWT signing key | Minimum 32 characters, cryptographically random |
| `POSTGRES_PASSWORD` | PostgreSQL password | Strong password, minimum 16 characters |
| `PHAROS_ADMIN_TOKEN` | API ingestion token | Minimum 32 characters, cryptographically random |

**Generating Secure Secrets**:

```bash
# Generate JWT secret (Linux/macOS)
openssl rand -hex 32

# Generate JWT secret (Python)
python -c "import secrets; print(secrets.token_hex(32))"

# Generate admin token
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Authentication

**Ingestion Endpoint**:
- Requires Bearer token authentication
- Set `PHAROS_ADMIN_TOKEN` in environment
- Include in requests: `Authorization: Bearer $PHAROS_ADMIN_TOKEN`

**Rate Limiting**:
- Queue cap: 10 pending tasks maximum
- Task TTL: 24 hours
- Prevents zombie queue problem

### Best Practices

1. **Never commit** `.env` files to git
2. **Rotate tokens** regularly
3. **Use HTTPS** for all external services
4. **Monitor logs** for authentication failures
5. **Limit queue size** to prevent abuse
6. **Validate secrets** at startup - app will fail if secrets are not set in production

## Performance

### Cloud API

- Response time: P95 < 200ms
- Concurrent requests: 100+ req/sec
- Database queries: < 100ms
- Memory usage: < 400MB

### Edge Worker

- Training time: ~30-60s per repository
- GPU utilization: 80-90% during training
- Memory usage: 2-4GB
- Embeddings: 64-dimensional vectors

## Scaling

### Horizontal Scaling

**Edge Workers**:
- Run multiple workers on different machines
- Each polls the same Redis queue
- Automatic load distribution

**Cloud API**:
- Render handles auto-scaling
- Free tier: Single instance
- Paid tiers: Multiple instances with load balancing

### Vertical Scaling

**Edge Workers**:
- Upgrade GPU for faster training
- Increase RAM for larger repositories
- Add SSD for faster cloning

**Cloud API**:
- Upgrade Render plan for more resources
- Scale database (Neon) for more connections
- Scale Qdrant for more vectors

## Related Documentation

- [Phase 19 Architecture](../architecture/phase19-hybrid.md)
- [Edge Setup Guide](phase19-edge-setup.md)
- [Monitoring Guide](phase19-monitoring.md)
- [API Reference](../api/ingestion.md)
- [Requirements Strategy](../../REQUIREMENTS_STRATEGY.md)
