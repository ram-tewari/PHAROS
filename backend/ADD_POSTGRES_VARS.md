# 🔧 Add PostgreSQL Component Variables

## New Error

```
POSTGRES_PASSWORD must be set when using PostgreSQL
```

## What Happened

The settings validation requires individual PostgreSQL components (server, user, password, database, port) even though we're providing a complete `DATABASE_URL`. This is overly strict validation, but we can work around it.

## Quick Fix (2 minutes)

Add these 5 environment variables in Render Dashboard:

### Go to Environment Tab

Already there? Great! If not:
1. https://dashboard.render.com
2. Click **pharos-cloud-api**
3. Click **Environment** tab

### Add These Variables

Click **"Add Environment Variable"** for each:

#### 1. POSTGRES_SERVER
```
Key: POSTGRES_SERVER
Value: ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech
```

#### 2. POSTGRES_USER
```
Key: POSTGRES_USER
Value: neondb_owner
```

#### 3. POSTGRES_PASSWORD
```
Key: POSTGRES_PASSWORD
Value: npg_2Lv8pxVJzgyd
```

#### 4. POSTGRES_DB
```
Key: POSTGRES_DB
Value: neondb
```

#### 5. POSTGRES_PORT
```
Key: POSTGRES_PORT
Value: 5432
```

### Save Changes

Click **"Save Changes"** at the bottom

### Wait for Redeploy

2-3 minutes for automatic redeploy

## Why This Is Needed

The validation logic checks for these individual components when it detects PostgreSQL in the `DATABASE_URL`. Even though `DATABASE_URL` contains all this information, the validator requires them separately.

These values are extracted from your NeonDB connection string:
```
postgresql+asyncpg://neondb_owner:npg_2Lv8pxVJzgyd@ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech/neondb
                     └─────┬─────┘ └──────┬──────┘ └────────────────────────┬────────────────────────┘ └──┬──┘
                        USER         PASSWORD                            SERVER                          DB
```

## Alternative: Update render.yaml

The `backend/deployment/render.yaml` has been updated with these variables. To use it:

```bash
git add backend/deployment/render.yaml
git commit -m "Add PostgreSQL component variables for validation"
git push origin master
```

Render will auto-redeploy with the new configuration.

## Expected Result

After adding these variables:

```
✅ Settings loaded successfully
✅ POSTGRES_SERVER validated
✅ POSTGRES_USER validated
✅ POSTGRES_PASSWORD validated
✅ POSTGRES_DB validated
✅ POSTGRES_PORT validated
✅ Running Alembic migrations...
✅ Migrations completed
✅ Starting Uvicorn server...
✅ Application startup complete
```

## Complete Environment Variables

After this fix, you'll have:

**Core**:
- MODE=CLOUD
- ENV=prod
- DATABASE_URL=(full connection string)

**PostgreSQL Components** (NEW):
- POSTGRES_SERVER
- POSTGRES_USER
- POSTGRES_PASSWORD
- POSTGRES_DB
- POSTGRES_PORT

**Redis**:
- UPSTASH_REDIS_REST_URL
- UPSTASH_REDIS_REST_TOKEN

**Auth**:
- JWT_SECRET_KEY
- PHAROS_ADMIN_TOKEN
- ALLOWED_REDIRECT_URLS

**Resource Limits**:
- MAX_QUEUE_SIZE=10
- TASK_TTL_SECONDS=3600
- MAX_WORKERS=2

**RAG**:
- CHUNK_ON_RESOURCE_CREATE=false
- GRAPH_EXTRACTION_ENABLED=true
- SYNTHETIC_QUESTIONS_ENABLED=false
- EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1

## Summary

**Action**: Add 5 PostgreSQL component variables  
**Time**: 2 minutes  
**Why**: Settings validation requires them  
**Note**: DATABASE_URL still takes precedence for actual connections

---

**Go add them now**: https://dashboard.render.com → Environment tab
