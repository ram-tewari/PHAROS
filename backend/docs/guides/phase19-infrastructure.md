# Phase 19 Infrastructure Setup Guide

This guide provides step-by-step instructions for setting up the infrastructure required for Neo Alexandria's hybrid edge-cloud architecture.

## Overview

The Phase 19 architecture requires four external services:

1. **Neon Database** - Serverless PostgreSQL for metadata storage
2. **Qdrant Cloud** - Vector database for embeddings
3. **Upstash Redis** - HTTP-based Redis for task queue and status
4. **Render** - Cloud hosting for the API (optional, can self-host)

All services offer free tiers suitable for development and small-scale production use.

## Prerequisites

- GitHub account (for Render deployment)
- Email address for service signups
- Credit card (may be required for verification, but not charged on free tiers)

---

## 1. Neon Database Setup

Neon provides serverless PostgreSQL with a generous free tier (0.5GB storage, 1 compute unit).

### Step 1: Create Account

1. Go to https://neon.tech
2. Click "Sign Up" and authenticate with GitHub, Google, or email
3. Verify your email if required

### Step 2: Create Project

1. Click "Create Project" or "New Project"
2. Configure project:
   - **Name**: `neo-alexandria` (or your preferred name)
   - **Region**: Choose closest to your location (e.g., `US East (Ohio)`)
   - **PostgreSQL Version**: `15` (recommended)
   - **Compute Size**: `0.25 CU` (free tier)
3. Click "Create Project"

### Step 3: Get Connection String

1. After project creation, you'll see the connection details
2. Copy the **Connection String** (format: `postgresql://user:password@host/database`)
3. Save this as `DATABASE_URL` for later

**Example:**
```
postgresql://neondb_owner:<REDACTED-rotate>@ep-cool-name-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
```

### Step 4: Configure Database

The database schema will be created automatically by Alembic migrations when you first run the application.

### Verification

Test the connection:
```bash
# Install psql if not already installed
# Ubuntu/Debian: sudo apt-get install postgresql-client
# macOS: brew install postgresql

# Test connection (replace with your connection string)
psql "postgresql://user:password@host/database"
```

You should see a PostgreSQL prompt. Type `\q` to exit.

---

## 2. Qdrant Cloud Setup

Qdrant provides vector database hosting with a free tier (1GB storage, 1M vectors).

### Step 1: Create Account

1. Go to https://cloud.qdrant.io
2. Click "Sign Up" and authenticate with GitHub or email
3. Verify your email

### Step 2: Create Cluster

1. Click "Create Cluster"
2. Configure cluster:
   - **Name**: `neo-alexandria`
   - **Cloud Provider**: `AWS` (recommended)
   - **Region**: Choose closest to your Neon database region
   - **Cluster Type**: `Free` (1GB storage)
3. Click "Create"
4. Wait 2-3 minutes for cluster provisioning

### Step 3: Get API Credentials

1. Once cluster is ready, click on it to view details
2. Copy the **Cluster URL** (format: `https://xyz-abc.aws.cloud.qdrant.io`)
3. Click "API Keys" tab
4. Click "Create API Key"
5. Give it a name (e.g., `neo-alexandria-key`)
6. Copy the **API Key** (you won't be able to see it again!)
7. Save both as `QDRANT_URL` and `QDRANT_API_KEY`

**Example:**
```
QDRANT_URL=https://abc123-def456.us-east-1.aws.cloud.qdrant.io
QDRANT_API_KEY=<REDACTED-rotate>
```

### Step 4: Create Collections (Optional)

Collections will be created automatically by the application, but you can create them manually:

1. In Qdrant dashboard, go to "Collections"
2. Click "Create Collection"
3. Configure:
   - **Name**: `code_embeddings`
   - **Vector Size**: `64`
   - **Distance**: `Cosine`
4. Click "Create"

### Verification

Test the connection:
```bash
# Using curl
curl -X GET "https://your-cluster.aws.cloud.qdrant.io/collections" \
  -H "api-key: your-api-key"
```

You should see a JSON response with collection information.

---

## 3. Upstash Redis Setup

Upstash provides serverless Redis with HTTP API and a generous free tier (10K commands/day).

### Step 1: Create Account

1. Go to https://upstash.com
2. Click "Sign Up" and authenticate with GitHub, Google, or email
3. Verify your email

### Step 2: Create Database

1. Click "Create Database"
2. Configure database:
   - **Name**: `neo-alexandria-queue`
   - **Type**: `Regional` (free tier)
   - **Region**: Choose closest to your location
   - **Eviction**: `No eviction` (recommended)
3. Click "Create"

### Step 3: Get Connection Details

1. Click on your database to view details
2. Scroll to "REST API" section
3. Copy the following:
   - **UPSTASH_REDIS_REST_URL**: The REST API endpoint
   - **UPSTASH_REDIS_REST_TOKEN**: The authentication token

**Example:**
```
UPSTASH_REDIS_REST_URL=https://us1-abc-123.upstash.io
UPSTASH_REDIS_REST_TOKEN=AXXXeyJpZCI6IjEyMzQ1Njc4OTAiLCJ1c2VybmFtZSI6ImRlZmF1bHQifQ==
```

### Step 4: Configure for Python Client

The Python `upstash-redis` library uses slightly different variable names:

```bash
UPSTASH_REDIS_URL=https://us1-abc-123.upstash.io
UPSTASH_REDIS_TOKEN=AXXXeyJpZCI6IjEyMzQ1Njc4OTAiLCJ1c2VybmFtZSI6ImRlZmF1bHQifQ==
```

### Verification

Test the connection:
```bash
# Using curl
curl -X POST "https://your-redis.upstash.io/ping" \
  -H "Authorization: Bearer your-token"
```

You should see: `{"result":"PONG"}`

Or test with Python:
```python
from upstash_redis import Redis
import os

redis = Redis(
    url=os.getenv("UPSTASH_REDIS_URL"),
    token=os.getenv("UPSTASH_REDIS_TOKEN")
)
print(redis.ping())  # Should print: True
```

---

## 4. Render Setup (Cloud API Deployment)

Render provides free hosting for web services (512MB RAM, sleeps after 15 min inactivity).

### Step 1: Create Account

1. Go to https://render.com
2. Click "Get Started" and authenticate with GitHub
3. Authorize Render to access your repositories

### Step 2: Fork/Push Repository

Ensure your Neo Alexandria repository is on GitHub:

```bash
# If not already on GitHub, create a new repository and push
git remote add origin https://github.com/yourusername/neo-alexandria-2.0.git
git push -u origin main
```

### Step 3: Create Web Service

1. In Render dashboard, click "New +"
2. Select "Web Service"
3. Connect your GitHub repository
4. Configure service:
   - **Name**: `neo-alexandria-api`
   - **Region**: Choose closest to your Neon database
   - **Branch**: `main`
   - **Root Directory**: `backend`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements-cloud.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: `Free`

### Step 4: Configure Environment Variables

In the "Environment" section, add the following variables:

| Key | Value | Notes |
|-----|-------|-------|
| `MODE` | `CLOUD` | Required |
| `DATABASE_URL` | Your Neon connection string | From step 1 |
| `QDRANT_URL` | Your Qdrant cluster URL | From step 2 |
| `QDRANT_API_KEY` | Your Qdrant API key | From step 2 |
| `UPSTASH_REDIS_URL` | Your Upstash Redis URL | From step 3 |
| `UPSTASH_REDIS_TOKEN` | Your Upstash Redis token | From step 3 |
| `PHAROS_ADMIN_TOKEN` | Generate a secure token | See below |
| `PYTHON_VERSION` | `3.11.0` | Optional |

**Generate PHAROS_ADMIN_TOKEN:**
```bash
# Generate a secure random token
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save this token - you'll need it to authenticate API requests.

### Step 5: Deploy

1. Click "Create Web Service"
2. Render will automatically deploy your application
3. Wait 5-10 minutes for first deployment
4. Once deployed, you'll get a URL like: `https://neo-alexandria-api.onrender.com`

### Step 6: Configure Health Check

Render automatically uses the `/health` endpoint for health checks. Verify it's working:

```bash
curl https://your-app.onrender.com/health
```

You should see:
```json
{
  "status": "healthy",
  "mode": "CLOUD",
  "services": {
    "database": "connected",
    "redis": "connected",
    "qdrant": "connected"
  }
}
```

### Verification

Test the API:
```bash
# Test worker status endpoint
curl https://your-app.onrender.com/api/v1/ingestion/worker/status

# Test ingestion endpoint (requires auth)
curl -X POST "https://your-app.onrender.com/api/v1/ingestion/ingest/https://github.com/user/repo" \
  -H "Authorization: Bearer your-pharos-admin-token"
```

---

## 5. Edge Worker Setup

The edge worker runs on your local machine with GPU support.

### Step 1: Clone Repository

```bash
git clone https://github.com/yourusername/neo-alexandria-2.0.git
cd neo-alexandria-2.0/backend
```

### Step 2: Run Setup Script

**Linux/macOS:**
```bash
chmod +x setup_edge.sh
./setup_edge.sh
```

**Windows:**
```powershell
.\setup_edge.ps1
```

The script will:
- Check Python version
- Detect CUDA/GPU
- Create virtual environment
- Install dependencies
- Create `.env.edge` from template
- Optionally install as system service

### Step 3: Configure Environment

Edit `.env.edge` with your credentials:

```bash
# Mode
MODE=EDGE

# Redis (from step 3)
UPSTASH_REDIS_URL=https://your-redis.upstash.io
UPSTASH_REDIS_TOKEN=your-token

# Qdrant (from step 2)
QDRANT_URL=https://your-cluster.aws.cloud.qdrant.io
QDRANT_API_KEY=your-api-key

# Optional: Database (if worker needs direct DB access)
DATABASE_URL=postgresql://user:password@host/database
```

### Step 4: Test Worker

```bash
# Activate virtual environment
source .venv/bin/activate  # Linux/macOS
.\.venv\Scripts\Activate.ps1  # Windows

# Run worker
python worker.py
```

You should see:
```
[INFO] Edge Worker starting...
[INFO] CUDA available: True
[INFO] GPU: NVIDIA GeForce RTX 4070
[INFO] Worker status: Idle
[INFO] Polling queue every 2 seconds...
```

### Step 5: Install as Service (Optional)

The setup script can install the worker as a system service:

**Linux (systemd):**
```bash
sudo systemctl start neo-alexandria-worker
sudo systemctl enable neo-alexandria-worker
sudo systemctl status neo-alexandria-worker
```

**Windows (NSSM):**
```powershell
nssm start NeoAlexandriaWorker
nssm status NeoAlexandriaWorker
```

See `NSSM_SERVICE_CONFIG.md` for detailed Windows service configuration.

---

## 6. End-to-End Verification

Test the complete workflow:

### Step 1: Submit Repository

```bash
curl -X POST "https://your-app.onrender.com/api/v1/ingestion/ingest/https://github.com/octocat/Hello-World" \
  -H "Authorization: Bearer your-pharos-admin-token"
```

Expected response:
```json
{
  "job_id": "abc123",
  "queue_position": 1,
  "queue_size": 1,
  "message": "Repository queued for processing"
}
```

### Step 2: Check Worker Status

```bash
curl https://your-app.onrender.com/api/v1/ingestion/worker/status
```

Expected response (while processing):
```json
{
  "status": "Training Graph on https://github.com/octocat/Hello-World",
  "last_updated": "2024-01-15T10:30:00Z"
}
```

### Step 3: Check Job History

```bash
curl https://your-app.onrender.com/api/v1/ingestion/jobs/history
```

Expected response:
```json
{
  "jobs": [
    {
      "job_id": "abc123",
      "repo_url": "https://github.com/octocat/Hello-World",
      "status": "complete",
      "files_processed": 42,
      "embeddings_generated": 42,
      "duration_seconds": 127.5,
      "completed_at": "2024-01-15T10:32:07Z"
    }
  ]
}
```

### Step 4: Verify Embeddings in Qdrant

```bash
curl -X POST "https://your-qdrant-cluster.aws.cloud.qdrant.io/collections/code_embeddings/points/scroll" \
  -H "api-key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"limit": 10}'
```

You should see embeddings with metadata including `file_path` and `repo_url`.

---

## Cost Breakdown

All services offer free tiers suitable for development:

| Service | Free Tier | Limits | Cost After Free Tier |
|---------|-----------|--------|---------------------|
| **Neon** | 0.5GB storage, 1 compute unit | 10GB data transfer/month | $0.102/GB storage, $0.16/compute hour |
| **Qdrant** | 1GB storage, 1M vectors | 100 requests/sec | $25/month for 4GB |
| **Upstash** | 10K commands/day | 256MB storage | $0.20 per 100K commands |
| **Render** | 512MB RAM, 750 hours/month | Sleeps after 15 min | $7/month for always-on |
| **Edge Worker** | Local hardware | Electricity costs | N/A |

**Total Monthly Cost (Free Tier):** $0

**Estimated Cost at Scale:**
- 100 repos/day: Still free tier
- 1000 repos/day: ~$10-20/month
- 10000 repos/day: ~$50-100/month

---

## Troubleshooting

### Cloud API Won't Start

1. Check Render logs:
   - Go to Render dashboard → Your service → Logs
   - Look for errors in build or runtime logs

2. Verify environment variables:
   - Ensure all required variables are set
   - Check for typos in URLs and tokens

3. Test database connection:
   ```bash
   psql "your-database-url"
   ```

### Edge Worker Can't Connect to Redis

1. Verify credentials:
   ```python
   from upstash_redis import Redis
   import os
   from dotenv import load_dotenv
   
   load_dotenv('.env.edge')
   redis = Redis(
       url=os.getenv('UPSTASH_REDIS_URL'),
       token=os.getenv('UPSTASH_REDIS_TOKEN')
   )
   print(redis.ping())
   ```

2. Check firewall:
   - Ensure outbound HTTPS (443) is allowed
   - Upstash uses HTTPS, not Redis protocol (6379)

### Embeddings Not Appearing in Qdrant

1. Check worker logs for upload errors
2. Verify Qdrant API key has write permissions
3. Check collection exists:
   ```bash
   curl "https://your-cluster.aws.cloud.qdrant.io/collections" \
     -H "api-key: your-api-key"
   ```

### High Costs

1. Monitor usage in each service dashboard
2. Check for runaway processes or infinite loops
3. Consider upgrading to paid tiers with better pricing
4. Implement rate limiting and queue caps

---

## Security Best Practices

1. **Rotate Tokens Regularly**
   - Change PHAROS_ADMIN_TOKEN every 90 days
   - Rotate API keys if compromised

2. **Use Environment Variables**
   - Never commit credentials to Git
   - Use `.env` files (already in `.gitignore`)

3. **Restrict API Access**
   - Use PHAROS_ADMIN_TOKEN for all ingestion requests
   - Consider IP whitelisting for production

4. **Monitor Logs**
   - Check Render logs for authentication failures
   - Monitor Redis for unusual activity

5. **Backup Data**
   - Neon provides automatic backups
   - Export Qdrant collections periodically
   - Keep local backups of important data

---

## Next Steps

1. **Test the System**: Submit a few test repositories
2. **Monitor Performance**: Check logs and metrics
3. **Scale as Needed**: Upgrade to paid tiers when necessary
4. **Customize**: Adjust worker parameters for your use case
5. **Integrate**: Connect to your frontend or other services

---

## Additional Resources

- [Neon Documentation](https://neon.tech/docs)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [Upstash Documentation](https://docs.upstash.com/)
- [Render Documentation](https://render.com/docs)
- [Neo Alexandria Documentation](./docs/)

---

## Support

For issues or questions:
- Check existing documentation in `backend/docs/`
- Review Phase 19 requirements and design documents
- Open an issue on GitHub
- Contact the development team
