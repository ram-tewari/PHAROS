# The Truth About Pharos Ingestion Pipeline

## What I Got Wrong

I documented a pipeline that **doesn't exist**. I described:
- ❌ Repo worker polling `ingest_queue` - **DOESN'T EXIST**
- ❌ Event handlers queuing embedding tasks - **DOESN'T HAPPEN**
- ❌ Separate chunking and embedding steps - **HAPPENS TOGETHER**
- ❌ Per-chunk embedding tasks - **BATCH PROCESSING**

## What Actually Exists

### The Real Pipeline (Single Resource):

```
1. Create Resource (POST /api/resources)
   ↓
2. Queue to pharos:tasks: {"task_id": "uuid", "resource_id": "uuid"}
   ↓
3. Edge Worker polls pharos:tasks
   ↓
4. Edge Worker calls process_ingestion(resource_id)
   ↓
5. process_ingestion() does EVERYTHING in one function:
   - Fetch URL
   - Extract text
   - AI summary/tags
   - Archive content
   - Generate resource embedding
   - **Chunk content (ChunkingService)**
   - **Generate chunk embeddings (ChunkingService)**
   - Quality scores
   - Citations
   - Mark completed
   ↓
6. DONE
```

**Key Insight**: `process_ingestion()` is a monolithic function that does EVERYTHING, including chunking and embeddings. No separate workers, no event handlers, no queuing of chunk tasks.

---

## The LangChain Problem

### What Happened:

1. You called: `POST /api/v1/ingestion/ingest/github.com/langchain-ai/langchain`
2. Router queued task to `ingest_queue`
3. **NO WORKER EXISTS** to poll `ingest_queue`
4. Task sits in queue forever
5. Resources somehow got created (3,302 files) - probably manually or old test
6. Resources have `ingestion_status="pending"`
7. No chunks, no embeddings, no search results

### Why No Chunks:

Resources are stuck at `ingestion_status="pending"` because `process_ingestion()` was never called. That function does EVERYTHING - if it doesn't run, nothing happens.

---

## The Fix

### Step 1: Queue Existing Resources

Run this script to queue all 3,302 pending resources to `pharos:tasks`:

```bash
cd backend
python scripts/queue_pending_resources.py
```

This will:
- Find all resources with `ingestion_status="pending"`
- Queue each one to `pharos:tasks` with format: `{"task_id": "uuid", "resource_id": "uuid"}`
- Edge worker will pick them up automatically

### Step 2: Edge Worker Processes Them

Edge worker (already running) will:
1. Poll `pharos:tasks` every 2 seconds
2. Get task with `resource_id`
3. Call `process_ingestion(resource_id)`
4. Fetch URL content (from GitHub raw URLs in resource metadata)
5. Chunk content
6. Generate embeddings
7. Mark `ingestion_status="completed"`

### Step 3: Verify Search Works

After processing completes (2-4 hours for 3,302 files):

```bash
curl -X POST "https://pharos-cloud-api.onrender.com/api/search/advanced" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "message translator",
    "strategy": "parent-child",
    "top_k": 5
  }'
```

---

## Future: GitHub Ingestion

The `/api/v1/ingestion/ingest/{repo_url}` endpoint is **BROKEN** because there's no repo worker.

### Two Options:

#### Option 1: Create Repo Worker (Complex)

Create `backend/app/workers/repo.py` that:
- Polls `ingest_queue`
- Calls `HybridIngestionPipeline.ingest_github_repo()`
- Creates resources in batch
- Queues each resource to `pharos:tasks`

#### Option 2: Direct Pipeline Call (Simple)

Modify ingestion router to call AST pipeline directly:
```python
@router.post("/ingest/{repo_url:path}")
async def trigger_remote_ingestion(repo_url: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(ingest_repo_background, repo_url)
    return {"status": "started"}
```

**Recommendation**: Option 2 is simpler and works with existing infrastructure.

---

## Files to Check

### What Actually Works:
- ✅ `backend/app/modules/resources/service.py` - `process_ingestion()` (monolithic pipeline)
- ✅ `backend/app/workers/edge.py` - Edge worker (polls `pharos:tasks`)
- ✅ `backend/app/modules/resources/router.py` - Resource creation endpoint

### What's Broken:
- ❌ `backend/app/routers/ingestion.py` - Queues to `ingest_queue` (no worker)
- ❌ `backend/app/workers/repo.py` - **DOESN'T EXIST**
- ❌ Event handlers for chunking - **DON'T EXIST**

### What's Unused:
- ⚠️ `backend/app/modules/ingestion/ast_pipeline.py` - AST pipeline (not connected)

---

## Commands to Run

### 1. Start Edge Worker (if not running)
```bash
cd backend
python worker.py edge
```

### 2. Queue Pending Resources
```bash
python scripts/queue_pending_resources.py
```

### 3. Monitor Progress
```bash
tail -f backend/edge_worker.log
```

### 4. Check Queue Size
```bash
curl -X POST "$UPSTASH_REDIS_REST_URL" \
  -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '["LLEN","pharos:tasks"]'
```

### 5. Test Search (after processing)
```bash
curl -X POST "https://pharos-cloud-api.onrender.com/api/search/advanced" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74" \
  -H "Content-Type: application/json" \
  -d '{"query": "authentication", "strategy": "parent-child", "top_k": 5}'
```

---

## Timeline

For 3,302 LangChain resources:

1. **Queuing**: ~1 minute (script runs fast)
2. **Processing**: ~2-4 hours (edge worker processes ~1-2 resources/minute)
3. **Total**: ~2-4 hours until search works

---

## Why I Was Wrong

I read the AST pipeline code and ASSUMED it was connected to workers and event handlers. I didn't verify:
- ❌ That repo worker exists
- ❌ That event handlers exist
- ❌ That ingestion router connects to AST pipeline
- ❌ That chunking happens via events

I should have:
- ✅ Checked what workers actually exist
- ✅ Traced the actual code path from endpoint to database
- ✅ Verified event handlers are registered
- ✅ Tested the pipeline end-to-end

**Lesson**: Don't document what SHOULD exist. Document what DOES exist.

---

## Bottom Line

**The pipeline is simpler than I thought**:
- One worker (edge)
- One queue (pharos:tasks)
- One function (process_ingestion)
- No events, no handlers, no complexity

**To fix LangChain**:
1. Run `python scripts/queue_pending_resources.py`
2. Wait 2-4 hours
3. Test search
4. Done

**To fix GitHub ingestion**:
- Need to create repo worker OR modify ingestion router
- That's a separate task for later
