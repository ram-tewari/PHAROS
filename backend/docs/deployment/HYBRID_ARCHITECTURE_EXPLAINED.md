# Hybrid Edge-Cloud Architecture Explained

## Overview

Pharos uses a **hybrid edge-cloud architecture** where compute-intensive ML workloads run on your local GPU (edge worker) while the lightweight API server runs in the cloud (Render).

## Architecture Components

### 1. Cloud API (Render Starter)
**Location**: `https://pharos-cloud-api.onrender.com`  
**RAM**: 512MB  
**Role**: Lightweight API server

**Responsibilities**:
- Handle HTTP requests from Ronin
- Store metadata in NeonDB PostgreSQL
- Queue ingestion tasks in Upstash Redis
- For search queries: call `EDGE_EMBEDDING_URL/embed` (Tailscale Funnel) to get query embeddings, then run **pgvector HNSW cosine similarity** against `resources.embedding` in NeonDB (never pure-Python cosine — that O(N) path was removed in 2026-04-24)
- **Does NOT load embedding models** (would OOM the 512 MB instance)

**Environment**:
```bash
MODE=CLOUD
DATABASE_URL=postgresql+asyncpg://...       # NeonDB
UPSTASH_REDIS_REST_URL=https://...
EDGE_EMBEDDING_URL=https://<machine>.<tailnet>.ts.net   # Tailscale Funnel URL
```

### 2. Edge Worker (Your Local GPU) — Two Processes

**Location**: Your local machine (RTX 4070)  
**Role**: All ML compute

#### 2a. Ingestion Worker (`app.edge_worker`)

- Polls Upstash Redis for ingestion tasks
- Fetches content, generates document embeddings, stores in NeonDB
- Runs as NSSM service `PharosEdgeWorker`

#### 2b. Embedding HTTP Server (`embed_server.py`)

- Exposes `POST /embed {"text":"…"} → {"embedding":[…]}` on port 8001
- Loaded model: `nomic-ai/nomic-embed-text-v1` (768-dim, CUDA)
- Tailscale Funnel proxies `https://<machine>.<tailnet>.ts.net → 127.0.0.1:8001`
- Called synchronously by the cloud API during search queries
- Runs as NSSM service `PharosEmbedServer`

**Environment** (both processes):
```bash
MODE=EDGE
EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1
UPSTASH_REDIS_REST_URL=https://...    # ingestion worker only
DATABASE_URL=postgresql+asyncpg://... # ingestion worker only
```

### 3. Tailscale Funnel

Provides a stable public HTTPS hostname for the embed server at no cost.
The Tailscale daemon (`tailscaled`) runs as a Windows service (installed
automatically by the Tailscale installer). Funnel routing persists in
`tailscaled` state and survives reboots without a separate service.

## How It Works

### Ingestion Flow (async, background)

```
1. Ronin → Cloud API: POST /api/resources (add resource)
   ↓
2. Cloud API → Upstash Redis: Queue ingestion task
   ↓
3. Cloud API → Ronin: 202 Accepted
   ↓
4. Edge ingestion worker polls Redis: dequeues task
   ↓
5. Edge worker: fetch content, generate document embedding (GPU)
   ↓
6. Edge worker → NeonDB: store embedding vector
   ↓
7. Edge worker → Redis: mark task complete
```

### Search / Query Flow (synchronous, on every search)

```
1. Ronin → Cloud API: POST /api/search (query text)
   ↓
2. Cloud API → Tailscale Funnel: POST /embed {"text": query}  [5s timeout]
   ↓
3. Tailscale Funnel → embed_server (127.0.0.1:8001): forward request
   ↓
4. embed_server: encode query with nomic-embed-text-v1 (GPU, ~50ms)
   ↓
5. embed_server → Cloud API: {"embedding": [768 floats]}
   ↓
6. Cloud API: cosine similarity against NeonDB stored vectors
   ↓
7. Cloud API → Ronin: ranked search results
```

If Tailscale Funnel is unreachable, step 2 raises HTTP 503 — the error
propagates to Ronin rather than silently returning zero results.

### Why This Architecture?

**Problem**: Embedding models require >512 MB RAM to load
- `nomic-embed-text-v1`: ~600 MB
- Render Starter: 512 MB limit
- **Solution**: Load model on local GPU; expose via Tailscale Funnel

**Benefits**:
1. **Cost**: $0 for compute — local RTX 4070 handles all ML
2. **Latency**: GPU embedding ~50 ms vs. ~500 ms on CPU
3. **Correctness**: Query and document embeddings always use the same model
4. **Simplicity**: No hosted embedding API, no API key, no per-request cost

**Trade-offs**:
1. **Laptop dependency**: Search requires laptop to be on and Funnel reachable
2. **Cold start**: First search after laptop sleep takes ~5 s (model already loaded; just NSSM restart warmup)
3. **Funnel latency**: ~20–80 ms network round-trip (acceptable within 800 ms budget)

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
- [ ] Set `EDGE_EMBEDDING_URL=https://<machine>.<tailnet>.ts.net` (after Funnel live)
- [x] Deploy and verify startup (no OOM)

### Edge — Ingestion Worker (Local, NSSM: PharosEdgeWorker)
- [ ] Set `MODE=EDGE` in `.env.edge`
- [ ] Set `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN`
- [ ] Set `DATABASE_URL` (same NeonDB)
- [ ] Install `requirements-edge.txt`
- [ ] Install NSSM service `PharosEdgeWorker`
- [ ] Verify GPU detection and model loading in logs

### Edge — Embedding HTTP Server (Local, NSSM: PharosEmbedServer)
- [ ] Install NSSM service `PharosEmbedServer` (runs `embed_server.py`)
- [ ] Verify `GET /health` returns `{"status":"ok"}` on 127.0.0.1:8001

### Tailscale Funnel
- [ ] Install Tailscale for Windows; sign in with GitHub (ram-tewari)
- [ ] Enable `funnel` node attribute in admin console
- [ ] Run `tailscale funnel 8001`
- [ ] Reboot; verify `tailscale funnel status` shows port 8001
- [ ] Set `EDGE_EMBEDDING_URL` in Render dashboard
- [ ] Verify: `curl https://<host>.ts.net/embed -d '{"text":"test"}'` returns 768-float vector

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

### Search returns HTTP 503 "embedding service unreachable"
**Cause**: Cloud API cannot reach `EDGE_EMBEDDING_URL`  
**Fix checklist**:
1. Is `PharosEmbedServer` running? Check `nssm status PharosEmbedServer`
2. Does `curl http://127.0.0.1:8001/health` return `{"status":"ok"}`?
3. Is Tailscale signed in? `tailscale status`
4. Is Funnel active? `tailscale funnel status` — should show port 8001
5. Is `EDGE_EMBEDDING_URL` set correctly in Render (no trailing slash)?

### Search returns HTTP 503 "EDGE_EMBEDDING_URL not configured"
**Cause**: Render env var not set  
**Fix**: Add `EDGE_EMBEDDING_URL=https://<machine>.<tailnet>.ts.net` in Render dashboard

### Cloud API: Out of Memory at startup
**Symptom**: `Killed` or `Out of memory` during startup  
**Cause**: Embedding model loading in CLOUD mode  
**Fix**: Verify `MODE=CLOUD` is set — the `_ensure_loaded()` guard skips model loading in CLOUD mode

### Ingestion tasks not processing
**Symptom**: Tasks stuck in pending status  
**Cause**: `PharosEdgeWorker` not running or not polling Redis  
**Fix**: `nssm start PharosEdgeWorker`; check logs at `backend/edge_worker.log`

### Edge worker: no GPU detected
**Symptom**: `CUDA not available, falling back to CPU`  
**Fix**: `pip install torch --index-url https://download.pytorch.org/whl/cu118`

### Connection refused to NeonDB
**Symptom**: `Connection refused` or `SSL required`  
**Fix**: Add `?sslmode=require` to NeonDB `DATABASE_URL`

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

## Production Status (2026-04-24)

### ✅ Fully Operational

**Cloud API**: https://pharos-cloud-api.onrender.com
- Render Starter ($7/mo)
- NeonDB PostgreSQL (free tier, 500MB)
- Upstash Redis (free tier, 10k req/day)
- pgvector search: 1.8-1.9s latency
- GitHub code fetching: <100ms (cached)

**Edge Worker**: WSL2 + RTX 4070
- Tailscale Funnel: `https://pc.tailf7b210.ts.net`
- nomic-embed-text-v1 (768-dim)
- ~1.5s per embedding (GPU-accelerated)
- BLPOP 9s (Upstash free-tier safe)

**Search Quality**: 8.5-9/10 for Ronin context retrieval
- 3,293 searchable files (langchain corpus)
- Test file downweighting (0.10 penalty)
- Semantic summary embeddings (not JSON blob)
- Pinecone discovery fixed (0 → #2 ranked)

### Recent Improvements (2026-04-24)

1. **pgvector for parent-child search**
   - Replaced O(N) Python cosine with HNSW index
   - 40% latency reduction (2.7-4.7s → 1.8-1.9s)
   - Scalable to 10K+ files

2. **Test file downweighting**
   - 0.10 distance penalty for `/tests/` paths
   - Reduced test file dominance (4/5 → 1/5 in top-5)
   - No over-correction on test-intent queries

3. **Embed semantic_summary (not JSON blob)**
   - Spread score distribution meaningfully
   - Fixed vendor-specific discovery (pinecone)
   - Faster embedding (shorter text)

4. **Ingestion path normalization**
   - POSIX paths in github_uri (no backslashes)
   - HEAD ref for default branch resolution
   - CAST embeddings to vector(768) for asyncpg

5. **Free-tier compliance**
   - BLPOP 9s → ~8.6k Upstash req/day (under 10k limit)
   - Redis cache for GitHub fetches (1h TTL)
   - Hybrid storage: 17x reduction (100GB → 6GB)

### Benchmark Results

**8-Query Evaluation** (langchain corpus):

| Query | Top-1 | Score | Status |
|-------|-------|-------|--------|
| OpenAI chat streaming | chat_models/base.py | 0.620 | ✅ Exact |
| retry exponential backoff | runnables/retry.py | 0.488 | ✅ Better impl |
| token counting | summarization.py | 0.576 | ⚠️ Uses it |
| custom tool agent | tool_calling_agent/base.py | 0.597 | ✅ Perfect |
| pinecone vector store | vectorstores/pinecone.py | 0.561 | 🎯 Fixed |
| fake LLM mock | tests/.../fake_llm.py | 0.576 | ✅ Literal |
| recursive text splitter | character.py | 0.715 | ✅ Highest |
| async batch embeddings | mistralai/embeddings.py | 0.634 | ✅ Strong |

**Infrastructure**: 100% success rate, 0 errors, 1.8-1.9s avg latency

---

**Status**: ✅ Production  
**Last Updated**: 2026-04-24  
**Cost**: $7/mo (Render Starter only)  
**Next**: Add filtered imports to semantic_summary (optional enhancement)
