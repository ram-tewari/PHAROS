# FIX REDIS_URL NOW - Critical Issue Found

## 🚨 PROBLEM IDENTIFIED

Your `REDIS_URL` is set to the REST API URL:
```bash
REDIS_URL=https://living-sculpin-96916.upstash.io  # ❌ WRONG
```

This is causing the Redis connection to fail, which may be contributing to the deployment issues.

---

## ✅ SOLUTION (2 Minutes)

### Step 1: Get the Correct Redis URL

1. Go to Upstash Console: https://console.upstash.com
2. Click on your database: `living-sculpin-96916`
3. Look for the **"Connect"** section (scroll down past REST API)
4. Find the connection string that looks like:
   ```
   rediss://default:YOUR_PASSWORD@living-sculpin-96916.upstash.io:6379
   ```

### Step 2: Update in Render

1. Go to Render Dashboard
2. Select your `pharos-api` service
3. Go to **Environment** tab
4. Find `REDIS_URL`
5. Click **Edit**
6. Replace with the `rediss://` URL from Step 1
7. Click **Save Changes**

Render will automatically redeploy.

---

## 📋 Correct Environment Variables

Here's what your Redis variables should look like:

```bash
# ✅ CORRECT - Redis connection string (starts with rediss://)
REDIS_URL=rediss://default:YOUR_PASSWORD@living-sculpin-96916.upstash.io:6379

# ✅ CORRECT - REST API URL (for task queue)
UPSTASH_REDIS_REST_URL=https://living-sculpin-96916.upstash.io

# ✅ CORRECT - REST API token (for task queue)
UPSTASH_REDIS_REST_TOKEN=<REDACTED-rotate>
```

**Note**: You have the REST API URL and token correct. You just need to fix the `REDIS_URL`.

---

## 🔍 How to Find the Redis URL in Upstash

When you open your database in Upstash, you'll see multiple sections:

```
┌─────────────────────────────────────────┐
│ REST API (DON'T USE THIS FOR REDIS_URL)│
│ https://living-sculpin-96916.upstash.io│ ← You used this by mistake
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ Connect (USE THIS FOR REDIS_URL)        │
│ rediss://default:password@...           │ ← You need this
└─────────────────────────────────────────┘
```

Look for these labels in the Upstash dashboard:
- **"Redis URL"** or
- **"Connect"** or
- **"Connection String"**

It will start with `rediss://` (note the double 's' for SSL).

---

## 🧪 How to Verify You Have the Right URL

The correct Redis URL should:
- ✅ Start with `rediss://` (with SSL)
- ✅ Contain `default:` (username)
- ✅ Contain a password after `default:`
- ✅ End with `:6379` (Redis port)

Example format:
```
rediss://default:<REDACTED-rotate>@living-sculpin-96916.upstash.io:6379
```

---

## 📊 Current Status of Your Environment Variables

### ✅ Correct Variables
- `MODE=CLOUD` ✅
- `ENV=prod` ✅
- `DATABASE_URL=postgresql+asyncpg://...` ✅
- `UPSTASH_REDIS_REST_URL=https://...` ✅
- `UPSTASH_REDIS_REST_TOKEN=...` ✅
- `WEB_CONCURRENCY` not set (will default to 1 from render.yaml) ✅

### ❌ Incorrect Variables
- `REDIS_URL=https://...` ❌ Should be `rediss://...`

### ⚠️ Optional Variables (Not Critical)
- `MAX_WORKERS=2` - This might conflict with `WEB_CONCURRENCY=1` in render.yaml
  - Recommendation: Remove `MAX_WORKERS` and let `WEB_CONCURRENCY=1` control it

---

## 🚀 After Fixing REDIS_URL

Once you update `REDIS_URL` and Render redeploys, you should see:

### Success Logs
```
✓ Redis cache connection established successfully
Deployment mode: CLOUD
Cloud mode: ML models will NOT be loaded
Module registration complete
Pharos API ready to accept connections
```

### Memory Usage
- Should be <300MB (not >512MB)
- Should stay stable

### Health Check
```bash
curl https://pharos-cloud-api.onrender.com/health
# Should return: {"status": "healthy", "service": "pharos-api"}
```

---

## 🆘 If You Can't Find the Redis URL

If you're having trouble finding the Redis connection string in Upstash:

1. **Look for tabs/sections** in the database view:
   - "Overview"
   - "Connect" ← Look here
   - "REST API"
   - "Settings"

2. **Look for labels**:
   - "Redis URL"
   - "Connection String"
   - "TLS/SSL URL"

3. **Alternative**: Use the Upstash CLI
   ```bash
   upstash redis get living-sculpin-96916
   ```

4. **Last resort**: Create a new Redis database
   - The free tier allows multiple databases
   - Copy the `rediss://` URL immediately
   - Update `REDIS_URL` in Render

---

## 📞 Quick Reference

**What you have now (WRONG)**:
```bash
REDIS_URL=https://living-sculpin-96916.upstash.io
```

**What you need (CORRECT)**:
```bash
REDIS_URL=rediss://default:YOUR_PASSWORD@living-sculpin-96916.upstash.io:6379
```

**Where to find it**:
- Upstash Console → Your Database → "Connect" section

**Where to update it**:
- Render Dashboard → pharos-api → Environment → REDIS_URL

---

## ⏱️ Time to Fix

- Finding Redis URL: 1 minute
- Updating in Render: 1 minute
- Redeployment: 2-3 minutes
- **Total: ~5 minutes**

---

**Last Updated**: 2026-04-16  
**Status**: 🔴 CRITICAL - Fix immediately  
**Impact**: Redis connection failing, may contribute to OOM
