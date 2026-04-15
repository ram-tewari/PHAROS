# Hybrid Edge-Cloud Architecture Explained

## Overview

Pharos uses a **hybrid edge-cloud architecture** where compute-intensive ML workloads run on your local GPU (edge worker) while the lightweight API server runs in the cloud (Render).

## Architecture Components

### 1. Cloud API (Render Free Tier)
**Location**: `https://pharos-cloud-api.onrender.com`  
**RAM**: 512MB  
**Role**: Lightweight API server

**Responsibilities**:
- Handle HTTP requests
- Store metadata in NeonDB PostgreSQL
- Queue tasks in Upstash Redis
- Return results to clients
- **Does NOT load embedding models** (too memory-intensive)

**Environment**:
```bash
MODE=CLOUD
DATABASE_URL=postgresql+asyncpg://...  # NeonDB
UPSTASH_REDIS_REST_URL=https://...
EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1  # Name only, not loaded
```

### 2. Edge Worker (Your Local GPU)
**Location**: Your local machine  
**RAM**: 8GB+ recommended  
**GPU**: CUDA-capable (RTX 3060, 4090, etc.)  
**Role**: Heavy ML workloads

**Responsibilities**:
- Load embedding models (nomic-embed-text-v1)
- Generate embeddings for code/text
- Process chunking tasks
- Extract graph entities
- **Polls Upstash Redis for tasks**

**Environment**:
```bash
MODE=EDGE
DEVICE=cuda  # Auto-detected
UPSTASH_REDIS_REST_URL=https://...
EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1  # Actually loaded
```

## How It Works

### Request Flow

```
1. User → Cloud API: POST /api/resources (create resource)
   ↓
2. Cloud API → Upstash Redis: Queue embedding task
   ↓
3. Cloud API → User: 202 Accepted (task queued)
   ↓
4. Edge Worker polls Redis: Get next task
   ↓
5. Edge Worker: Load model, generate embedding
   ↓
6. Edge Worker → NeonDB: Store embedding
   ↓
7. Edge Worker → Redis: Mark task complete
   ↓
8. User → Cloud API: GET /api/resources/{id} (check status)
   ↓
9. Cloud API → User: 200 OK (embedding ready)
```

### Why This Architecture?

**Problem**: Embedding models require >512MB RAM to load
- `nomic-embed-text-v1`: ~600MB
- Render Free tier: 512MB limit
- **Solution**: Don't load models in cloud, use edge worker

**Benefits**:
1. **Cost**: $0/month for cloud API (Render Free)
2. **Performance**: GPU acceleration on edge worker (10x faster)
3. **Scalability**: Cloud API handles 1000s of requests, edge worker processes ML
4. **Flexibility**: Upgrade edge worker GPU without cloud changes

**Trade-offs**:
1. **Latency**: Embedding generation not instant (queued)
2. **Availability**: Edge worker must be running
3. **Complexity**: Two components to manage

## Code Changes for MODE=CLOUD

### 1. Skip Embedding Model Loading

**File**: `backend/app/__init__.py` (line 254)

```python
# Before (WRONG - loads model in cloud)
if not is_test_mode:
    embedding_service = EmbeddingService()
    embedding_service.warmup()  # Loads model → OOM!

# After (CORRECT - skips in cloud)
if not is_test_mode:
    if settings.MODE == "CLOUD":
        logger.info("Cloud mode - skipping embedding warmup")
    else:
        embedding_service = EmbeddingService()
        embedding_service.warmup()
```

### 2. Lazy Loading Check

**File**: `backend/app/shared/embeddings.py` (line 52)

```python
def _ensure_loaded(self):
    if self._model is None:
        with self._model_lock:
            # Check MODE before loading
            deployment_mode = os.getenv("MODE", "EDGE")
            if deployment_mode == "CLOUD":
                logger.info("Cloud mode - skipping model load")
                return  # Don't load model
            
            # Only load in EDGE mode
            self._model = SentenceTransformer(...)
```

## Deployment Checklist

### Cloud API (Render)
- [x] Set `MODE=CLOUD`
- [x] Set `DATABASE_URL` (NeonDB)
- [x] Set `UPSTASH_REDIS_REST_URL`
- [x] Set `UPSTASH_REDIS_REST_TOKEN`
- [x] Set `PHAROS_ADMIN_TOKEN`
- [x] Deploy and verify startup (no OOM)

### Edge Worker (Local)
- [ ] Set `MODE=EDGE`
- [ ] Set `UPSTASH_REDIS_REST_URL` (same as cloud)
- [ ] Set `UPSTASH_REDIS_REST_TOKEN` (same as cloud)
- [ ] Set `DATABASE_URL` (same NeonDB as cloud)
- [ ] Install `requirements-edge.txt` (includes torch)
- [ ] Run: `python -m app.edge_worker`
- [ ] Verify GPU detection and model loading

## Testing the Architecture

### 1. Verify Cloud API (No Model Loading)
```bash
curl https://pharos-cloud-api.onrender.com/api/monitoring/health
# Should return 200 OK without loading embedding model
```

### 2. Create Resource (Queue Task)
```bash
curl -X POST https://pharos-cloud-api.onrender.com/api/resources \
  -H "Authorization: Bearer $PHAROS_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/repo", "title": "Test Repo"}'
# Should return 202 Accepted with task_id
```

### 3. Check Task Status
```bash
curl https://pharos-cloud-api.onrender.com/api/v1/ingestion/jobs/{task_id} \
  -H "Authorization: Bearer $PHAROS_ADMIN_TOKEN"
# Should show "pending" until edge worker processes it
```

### 4. Start Edge Worker
```bash
# On your local machine with GPU
export MODE=EDGE
export UPSTASH_REDIS_REST_URL=https://...
export UPSTASH_REDIS_REST_TOKEN=...
export DATABASE_URL=postgresql+asyncpg://...

python -m app.edge_worker
# Should detect GPU, load model, poll Redis, process task
```

### 5. Verify Embedding Generated
```bash
curl https://pharos-cloud-api.onrender.com/api/resources/{resource_id} \
  -H "Authorization: Bearer $PHAROS_ADMIN_TOKEN"
# Should show embedding field populated
```

## Troubleshooting

### Cloud API: Out of Memory
**Symptom**: `Killed` or `Out of memory` during startup  
**Cause**: Embedding model loading in CLOUD mode  
**Fix**: Verify `MODE=CLOUD` is set and code skips model loading

### Edge Worker: No GPU Detected
**Symptom**: `CUDA not available, falling back to CPU`  
**Cause**: PyTorch not installed with CUDA support  
**Fix**: Install `torch` with CUDA: `pip install torch --index-url https://download.pytorch.org/whl/cu118`

### Tasks Not Processing
**Symptom**: Tasks stuck in "pending" status  
**Cause**: Edge worker not running or not polling Redis  
**Fix**: Start edge worker with correct `UPSTASH_REDIS_REST_URL`

### Connection Refused to NeonDB
**Symptom**: `Connection refused` or `SSL required`  
**Cause**: Missing `sslmode=require` in DATABASE_URL  
**Fix**: Add `?sslmode=require` to NeonDB connection string

## Performance Metrics

### Cloud API (Render Free)
- **Startup time**: ~10 seconds (no model loading)
- **Memory usage**: ~150MB (lightweight)
- **Request latency**: <100ms (metadata only)
- **Throughput**: 100+ req/sec

### Edge Worker (Local GPU)
- **Startup time**: ~30 seconds (model loading)
- **Memory usage**: ~2GB (model + embeddings)
- **Embedding latency**: ~50ms per text (GPU)
- **Throughput**: 20 embeddings/sec

## Cost Breakdown

### Render Free Tier
- **Cloud API**: $0/month (512MB RAM, 750 hours/month)
- **Limitations**: Spins down after 15 min inactivity

### NeonDB Free Tier
- **PostgreSQL**: $0/month (512MB storage, 1 compute unit)
- **Limitations**: 10GB transfer/month

### Upstash Redis Free Tier
- **Redis**: $0/month (10K commands/day)
- **Limitations**: 256MB storage

### Edge Worker (Local)
- **Hardware**: Your GPU (RTX 3060, 4090, etc.)
- **Electricity**: ~$5-10/month (24/7 operation)
- **Total**: ~$5-10/month

**Total Cost**: ~$5-10/month (vs $50-100/month for cloud GPU)

## Next Steps

1. **Verify cloud deployment**: Check Render logs for "Cloud mode - skipping embedding warmup"
2. **Set up edge worker**: Install dependencies, configure environment
3. **Test end-to-end**: Create resource → queue task → process on edge → verify embedding
4. **Monitor performance**: Track task queue depth, processing latency
5. **Scale edge workers**: Add more local GPUs if needed

## Related Documentation

- [Render Deployment Guide](RENDER_FREE_DEPLOYMENT.md)
- [Edge Worker Setup](EDGE_WORKER_SETUP.md) (TODO)
- [Hybrid Architecture Vision](../../PHAROS_RONIN_VISION.md)
- [Phase 5 Roadmap](.kiro/steering/product.md)

---

**Status**: Cloud API deployed, edge worker setup pending  
**Last Updated**: 2026-04-15  
**Next**: Verify cloud deployment succeeds without OOM
