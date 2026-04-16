# 🔧 Visual Guide: Fix Render Environment Variables

## Current Error

Your deployment logs show:
```
ValidationError: ENV
  Input should be 'dev', 'staging' or 'prod'
  [input_value='production']
```

## What This Means

Pharos expects `ENV=prod` but Render set it to `ENV=production`

## How to Fix (2 minutes)

### Step 1: Open Render Dashboard

```
https://dashboard.render.com
```

### Step 2: Navigate to Your Service

```
Dashboard → Services → pharos-cloud-api
```

### Step 3: Open Environment Tab

```
Left sidebar → Environment
```

### Step 4: Find ENV Variable

Look for this row:
```
┌─────────┬──────────────┬────────┐
│ Key     │ Value        │ Action │
├─────────┼──────────────┼────────┤
│ ENV     │ production   │ Edit   │  ← WRONG VALUE
└─────────┴──────────────┴────────┘
```

### Step 5: Edit ENV Variable

Click **Edit** button, change to:
```
┌─────────┬──────────────┬────────┐
│ Key     │ Value        │ Action │
├─────────┼──────────────┼────────┤
│ ENV     │ prod         │ Save   │  ← CORRECT VALUE
└─────────┴──────────────┴────────┘
```

### Step 6: Verify JWT_SECRET_KEY

Scroll down and find:
```
┌──────────────────┬────────────────────────────────────┬────────┐
│ Key              │ Value                              │ Action │
├──────────────────┼────────────────────────────────────┼────────┤
│ JWT_SECRET_KEY   │ a1b2c3d4e5f6...                   │ Edit   │  ← Should be 64 chars
└──────────────────┴────────────────────────────────────┴────────┘
```

**If missing or shows default value**, add it:
1. Click **"Add Environment Variable"**
2. Key: `JWT_SECRET_KEY`
3. Value: Generate using command below
4. Click **"Add"**

**Generate secure key**:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Example output (copy this):
```
a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2
```

### Step 7: Save Changes

Click **"Save Changes"** button at bottom

### Step 8: Wait for Redeploy

Render will automatically redeploy (2-3 minutes)

Watch the **Logs** tab for progress

---

## Expected Success

After fixing, you should see in logs:

```
✅ Settings loaded successfully
✅ ENV=prod
✅ JWT_SECRET_KEY validated (64 characters)
✅ Running Alembic migrations...
✅ Migrations completed
✅ Starting Uvicorn server...
✅ Application startup complete
✅ Listening on http://0.0.0.0:10000
```

---

## Quick Checklist

Before saving, verify these values:

- [ ] **ENV**: `prod` (NOT `production`, `PROD`, or `Prod`)
- [ ] **JWT_SECRET_KEY**: 64-character random hex (NOT default value)
- [ ] **PHAROS_ADMIN_TOKEN**: 64-character random hex (auto-generated)
- [ ] **DATABASE_URL**: NeonDB connection string (starts with `postgresql+asyncpg://`)
- [ ] **UPSTASH_REDIS_REST_URL**: Upstash URL (starts with `https://`)
- [ ] **UPSTASH_REDIS_REST_TOKEN**: Upstash token (long string)

---

## Visual: Before vs After

### ❌ BEFORE (Wrong)
```
ENV = production          ← Wrong value
JWT_SECRET_KEY = (empty)  ← Missing
```

### ✅ AFTER (Correct)
```
ENV = prod                                              ← Correct
JWT_SECRET_KEY = a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6...  ← Secure
```

---

## Still Having Issues?

### If ENV error persists:
1. Double-check spelling: `prod` (lowercase, no extra characters)
2. Click **Save Changes** button
3. Wait for automatic redeploy (2-3 minutes)
4. Check logs for new errors

### If JWT_SECRET_KEY error persists:
1. Verify value is exactly 64 characters
2. Verify it's NOT: `change-this-secret-key-in-production-min-32-chars-long`
3. Generate new one: `python -c "import secrets; print(secrets.token_hex(32))"`
4. Click **Save Changes**

### If deployment still fails:
1. Check Render logs for specific error message
2. Verify all environment variables are set correctly
3. Check database connection (NeonDB)
4. Check Redis connection (Upstash)

---

## Need More Help?

**Detailed guide**: `backend/docs/deployment/FIX_RENDER_ENV.md`  
**Complete deployment guide**: `backend/RENDER_FREE_DEPLOYMENT.md`  
**Quick start**: `backend/docs/deployment/DEPLOY_NOW.md`

---

## Summary

**Two fixes needed**:
1. Change `ENV` from `production` to `prod`
2. Verify `JWT_SECRET_KEY` is set to secure random value

**Where**: Render Dashboard → Environment tab  
**Time**: 2 minutes  
**Result**: Successful deployment

---

**Ready?** Go to https://dashboard.render.com and make these changes!
