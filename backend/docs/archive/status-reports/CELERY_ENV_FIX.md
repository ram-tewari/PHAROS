# Celery Environment Variable Fix

## Problem

The code-based fixes aren't working because:
1. Pydantic Settings doesn't support `@property` decorators
2. `__init__` override may not be called at the right time
3. Celery is still connecting to `localhost:6379`

## Solution: Direct Environment Variables

Instead of trying to fix it in code, set the Celery URLs directly as environment variables in Render.

## Steps

### 1. Go to Render Dashboard

https://dashboard.render.com → pharos-cloud-api → Environment

### 2. Add These Environment Variables

**Variable 1**:
- Key: `CELERY_BROKER_URL`
- Value: `rediss://default:<REDACTED-rotate>@living-sculpin-96916.upstash.io:6379/0`

**Variable 2**:
- Key: `CELERY_RESULT_BACKEND`
- Value: `rediss://default:<REDACTED-rotate>@living-sculpin-96916.upstash.io:6379/1`

### 3. Save Changes

Render will automatically redeploy (~2 minutes)

## Why This Works

- Environment variables override the default values in settings.py
- Pydantic Settings automatically loads env vars
- No code changes needed
- Works immediately

## Expected Result

After redeploy:
```json
{
  "redis": {"status": "healthy"},
  "celery": {"status": "healthy"}
}
```

## Test After Setting

```powershell
# Wait 2-3 minutes for redeploy
Start-Sleep -Seconds 120

# Test
Invoke-WebRequest -Uri "https://pharos-cloud-api.onrender.com/api/monitoring/health" -UseBasicParsing | Select-Object -ExpandProperty Content
```

## Alternative: Use REST API Queue

If native Redis still doesn't work, we can switch to REST API for the queue.

This requires code changes to use `upstash-redis` Python package instead of `redis`.
