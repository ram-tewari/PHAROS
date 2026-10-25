# Phase 19 - Quick Start Guide

**Status**: Redis ✅ Connected | Database ✅ Connected | Qdrant ✅ Connected

## ✅ Infrastructure Complete!

All three cloud services are configured and tested:

✅ **Upstash Redis** - Queue management
- URL: `https://lucky-pug-47555.upstash.io`
- Status: **WORKING**

✅ **Neon PostgreSQL** - Database
- Host: `ep-fancy-grass-ah0xirjl-pooler.c-3.us-east-1.aws.neon.tech`
- Status: **WORKING**

✅ **Qdrant Cloud** - Vector database
- URL: `https://1387e31e-904c-48dc-8f3a-772c6da3621e.us-east4-0.gcp.cloud.qdrant.io`
- Status: **WORKING**

## Next Steps

### 1. Generate Secure Admin Token (1 minute)

**For production**, generate a secure token:

```powershell
# PowerShell
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
```

Update in `.env.staging`:
```bash
PHAROS_ADMIN_TOKEN=your-secure-token-here
```

### 2. Deploy to Render (10-15 minutes)

### Option A: Using render.yaml (Recommended)

1. **Commit your code** (don't commit .env.staging!):
   ```bash
   git add render.yaml
   git add requirements-cloud.txt
   git add app/
   git commit -m "Add Phase 19 Cloud API"
   git push origin main
   ```

2. **In Render Dashboard**:
   - Go to https://dashboard.render.com
   - Click "New" → "Blueprint"
   - Connect your GitHub repository
   - Select `render.yaml`
   - Click "Apply"

3. **Add Environment Variables**:
   - In Render dashboard, go to your service
   - Click "Environment"
   - Add each variable from `.env.staging`:
     ```
     MODE=CLOUD
     UPSTASH_REDIS_REST_URL=https://lucky-pug-47555.upstash.io
     UPSTASH_REDIS_REST_TOKEN=<REDACTED-UPSTASH_TOKEN-rotate>
     DATABASE_URL=your-neon-connection-string
     QDRANT_URL=your-qdrant-url
     QDRANT_API_KEY=your-qdrant-key
     PHAROS_ADMIN_TOKEN=your-admin-token
     MAX_QUEUE_SIZE=10
     TASK_TTL_SECONDS=3600
     ```
   - Click "Save Changes"

4. **Deploy**:
   - Render will automatically deploy
   - Wait for build to complete (5-10 minutes)
   - Note your app URL: `https://your-app.onrender.com`

### Option B: Manual Setup

1. **In Render Dashboard**:
   - New → Web Service
   - Connect GitHub repository
   - Configure:
     - **Name**: `neo-alexandria-cloud-api`
     - **Environment**: Python 3
     - **Build Command**: `pip install -r requirements-cloud.txt`
     - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Add all environment variables from above
   - Click "Create Web Service"

## Test Cloud API

Once deployed, test your endpoints:

```bash
# Set your Render URL
$CLOUD_API_URL = "https://your-app.onrender.com"

# Test health endpoint
Invoke-RestMethod -Uri "$CLOUD_API_URL/health"

# Test authentication (should return 401)
Invoke-RestMethod -Uri "$CLOUD_API_URL/api/v1/ingestion/ingest/github.com/test/repo"

# Test with valid token (should return 200)
Invoke-RestMethod -Uri "$CLOUD_API_URL/api/v1/ingestion/ingest/github.com/test/repo" `
  -Headers @{"Authorization"="Bearer YOUR_PHAROS_ADMIN_TOKEN"}

# Check worker status
Invoke-RestMethod -Uri "$CLOUD_API_URL/api/v1/ingestion/worker/status"
```

## Set Up Edge Worker Locally

### 1. Create Edge Environment File

```bash
# Copy template
cp .env.edge.template .env.edge

# Edit with your values
notepad .env.edge
```

Add:
```bash
MODE=EDGE
UPSTASH_REDIS_REST_URL=https://lucky-pug-47555.upstash.io
UPSTASH_REDIS_REST_TOKEN=<REDACTED-UPSTASH_TOKEN-rotate>
QDRANT_URL=your-qdrant-url
QDRANT_API_KEY=your-qdrant-key
WORKER_POLL_INTERVAL=2
```

### 2. Install Edge Dependencies

```bash
# Install PyTorch and dependencies
pip install -r requirements-edge.txt

# Verify installation
python -c "import torch; print(f'PyTorch: {torch.__version__}')"
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

### 3. Start Worker

```bash
# Test run (manual)
python worker.py

# You should see:
# 🚀 Edge Worker Starting...
# 📊 Hardware: CPU (or CUDA if available)
# 🔄 Polling queue every 2 seconds...
# ✅ Worker Status: Idle
```

## End-to-End Test

### 1. Submit Test Repository

```powershell
$CLOUD_API_URL = "https://your-app.onrender.com"
$TOKEN = "your-admin-token"

Invoke-RestMethod -Method Post `
  -Uri "$CLOUD_API_URL/api/v1/ingestion/ingest/github.com/octocat/Hello-World" `
  -Headers @{"Authorization"="Bearer $TOKEN"}
```

### 2. Monitor Processing

```powershell
# Watch worker status (run in loop)
while ($true) {
  $status = Invoke-RestMethod -Uri "$CLOUD_API_URL/api/v1/ingestion/worker/status"
  Write-Host "Worker Status: $($status.status)"
  Start-Sleep -Seconds 5
}

# Check job history
Invoke-RestMethod -Uri "$CLOUD_API_URL/api/v1/ingestion/jobs/history"
```

### 3. Verify in Qdrant

```powershell
# Check collection
Invoke-RestMethod -Uri "$QDRANT_URL/collections/code_embeddings" `
  -Headers @{"api-key"="$QDRANT_API_KEY"}
```

## Expected Timeline

- **Infrastructure Setup**: ✅ Complete (30 minutes)
- **Render Deployment**: ⏳ Next (15 minutes)
- **Edge Worker Setup**: ⏳ Pending (10 minutes)
- **End-to-End Test**: ⏳ Pending (5 minutes)
- **Total Remaining**: ~30 minutes

## Quick Commands Reference

### Deploy to Render
1. Go to https://dashboard.render.com
2. New → Web Service → Connect GitHub
3. Add environment variables from `.env.staging`
4. Deploy!

### Test Deployment
```powershell
.\test_deployment.ps1 -CloudApiUrl "https://your-app.onrender.com"
```

### Start Edge Worker
```powershell
# Create .env.edge (copy from .env.staging, change MODE=EDGE)
Copy-Item .env.edge.template .env.edge
notepad .env.edge

# Install dependencies
pip install -r requirements-edge.txt

# Start worker
python worker.py
```

### Monitor System
```powershell
.\monitor_deployment.ps1 -CloudApiUrl "https://your-app.onrender.com"
```

### Submit Test Job
```powershell
$CLOUD_API_URL = "https://your-app.onrender.com"
$TOKEN = "staging-admin-token-change-me-in-production"

Invoke-RestMethod -Method Post `
  -Uri "$CLOUD_API_URL/api/v1/ingestion/ingest/github.com/octocat/Hello-World" `
  -Headers @{"Authorization"="Bearer $TOKEN"}
```

## Troubleshooting

### Cloud API won't start
- Check Render logs for errors
- Verify all environment variables are set
- Test Redis/Qdrant connections manually

### Edge Worker won't start
- Check `.env.edge` file exists and has all variables
- Verify PyTorch installed: `python -c "import torch"`
- Check Redis connection: `python verify_staging_setup.py`

### Jobs not processing
- Check worker is running: `python worker.py`
- Check worker status via API
- Check Redis queue: Use Upstash dashboard
- Check worker logs for errors

### Embeddings not in Qdrant
- Verify Qdrant credentials
- Check worker completed successfully
- Check Qdrant collection exists
- Review worker logs for upload errors

## Next Steps

1. ✅ **Complete infrastructure setup** (Neon + Qdrant)
2. ✅ **Deploy Cloud API to Render**
3. ✅ **Set up Edge Worker locally**
4. ✅ **Run end-to-end test**
5. ⏳ **Monitor for 24-48 hours**
6. ⏳ **Fix test issues in parallel**
7. ⏳ **Deploy to production**

## Support

- **Deployment Guide**: `docs/guides/phase19-deployment.md`
- **Edge Setup**: `docs/guides/phase19-edge-setup.md`
- **Monitoring**: `docs/guides/phase19-monitoring.md`
- **API Docs**: `docs/api/ingestion.md`
- **Full Plan**: `PHASE19_STAGING_DEPLOYMENT_PLAN.md`

---

**You're 1/3 of the way there!** 🎉

Redis is working. Now set up Neon and Qdrant, and you'll be ready to deploy!
