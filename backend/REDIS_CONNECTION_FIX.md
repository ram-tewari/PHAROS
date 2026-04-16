# Redis Connection Issue - Diagnosis & Fix

## Problem

From the Render logs:
```
"Redis cache ping failed - caching will be disabled"
```

The Redis connection is failing during application startup, causing caching to be disabled.

## Root Causes (Likely)

### 1. Cold Start Delay (Most Likely)
Upstash Redis on free tier can have cold start delays of 5-15 seconds when waking from sleep. The current 10-second timeout might not be enough.

### 2. Missing or Incorrect REDIS_URL
The `REDIS_URL` environment variable might not be set in Render dashboard, or might be using wrong format.

### 3. SSL/TLS Protocol Issue
Upstash requires `rediss://` (with two S's) for SSL/TLS. Using `redis://` will fail.

### 4. Network Latency
Render Oregon → Upstash (unknown region) might have high latency on first connection.

## Verification Steps

### Step 1: Check Environment Variables in Render

1. Go to Render Dashboard → pharos-api → Environment
2. Verify these variables exist:
   - `REDIS_URL` - Should start with `rediss://` (two S's)
   - `UPSTASH_REDIS_REST_URL` - Should be set
   - `UPSTASH_REDIS_REST_TOKEN` - Should be set

### Step 2: Check Upstash Dashboard

1. Go to Upstash Dashboard → Your Redis Database
2. Check "Connection" status - should be "Active"
3. Check "Region" - ideally same as Render (Oregon/US-West)
4. Copy the connection string - verify it starts with `rediss://`

### Step 3: Test Connection Manually

SSH into Render shell (if available) or use a test endpoint:

```bash
# Test Redis connection
redis-cli -u $REDIS_URL ping
```

Expected: `PONG`

## Solutions

### Solution 1: Increase Timeout (Quick Fix)

Increase the connection timeout to handle cold starts:

**File**: `backend/app/shared/cache.py`

Change line 169:
```python
# Before
"socket_connect_timeout": 10,  # 10s for serverless wake-up
"socket_timeout": 10,  # 10s for command execution

# After
"socket_connect_timeout": 30,  # 30s for serverless cold start
"socket_timeout": 30,  # 30s for command execution
```

### Solution 2: Retry Logic (Better Fix)

Add retry logic with exponential backoff:

**File**: `backend/app/shared/cache.py`

Add after line 193:

```python
# Test connection with retries
max_retries = 3
retry_delay = 2  # seconds
for attempt in range(max_retries):
    try:
        self.redis.ping()
        logger.info(f"✓ Redis connection successful (attempt {attempt + 1})")
        break
    except Exception as e:
        if attempt < max_retries - 1:
            logger.warning(
                f"Redis ping failed (attempt {attempt + 1}/{max_retries}): {e}. "
                f"Retrying in {retry_delay}s..."
            )
            import time
            time.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff
        else:
            logger.error(f"✗ Redis ping failed after {max_retries} attempts: {e}")
            logger.error(f"Redis URL (first 50 chars): {redis_url[:50]}")
```

### Solution 3: Lazy Connection (Best Fix)

Don't test connection on startup - let it connect on first use:

**File**: `backend/app/__init__.py`

Change lines 295-305:

```python
# Before
elif cache.ping():
    logger.info("✓ Redis cache connection established successfully")
else:
    logger.warning(
        "Redis cache ping failed - caching will be disabled"
    )

# After
# Skip ping on startup - will connect on first use
logger.info("✓ Redis cache initialized (will connect on first use)")
```

This avoids blocking startup on Redis availability.

### Solution 4: Verify REDIS_URL Format

Ensure the URL is correct:

1. Go to Upstash Dashboard
2. Copy the "Redis URL" (should start with `rediss://`)
3. Go to Render Dashboard → Environment
4. Set `REDIS_URL` to the copied value
5. Redeploy

**Correct format**:
```
rediss://default:YOUR_PASSWORD@YOUR_HOST.upstash.io:6379
```

**Incorrect format** (will fail):
```
redis://default:YOUR_PASSWORD@YOUR_HOST.upstash.io:6379  # Missing second 's'
```

## Recommended Fix (Combination)

Apply all three fixes for maximum reliability:

1. **Increase timeout** to 30 seconds (handles cold starts)
2. **Add retry logic** with 3 attempts (handles transient failures)
3. **Make connection lazy** (don't block startup)

This ensures:
- Startup is fast (no blocking)
- Connection succeeds even with cold starts
- Transient failures are handled gracefully
- Application works even if Redis is temporarily unavailable

## Testing

After applying fixes:

1. Redeploy to Render
2. Check logs for:
   ```
   ✓ Redis cache initialized (will connect on first use)
   ```
3. Make a request that uses cache (e.g., search)
4. Check logs for:
   ```
   ✓ Redis connection successful
   ```

## Monitoring

Add a health check endpoint to monitor Redis:

**File**: `backend/app/routers/monitoring.py`

```python
@router.get("/redis-status")
async def redis_status():
    """Check Redis connection status."""
    from app.shared.cache import cache
    
    if cache.redis is None:
        return {"status": "disabled", "message": "Redis not configured"}
    
    try:
        if cache.ping():
            return {"status": "connected", "message": "Redis is healthy"}
        else:
            return {"status": "disconnected", "message": "Redis ping failed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

Test: `https://pharos-cloud-api.onrender.com/api/monitoring/redis-status`

## Cost Consideration

If Redis connection issues persist, consider:

1. **Upgrade Upstash** to paid tier ($10/mo) for:
   - No cold starts
   - Better performance
   - Higher connection limits

2. **Use Render Redis** ($10/mo) for:
   - Same region as API (lower latency)
   - No cold starts
   - Integrated monitoring

3. **Disable Redis** temporarily:
   - Remove `REDIS_URL` from environment
   - Application will work without caching
   - Slightly slower but functional

## Next Steps

1. Apply Solution 3 (Lazy Connection) immediately - no risk, fast startup
2. Monitor logs after next deploy
3. If still issues, apply Solution 1 (Increase Timeout)
4. If still issues, apply Solution 2 (Retry Logic)
5. If still issues, check Upstash dashboard for errors

## Status

- **Current**: Redis connection failing on startup
- **Impact**: Caching disabled, slightly slower performance
- **Severity**: Low (application still works)
- **Priority**: Medium (nice to have, not critical)
- **ETA**: 5 minutes to apply lazy connection fix
