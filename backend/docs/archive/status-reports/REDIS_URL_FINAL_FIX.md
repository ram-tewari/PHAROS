# REDIS_URL Final Fix - Wrong Format

## 🚨 CURRENT PROBLEM

Your `REDIS_URL` contains the entire CLI command:
```bash
REDIS_URL="redis-cli --tls -u redis://default:<REDACTED-rotate>@living-sculpin-96916.upstash.io:6379"
```

This is **WRONG**. The app expects just the connection URL, not the CLI command.

---

## ✅ CORRECT FORMAT

Based on your current value, the correct `REDIS_URL` should be:

```bash
REDIS_URL=rediss://default:<REDACTED-rotate>@living-sculpin-96916.upstash.io:6379
```

**Key changes**:
1. Remove `redis-cli --tls -u` (this is just the CLI command)
2. Change `redis://` to `rediss://` (with SSL - note the double 's')
3. Keep everything else the same

---

## 🔧 Quick Fix

### In Render Dashboard:

1. Go to **Environment** tab
2. Find `REDIS_URL`
3. Click **Edit**
4. Replace with:
   ```
   rediss://default:<REDACTED-rotate>@living-sculpin-96916.upstash.io:6379
   ```
5. Click **Save Changes**

---

## 📋 Understanding the Format

### What Upstash Shows You:
```bash
# CLI Command (for terminal use)
redis-cli --tls -u redis://default:PASSWORD@host:6379

# Connection String (for apps)
rediss://default:PASSWORD@host:6379
```

### What Your App Needs:
```bash
# Just the connection string (with rediss:// for SSL)
REDIS_URL=rediss://default:PASSWORD@host:6379
```

---

## 🎯 All Your Redis Variables (Corrected)

```bash
# ✅ CORRECT - Connection string for app
REDIS_URL=rediss://default:<REDACTED-rotate>@living-sculpin-96916.upstash.io:6379

# ✅ CORRECT - REST API URL (already correct)
UPSTASH_REDIS_REST_URL=https://living-sculpin-96916.upstash.io

# ✅ CORRECT - REST API token (already correct)
UPSTASH_REDIS_REST_TOKEN=<REDACTED-rotate>
```

---

## 🔍 How to Verify

After updating, your logs should show:
```
✓ Redis cache connection established successfully
```

Instead of:
```
❌ Redis URL must specify one of the following schemes (redis://, rediss://, unix://)
```

---

## ⚠️ Additional Issue: MAX_WORKERS

I also noticed:
```bash
MAX_WORKERS=2  # ⚠️ This might conflict with WEB_CONCURRENCY=1
```

**Recommendation**: Remove `MAX_WORKERS` from Render environment variables. Let `WEB_CONCURRENCY=1` (from render.yaml) control the worker count to prevent OOM.

---

## 📊 Summary of Changes Needed

### Change 1: Fix REDIS_URL
**From**:
```bash
REDIS_URL="redis-cli --tls -u redis://default:<REDACTED-rotate>@living-sculpin-96916.upstash.io:6379"
```

**To**:
```bash
REDIS_URL=rediss://default:<REDACTED-rotate>@living-sculpin-96916.upstash.io:6379
```

### Change 2: Remove MAX_WORKERS (Optional but Recommended)
**Remove**: `MAX_WORKERS=2`  
**Reason**: Let `WEB_CONCURRENCY=1` from render.yaml control workers to prevent OOM

---

## ⏱️ Time to Fix

- Update REDIS_URL: 1 minute
- Remove MAX_WORKERS: 30 seconds
- Redeployment: 2-3 minutes
- **Total: ~4 minutes**

---

## 🧪 Test After Deployment

```bash
# Should return healthy with Redis connected
curl https://pharos-cloud-api.onrender.com/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "pharos-api",
  "redis": "connected"
}
```

---

**Last Updated**: 2026-04-16  
**Status**: 🔴 CRITICAL - Fix immediately  
**Impact**: Redis connection failing due to wrong URL format
