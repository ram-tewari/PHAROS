# Resource Creation Issue - CLOUD Mode Not Queuing to Redis

## Problem

Resource creation endpoint (`POST /api/resources`) is failing with 500 Internal Server Error when deployed to Render in CLOUD mode.

## Root Cause

The resource creation endpoint in `backend/app/modules/resources/router.py` uses FastAPI's `background.add_task()` to process ingestion:

```python
@router.post("", response_model=ResourceAccepted)
async def create_resource_endpoint(
    payload: ResourceIngestRequest,
    background: BackgroundTasks,
    ...
):
    # Creates pending resource
    resource = create_pending_resource(db, payload_dict)
    
    # ❌ PROBLEM: Uses FastAPI background tasks (runs locally in cloud API)
    background.add_task(
        process_ingestion,
        str(resource.id),
        archive_root=None,
        ai=None,
        engine_url=engine_url,
    )
```

**Why this fails in CLOUD mode:**
1. Cloud API has no GPU/ML models (MODE=CLOUD)
2. `process_ingestion` tries to run AI operations (embeddings, summarization)
3. These operations fail because models aren't loaded
4. Resource gets stuck in "pending" status

## Expected Behavior (Hybrid Architecture)

In CLOUD mode, the endpoint should:
1. Create pending resource in database ✅
2. Queue task to Redis (Upstash) ✅ (but not happening)
3. Edge worker picks up task from Redis
4. Edge worker processes ingestion with GPU
5. Edge worker updates resource status to "completed"

## Solution Options

### Option 1: Use Ingestion Router (Recommended)

The ingestion router (`backend/app/routers/ingestion.py`) already implements proper Redis queuing:

```python
@router.post("/ingest/{repo_url:path}", response_model=IngestionResponse)
async def trigger_remote_ingestion(repo_url: str, ...):
    # ✅ Queues to Redis using QueueService
    job_id = await queue_service.submit_job(task_data)
```

**Implementation:**
- Modify resource creation endpoint to check MODE
- If MODE=CLOUD, redirect to ingestion router
- If MODE=EDGE, use background.add_task() as before

### Option 2: Add MODE Check to Resource Router

Modify `backend/app/modules/resources/router.py`:

```python
from ...config.settings import get_settings

@router.post("", response_model=ResourceAccepted)
async def create_resource_endpoint(...):
    resource = create_pending_resource(db, payload_dict)
    
    settings = get_settings()
    
    if settings.MODE == "CLOUD":
        # Queue to Redis for edge worker
        from ...services.queue_service import QueueService
        queue_service = QueueService()
        
        task_data = {
            "resource_id": str(resource.id),
            "url": str(payload.url),
            "submitted_at": datetime.now().isoformat(),
        }
        
        job_id = await queue_service.submit_job(task_data)
        logger.info(f"Queued resource {resource.id} to Redis (job_id={job_id})")
    else:
        # Run locally (EDGE mode)
        background.add_task(
            process_ingestion,
            str(resource.id),
            archive_root=None,
            ai=None,
            engine_url=engine_url,
        )
```

### Option 3: Modify process_ingestion to Queue Itself

Add MODE check inside `process_ingestion`:

```python
def process_ingestion(resource_id: str, ...):
    settings = get_settings()
    
    if settings.MODE == "CLOUD":
        # We're in cloud API - queue to Redis instead
        from ...services.queue_service import QueueService
        queue_service = QueueService()
        
        task_data = {
            "resource_id": resource_id,
            "submitted_at": datetime.now().isoformat(),
        }
        
        # This would need to be async, which is a problem
        # because process_ingestion is sync
        # NOT RECOMMENDED
```

## Recommended Fix: Option 2

Add MODE check to resource router to queue to Redis in CLOUD mode.

**Advantages:**
- Minimal code changes
- Preserves existing EDGE mode behavior
- Uses existing QueueService infrastructure
- Clear separation of concerns

**Implementation Steps:**
1. Import QueueService and settings in router
2. Add MODE check after creating pending resource
3. If CLOUD: queue to Redis
4. If EDGE: use background.add_task()
5. Test both modes

## Testing

### Test CLOUD Mode (Render)
```bash
curl -X POST "https://pharos-cloud-api.onrender.com/api/resources" \
  -H "Content-Type: application/json" \
  -H "Origin: https://pharos-cloud-api.onrender.com" \
  -d '{"url": "https://example.com", "title": "Test"}'

# Should return 202 Accepted with resource ID
# Check Redis queue: should have 1 pending task
# Edge worker should pick up task and process it
```

### Test EDGE Mode (Local)
```bash
curl -X POST "http://localhost:8000/api/resources" \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8000" \
  -d '{"url": "https://example.com", "title": "Test"}'

# Should return 202 Accepted with resource ID
# Should process immediately in background
# Resource should transition to "completed" within seconds
```

## Related Files

- `backend/app/modules/resources/router.py` - Resource creation endpoint (needs fix)
- `backend/app/modules/resources/service.py` - process_ingestion function
- `backend/app/routers/ingestion.py` - Ingestion router with Redis queuing
- `backend/app/services/queue_service.py` - QueueService for Redis operations
- `backend/app/config/settings.py` - MODE configuration

## Current Status

- ❌ Resource creation fails in CLOUD mode (500 error)
- ✅ Ingestion router works correctly (queues to Redis)
- ✅ Edge worker can process tasks from Redis
- ❌ Resource endpoint doesn't queue to Redis in CLOUD mode

## Next Steps

1. Implement Option 2 (MODE check in resource router)
2. Test resource creation in CLOUD mode
3. Verify edge worker picks up task
4. Verify resource transitions to "completed"
5. Document the fix
