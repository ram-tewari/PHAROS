# Render + Edge Worker Configuration Checklist

## Quick Setup Checklist

### ✅ Render Configuration

- [ ] Set `MODE=CLOUD` in Render dashboard
- [ ] Set `UPSTASH_REDIS_REST_URL` in Render dashboard
- [ ] Set `UPSTASH_REDIS_REST_TOKEN` in Render dashboard
- [ ] Set `DATABASE_URL` (NeonDB pooled connection)
- [ ] Set `PHAROS_ADMIN_TOKEN`
- [ ] Set `JWT_SECRET_KEY`
- [ ] Verify other env vars from your `.env` file
- [ ] Save changes and wait for redeploy

### ✅ Verify Render Deployment

- [ ] Check logs for "Cloud mode detected - skipping embedding model load"
- [ ] No "Loading embedding model" messages in logs
- [ ] Health check passes: `curl https://pharos-api.onrender.com/health`
- [ ] API docs accessible: https://pharos-api.onrender.com/docs

### ✅ Edge Worker Configuration

- [ ] Create `.env` file in `backend/` directory
- [ ] Set `MODE=EDGE` in `.env`
- [ ] Set `UPSTASH_REDIS_REST_URL` (SAME as Render)
- [ ] Set `UPSTASH_REDIS_REST_TOKEN` (SAME as Render)
- [ ] Set `DATABASE_URL` (SAME as Render)
- [ ] Set `EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1`
- [ ] Set `WORKER_POLL_INTERVAL=2`

### ✅ Start Edge Worker

- [ ] Open PowerShell as Administrator
- [ ] Navigate to `backend/` directory
- [ ] Run `.\start_edge_worker.ps1`
- [ ] Verify GPU detected in logs
- [ ] Verify "Embedding model loaded successfully"
- [ ] Verify "Connected to Upstash Redis"
- [ ] Verify "Connected to database"
- [ ] See "Edge worker ready - waiting for tasks..."

### ✅ Test End-to-End

- [ ] Upload test resource via Render API
- [ ] Check Render logs for "queuing embedding task"
- [ ] Check Edge Worker logs for "Received task"
- [ ] Check Edge Worker logs for "Task completed"
- [ ] Verify resource has embedding in database
- [ ] Check task status in Upstash dashboard

## Environment Variable Reference

### Render Dashboard (MODE=CLOUD)

```bash
MODE=CLOUD
UPSTASH_REDIS_REST_URL=https://living-sculpin-96916.upstash.io
UPSTASH_REDIS_REST_TOKEN=gQAAAAAAAXqUAAIncDFmMDExYmFjN2Y1ZjQ0ZDY2Yjc0NWE1NTBhMzg2ZDg5M3AxOTY5MTYUPSTASH_REDIS_REST_TOKEN
DATABASE_URL=postgresql+asyncpg://neondb_owner:npg_2Lv8pxVJzgyd@ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require
PHAROS_ADMIN_TOKEN=4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74
JWT_SECRET_KEY=11a7da6fb545fc0d8d2ddd0ee03be15672799fa57128e0e55328d8750483bd79
EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1
GRAPH_EXTRACTION_ENABLED=true
SYNTHETIC_QUESTIONS_ENABLED=false
CHUNK_ON_RESOURCE_CREATE=false
MAX_WORKERS=2
MAX_QUEUE_SIZE=10
TASK_TTL_SECONDS=3600
ENV=prod
ALLOWED_REDIRECT_URLS='["https://pharos-cloud-api.onrender.com"]'
```

### Local .env (MODE=EDGE)

```bash
MODE=EDGE
UPSTASH_REDIS_REST_URL=https://living-sculpin-96916.upstash.io
UPSTASH_REDIS_REST_TOKEN=gQAAAAAAAXqUAAIncDFmMDExYmFjN2Y1ZjQ0ZDY2Yjc0NWE1NTBhMzg2ZDg5M3AxOTY5MTYUPSTASH_REDIS_REST_TOKEN
DATABASE_URL=postgresql+asyncpg://neondb_owner:npg_2Lv8pxVJzgyd@ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require
EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1
WORKER_POLL_INTERVAL=2
```

## Common Issues

### ❌ Render Still Loading Models

**Check**: Render logs show "Loading embedding model..."

**Fix**: 
1. Verify `MODE=CLOUD` in Render dashboard
2. Redeploy Render service
3. Check logs for "Cloud mode detected"

### ❌ Edge Worker Not Receiving Tasks

**Check**: Edge worker shows "No tasks available"

**Fix**:
1. Verify `UPSTASH_REDIS_REST_URL` matches between Render and edge worker
2. Verify `UPSTASH_REDIS_REST_TOKEN` matches
3. Check Upstash dashboard for queue depth

### ❌ GPU Not Detected

**Check**: Edge worker shows "CUDA not available"

**Fix**:
1. Run `nvidia-smi` to check drivers
2. Run `python test_gpu.py` to verify PyTorch CUDA
3. Reinstall PyTorch with CUDA if needed

## Success Indicators

### ✅ Render (Cloud Mode)

```
Cloud mode detected - skipping embedding model load (handled by edge worker)
✓ Cloud mode detected - skipping embedding model warmup (handled by edge worker)
```

### ✅ Edge Worker (Edge Mode)

```
GPU Detected:
   Device: NVIDIA GeForce RTX 4070
   Memory: 12.0 GB
Embedding model loaded successfully (2.3s)
Connected to Upstash Redis
Connected to database
Edge worker ready - waiting for tasks...
```

### ✅ Task Processing

```
Received task: task_abc123
Processing task task_abc123 for resource res_xyz789
Generated embedding (768 dims) in 45ms
Stored embedding for resource res_xyz789
Task completed (total: 1 processed, 0 failed)
```

## Quick Commands

### Test Render Health
```bash
curl https://pharos-cloud-api.onrender.com/health
```

### Test Upstash Connection
```bash
curl https://living-sculpin-96916.upstash.io/ping \
  -H "Authorization: Bearer gQAAAAAAAXqUAAIncDFmMDExYmFjN2Y1ZjQ0ZDY2Yjc0NWE1NTBhMzg2ZDg5M3AxOTY5MTYUPSTASH_REDIS_REST_TOKEN"
```

### Check Queue Depth
```bash
curl https://living-sculpin-96916.upstash.io/llen/embedding_tasks \
  -H "Authorization: Bearer gQAAAAAAAXqUAAIncDFmMDExYmFjN2Y1ZjQ0ZDY2Yjc0NWE1NTBhMzg2ZDg5M3AxOTY5MTYUPSTASH_REDIS_REST_TOKEN"
```

### Monitor GPU
```bash
nvidia-smi -l 1
```

---

**Status**: Ready to deploy! Follow the checklist above to configure Render and start the edge worker.
