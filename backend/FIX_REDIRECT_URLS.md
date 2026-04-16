# 🔧 Fix OAuth Redirect URLs - 1 Minute

## Current Error

```
Production redirect URLs must use HTTPS: http://localhost:5173
HTTP URLs are only allowed for localhost in development mode
```

## What This Means

In production mode (`ENV=prod`), all OAuth redirect URLs must use HTTPS. The default settings include `http://localhost:5173` which is only for development.

## Quick Fix (1 minute)

### Option 1: Add Environment Variable in Render Dashboard

1. Go to Render Dashboard: https://dashboard.render.com
2. Click on **pharos-cloud-api**
3. Go to **Environment** tab
4. Click **"Add Environment Variable"**
5. Add:
   - **Key**: `ALLOWED_REDIRECT_URLS`
   - **Value**: `["https://pharos-cloud-api.onrender.com"]`
6. Click **"Add"**
7. Click **"Save Changes"**
8. Wait 2-3 minutes for redeploy

### Option 2: Update render.yaml and Redeploy

The `backend/deployment/render.yaml` has been updated with the fix. To apply it:

```bash
# Commit the updated render.yaml
git add backend/deployment/render.yaml
git commit -m "Fix: Add ALLOWED_REDIRECT_URLS for production"
git push origin master

# Render will auto-redeploy
```

## What This Does

Sets the allowed OAuth redirect URLs to only include your production HTTPS URL:
- ✅ `https://pharos-cloud-api.onrender.com` (HTTPS, allowed)
- ❌ `http://localhost:5173` (HTTP, not allowed in production)
- ❌ `http://localhost:3000` (HTTP, not allowed in production)

## Expected Result

After fixing, deployment should succeed:

```
✅ Settings loaded successfully
✅ ENV=prod
✅ JWT_SECRET_KEY validated
✅ ALLOWED_REDIRECT_URLS validated (HTTPS only)
✅ Running Alembic migrations...
✅ Migrations completed
✅ Starting Uvicorn server...
✅ Application startup complete
```

## Why This Happens

The default `ALLOWED_REDIRECT_URLS` in `settings.py` includes localhost URLs for development:

```python
ALLOWED_REDIRECT_URLS: list[str] = [
    "http://localhost:5173",  # Vite dev server (dev only)
    "http://localhost:3000",  # Common dev server (dev only)
    "https://pharos.onrender.com",  # Production
]
```

In production mode, the validator rejects HTTP URLs to prevent security vulnerabilities (open redirect attacks).

## Security Note

This validation is intentional and protects against:
- **Open Redirect Attacks**: Attackers redirecting users to malicious sites
- **Man-in-the-Middle**: HTTP traffic can be intercepted
- **Session Hijacking**: Tokens exposed over unencrypted connections

Always use HTTPS in production!

## Verification

Once deployed, test:

```bash
curl https://pharos-cloud-api.onrender.com/health
```

Expected:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "environment": "prod"
}
```

---

**Recommended**: Use Option 1 (add environment variable) for fastest fix.

**Time**: 1 minute  
**Result**: Successful deployment
