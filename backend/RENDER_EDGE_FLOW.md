# Render + Edge Worker Flow Diagram

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PHAROS HYBRID ARCHITECTURE                      │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                         RENDER CLOUD                             │  │
│  │                         (MODE=CLOUD)                             │  │
│  │                                                                  │  │
│  │  ┌────────────┐                                                 │  │
│  │  │   FastAPI  │  1. Receive Request                             │  │
│  │  │    API     │◄────────────────────────────────────────────┐   │  │
│  │  └─────┬──────┘                                              │   │  │
│  │        │                                                     │   │  │
│  │        │ 2. Queue Task                                       │   │  │
│  │        ▼                                                     │   │  │
│  │  ┌────────────┐                                              │   │  │
│  │  │  Upstash   │                                              │   │  │
│  │  │   Redis    │                                              │   │  │
│  │  │   Queue    │                                              │   │  │
│  │  └─────┬──────┘                                              │   │  │
│  │        │                                                     │   │  │
│  └────────┼─────────────────────────────────────────────────────┼───┘  │
│           │                                                     │      │
│           │ 3. Poll for Tasks                                  │      │
│           │                                                     │      │
│  ┌────────▼─────────────────────────────────────────────────────┼───┐  │
│  │                      LOCAL EDGE WORKER                       │   │  │
│  │                       (MODE=EDGE)                            │   │  │
│  │                                                              │   │  │
│  │  ┌────────────┐                                              │   │  │
│  │  │   Worker   │  4. Receive Task                             │   │  │
│  │  │   Process  │◄─────────────────────────────────────────────┘   │  │
│  │  └─────┬──────┘                                                  │  │
│  │        │                                                         │  │
│  │        │ 5. Load Model                                           │  │
│  │        ▼                                                         │  │
│  │  ┌────────────┐                                                  │  │
│  │  │ RTX 4070   │  6. Generate Embedding                           │  │
│  │  │    GPU     │     (40-60ms)                                    │  │
│  │  └─────┬──────┘                                                  │  │
│  │        │                                                         │  │
│  │        │ 7. Store Result                                         │  │
│  │        ▼                                                         │  │
│  │  ┌────────────┐                                                  │  │
│  │  │   NeonDB   │  8. Save Embedding                               │  │
│  │  │ PostgreSQL │                                                  │  │
│  │  └─────┬──────┘                                                  │  │
│  │        │                                                         │  │
│  └────────┼─────────────────────────────────────────────────────────┘  │
│           │                                                            │
│           │ 9. Mark Complete                                           │
│           ▼                                                            │
│     ┌────────────┐                                                     │
│     │  Upstash   │  10. Update Status                                 │
│     │   Redis    │                                                     │
│     └────────────┘                                                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Detailed Flow

### Step 1: User Uploads Resource

```
POST /api/resources
{
  "title": "My Resource",
  "description": "Test resource",
  "url": "https://example.com"
}
```

### Step 2: Render Queues Task

```python
# In app/shared/embeddings.py (MODE=CLOUD)
if deployment_mode == "CLOUD":
    logger.info("Cloud mode detected - skipping embedding model load")
    # Queue task to Upstash Redis
    task = {
        "task_id": "task_abc123",
        "resource_id": "res_xyz789",
        "text": "My Resource Test resource",
        "timestamp": "2026-04-15T10:30:00Z"
    }
    redis.lpush("embedding_tasks", json.dumps(task))
```

### Step 3: Edge Worker Polls Queue

```python
# In app/edge_worker.py (MODE=EDGE)
while True:
    task = await redis.rpop("embedding_tasks")
    if task:
        process_task(task)
    else:
        await asyncio.sleep(2)  # Poll every 2 seconds
```

### Step 4: Edge Worker Processes Task

```python
# In app/edge_worker.py
def process_task(task):
    # 1. Parse task
    task_id = task["task_id"]
    resource_id = task["resource_id"]
    text = task["text"]
    
    # 2. Generate embedding (GPU)
    embedding = embedding_service.generate_embedding(text)
    # Result: [0.123, 0.456, ...] (768 dimensions)
    # Time: 40-60ms on RTX 4070
    
    # 3. Store in database
    resource = db.query(Resource).get(resource_id)
    resource.embedding = embedding
    db.commit()
    
    # 4. Update task status
    redis.set(f"task:{task_id}:status", "completed")
```

### Step 5: User Queries Resource

```
GET /api/resources/res_xyz789
{
  "id": "res_xyz789",
  "title": "My Resource",
  "description": "Test resource",
  "embedding": [0.123, 0.456, ...],  # ✅ Embedding present
  "embedding_status": "completed"
}
```

## Timing Breakdown

| Step | Component | Time |
|------|-----------|------|
| 1. API Request | Render | 50ms |
| 2. Queue Task | Upstash | 20ms |
| 3. Poll Interval | Edge Worker | 0-2s |
| 4. Receive Task | Edge Worker | 10ms |
| 5. Load Model | Edge Worker | 0ms (cached) |
| 6. Generate Embedding | RTX 4070 GPU | 40-60ms |
| 7. Store Result | NeonDB | 50-100ms |
| 8. Update Status | Upstash | 20ms |
| **Total** | | **2-5s** |

## Configuration Comparison

### ❌ Wrong: Render Running Models (MODE=EDGE)

```yaml
# render.yaml
envVars:
  - key: MODE
    value: EDGE  # ❌ WRONG: Loads models on Render
```

**Problems**:
- High memory usage (1-2GB for models)
- Slow CPU inference (200-400ms)
- OOM errors on Render Starter
- Requires Render Standard ($25/mo)

### ✅ Correct: Render Queuing Tasks (MODE=CLOUD)

```yaml
# render.yaml
envVars:
  - key: MODE
    value: CLOUD  # ✅ CORRECT: Queues tasks to edge worker
  - key: UPSTASH_REDIS_REST_URL
    sync: false  # Set in dashboard
  - key: UPSTASH_REDIS_REST_TOKEN
    sync: false  # Set in dashboard
```

**Benefits**:
- Low memory usage (<200MB)
- No model loading
- Fast API responses
- Render Starter sufficient ($7/mo)

## Environment Variables

### Render (MODE=CLOUD)

```bash
MODE=CLOUD
UPSTASH_REDIS_REST_URL=https://living-sculpin-96916.upstash.io
UPSTASH_REDIS_REST_TOKEN=gQAAAAAAAXqUAAIncDFmMDExYmFjN2Y1ZjQ0ZDY2Yjc0NWE1NTBhMzg2ZDg5M3AxOTY5MTYUPSTASH_REDIS_REST_TOKEN
DATABASE_URL=postgresql+asyncpg://...
```

### Edge Worker (MODE=EDGE)

```bash
MODE=EDGE
UPSTASH_REDIS_REST_URL=https://living-sculpin-96916.upstash.io
UPSTASH_REDIS_REST_TOKEN=gQAAAAAAAXqUAAIncDFmMDExYmFjN2Y1ZjQ0ZDY2Yjc0NWE1NTBhMzg2ZDg5M3AxOTY5MTYUPSTASH_REDIS_REST_TOKEN
DATABASE_URL=postgresql+asyncpg://...
EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1
WORKER_POLL_INTERVAL=2
```

## Verification Commands

### Check Render Mode

```bash
curl https://pharos-cloud-api.onrender.com/health
# Should see: "Cloud mode detected"
```

### Check Edge Worker Status

```bash
# In edge worker logs
grep "Edge worker ready" edge_worker.log
# Should see: "Edge worker ready - waiting for tasks..."
```

### Check Queue Depth

```bash
curl https://living-sculpin-96916.upstash.io/llen/embedding_tasks \
  -H "Authorization: Bearer gQAAAAAAAXqUAAIncDFmMDExYmFjN2Y1ZjQ0ZDY2Yjc0NWE1NTBhMzg2ZDg5M3AxOTY5MTYUPSTASH_REDIS_REST_TOKEN"
# Should return: 0 (if no pending tasks)
```

### Monitor GPU Usage

```bash
nvidia-smi -l 1
# Should show GPU utilization when processing tasks
```

## Success Indicators

### ✅ Render Logs

```
Cloud mode detected - skipping embedding model load (handled by edge worker)
✓ Cloud mode detected - skipping embedding model warmup (handled by edge worker)
Task queued: task_abc123
```

### ✅ Edge Worker Logs

```
GPU Detected:
   Device: NVIDIA GeForce RTX 4070
   Memory: 12.0 GB
Embedding model loaded successfully (2.3s)
Connected to Upstash Redis
Connected to database
Edge worker ready - waiting for tasks...
Received task: task_abc123
Processing task task_abc123 for resource res_xyz789
Generated embedding (768 dims) in 45ms
Stored embedding for resource res_xyz789
Task completed (total: 1 processed, 0 failed)
```

---

**Next Steps**: Follow `RENDER_EDGE_CHECKLIST.md` to configure and verify your setup.
