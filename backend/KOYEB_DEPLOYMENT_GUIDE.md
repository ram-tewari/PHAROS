# Koyeb Deployment Guide - Pharos Backend

## Overview

This guide walks you through deploying Pharos to Koyeb's Free Tier, which provides:

- **24/7 Always-On**: No cold starts (unlike Render Free Tier)
- **512MB RAM**: Sufficient for cloud API (no ML workloads)
- **Zero Cost**: Free tier with no credit card required
- **Serverless**: Auto-scaling, auto-healing, zero-downtime deployments

## Prerequisites

### 1. External Services (Free Tier)

**NeonDB (PostgreSQL)**
- Sign up: https://neon.tech
- Create project: `pharos-db`
- Copy connection string: `postgresql://user:password@host/database?sslmode=require`

**Upstash (Redis)**
- Sign up: https://upstash.com
- Create database: `pharos-cache`
- Copy connection string: `rediss://default:password@host:6379`

### 2. Koyeb Account

- Sign up: https://www.koyeb.com
- No credit card required for free tier
- Install Koyeb CLI (optional, for IaC deployment):

```bash
# macOS
brew install koyeb/tap/koyeb-cli

# Linux
curl -fsSL https://cli.koyeb.com/install.sh | sh

# Windows
scoop install koyeb-cli
```

## Deployment Methods

### Method 1: Koyeb Dashboard (Easiest)

#### Step 1: Create Secrets

1. Go to https://app.koyeb.com/secrets
2. Click "Create Secret"
3. Create three secrets:

**Secret 1: database-url**
```
Name: database-url
Type: Simple
Value: postgresql://user:password@host/database?sslmode=require
```

**Secret 2: redis-url**
```
Name: redis-url
Type: Simple
Value: rediss://default:password@host:6379
```

**Secret 3: pharos-api-key**
```
Name: pharos-api-key
Type: Simple
Value: your-secure-api-key-here
```

#### Step 2: Create Service

1. Go to https://app.koyeb.com/services
2. Click "Create Service"
3. Select "Docker" as build method
4. Configure:

**Git Repository**
```
Repository: https://github.com/yourusername/pharos
Branch: main
```

**Build Configuration**
```
Dockerfile: backend/Dockerfile
Build context: backend
```

**Instance Configuration**
```
Region: Frankfurt (fra)
Instance type: nano (512MB RAM)
Scaling: min=1, max=1
```

**Port Configuration**
```
Port: 8000
Protocol: HTTP
Public: Yes
```

**Health Check**
```
Path: /health
Port: 8000
Protocol: HTTP
Interval: 30s
Timeout: 10s
Grace period: 60s
```

**Environment Variables**
```
ENVIRONMENT=production
PORT=8000
WEB_CONCURRENCY=2
LOG_LEVEL=info
JSON_LOGGING=true
TZ=UTC
```

**Secrets** (Link to created secrets)
```
DATABASE_URL → database-url
REDIS_URL → redis-url
PHAROS_API_KEY → pharos-api-key
```

5. Click "Deploy"

#### Step 3: Monitor Deployment

1. Watch build logs in real-time
2. Wait for health check to pass (~60 seconds)
3. Service will be available at: `https://pharos-api-<random>.koyeb.app`

### Method 2: Koyeb CLI (Infrastructure as Code)

#### Step 1: Login to Koyeb

```bash
koyeb login
```

#### Step 2: Create Secrets

```bash
# Database URL (NeonDB)
koyeb secrets create database-url \
  --value "postgresql://user:password@host/database?sslmode=require"

# Redis URL (Upstash)
koyeb secrets create redis-url \
  --value "rediss://default:password@host:6379"

# API Key
koyeb secrets create pharos-api-key \
  --value "your-secure-api-key-here"
```

#### Step 3: Deploy Service

```bash
# From repository root
cd backend
koyeb service create --config koyeb.yaml
```

#### Step 4: Monitor Deployment

```bash
# Watch deployment status
koyeb service get pharos-api

# Stream logs
koyeb logs pharos-api --follow

# Check health
curl https://pharos-api-<random>.koyeb.app/health
```

## Post-Deployment

### 1. Verify Deployment

```bash
# Health check
curl https://your-app.koyeb.app/health

# Expected response:
{
  "status": "healthy",
  "timestamp": "2026-04-11T12:00:00Z",
  "version": "1.0.0",
  "database": "connected",
  "redis": "connected"
}
```

### 2. Test API Endpoints

```bash
# Get API documentation
curl https://your-app.koyeb.app/docs

# Test context retrieval (requires API key)
curl -X POST https://your-app.koyeb.app/api/context/retrieve \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "query": "authentication",
    "codebase": "myapp",
    "max_chunks": 10
  }'
```

### 3. Monitor Performance

**Koyeb Dashboard**
- Metrics: https://app.koyeb.com/services/pharos-api/metrics
- Logs: https://app.koyeb.com/services/pharos-api/logs
- Events: https://app.koyeb.com/services/pharos-api/events

**Key Metrics to Watch**
- CPU usage: Should stay < 80%
- Memory usage: Should stay < 400MB (80% of 512MB)
- Request latency: P95 < 1s
- Error rate: < 1%

## Troubleshooting

### Build Failures

**Error: "Cannot find Dockerfile"**
```bash
# Solution: Ensure Dockerfile is in backend/ directory
ls backend/Dockerfile

# If missing, create it from this guide
```

**Error: "pip install failed"**
```bash
# Solution: Check requirements-cloud.txt exists
ls backend/config/requirements-cloud.txt

# Ensure requirements-base.txt is also present
ls backend/config/requirements-base.txt
```

### Runtime Failures

**Error: "DATABASE_URL not set"**
```bash
# Solution: Verify secret is created and linked
koyeb secrets list | grep database-url

# Recreate if missing
koyeb secrets create database-url --value "postgresql://..."
```

**Error: "Health check failed"**
```bash
# Solution: Check logs for startup errors
koyeb logs pharos-api --tail 100

# Common causes:
# 1. Database connection failed (check DATABASE_URL)
# 2. Redis connection failed (check REDIS_URL)
# 3. Migration failed (check alembic logs)
# 4. Port mismatch (ensure PORT=8000)
```

**Error: "Out of memory (OOM)"**
```bash
# Solution: Reduce worker count
koyeb service update pharos-api \
  --env WEB_CONCURRENCY=1

# Or upgrade to micro instance (1GB RAM)
koyeb service update pharos-api \
  --instance-type micro
```

### Migration Issues

**Error: "alembic: command not found"**
```bash
# Solution: Ensure alembic is in requirements-base.txt
grep alembic backend/config/requirements-base.txt

# Should see: alembic==1.x.x
```

**Error: "Migration failed: relation already exists"**
```bash
# Solution: Database already has schema, stamp current version
# SSH into container (not available on free tier)
# Alternative: Drop database and redeploy (development only!)

# For production: Create manual migration to handle existing schema
```

## Updating Deployment

### Update Code

```bash
# Push changes to Git
git add .
git commit -m "Update feature"
git push origin main

# Koyeb auto-deploys on push (if configured)
# Or manually trigger deployment:
koyeb service redeploy pharos-api
```

### Update Configuration

```bash
# Update environment variable
koyeb service update pharos-api \
  --env LOG_LEVEL=debug

# Update secret
koyeb secrets update database-url \
  --value "postgresql://new-connection-string"

# Redeploy to apply changes
koyeb service redeploy pharos-api
```

### Update Instance Type

```bash
# Upgrade to micro (1GB RAM) - $5/month
koyeb service update pharos-api \
  --instance-type micro \
  --env WEB_CONCURRENCY=3

# Upgrade to small (2GB RAM) - $10/month
koyeb service update pharos-api \
  --instance-type small \
  --env WEB_CONCURRENCY=4
```

## Monitoring & Debugging

### View Logs

```bash
# Real-time logs
koyeb logs pharos-api --follow

# Last 100 lines
koyeb logs pharos-api --tail 100

# Filter by level
koyeb logs pharos-api --level error

# Time range
koyeb logs pharos-api --since 1h
```

### Check Metrics

```bash
# Service status
koyeb service get pharos-api

# Instance status
koyeb instance list --service pharos-api

# Deployment history
koyeb deployment list --service pharos-api
```

### Debug Health Check

```bash
# Test health endpoint locally
curl http://localhost:8000/health

# Test on Koyeb
curl https://your-app.koyeb.app/health

# Check health check configuration
koyeb service get pharos-api --output json | jq '.health_checks'
```

## Cost Optimization

### Free Tier Limits

**Koyeb Free Tier**
- 1 service
- 1 instance (nano: 512MB RAM)
- 1 region
- 100GB bandwidth/month
- No custom domains

**NeonDB Free Tier**
- 0.5GB storage
- 1 project
- 3 branches
- Autosuspend after 5 minutes of inactivity

**Upstash Free Tier**
- 10,000 requests/day
- 256MB storage
- 1 database

### Upgrade Path

**Scenario 1: More Memory**
```
Koyeb Starter: $5/month (1GB RAM, micro instance)
Total: $5/month
```

**Scenario 2: More Requests**
```
Upstash Pro: $10/month (100K requests/day)
Total: $10/month
```

**Scenario 3: More Storage**
```
NeonDB Scale: $19/month (3GB storage, autoscaling)
Total: $19/month
```

**Scenario 4: Production Ready**
```
Koyeb Starter: $5/month (1GB RAM)
NeonDB Scale: $19/month (3GB storage)
Upstash Pro: $10/month (100K requests/day)
Total: $34/month
```

## Security Best Practices

### 1. Secrets Management

- ✅ Use Koyeb Secrets (not environment variables)
- ✅ Rotate API keys regularly
- ✅ Use strong passwords (32+ characters)
- ✅ Enable SSL/TLS for database connections

### 2. Network Security

- ✅ Use HTTPS only (Koyeb handles SSL termination)
- ✅ Restrict database access to Koyeb IPs
- ✅ Enable Redis AUTH (Upstash default)
- ✅ Use API key authentication for sensitive endpoints

### 3. Application Security

- ✅ Enable rate limiting (FastAPI middleware)
- ✅ Validate all inputs (Pydantic schemas)
- ✅ Sanitize SQL queries (SQLAlchemy ORM)
- ✅ Log security events (JSON logging)

## Performance Tuning

### 1. Worker Configuration

**512MB RAM (nano)**
```bash
WEB_CONCURRENCY=2  # Safe (2 × 150MB = 300MB)
```

**1GB RAM (micro)**
```bash
WEB_CONCURRENCY=3  # Safe (3 × 150MB = 450MB)
```

**2GB RAM (small)**
```bash
WEB_CONCURRENCY=4  # Safe (4 × 150MB = 600MB)
```

### 2. Database Connection Pooling

**gunicorn_conf.py** (already configured)
```python
# SQLAlchemy pool settings
pool_size = 3  # Base connections per worker
max_overflow = 7  # Additional connections under load
pool_pre_ping = True  # Test connections before use
```

**Total connections**: `workers × (pool_size + max_overflow)`
- 2 workers: 2 × 10 = 20 connections (safe for NeonDB free tier: 22 max)

### 3. Redis Caching

**Cache TTL** (Time To Live)
```python
# Code chunks: 1 hour (frequently accessed)
CACHE_TTL_CODE = 3600

# Search results: 5 minutes (dynamic)
CACHE_TTL_SEARCH = 300

# Embeddings: 24 hours (expensive to generate)
CACHE_TTL_EMBEDDINGS = 86400
```

## Rollback Procedure

### Rollback to Previous Deployment

```bash
# List deployments
koyeb deployment list --service pharos-api

# Rollback to previous deployment
koyeb service rollback pharos-api --deployment <deployment-id>

# Verify rollback
koyeb service get pharos-api
```

### Emergency Rollback

```bash
# Stop service (emergency only)
koyeb service pause pharos-api

# Fix issue locally
git revert HEAD
git push origin main

# Resume service
koyeb service resume pharos-api
```

## Next Steps

1. **Custom Domain** (Paid tier only)
   - Add CNAME record: `api.yourdomain.com → <koyeb-url>`
   - Configure in Koyeb Dashboard

2. **Auto-Scaling** (Paid tier only)
   - Set min=1, max=3 instances
   - Configure CPU/memory thresholds

3. **Multi-Region** (Paid tier only)
   - Deploy to multiple regions (fra, was, sin)
   - Use Koyeb's global load balancer

4. **CI/CD Integration**
   - GitHub Actions: Auto-deploy on push
   - GitLab CI: Auto-deploy on merge

## Support

- **Koyeb Docs**: https://www.koyeb.com/docs
- **Koyeb Community**: https://community.koyeb.com
- **Pharos Issues**: https://github.com/yourusername/pharos/issues

---

**Deployment Status**: Ready for production  
**Last Updated**: 2026-04-11  
**Version**: 1.0.0
