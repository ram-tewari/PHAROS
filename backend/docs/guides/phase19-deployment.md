# Phase 19 Cloud Deployment Guide

## Overview

This guide covers deploying the Pharos Cloud API to Render's free tier. The Cloud API is a lightweight control plane that dispatches repository ingestion tasks to edge workers without loading heavy ML dependencies.

## Prerequisites

- GitHub account
- Render account (free tier)
- Neon PostgreSQL database (provisioned)
- Qdrant Cloud vector database (provisioned)
- Upstash Redis instance (provisioned)

## Architecture Overview

```
User → Cloud API (Render) → Redis Queue → Edge Worker (Local)
         ↓
    Neon Postgres (Metadata)
    Qdrant Cloud (Vectors)
```

The Cloud API runs in `MODE=CLOUD` which excludes PyTorch and other heavy ML libraries, keeping memory usage under 512MB.

## Infrastructure Setup

### Step 1: Provision Neon Database

1. Go to [https://neon.tech](https://neon.tech)
2. Create a new project
3. Copy the connection string (format: `postgresql://user:pass@ep-xxx.neon.tech/neondb`)
4. Save for environment configuration

**Free Tier Limits**:
- 3GB storage
- Scales to zero when inactive
- Unlimited queries

### Step 2: Provision Qdrant Cloud

1. Go to [https://cloud.qdrant.io](https://cloud.qdrant.io)
2. Create a 1GB free cluster
3. Copy the cluster URL and API key
4. Save for environment configuration

**Free Tier Limits**:
- 1GB storage
- ~1M vectors (64 dimensions)
- Unlimited queries

### Step 3: Provision Upstash Redis

1. Go to [https://upstash.com](https://upstash.com)
2. Create a Redis database
3. Copy the REST URL and REST token (not the regular Redis URL)
4. Save for environment configuration

**Free Tier Limits**:
- 10,000 commands per day
- 256MB storage
- HTTP-based access (no port forwarding needed)

### Step 4: Generate Admin Token

The Cloud API requires a Bearer token for authentication to prevent unauthorized access:

```bash
# Generate a secure random token
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save this token - you'll need it for:
- Cloud API environment variable (`PHAROS_ADMIN_TOKEN`)
- API requests (`Authorization: Bearer <token>`)

## Render Deployment

### Step 1: Prepare Repository

Ensure your repository has:

```
backend/
├── app/
├── requirements-base.txt
├── requirements-cloud.txt
├── .env.cloud.template
└── render.yaml
```

The `render.yaml` file should contain:

```yaml
services:
  - type: web
    name: neo-alexandria-cloud-api
    env: python
    region: oregon
    plan: free
    buildCommand: pip install -r requirements-cloud.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: MODE
        value: CLOUD
      - key: UPSTASH_REDIS_REST_URL
        sync: false
      - key: UPSTASH_REDIS_REST_TOKEN
        sync: false
      - key: NEON_DATABASE_URL
        sync: false
      - key: QDRANT_URL
        sync: false
      - key: QDRANT_API_KEY
        sync: false
      - key: PHAROS_ADMIN_TOKEN
        sync: false
    healthCheckPath: /health
```

### Step 2: Connect to Render

1. Log in to [Render Dashboard](https://dashboard.render.com)
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Select the repository containing Pharos

### Step 3: Configure Service

Render will auto-detect `render.yaml`. Verify the configuration:

- **Name**: `neo-alexandria-cloud-api`
- **Environment**: Python 3
- **Region**: Oregon (or closest to you)
- **Branch**: `main` (or your deployment branch)
- **Build Command**: `pip install -r requirements-cloud.txt`
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### Step 4: Set Environment Variables

Add the following environment variables in Render dashboard:

| Variable | Value | Description |
|----------|-------|-------------|
| `MODE` | `CLOUD` | Deployment mode (excludes ML libraries) |
| `UPSTASH_REDIS_REST_URL` | `https://xxx.upstash.io` | Upstash Redis REST URL |
| `UPSTASH_REDIS_REST_TOKEN` | `your-token` | Upstash Redis REST token |
| `NEON_DATABASE_URL` | `postgresql://...` | Neon PostgreSQL connection string |
| `QDRANT_URL` | `https://xxx.qdrant.io` | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | `your-api-key` | Qdrant Cloud API key |
| `PHAROS_ADMIN_TOKEN` | `your-secure-token` | Admin token for API authentication |

**Security Note**: Mark all variables as "Secret" in Render to prevent exposure in logs.

### Step 5: Deploy

1. Click "Create Web Service"
2. Render will build and deploy automatically
3. Monitor build logs for errors
4. Wait for "Live" status (typically 2-3 minutes)

### Step 6: Verify Deployment

Test the health check endpoint:

```bash
curl https://your-app.onrender.com/health
```

Expected response:
```json
{
  "status": "healthy",
  "services": {
    "redis": "connected",
    "database": "connected",
    "qdrant": "connected"
  }
}
```

## API Usage

### Submit Repository for Ingestion

```bash
curl -X POST https://your-app.onrender.com/api/v1/ingestion/ingest/github.com/user/repo \
  -H "Authorization: Bearer YOUR_PHAROS_ADMIN_TOKEN"
```

Response:
```json
{
  "status": "dispatched",
  "job_id": 1,
  "queue_position": 1,
  "target": "RTX-4070-Node",
  "queue_size": 1,
  "max_queue_size": 10
}
```

### Check Worker Status

```bash
curl https://your-app.onrender.com/api/v1/ingestion/worker/status
```

Response:
```json
{
  "status": "Training Graph on github.com/user/repo"
}
```

### View Job History

```bash
curl https://your-app.onrender.com/api/v1/ingestion/jobs/history?limit=10
```

Response:
```json
{
  "jobs": [
    {
      "repo_url": "github.com/user/repo",
      "status": "complete",
      "duration_seconds": 127.5,
      "files_processed": 342,
      "embeddings_generated": 342,
      "timestamp": "2024-01-20T10:30:00Z"
    }
  ]
}
```

## Monitoring

### Render Dashboard

Monitor your service in the Render dashboard:

- **Metrics**: CPU, memory, request count
- **Logs**: Real-time application logs
- **Events**: Deployment history
- **Health**: Automatic health checks

### Health Check Endpoint

The `/health` endpoint is checked every 30 seconds:

- **200 OK**: All services connected
- **503 Service Unavailable**: One or more services down

### Log Monitoring

View logs in Render dashboard or via CLI:

```bash
# Install Render CLI
npm install -g render-cli

# View logs
render logs -s neo-alexandria-cloud-api
```

## Troubleshooting

### Build Failures

**Problem**: Build fails with "No module named 'torch'"

**Solution**: Verify `requirements-cloud.txt` does NOT include torch:
```bash
# requirements-cloud.txt should have:
-r requirements-base.txt
psycopg2-binary==2.9.9
qdrant-client==1.7.0

# NOT torch or torch-geometric
```

**Problem**: Build exceeds memory limit

**Solution**: Ensure MODE=CLOUD is set to prevent loading ML libraries

### Runtime Errors

**Problem**: 503 Service Unavailable on /health

**Solution**: Check environment variables are set correctly:
```bash
# Verify in Render dashboard:
- UPSTASH_REDIS_REST_URL
- UPSTASH_REDIS_REST_TOKEN
- NEON_DATABASE_URL
- QDRANT_URL
- QDRANT_API_KEY
```

**Problem**: 401 Unauthorized on /ingest

**Solution**: Include Bearer token in request:
```bash
curl -X POST https://your-app.onrender.com/api/v1/ingestion/ingest/github.com/user/repo \
  -H "Authorization: Bearer YOUR_PHAROS_ADMIN_TOKEN"
```

**Problem**: 429 Too Many Requests

**Solution**: Queue is full (10 pending tasks). Wait for edge worker to process jobs or check worker status.

### Connection Issues

**Problem**: Cannot connect to Neon database

**Solution**: 
1. Verify connection string format: `postgresql://user:pass@host/db`
2. Check Neon project is not suspended (free tier scales to zero)
3. Test connection locally:
```bash
psql "postgresql://user:pass@ep-xxx.neon.tech/neondb"
```

**Problem**: Cannot connect to Qdrant

**Solution**:
1. Verify cluster is running in Qdrant dashboard
2. Check API key is correct
3. Test connection:
```bash
curl https://xxx.qdrant.io/collections \
  -H "api-key: YOUR_API_KEY"
```

**Problem**: Cannot connect to Upstash Redis

**Solution**:
1. Use REST URL (not regular Redis URL)
2. Use REST token (not password)
3. Test connection:
```bash
curl https://xxx.upstash.io/get/test \
  -H "Authorization: Bearer YOUR_REST_TOKEN"
```

### Performance Issues

**Problem**: Slow response times (>1s)

**Solution**:
1. Check Render service is not sleeping (free tier sleeps after 15min inactivity)
2. Upgrade to Starter plan ($7/month) for always-on service
3. Monitor memory usage - may need to optimize queries

**Problem**: Out of memory errors

**Solution**:
1. Verify MODE=CLOUD is set (prevents loading ML libraries)
2. Check for memory leaks in application code
3. Upgrade to Starter plan for 512MB guaranteed memory

## Scaling

### Free Tier Limitations

- **Memory**: 512MB shared
- **CPU**: Shared
- **Sleep**: After 15 minutes of inactivity
- **Bandwidth**: 100GB/month

### Upgrade Options

**Starter Plan ($7/month)**:
- 512MB guaranteed memory
- Always-on (no sleep)
- Faster CPU
- 100GB bandwidth

**Standard Plan ($25/month)**:
- 2GB memory
- Dedicated CPU
- 400GB bandwidth
- Priority support

### Horizontal Scaling

Not available on free tier. For horizontal scaling:
1. Upgrade to Standard plan or higher
2. Enable auto-scaling in Render dashboard
3. Configure min/max instances

## Security Best Practices

### Environment Variables

- Mark all credentials as "Secret" in Render
- Never commit `.env` files to Git
- Rotate credentials regularly
- Use strong, random tokens for PHAROS_ADMIN_TOKEN

### API Authentication

- Always use HTTPS (enforced by Render)
- Include Bearer token in all /ingest requests
- Monitor authentication failures in logs
- Implement rate limiting (future enhancement)

### Network Security

- All external APIs use HTTPS
- No inbound ports required
- Upstash Redis uses HTTP REST (no port forwarding)
- Qdrant uses HTTPS with API key

## Cost Analysis

### Monthly Costs (Free Tier)

- Render Free Tier: **$0**
- Neon Free Tier: **$0** (3GB storage)
- Qdrant Cloud Free: **$0** (1GB cluster)
- Upstash Redis Free: **$0** (10K commands/day)

**Total: $0/month**

### Scaling Costs

If you need to scale:

- Render Starter: **$7/month**
- Neon Pro: **$19/month** (unlimited storage)
- Qdrant Cloud: **$25/month** (4GB cluster)
- Upstash Redis: **$10/month** (100K commands/day)

**Total Scaled: $61/month**

## Maintenance

### Updates and Deployments

Render auto-deploys on Git push:

1. Push changes to GitHub
2. Render detects changes
3. Builds and deploys automatically
4. Zero-downtime deployment

### Manual Deployment

Force a deployment in Render dashboard:

1. Go to service page
2. Click "Manual Deploy"
3. Select branch
4. Click "Deploy"

### Rollback

Rollback to previous deployment:

1. Go to service page
2. Click "Events" tab
3. Find previous successful deployment
4. Click "Rollback"

## Next Steps

- [Edge Worker Setup Guide](phase19-edge-setup.md) - Set up local GPU worker
- [Monitoring Guide](phase19-monitoring.md) - Monitor system health
- [Troubleshooting Guide](troubleshooting.md) - Common issues and solutions

## Support

- **Documentation**: [Pharos Docs](../README.md)
- **Issues**: [GitHub Issues](https://github.com/your-org/pharos/issues)
- **Render Support**: [Render Documentation](https://render.com/docs)
