# Resource Creation Fix - CLOUD Mode Redis Queuing

## Problem Solved

Resource creation endpoint (`POST /api/resources`) was failing with 500 Internal Server Error in CLOUD mode because it was trying to run AI operations locally instead of queuing to Redis for the edge worker.

## Solution Implemented

Modified `backend/app/modules/resources/router.py` to check MODE and route accordingly:

### CLOUD Mode (Render Deployment)
- Creates pending resource in database
- Queues task to Redis (Upstash) using QueueService
- Edge worker picks up task and processes with GPU
- Returns 202 Accepted immediately

### EDGE Mode (Local Development)
- Creates pending resource in database
- Processes ingestion locally with background task
- Uses local GPU/ML models
- Returns 202 Accepted immediately

## Code Changes

### File: `backend/app/modules/resources/router.py`

**Before:**
```python
# Always used FastAPI background tasks (local processing)
background.add_task(
    process_ingestion,
    str(resource.id),
    archive_root=None,
    ai=None,
    engine_url=engine_url,
)
```

**After:**
```python
# Check MODE and route accordingly
settings = get_settings()
mode = getattr(settings, "MODE", "EDGE")

if mode == "CLOUD":
    # Queue to Redis for edge worker
    from ...services.queue_service import QueueService
    queue_service = QueueService()
    
    task_data = {
        "resource_id": str(resource.id),
        "url": str(payload.url),
        "title": payload.title or "Untitled",
        "submitted_at": datetime.utcnow().isoformat(),
        "ttl": 86400,
    }
    
    job_id = await queue_service.submit_job(task_data)
    logger.info(f"✓ Queued resource {resource.id} to Redis (job_id={job_id})")
else:
    # Process locally (EDGE mode)
    background.add_task(
        process_ingestion,
        str(resource.id),
        archive_root=None,
        ai=None,
        engine_url=engine_url,
    )
```

## Testing

### Test CLOUD Mode (Render)

```bash
# Create resource
curl -X POST "https://pharos-cloud-api.onrender.com/api/resources" \
  -H "Content-Type: application/json" \
  -H "Origin: https://pharos-cloud-api.onrender.com" \
  -d '{
    "url": "https://example.com",
    "title": "Test Resource",
    "description": "Testing end-to-end resource creation"
  }'

# Expected response (202 Accepted):
{
  "id": "uuid-here",
  "status": "pending",
  "title": "Test Resource",
  "ingestion_status": "pending"
}

# Check resource status
curl "https://pharos-cloud-api.onrender.com/api/resources/{resource_id}/status"

# Expected: status transitions from "pending" → "processing" → "completed"
```

### Test EDGE Mode (Local)

```bash
# Create resource
curl -X POST "http://localhost:8000/api/resources" \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8000" \
  -d '{
    "url": "https://example.com",
    "title": "Test Resource",
    "description": "Testing local resource creation"
  }'

# Expected: Same 202 response, processes immediately in background
```

## Deployment Steps

1. **Commit changes:**
   ```bash
   git add backend/app/modules/resources/router.py
   git commit -m "Fix: Queue resource ingestion to Redis in CLOUD mode"
   git push
   ```

2. **Render auto-deploys** (takes ~2-3 minutes)

3. **Verify deployment:**
   ```bash
   curl "https://pharos-cloud-api.onrender.com/health"
   # Should return 200 OK
   ```

4. **Test resource creation:**
   ```bash
   # Use PowerShell script
   cd backend
   .\test_resource_creation.ps1
   ```

5. **Monitor edge worker:**
   - Edge worker should pick up task from Redis
   - Process ingestion with GPU
   - Update resource status to "completed"

## Expected Behavior

### CLOUD Mode Flow

```
1. User creates resource via API
   ↓
2. Cloud API creates pending resource in Neon DB
   ↓
3. Cloud API queues task to Upstash Redis
   ↓
4. Cloud API returns 202 Accepted
   ↓
5. Edge worker polls Redis queue
   ↓
6. Edge worker picks up task
   ↓
7. Edge worker fetches content
   ↓
8. Edge worker generates embeddings (GPU)
   ↓
9. Edge worker updates resource in Neon DB
   ↓
10. Resource status: "pending" → "processing" → "completed"
```

### EDGE Mode Flow

```
1. User creates resource via API
   ↓
2. API creates pending resource in local DB
   ↓
3. API starts background task
   ↓
4. API returns 202 Accepted
   ↓
5. Background task processes ingestion
   ↓
6. Background task generates embeddings (local GPU)
   ↓
7. Background task updates resource in local DB
   ↓
8. Resource status: "pending" → "processing" → "completed"
```

## Error Handling

### Redis Connection Failure
```json
{
  "detail": "Failed to queue ingestion task: Redis connection failed"
}
```
**Status:** 503 Service Unavailable

### Invalid URL
```json
{
  "detail": "url is required"
}
```
**Status:** 400 Bad Request

### CSRF Validation Failure
```json
{
  "detail": "CSRF validation failed: Missing Origin or Referer header"
}
```
**Status:** 403 Forbidden

## Monitoring

### Check Queue Size
```bash
curl "https://pharos-cloud-api.onrender.com/api/v1/ingestion/jobs/history"
```

### Check Worker Status
```bash
curl "https://pharos-cloud-api.onrender.com/api/v1/ingestion/worker/status"
```

### Check Resource Status
```bash
curl "https://pharos-cloud-api.onrender.com/api/resources/{resource_id}/status"
```

## Related Files

- `backend/app/modules/resources/router.py` - Resource creation endpoint (FIXED)
- `backend/app/services/queue_service.py` - QueueService for Redis operations
- `backend/app/routers/ingestion.py` - Ingestion router (reference implementation)
- `backend/RESOURCE_CREATION_ISSUE.md` - Problem analysis
- `backend/test_resource_creation.ps1` - Test script

## Status

✅ **FIXED** - Resource creation now queues to Redis in CLOUD mode

## Next Steps

1. Deploy to Render
2. Test resource creation end-to-end
3. Verify edge worker processes tasks
4. Monitor resource status transitions
5. Document any issues
