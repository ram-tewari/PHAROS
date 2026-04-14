# Serverless Deployment Gotchas & Solutions

**Last Updated**: April 11, 2026  
**Status**: Production-Tested

This document covers common "gotchas" when deploying Pharos with serverless databases (NeonDB, Upstash) and their solutions.

---

## 🚨 Critical Gotcha #1: NeonDB Connection Drops

### The Problem

**NeonDB scales to zero** and actively kills idle connections after 5 minutes of inactivity. If your FastAPI app tries to use a dead connection to run a pgvector search, it will crash with:

```
OperationalError: connection closed
asyncpg.exceptions.ConnectionDoesNotExistError: connection was closed in the middle of operation
```

This happens because:
1. NeonDB suspends compute after 5 minutes idle
2. Existing connections are terminated
3. SQLAlchemy tries to reuse a dead connection from the pool
4. Query fails with "connection closed" error

### The Solution

**Enable `pool_pre_ping=True`** in your SQLAlchemy engine configuration. This checks if the connection is alive before using it.

#### Already Implemented ✅

The fix is already in `backend/app/shared/database.py`:

```python
engine_params = {
    "pool_size": 3,              # Base pool size
    "max_overflow": 7,           # Additional connections on demand
    "pool_recycle": 300,         # Recycle connections after 5 minutes
    "pool_pre_ping": True,       # 🔥 THE LIFESAVER: Check if connection is alive
    "pool_timeout": 30,          # Wait 30s for connection from pool
    "isolation_level": "READ COMMITTED",
}
```

#### How It Works

1. **Before each query**: SQLAlchemy sends a lightweight "ping" (SELECT 1)
2. **If connection is dead**: Automatically creates a new connection
3. **If connection is alive**: Uses the existing connection
4. **Result**: No more "connection closed" errors

#### Performance Impact

- **Overhead**: ~1-2ms per query (negligible)
- **Benefit**: Prevents crashes and automatic recovery
- **Trade-off**: Worth it for serverless databases

### Verification

Test that pool_pre_ping is working:

```bash
# 1. Start your app
uvicorn app.main:app --reload

# 2. Make a request (creates connection)
curl http://localhost:8000/api/resources

# 3. Wait 6 minutes (NeonDB suspends and kills connection)
sleep 360

# 4. Make another request (should work without error)
curl http://localhost:8000/api/resources

# Expected: Request succeeds (connection automatically recreated)
# Without pool_pre_ping: Request fails with "connection closed"
```

---

## 🚨 Critical Gotcha #2: Upstash Requires SSL/TLS

### The Problem

**Upstash routes traffic over the public internet** and absolutely mandates secure connections. Standard local Redis uses `redis://`. Upstash requires `rediss://` (with two S's).

If you miss the second 's', your app will fail with:

```
redis.exceptions.ConnectionError: Error connecting to Redis
ssl.SSLError: [SSL: WRONG_VERSION_NUMBER] wrong version number
```

This happens because:
1. Upstash enforces SSL/TLS for security
2. `redis://` tries to connect without SSL
3. Upstash rejects the connection
4. App crashes or cache is disabled

### The Solution

**Use `rediss://` (two S's) in your REDIS_URL** and configure SSL in the Redis client.

#### Already Implemented ✅

The fix is already in `backend/app/shared/cache.py`:

```python
# Validate Redis URL format
if redis_url:
    if not redis_url.startswith("redis://") and not redis_url.startswith("rediss://"):
        logger.error("Invalid REDIS_URL format (must start with redis:// or rediss://)")
        return
    
    # Warn if using non-SSL with Upstash
    if is_upstash and redis_url.startswith("redis://"):
        logger.error(
            "CRITICAL: Upstash requires SSL/TLS. "
            "Your REDIS_URL starts with 'redis://' but should start with 'rediss://' (two S's). "
            "Connection will fail. Please update your REDIS_URL."
        )
        return

# SSL/TLS configuration for Upstash
if is_upstash:
    connection_kwargs["ssl"] = True
    connection_kwargs["ssl_cert_reqs"] = "required"  # Verify SSL certificate
```

#### Correct REDIS_URL Format

```bash
# ❌ WRONG (will fail with Upstash)
REDIS_URL=redis://default:password@host:port

# ✅ CORRECT (works with Upstash)
REDIS_URL=rediss://default:password@host:port
#         ^^^^^^^ Note the two S's
```

#### How to Get the Correct URL

1. Go to Upstash dashboard
2. Select your Redis database
3. Copy the **Redis URL** (not REST URL)
4. Verify it starts with `rediss://`
5. Paste into Render environment variables

### Verification

Test that SSL/TLS is working:

```bash
# 1. Set REDIS_URL with rediss://
export REDIS_URL="rediss://default:password@host:port"

# 2. Start your app
uvicorn app.main:app --reload

# 3. Check logs for successful connection
# Expected: "Connecting to Upstash Redis (native protocol): rediss://..."
# Expected: "Redis connection successful"

# 4. Test cache endpoint
curl http://localhost:8000/api/monitoring/cache-stats

# Expected: {"hits": 0, "misses": 0, "hit_rate": 0.0}
# Without SSL: Connection error
```

---

## 🚨 Gotcha #3: Celery with Upstash SSL

### The Problem

If you're using Celery for background tasks with Upstash Redis, you need to configure SSL for both the broker and backend.

### The Solution

Update your Celery configuration:

```python
import os
from celery import Celery

# This URL MUST start with rediss://
REDIS_URL = os.getenv("REDIS_URL")

celery_app = Celery(
    "pharos_worker",
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Configure SSL for Upstash
celery_app.conf.update(
    broker_connection_retry_on_startup=True,  # Required for Upstash TLS
    
    # SSL configuration for Redis backend
    redis_backend_use_ssl={
        "ssl_cert_reqs": "required",  # Verify SSL certificate (production)
        # "ssl_cert_reqs": "none",    # Skip verification (debugging only)
    },
    
    # SSL configuration for Redis broker
    broker_use_ssl={
        "ssl_cert_reqs": "required",  # Verify SSL certificate (production)
        # "ssl_cert_reqs": "none",    # Skip verification (debugging only)
    }
)
```

### Verification

```bash
# 1. Start Celery worker
celery -A app.tasks.celery_tasks worker --loglevel=info

# Expected: "Connected to rediss://..."
# Expected: No SSL errors

# 2. Send a test task
python -c "from app.tasks.celery_tasks import test_task; test_task.delay()"

# Expected: Task executes successfully
# Without SSL config: SSL handshake errors
```

---

## 🚨 Gotcha #4: NeonDB Pooled vs Direct Connection

### The Problem

NeonDB provides two connection strings:
1. **Direct Connection**: Connects directly to compute instance
2. **Pooled Connection**: Uses PgBouncer connection pooler

For serverless deployments, you MUST use the **Pooled Connection** string.

### Why Pooled Connection?

- **Connection pooling**: Handles connection pooling at database level
- **Prevents exhaustion**: Limits total connections across all workers
- **Better performance**: Reuses connections efficiently
- **Required for serverless**: Direct connections don't survive scale-to-zero

### The Solution

Use the **Pooled Connection** string from NeonDB dashboard:

```bash
# ❌ WRONG (Direct Connection)
DATABASE_URL=postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/db

# ✅ CORRECT (Pooled Connection)
DATABASE_URL=postgresql://user:pass@ep-xxx-pooler.us-east-2.aws.neon.tech/db
#                                    ^^^^^^^ Note the "-pooler" suffix
```

### How to Get Pooled Connection

1. Go to NeonDB dashboard
2. Select your project
3. Click "Connection Details"
4. Select **"Pooled connection"** (not "Direct connection")
5. Copy the connection string
6. Verify it contains `-pooler` in the hostname

### Verification

```bash
# Check if using pooled connection
echo $DATABASE_URL | grep -o "pooler"

# Expected: "pooler"
# If empty: You're using direct connection (wrong)
```

---

## 🚨 Gotcha #5: SSL Mode for NeonDB

### The Problem

NeonDB requires SSL/TLS for all connections. If your connection string doesn't specify `sslmode=require`, connections may fail or be insecure.

### The Solution

Ensure your DATABASE_URL includes `?sslmode=require`:

```bash
# ❌ WRONG (no SSL mode specified)
DATABASE_URL=postgresql://user:pass@host/db

# ✅ CORRECT (SSL mode specified)
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
```

#### Already Implemented ✅

The fix is already in `backend/app/shared/database.py`:

```python
# Detect if using NeonDB (serverless PostgreSQL)
is_neondb = "neon.tech" in database_url or "neon.db" in database_url

# SSL Configuration
if is_neondb:
    # NeonDB requires SSL with SNI routing
    connect_args["ssl"] = "require"  # Enforce SSL for NeonDB
    logger.info("NeonDB detected: SSL required, SNI routing enabled")
else:
    # Other PostgreSQL providers (Render, AWS RDS, etc.)
    connect_args["ssl"] = "prefer"  # Use SSL if available
```

### Verification

```bash
# Check if SSL mode is in connection string
echo $DATABASE_URL | grep -o "sslmode=require"

# Expected: "sslmode=require"
# If empty: Add ?sslmode=require to your DATABASE_URL
```

---

## 🚨 Gotcha #6: Connection Pool Exhaustion

### The Problem

If you set `pool_size` too high, you'll exhaust NeonDB's connection limit (100 on free tier).

**Formula**: `(pool_size + max_overflow) × workers = total_connections`

**Example (TOO HIGH)**:
- Pool size: 10
- Max overflow: 20
- Workers: 4
- Total: (10 + 20) × 4 = 120 connections
- NeonDB limit: 100
- Result: Connection exhaustion errors

### The Solution

Use conservative pool settings:

```python
# ✅ CORRECT (for Render Starter with 2 workers)
pool_size = 3              # Base pool size
max_overflow = 7           # Additional connections on demand
workers = 2                # Gunicorn workers
total = (3 + 7) × 2 = 20   # Total connections (safe for NeonDB: 100 max)
```

#### Already Implemented ✅

The configuration is already optimized in `backend/app/shared/database.py`:

```python
# Get pool configuration from environment (allows per-deployment tuning)
pool_size = int(os.getenv("DB_POOL_SIZE", "3"))  # Reduced from 5 for Render
max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "7"))  # Total: 10 connections per worker

# Calculate total connections: (pool_size + max_overflow) × workers
# Example: (3 + 7) × 2 workers = 20 connections (safe for Render Starter: 22 max)
```

### Verification

```bash
# Check pool status
curl http://localhost:8000/api/monitoring/pool-status

# Expected output:
{
  "size": 3,
  "max_overflow": 7,
  "checked_out": 2,
  "total_capacity": 10,
  "pool_usage_percent": 20.0
}

# If pool_usage_percent > 90%: Reduce workers or increase pool size
```

---

## 🚨 Gotcha #7: Statement Timeout

### The Problem

Long-running queries can block connections and cause timeouts. Without a statement timeout, a runaway query can hold a connection indefinitely.

### The Solution

Set a statement timeout (30s recommended):

```python
# Already implemented in backend/app/shared/database.py
statement_timeout = int(os.getenv("DB_STATEMENT_TIMEOUT", "30000"))  # 30s in milliseconds

connect_args = {
    "server_settings": {
        "statement_timeout": str(statement_timeout),  # Milliseconds
    }
}
```

### Verification

```bash
# Test statement timeout (should fail after 30s)
curl -X POST http://localhost:8000/api/test/slow-query

# Expected: Timeout error after 30s
# Without timeout: Query runs indefinitely
```

---

## 🚨 Gotcha #8: Memory Limits on Render Starter

### The Problem

Render Starter has only 512MB RAM. If you run too many workers or load large models, you'll hit OOM (Out of Memory) errors.

### The Solution

Use conservative worker count and monitor memory:

```bash
# ✅ CORRECT (for Render Starter: 512MB RAM)
WEB_CONCURRENCY=2  # 2 workers × 150MB = 300MB (safe)

# ❌ WRONG (for Render Starter: 512MB RAM)
WEB_CONCURRENCY=4  # 4 workers × 150MB = 600MB (OOM)
```

#### Memory Breakdown (Render Starter)

```
OS & System: 100MB
Gunicorn Master: 50MB
Worker 1: 150MB
Worker 2: 150MB
Headroom: 62MB
-----------------
Total: 512MB
```

### Verification

```bash
# SSH into Render instance
render ssh

# Check memory usage
ps aux | grep gunicorn

# Expected: Each worker uses ~150MB RSS
# If > 200MB per worker: Reduce workers or upgrade to Render Standard
```

---

## 📋 Troubleshooting Checklist

### NeonDB Connection Issues

- [ ] Using **Pooled Connection** string (contains `-pooler`)
- [ ] `pool_pre_ping=True` enabled
- [ ] `sslmode=require` in connection string
- [ ] Total connections < 100 (NeonDB free tier limit)
- [ ] Statement timeout set (30s recommended)

### Upstash Redis Issues

- [ ] REDIS_URL starts with `rediss://` (two S's)
- [ ] SSL enabled: `ssl=True`
- [ ] SSL cert verification: `ssl_cert_reqs="required"`
- [ ] Celery SSL configured (if using Celery)
- [ ] Request count < 10K/day (free tier limit)

### Render Deployment Issues

- [ ] Workers ≤ 2 (for Starter: 512MB RAM)
- [ ] Pool size ≤ 3 (per worker)
- [ ] Max overflow ≤ 7 (per worker)
- [ ] Total connections ≤ 20 (2 workers × 10)
- [ ] Health check passing: `/health`

---

## 🔍 Debugging Commands

### Check Database Connection

```bash
# Test connection
curl http://localhost:8000/health

# Check pool status
curl http://localhost:8000/api/monitoring/pool-status

# Check for connection errors in logs
render logs | grep "connection"
```

### Check Redis Connection

```bash
# Test cache
curl http://localhost:8000/api/monitoring/cache-stats

# Check for SSL errors in logs
render logs | grep "ssl"

# Test Redis directly
redis-cli -u $REDIS_URL ping
```

### Check Memory Usage

```bash
# SSH into Render
render ssh

# Check memory
free -h

# Check worker memory
ps aux | grep gunicorn

# Check for OOM errors
dmesg | grep -i "out of memory"
```

---

## 📚 Additional Resources

- [NeonDB Connection Pooling](https://neon.tech/docs/connect/connection-pooling)
- [Upstash Redis TLS](https://docs.upstash.com/redis/features/tls)
- [SQLAlchemy Pool Pre-Ping](https://docs.sqlalchemy.org/en/20/core/pooling.html#pool-disconnects-pessimistic)
- [Render Memory Limits](https://render.com/docs/free#free-web-services)

---

## ✅ Summary

All critical gotchas are already handled in the codebase:

1. ✅ **NeonDB connection drops**: `pool_pre_ping=True`
2. ✅ **Upstash SSL/TLS**: `rediss://` validation and SSL config
3. ✅ **Pooled connection**: Documentation and validation
4. ✅ **SSL mode**: Automatic detection and enforcement
5. ✅ **Connection pool**: Conservative sizing (3 + 7 = 10 per worker)
6. ✅ **Statement timeout**: 30s default
7. ✅ **Memory limits**: 2 workers for Render Starter

**Your deployment is production-ready!** 🚀
