# Render + Edge Worker Setup Guide

## Overview

This guide explains how to configure Render to queue embedding tasks to your local edge worker instead of running models directly on Render.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     HYBRID EDGE-CLOUD ARCHITECTURE              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐                           ┌──────────────┐   │
│  │   Render     │      Upstash Redis        │ Local Edge   │   │
│  │  Cloud API   │◄────► Task Queue ◄────────┤   Worker     │   │
│  │  (MODE=CLOUD)│                           │ (MODE=EDGE)  │   │
│  │              │                           │ RTX 4070 GPU │   │
│  └──────────────┘                           └──────────────┘   │
│         │                                           │           │
│         │                                           │           │
│         └───────────────┬───────────────────────────┘           │
│                         │                                       │
│                         ▼                                       │
│                  ┌──────────────┐                               │
│                  │   NeonDB     │                               │
│                  │  PostgreSQL  │                               │
│                  └──────────────┘                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## How It Works

1. **User uploads resource** → Render API receives request
2. **Render queues task** → Pushes embedding task to Upstash Redis
3. **Edge worker polls** → Detects new task in queue
4. **Edge worker processes** → Generates embedding using local GPU
5. **Edge worker stores** → Saves embedding to NeonDB
6. **Edge worker updates** → Marks task as completed in Redis
7. **Render returns** → API returns success to user

## Key Configuration

### Render Environment Variables

Set these in the Render dashboard:

```bash
# CRITICAL: Set MODE to CLOUD (not EDGE)
MODE=CLOUD

# Upstash Redis (REQUIRED for task queue)
UPSTASH_REDIS_REST_URL=https://your-redis.upstash.io
UPSTASH_REDIS_REST_TOKEN=your-token-here

# Database (shared with edge worker)
DATABASE_URL=postgresql://...

# Other settings from your .env
PHAROS_ADMIN_TOKEN=...
JWT_SECRET_KEY=...
# ... etc
```

### Edge Worker Environment Variables

Your local `.env` file should have:

```bash
# CRITICAL: Set MODE to EDGE (not CLOUD)
MODE=EDGE

# Upstash Redis (SAME as Render)
UPSTASH_REDIS_REST_URL=https://your-redis.upstash.io
UPSTASH_REDIS_REST_TOKEN=your-token-here

# Database (SAME as Render)
DATABASE_URL=postgresql://...

# Embedding model
EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1

# Worker settings
WORKER_POLL_INTERVAL=2  # Poll every 2 seconds
```

## Step-by-Step Setup

### Step 1: Configure Render

1. Go to your Render dashboard
2. Select your `pharos-api` service
3. Go to "Environment" tab
4. Add/update these variables:

```
MODE = CLOUD
UPSTASH_REDIS_REST_URL = <from Upstash dashboard>
UPSTASH_REDIS_REST_TOKEN = <from Upstash dashboard>
```

5. Click "Save Changes"
6. Render will automatically redeploy

### Step 2: Verify Render Configuration

Check that Render is NOT loading embedding models:

```bash
# Check Render logs
curl https://pharos-api.onrender.com/health

# Should see:
# "Cloud mode detected - skipping embedding model load (handled by edge worker)"
```

### Step 3: Start Edge Worker

On your local machine:

```powershell
# Navigate to backend directory
cd backend

# Start edge worker
.\start_edge_worker.ps1
```

You should see:

```
========================================
Pharos Edge Worker - Local GPU Processing
========================================
Environment variables validated
GPU Detected:
   Device: NVIDIA GeForce RTX 4070
   Memory: 12.0 GB
   CUDA Version: 12.1
   PyTorch Version: 2.1.0
Loading embedding model...
Embedding model loaded successfully (2.3s)
Connecting to Upstash Redis...
Connected to Upstash Redis
Connecting to database...
   Database: ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech
Connected to database
========================================
Edge worker ready - waiting for tasks...
========================================
Starting task polling (interval: 2s)
Press Ctrl+C to stop
```

### Step 4: Test End-to-End

1. **Upload a resource via Render API**:

```bash
curl -X POST https://pharos-api.onrender.com/api/resources \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "title": "Test Resource",
    "description": "Testing edge worker integration",
    "url": "https://example.com"
  }'
```

2. **Check Render logs** (should see):
```
Cloud mode detected - queuing embedding task to edge worker
Task queued: task_abc123
```

3. **Check Edge Worker logs** (should see):
```
Received task: task_abc123
Processing task task_abc123 for resource res_xyz789
Generated embedding (768 dims) in 45ms
Stored embedding for resource res_xyz789
Task completed (total: 1 processed, 0 failed)
```

4. **Verify in database**:
```bash
# Check that resource has embedding
curl https://pharos-api.onrender.com/api/resources/res_xyz789
# Should have "embedding": [0.123, 0.456, ...]
```

## Troubleshooting

### Issue 1: Render Still Loading Models

**Symptoms**:
- Render logs show "Loading embedding model..."
- High memory usage on Render
- Slow startup times

**Solution**:
1. Verify `MODE=CLOUD` in Render dashboard
2. Redeploy Render service
3. Check logs for "Cloud mode detected"

### Issue 2: Edge Worker Not Receiving Tasks

**Symptoms**:
- Edge worker shows "No tasks available"
- Tasks stuck in "pending" status
- Embeddings not generated

**Solution**:
1. Verify `UPSTASH_REDIS_REST_URL` matches between Render and edge worker
2. Verify `UPSTASH_REDIS_REST_TOKEN` matches
3. Check Upstash dashboard for queue depth
4. Test Redis connection:
```bash
curl https://your-redis.upstash.io/ping \
  -H "Authorization: Bearer your-token"
```

### Issue 3: Database Connection Errors

**Symptoms**:
- Edge worker can't connect to database
- "OperationalError: could not connect to server"

**Solution**:
1. Verify `DATABASE_URL` is correct (same as Render)
2. Check NeonDB is not suspended (wake it up)
3. Verify SSL mode: `?sslmode=require`
4. Test connection:
```bash
psql $DATABASE_URL -c "SELECT 1"
```

### Issue 4: GPU Not Detected

**Symptoms**:
- Edge worker shows "CUDA not available"
- Falling back to CPU
- Slow embedding generation

**Solution**:
1. Check NVIDIA drivers: `nvidia-smi`
2. Check CUDA installation: `nvcc --version`
3. Check PyTorch CUDA: `python -c "import torch; print(torch.cuda.is_available())"`
4. Reinstall PyTorch with CUDA:
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

## Performance Metrics

### Expected Performance

| Metric | Value |
|--------|-------|
| Task queue latency | <100ms |
| Edge worker poll interval | 2s |
| Embedding generation (GPU) | 40-60ms |
| Embedding generation (CPU) | 200-400ms |
| Database write | 50-100ms |
| End-to-end latency | 2-5s |

### Monitoring

**Check queue depth**:
```bash
curl https://your-redis.upstash.io/llen/embedding_tasks \
  -H "Authorization: Bearer your-token"
```

**Check task status**:
```bash
curl https://your-redis.upstash.io/get/task:task_id:status \
  -H "Authorization: Bearer your-token"
```

**Check edge worker stats**:
- Watch edge worker logs for "total tasks processed"
- Monitor GPU usage: `nvidia-smi -l 1`
- Monitor memory: `nvidia-smi --query-gpu=memory.used --format=csv`

## Cost Breakdown

| Component | Cost |
|-----------|------|
| Render Web Service (Starter) | $7/mo |
| NeonDB PostgreSQL (Free) | $0/mo |
| Upstash Redis (Free) | $0/mo |
| Local Edge Worker | $0/mo |
| **TOTAL** | **$7/mo** |

## Security Notes

1. **Never commit secrets to Git**:
   - Use Render dashboard for `UPSTASH_REDIS_REST_TOKEN`
   - Use `.env` file for local edge worker (add to `.gitignore`)

2. **Use SSL/TLS**:
   - Upstash requires `https://` for REST API
   - NeonDB requires `?sslmode=require`

3. **Rotate tokens**:
   - Rotate `UPSTASH_REDIS_REST_TOKEN` quarterly
   - Rotate `PHAROS_ADMIN_TOKEN` quarterly

## Next Steps

1. ✅ Configure Render with `MODE=CLOUD`
2. ✅ Start local edge worker with `MODE=EDGE`
3. ✅ Test end-to-end flow
4. 📋 Monitor performance metrics
5. 📋 Set up edge worker as Windows service (optional)
6. 📋 Configure edge worker auto-restart (optional)

## Related Documentation

- [Serverless Deployment Guide](SERVERLESS_DEPLOYMENT_GUIDE.md)
- [Edge Worker Implementation](app/edge_worker.py)
- [Upstash Redis Client](app/shared/upstash_redis.py)
- [Embedding Service](app/shared/embeddings.py)

---

**Questions?** Check the logs first, then review this guide. Most issues are configuration mismatches between Render and edge worker.
