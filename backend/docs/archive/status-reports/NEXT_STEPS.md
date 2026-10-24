# Next Steps - After Redis Fix Deployment

## What We Did

1. ✅ Identified Redis connection issue (hardcoded localhost)
2. ✅ Fixed Celery broker URL to use REDIS_URL environment variable
3. ✅ Implemented lazy Redis connection (30s timeout for cold starts)
4. ✅ Pushed changes to GitHub
5. ⏳ Render is deploying the fix

## Current Status

**Deployment**: In Progress (triggered ~2 minutes ago)  
**Expected Completion**: 2-3 minutes from push  
**API**: Responding (health check passes)

## What to Do Now

### Option 1: Wait and Monitor (Recommended)

Run this script to automatically check when deployment completes:

```powershell
cd backend
.\wait_for_deploy.ps1
```

This will check every 10 seconds and notify you when Redis is healthy.

### Option 2: Manual Check

Wait 2-3 minutes, then run:

```powershell
Invoke-WebRequest -Uri "https://pharos-cloud-api.onrender.com/api/monitoring/health" -UseBasicParsing | Select-Object -ExpandProperty Content
```

Look for:
```json
{
  "redis": {"status": "healthy"},
  "celery": {"status": "healthy"}
}
```

### Option 3: Check Render Dashboard

1. Go to https://dashboard.render.com
2. Click on `pharos-cloud-api`
3. Watch "Events" tab for deployment status
4. Check "Logs" tab for any errors

## After Deployment Completes

### Test 1: Verify System Health

```powershell
$response = Invoke-WebRequest -Uri "https://pharos-cloud-api.onrender.com/api/monitoring/health" -UseBasicParsing
$health = $response.Content | ConvertFrom-Json

Write-Host "Redis: $($health.components.redis.status)"
Write-Host "Celery: $($health.components.celery.status)"
```

Expected: Both show "healthy"

### Test 2: Create a Test Resource

```powershell
$headers = @{
    "Content-Type" = "application/json"
    "Origin" = "https://pharos-cloud-api.onrender.com"
}

$body = @{
    url = "https://github.com/test/pharos-test"
    title = "Test Resource - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    resource_type = "code"
    tags = @("test", "deployment-test")
} | ConvertTo-Json

$response = Invoke-WebRequest -Uri "https://pharos-cloud-api.onrender.com/api/resources" -Method POST -Body $body -Headers $headers -UseBasicParsing
$resource = $response.Content | ConvertFrom-Json

Write-Host "Resource Created: $($resource.id)"
Write-Host "Status: $($resource.ingestion_status)"
```

Expected: 
- Status: 202 Accepted
- ingestion_status: "pending"
- Resource ID returned

### Test 3: Verify Edge Worker Receives Task

Check your edge worker console output for:

```
✓ Received task from queue
Task: ingest_resource
Resource ID: <the ID from Test 2>
Processing...
```

If you see this, the full pipeline is working!

### Test 4: Check Resource Status

Wait 10-30 seconds for processing, then:

```powershell
$resourceId = "<ID from Test 2>"
Invoke-WebRequest -Uri "https://pharos-cloud-api.onrender.com/api/resources/$resourceId" -UseBasicParsing | Select-Object -ExpandProperty Content
```

Expected: ingestion_status should change from "pending" to "completed"

## Troubleshooting

### If Redis Still Shows Unhealthy After 5 Minutes

1. Check Render logs:
   ```
   Dashboard → pharos-cloud-api → Logs
   ```
   Look for Redis connection errors

2. Verify environment variables in Render:
   ```
   Dashboard → pharos-cloud-api → Environment
   ```
   Confirm REDIS_URL is set correctly

3. Try REST API fallback:
   - Verify UPSTASH_REDIS_REST_URL is set
   - Verify UPSTASH_REDIS_REST_TOKEN is set

### If Edge Worker Can't Connect

1. Check `.env.edge` file:
   ```
   UPSTASH_REDIS_REST_URL=https://living-sculpin-96916.upstash.io
   UPSTASH_REDIS_REST_TOKEN=<REDACTED-rotate>
   ```

2. Restart edge worker:
   ```powershell
   .\start_edge_worker.ps1
   ```

3. Check edge worker logs for connection success

### If Resource Creation Fails

1. Check monitoring endpoint shows Redis + Celery healthy
2. Verify CSRF headers are included (Origin header)
3. Check Render logs for errors
4. Try creating resource again (may have been during deployment)

## Success Checklist

- [ ] Render deployment completed (check dashboard)
- [ ] Redis shows "healthy" in monitoring endpoint
- [ ] Celery shows "healthy" in monitoring endpoint
- [ ] Can create resources via POST /api/resources
- [ ] Edge worker receives tasks from queue
- [ ] Resources process successfully (pending → completed)
- [ ] Can search and retrieve processed resources

## Timeline

| Time | Event | Status |
|------|-------|--------|
| T+0 | Git push | ✅ Done |
| T+1m | Render detects changes | ⏳ In Progress |
| T+2m | Build completes | ⏳ Waiting |
| T+3m | Deploy completes | ⏳ Waiting |
| T+4m | Health checks pass | ⏳ Waiting |
| T+5m | Redis connected | ⏳ Waiting |

**Current Time**: Check Render dashboard for exact status

## Quick Commands Reference

```powershell
# Monitor deployment
.\wait_for_deploy.ps1

# Check health
Invoke-WebRequest -Uri "https://pharos-cloud-api.onrender.com/api/monitoring/health" -UseBasicParsing

# Create test resource
# (See Test 2 above for full command)

# Check edge worker
# Look at console output for task reception

# View Render logs
# Go to dashboard.render.com → pharos-cloud-api → Logs
```

## What's Fixed

1. ✅ Celery now uses REDIS_URL from environment (not localhost)
2. ✅ Redis connection is lazy (doesn't block startup)
3. ✅ Redis timeout increased to 30s (handles cold starts)
4. ✅ All Redis configuration centralized in settings

## What's Next

Once everything is working:

1. Test full ingestion pipeline with real repository
2. Verify embeddings are generated correctly
3. Test search functionality
4. Monitor performance and costs
5. Consider upgrading Upstash if needed (currently free tier)

## Support

If issues persist after 10 minutes:

1. Share Render logs (last 50 lines)
2. Share edge worker logs
3. Share monitoring endpoint output
4. I'll help debug further

---

**Status**: Waiting for deployment to complete  
**ETA**: 2-3 minutes from now  
**Action**: Run `.\wait_for_deploy.ps1` or wait and check manually
