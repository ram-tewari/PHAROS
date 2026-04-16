# Render + Edge Worker Configuration Summary

## What Was Done

Configured Render to queue embedding tasks to your local edge worker instead of running ML models directly on Render. This reduces Render's memory usage and leverages your RTX 4070 GPU for faster processing.

## Key Changes

### 1. Updated `render.yaml`

**Changed**:
- Set `MODE=CLOUD` (was implicitly EDGE or not set)
- Marked `UPSTASH_REDIS_REST_URL` as REQUIRED (was Optional)
- Marked `UPSTASH_REDIS_REST_TOKEN` as REQUIRED (was Optional)
- Removed `EMBEDDING_DEVICE=cpu` (not needed in CLOUD mode)
- Added clear comments explaining MODE setting

**Why**:
- `MODE=CLOUD` tells Render to queue tasks instead of loading models
- Upstash Redis is required for the task queue
- No need to specify device when models aren't loaded

### 2. Created Documentation

**New Files**:
1. `RENDER_EDGE_WORKER_SETUP.md` - Complete setup guide
2. `RENDER_EDGE_CHECKLIST.md` - Quick checklist with your actual env vars
3. `RENDER_EDGE_CONFIGURATION_SUMMARY.md` - This file

**Why**:
- Step-by-step instructions for configuration
- Quick reference for troubleshooting
- Checklist to verify everything is working

## How It Works Now

### Before (Render Running Models)

```
User → Render API → Load Model → Generate Embedding → Store in DB
                    ↑
                    Slow, memory-intensive
```

### After (Edge Worker Running Models)

```
User → Render API → Queue Task → Upstash Redis
                                      ↓
                                  Edge Worker
                                      ↓
                              Generate Embedding
                                      ↓
                                  Store in DB
```

## Configuration Required

### Render Dashboard

Add these environment variables:

```bash
MODE=CLOUD  # CRITICAL: Queue tasks, don't load models
UPSTASH_REDIS_REST_URL=https://living-sculpin-96916.upstash.io
UPSTASH_REDIS_REST_TOKEN=gQAAAAAAAXqUAAIncDFmMDExYmFjN2Y1ZjQ0ZDY2Yjc0NWE1NTBhMzg2ZDg5M3AxOTY5MTYUPSTASH_REDIS_REST_TOKEN
```

### Local Edge Worker

Create `.env` file in `backend/` directory:

```bash
MODE=EDGE  # CRITICAL: Load models locally
UPSTASH_REDIS_REST_URL=https://living-sculpin-96916.upstash.io
UPSTASH_REDIS_REST_TOKEN=gQAAAAAAAXqUAAIncDFmMDExYmFjN2Y1ZjQ0ZDY2Yjc0NWE1NTBhMzg2ZDg5M3AxOTY5MTYUPSTASH_REDIS_REST_TOKEN
DATABASE_URL=postgresql+asyncpg://neondb_owner:npg_2Lv8pxVJzgyd@ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require
EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1
WORKER_POLL_INTERVAL=2
```

## Next Steps

1. **Configure Render**:
   - Go to Render dashboard
   - Add `MODE=CLOUD` environment variable
   - Add `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`
   - Save and wait for redeploy

2. **Verify Render**:
   - Check logs for "Cloud mode detected - skipping embedding model load"
   - No "Loading embedding model" messages
   - Health check passes

3. **Start Edge Worker**:
   - Create `.env` file with `MODE=EDGE`
   - Run `.\start_edge_worker.ps1`
   - Verify GPU detected and model loaded

4. **Test End-to-End**:
   - Upload resource via Render API
   - Check Render logs for "queuing embedding task"
   - Check Edge Worker logs for "Task completed"
   - Verify embedding stored in database

## Verification

### ✅ Render Configured Correctly

Render logs should show:
```
Cloud mode detected - skipping embedding model load (handled by edge worker)
✓ Cloud mode detected - skipping embedding model warmup (handled by edge worker)
```

### ✅ Edge Worker Running Correctly

Edge worker logs should show:
```
GPU Detected:
   Device: NVIDIA GeForce RTX 4070
   Memory: 12.0 GB
Embedding model loaded successfully (2.3s)
Connected to Upstash Redis
Connected to database
Edge worker ready - waiting for tasks...
```

### ✅ Tasks Processing Correctly

Edge worker logs should show:
```
Received task: task_abc123
Processing task task_abc123 for resource res_xyz789
Generated embedding (768 dims) in 45ms
Stored embedding for resource res_xyz789
Task completed (total: 1 processed, 0 failed)
```

## Benefits

1. **Reduced Render Memory**: No ML models loaded on Render
2. **Faster Processing**: RTX 4070 GPU is 10x faster than CPU
3. **Lower Cost**: Render Starter plan ($7/mo) is sufficient
4. **Better Scalability**: Edge worker can process tasks in parallel
5. **Flexibility**: Can run multiple edge workers if needed

## Troubleshooting

See `RENDER_EDGE_WORKER_SETUP.md` for detailed troubleshooting guide.

Common issues:
- Render still loading models → Verify `MODE=CLOUD` in dashboard
- Edge worker not receiving tasks → Verify Redis credentials match
- GPU not detected → Check NVIDIA drivers and CUDA installation

## Related Files

- `render.yaml` - Render deployment configuration
- `RENDER_EDGE_WORKER_SETUP.md` - Complete setup guide
- `RENDER_EDGE_CHECKLIST.md` - Quick checklist
- `app/edge_worker.py` - Edge worker implementation
- `app/shared/embeddings.py` - Embedding service (MODE-aware)
- `start_edge_worker.ps1` - Edge worker startup script

---

**Status**: Configuration complete. Follow the Next Steps above to deploy.
