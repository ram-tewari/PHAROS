# Pharos Edge Worker Status - May 3, 2026

## Current Status: DEGRADED ⚠️

**Last Updated**: May 3, 2026 01:20 UTC  
**Worker State**: Degraded (heartbeat stale)  
**Last Heartbeat**: May 3, 2026 01:11:40 UTC (8+ minutes ago)  
**Threshold**: 5 minutes

---

## Summary

The edge worker **was running** and sending heartbeats successfully, but stopped ~8 minutes ago. The worker is in "degraded" state, meaning:

- ✅ Worker was properly configured and running
- ✅ Heartbeats were being sent to production API
- ✅ Worker metadata was recorded (worker_id, version, model)
- ❌ Worker stopped sending heartbeats 8+ minutes ago
- ❌ Ingestion endpoint returns 503 (refuses new work)

---

## What Happened

### Timeline

1. **Before 01:11:40 UTC**: Worker was running normally
   - Sending heartbeats every 60 seconds
   - Processing tasks from `ingest_queue`
   - Embedding model loaded (nomic-ai/nomic-embed-text-v1)

2. **01:11:40 UTC**: Last successful heartbeat
   - Worker ID: PC-1c2222b4
   - Version: 1.0.0
   - DLQ drained: 0 tasks

3. **After 01:11:40 UTC**: Worker stopped
   - No more heartbeats received
   - Likely causes:
     - User stopped the worker process
     - Worker crashed (check logs)
     - Network connectivity issue
     - System resource exhaustion

4. **01:16:40 UTC**: Worker marked as "degraded"
   - Heartbeat age exceeded 5-minute threshold
   - Ingestion endpoint starts rejecting new tasks

5. **Now (01:20+ UTC)**: Worker still offline
   - Heartbeat age: 8+ minutes
   - State: Degraded
   - Action needed: Restart worker

---

## Why Ingestion Returns 503

The ingestion router has a safety check that prevents accepting new work when the worker is offline:

```python
def _enforce_worker_online(redis: Redis, *, context: str) -> None:
    """Raise 503 'System Degraded' if the worker is offline."""
    online, age = is_worker_online(redis)
    if online:
        return
    # Worker is offline - refuse new work
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": "System Degraded: Edge Worker Offline",
            "context": context,
            "last_seen_seconds_ago": age,
            "threshold_seconds": WORKER_OFFLINE_THRESHOLD_SECONDS,
        },
        headers={"X-Pharos-Edge-Status": "offline"},
    )
```

This is **by design** to prevent:
- Queueing work that won't be processed
- Zombie queue problem (tasks piling up)
- User confusion (task submitted but never completes)

---

## How to Fix

### Option 1: Restart Worker (Recommended)

```powershell
# Check current status
.\check_worker_status.ps1

# Restart worker
.\restart_worker.ps1
```

The restart script will:
1. Stop any existing worker processes
2. Verify environment variables
3. Start fresh worker process
4. Worker will immediately send heartbeat
5. Ingestion endpoint will accept work again

### Option 2: Manual Restart

```powershell
# Stop existing worker (if running)
Get-Process -Name "python" | Where-Object { $_.CommandLine -like "*worker.py*" } | Stop-Process -Force

# Start worker
cd backend
python worker.py
```

### Option 3: Check Logs First

If the worker crashed, check logs to understand why:

```powershell
# Check recent worker logs
cd backend
Get-Content worker.log -Tail 50
```

Common issues:
- Out of memory (GPU memory exhausted)
- CUDA errors (GPU driver issue)
- Network timeout (Upstash Redis unreachable)
- Database connection lost

---

## Verification Steps

After restarting the worker:

### 1. Check Worker Status (30 seconds)
```powershell
.\check_worker_status.ps1
```

Expected output:
```
Worker State: online
Last Heartbeat: [recent timestamp]
Seconds Ago: <60s
✓ Worker is healthy and ready to process tasks
```

### 2. Test Ingestion Endpoint (1 minute)
```powershell
$token = '4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74'
Invoke-WebRequest -Uri "https://pharos-cloud-api.onrender.com/api/v1/ingestion/ingest/github.com/fatih/color" `
  -Method POST `
  -Headers @{ "Authorization" = "Bearer $token" } `
  | Select-Object -ExpandProperty Content | ConvertFrom-Json
```

Expected output:
```json
{
  "status": "dispatched",
  "job_id": 123456,
  "queue_position": 1,
  "target": "Edge-Worker",
  "queue_size": 1,
  "message": "Task queued successfully..."
}
```

### 3. Monitor Worker Logs (5 minutes)
```powershell
cd backend
Get-Content worker.log -Wait
```

Expected output:
```
[REPO] ingest https://github.com/fatih/color (branch=default)
[REPO] github.com/fatih/color done | resources=15 chunks=234 failed=0 duration=45.2s
```

---

## Phase 2 Testing Plan

Once worker is online:

### 1. Ingest Go Repository
```powershell
$token = '4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74'

# Ingest fatih/color (Go repo, ~15 files)
Invoke-WebRequest -Uri "https://pharos-cloud-api.onrender.com/api/v1/ingestion/ingest/github.com/fatih/color" `
  -Method POST `
  -Headers @{ "Authorization" = "Bearer $token" }
```

### 2. Wait for Completion (1-2 minutes)
Monitor worker logs for completion message.

### 3. Search for Go Code
```powershell
$searchBody = @{
    query = "color function"
    strategy = "parent-child"
    top_k = 10
    include_code = $true
} | ConvertTo-Json

Invoke-WebRequest -Uri "https://pharos-cloud-api.onrender.com/api/search/advanced" `
  -Method POST `
  -Headers @{ 
    "Authorization" = "Bearer $token"
    "Content-Type" = "application/json"
  } `
  -Body $searchBody `
  | Select-Object -ExpandProperty Content | ConvertFrom-Json
```

### 4. Verify AST Extraction
Check response for:
- ✅ `language: "go"`
- ✅ `ast_node_type: "function"` or `"class"` (not `"block"`)
- ✅ `symbol_name: "github.com/fatih/color.Color.Printf"` (qualified name)
- ✅ `code: "func (c *Color) Printf(...)"` (actual Go source)

### 5. Database Verification
```sql
-- Connect to production PostgreSQL
SELECT 
  identifier,
  language,
  ast_node_type,
  symbol_name,
  start_line,
  end_line
FROM document_chunks dc
JOIN resources r ON dc.resource_id = r.id
WHERE r.language = 'go'
LIMIT 10;
```

Expected:
- `ast_node_type` should be `function`, `method`, `class`, `struct`
- NOT `block` (which indicates line-chunking fallback)

---

## Root Cause Analysis

### Why Did Worker Stop?

**Most Likely**: User stopped the worker manually
- User mentioned "i stopped edge worker" in chat
- This is normal during development/testing

**Other Possibilities**:
1. **Crash**: Check logs for exceptions
2. **OOM**: GPU memory exhausted during large repo ingestion
3. **Network**: Upstash Redis connection lost
4. **System**: Windows update, sleep mode, etc.

### Why Didn't It Auto-Restart?

The worker is **not configured for auto-restart**. Options:

1. **Manual restart**: Run `restart_worker.ps1` when needed
2. **Windows Service**: Install as service with auto-restart
3. **Process monitor**: Use PM2 or similar
4. **Systemd** (Linux): Configure systemd service with restart policy

For development, manual restart is fine. For production, consider:
- Windows Service with auto-restart
- Docker container with restart policy
- Kubernetes deployment with liveness probes

---

## Next Steps

### Immediate (Now)
1. ✅ Understand why worker stopped (user stopped it)
2. ⏳ Restart worker with `.\restart_worker.ps1`
3. ⏳ Verify worker is online with `.\check_worker_status.ps1`
4. ⏳ Test ingestion endpoint (should return 200, not 503)

### Short-term (Next 30 minutes)
5. ⏳ Ingest Go repository (github.com/fatih/color)
6. ⏳ Search for Go code
7. ⏳ Verify `ast_node_type` is "function" (not "block")
8. ⏳ Confirm Phase 2 polyglot AST is working

### Medium-term (Next hour)
9. ⏳ Ingest Rust repository (github.com/rust-lang/regex)
10. ⏳ Ingest TypeScript repository (github.com/microsoft/TypeScript)
11. ⏳ Verify all 7 languages work correctly
12. ⏳ Update documentation with verification results

---

## Scripts Created

### `check_worker_status.ps1`
Quick status check - shows worker state, last heartbeat, and actionable advice.

**Usage**:
```powershell
.\check_worker_status.ps1
```

**Output**:
- Worker state (online/degraded/offline)
- Last heartbeat timestamp
- Worker metadata (ID, version, model)
- Actionable advice

### `restart_worker.ps1`
Safely restart the worker - stops existing processes, verifies environment, starts fresh worker.

**Usage**:
```powershell
.\restart_worker.ps1
```

**Steps**:
1. Stop existing worker processes
2. Verify environment variables
3. Check backend directory
4. Start worker (runs in foreground)

---

## Monitoring

### Real-time Status
```powershell
# Check every 30 seconds
while ($true) {
    Clear-Host
    .\check_worker_status.ps1
    Start-Sleep -Seconds 30
}
```

### Worker Logs
```powershell
cd backend
Get-Content worker.log -Wait
```

### API Health
```powershell
Invoke-WebRequest -Uri "https://pharos-cloud-api.onrender.com/health" | Select-Object -ExpandProperty Content
```

---

## Related Documentation

- [Phase 1 & 2 Deployment Status](PHASE_1_2_DEPLOYMENT_STATUS.md)
- [Implementation Summary](IMPLEMENTATION_SUMMARY.md)
- [Pharos + Ronin Quick Reference](.kiro/steering/PHAROS_RONIN_QUICK_REFERENCE.md)
- [Tech Stack](.kiro/steering/tech.md)

---

**Status**: Worker needs restart  
**Action**: Run `.\restart_worker.ps1`  
**ETA**: 30 seconds to online, 2 minutes to test Phase 2

