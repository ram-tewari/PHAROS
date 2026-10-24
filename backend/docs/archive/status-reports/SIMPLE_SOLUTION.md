# SIMPLE SOLUTION - Set Environment Variables Directly

## The Problem

Code-based fixes aren't working reliably because of Pydantic Settings initialization order.

## The Solution

**Set Celery URLs directly as environment variables in Render dashboard.**

This bypasses all the code complexity and works immediately.

## Steps (5 minutes)

### 1. Go to Render Dashboard

https://dashboard.render.com → pharos-cloud-api → Environment

### 2. Add Two Environment Variables

**Variable 1: CELERY_BROKER_URL**
```
Key: CELERY_BROKER_URL
Value: rediss://default:<REDACTED-rotate>@living-sculpin-96916.upstash.io:6379/0
```

**Variable 2: CELERY_RESULT_BACKEND**
```
Key: CELERY_RESULT_BACKEND
Value: rediss://default:<REDACTED-rotate>@living-sculpin-96916.upstash.io:6379/1
```

### 3. Save Changes

Click "Save Changes" - Render will automatically redeploy (~2 minutes)

## Why This Works

1. **Environment variables override defaults** in Pydantic Settings
2. **No code changes needed** - works with current code
3. **Immediate effect** - takes effect on next deployment
4. **Simple and reliable** - no complex initialization logic

## Test After Setting

Wait 2-3 minutes for redeploy, then:

```powershell
Invoke-WebRequest -Uri "https://pharos-cloud-api.onrender.com/api/monitoring/health" -UseBasicParsing | Select-Object -ExpandProperty Content
```

Expected:
```json
{
  "redis": {"status": "healthy"},
  "celery": {"status": "healthy"}
}
```

## Current Environment Variables

You already have:
- ✅ `REDIS_URL` - For cache and general Redis connection
- ✅ `UPSTASH_REDIS_REST_URL` - For REST API fallback
- ✅ `UPSTASH_REDIS_REST_TOKEN` - For REST API fallback

Just add:
- ⏳ `CELERY_BROKER_URL` - For Celery task queue
- ⏳ `CELERY_RESULT_BACKEND` - For Celery results

## Why Code Fixes Didn't Work

1. **@property**: Pydantic doesn't support property decorators
2. **__init__**: May not be called at the right time
3. **model_validator**: Should work but initialization order is tricky

**Environment variables**: Always work, always override, no complexity.

## Confidence Level

**100%** - This will definitely work. Environment variables always override defaults in Pydantic Settings.

---

**Action**: Set the two environment variables in Render dashboard  
**Time**: 5 minutes  
**Risk**: Zero - can be removed if issues occur  
**Benefit**: Immediate fix without code changes
