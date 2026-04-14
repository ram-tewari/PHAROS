# 🚀 Pre-Flight Checklist - Ready to Deploy!

**Date**: April 14, 2026  
**Status**: ✅ ALL SYSTEMS GO  
**Deployment Target**: Render Free Tier  
**Total Cost**: $0/month

---

## ✅ Configuration Verified

### Infrastructure Credentials
- ✅ **NeonDB PostgreSQL**: Connection string configured
  - Host: `ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech`
  - Database: `neondb`
  - User: `neondb_owner`
  - SSL: Required
  - Format: SQLAlchemy `postgresql+asyncpg://` ✓

- ✅ **Upstash Redis**: Credentials configured
  - URL: `https://living-sculpin-96916.upstash.io`
  - Token: Configured (hidden for security)
  - Protocol: REST API over HTTPS ✓

- ✅ **Render Configuration**: render.yaml ready
  - Service: `pharos-cloud-api`
  - Plan: Free (512MB RAM)
  - Region: Oregon
  - Auto-deploy: Enabled ✓

### Application Configuration
- ✅ **Dockerfile.cloud**: Optimized for 512MB RAM
- ✅ **Requirements**: All dependencies listed
- ✅ **Alembic**: Migrations ready (config/alembic.ini)
- ✅ **Health Check**: `/health` endpoint configured
- ✅ **Environment Variables**: All required vars set

### Verification Results
```
✅ PASS: render.yaml
✅ PASS: Dockerfile
✅ PASS: Requirements
✅ PASS: Alembic
✅ PASS: App Structure

Total: 5/5 checks passed
```

---

## 🎯 Deployment Commands

### Option 1: Automated (Recommended)

**Windows**:
```bash
deploy_to_render.bat
```

**Linux/Mac**:
```bash
chmod +x deploy_to_render.sh
./deploy_to_render.sh
```

### Option 2: Manual

```bash
# 1. Commit configuration
git add backend/deployment/render.yaml
git add backend/deployment/Dockerfile.cloud
git add backend/RENDER_FREE_DEPLOYMENT.md
git add backend/RENDER_DEPLOYMENT_CHECKLIST.md
git add backend/UPTIMEROBOT_SETUP.md
git add backend/verify_render_config.py
git add backend/test_render_deployment.py
git add RENDER_DEPLOYMENT_SUMMARY.md
git add DEPLOY_NOW.md
git add PRE_FLIGHT_CHECKLIST.md

git commit -m "Deploy Pharos to Render Free tier with NeonDB and Upstash"

# 2. Push to GitHub
git push origin main

# 3. Go to Render Dashboard
# https://dashboard.render.com
# Create New Web Service → Connect GitHub → Select "pharos"
```

---

## 📋 Deployment Timeline

### Phase 1: Push to GitHub (2 minutes)
- [ ] Run `git add` commands
- [ ] Commit with descriptive message
- [ ] Push to `main` branch
- [ ] Verify push succeeded

### Phase 2: Create Render Service (3 minutes)
- [ ] Go to https://dashboard.render.com
- [ ] Click "New +" → "Web Service"
- [ ] Connect GitHub repository
- [ ] Select "pharos" repository
- [ ] Verify Render detects render.yaml
- [ ] Review auto-populated settings
- [ ] Click "Create Web Service"

### Phase 3: Build & Deploy (10-15 minutes)
- [ ] Monitor build logs in Render dashboard
- [ ] Wait for "Build successful" message
- [ ] Wait for "Deploy live" message
- [ ] Service URL becomes active

### Phase 4: Verification (5 minutes)
- [ ] Test health endpoint
- [ ] Check API documentation
- [ ] Copy PHAROS_ADMIN_TOKEN
- [ ] Run test script

### Phase 5: Keep-Alive Setup (5 minutes)
- [ ] Sign up at UptimeRobot
- [ ] Create monitor
- [ ] Verify pings in logs

### Phase 6: Ronin Integration (5 minutes)
- [ ] Configure Ronin with Pharos URL
- [ ] Add API token to Ronin config
- [ ] Test connection
- [ ] Ingest test repository

**Total Time**: ~30-35 minutes

---

## 🧪 Post-Deployment Tests

### Test 1: Health Check
```bash
curl https://pharos-cloud-api.onrender.com/health
```

**Expected Response**:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "version": "2.0.0"
}
```

### Test 2: API Documentation
```bash
# Open in browser
https://pharos-cloud-api.onrender.com/docs
```

**Expected**: Swagger UI with all endpoints listed

### Test 3: Context Retrieval (Requires API Token)
```bash
curl -X POST https://pharos-cloud-api.onrender.com/api/context/retrieve \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_PHAROS_ADMIN_TOKEN" \
  -d '{
    "query": "test query",
    "codebase": "test-repo",
    "max_chunks": 5
  }'
```

**Expected**: JSON response with context (or 404 if no repos ingested yet)

### Test 4: GitHub Ingestion (Requires API Token)
```bash
curl -X POST https://pharos-cloud-api.onrender.com/api/ingest/github \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_PHAROS_ADMIN_TOKEN" \
  -d '{
    "repo_url": "https://github.com/octocat/Hello-World",
    "branch": "master"
  }'
```

**Expected**: JSON response with ingestion status

---

## 🔑 Important Information to Save

After deployment, save these values:

### Service URL
```
https://pharos-cloud-api.onrender.com
```

### API Token (from Render Dashboard)
```
PHAROS_ADMIN_TOKEN=<copy from Render environment variables>
```

### Ronin Configuration
```bash
PHAROS_API_URL=https://pharos-cloud-api.onrender.com
PHAROS_API_KEY=<paste PHAROS_ADMIN_TOKEN here>
PHAROS_TIMEOUT=5000
```

---

## 📊 Resource Limits (Free Tier)

### Render Free
- **RAM**: 512MB (monitor usage, upgrade if >400MB)
- **CPU**: Shared (adequate for API requests)
- **Bandwidth**: 100GB/month (sufficient for testing)
- **Build Minutes**: 500/month (plenty for deployments)
- **Cold Start**: 50 seconds after 15 min idle

### NeonDB Free
- **Storage**: 512MB (monitor usage, upgrade if >400MB)
- **Compute**: 0.5 units (adequate for queries)
- **Connections**: 100 max (sufficient for 2 workers)
- **Data Transfer**: 5GB/month (sufficient for testing)

### Upstash Free
- **Storage**: 256MB (sufficient for cache)
- **Commands**: 10K/day (~400 requests/hour)
- **Latency**: <50ms (excellent for cache)
- **Bandwidth**: 1GB/month (sufficient for testing)

---

## 🚨 Monitoring & Alerts

### What to Monitor

**Render Dashboard**:
- [ ] CPU usage (should be <50% average)
- [ ] RAM usage (should be <400MB)
- [ ] Request count (track growth)
- [ ] Error rate (should be <1%)
- [ ] Response time (should be <2s)

**NeonDB Dashboard**:
- [ ] Storage usage (should be <400MB)
- [ ] Connection count (should be <20)
- [ ] Query performance (should be <100ms)

**Upstash Dashboard**:
- [ ] Command count (should be <10K/day)
- [ ] Storage usage (should be <200MB)
- [ ] Latency (should be <50ms)

**UptimeRobot Dashboard**:
- [ ] Uptime percentage (should be >99%)
- [ ] Response time (should be <1s)
- [ ] Downtime incidents (should be 0)

### Alert Thresholds

Set up alerts for:
- ❗ RAM usage >450MB (approaching limit)
- ❗ Storage >450MB (approaching limit)
- ❗ Redis commands >9K/day (approaching limit)
- ❗ Error rate >5% (investigate issues)
- ❗ Response time >5s (performance issue)
- ❗ Downtime >5 minutes (service issue)

---

## 🆘 Troubleshooting Guide

### Issue: Build Failed

**Symptoms**: Render shows "Build failed" in logs

**Possible Causes**:
1. Dockerfile syntax error
2. Missing requirements file
3. Python dependency conflict
4. Out of build minutes

**Solutions**:
1. Check Render build logs for specific error
2. Verify Dockerfile.cloud is correct
3. Test Docker build locally: `docker build -f deployment/Dockerfile.cloud .`
4. Check requirements files exist and are valid

### Issue: Service Won't Start

**Symptoms**: Build succeeds but service shows "Starting..." forever

**Possible Causes**:
1. Database connection error
2. Redis connection error
3. Port binding issue
4. Migration failure

**Solutions**:
1. Check Render logs for error messages
2. Verify DATABASE_URL is correct
3. Verify Upstash credentials are correct
4. Check if migrations ran successfully

### Issue: 502 Bad Gateway

**Symptoms**: Health endpoint returns 502

**Possible Causes**:
1. Cold start (service spinning up)
2. Service crashed
3. Out of memory

**Solutions**:
1. Wait 50 seconds and retry (cold start)
2. Check Render logs for crash messages
3. Check RAM usage in Render dashboard
4. Restart service if needed

### Issue: Database Connection Error

**Symptoms**: Health endpoint shows "database": "disconnected"

**Possible Causes**:
1. NeonDB connection string incorrect
2. SSL mode not configured
3. NeonDB service down
4. Connection pool exhausted

**Solutions**:
1. Verify DATABASE_URL in Render environment
2. Check NeonDB dashboard for service status
3. Verify SSL mode is "require"
4. Restart service to reset connection pool

### Issue: Redis Connection Error

**Symptoms**: Health endpoint shows "redis": "disconnected"

**Possible Causes**:
1. Upstash credentials incorrect
2. Upstash service down
3. Network connectivity issue

**Solutions**:
1. Verify UPSTASH_REDIS_REST_URL and TOKEN
2. Check Upstash dashboard for service status
3. Test Redis connection manually
4. Restart service

---

## 💰 Cost Tracking

### Current (Free Tier)
| Service | Plan | Cost |
|---------|------|------|
| Render | Free | $0/mo |
| NeonDB | Free | $0/mo |
| Upstash | Free | $0/mo |
| UptimeRobot | Free | $0/mo |
| **Total** | | **$0/mo** |

### Upgrade Triggers
| Metric | Threshold | Upgrade To | Cost |
|--------|-----------|------------|------|
| RAM usage | >400MB | Render Starter | +$7/mo |
| Storage | >400MB | NeonDB Scale | +$19/mo |
| Redis commands | >9K/day | Upstash Pro | +$10/mo |
| Cold starts | Frequent | Render Starter | +$7/mo |

### Estimated Paid Tier
- **Minimum**: $7/mo (Render Starter only)
- **Typical**: $17/mo (Render + Upstash)
- **Maximum**: $36/mo (All services upgraded)

---

## 📖 Documentation Quick Links

### Getting Started
- **This Checklist**: `PRE_FLIGHT_CHECKLIST.md` (you are here)
- **Quick Start**: `DEPLOY_NOW.md`
- **Summary**: `RENDER_DEPLOYMENT_SUMMARY.md`

### Detailed Guides
- **Complete Guide**: `backend/RENDER_FREE_DEPLOYMENT.md`
- **Checklist**: `backend/RENDER_DEPLOYMENT_CHECKLIST.md`
- **Keep-Alive**: `backend/UPTIMEROBOT_SETUP.md`

### Scripts & Tools
- **Verify Config**: `backend/verify_render_config.py`
- **Test Deployment**: `backend/test_render_deployment.py`
- **Deploy Helper**: `deploy_to_render.bat` or `deploy_to_render.sh`

### Vision & Architecture
- **Pharos + Ronin Vision**: `PHAROS_RONIN_VISION.md`
- **Quick Reference**: `.kiro/steering/PHAROS_RONIN_QUICK_REFERENCE.md`

---

## ✅ Final Checklist

Before deploying, confirm:

- [x] Configuration verified (5/5 checks passed)
- [x] NeonDB connection string configured
- [x] Upstash credentials configured
- [x] render.yaml ready
- [x] Dockerfile.cloud ready
- [x] Documentation complete
- [x] Test scripts ready
- [ ] Git repository up to date
- [ ] Ready to commit and push
- [ ] Render account created
- [ ] GitHub connected to Render

After deploying, confirm:

- [ ] Build succeeded
- [ ] Service is live
- [ ] Health endpoint works
- [ ] API docs accessible
- [ ] API token copied
- [ ] Keep-alive configured
- [ ] Ronin configured
- [ ] Test repository ingested
- [ ] Context retrieval works
- [ ] End-to-end workflow tested

---

## 🎉 Ready to Deploy!

**All systems are GO!** ✅

**Next command**:
```bash
git add backend/deployment/render.yaml
git commit -m "Deploy Pharos to Render Free tier"
git push origin main
```

**Then**: Go to https://dashboard.render.com and create the web service!

**Estimated Time**: 30-35 minutes total  
**Cost**: $0/month  
**Difficulty**: Easy

**Let's deploy Pharos and test Ronin integration!** 🚀
