# Render Free Tier Deployment Checklist

**Quick Reference**: Step-by-step checklist for deploying Pharos to Render Free tier

---

## Pre-Deployment Checklist

- [ ] GitHub repository is up to date
- [ ] `render.yaml` configured with NeonDB and Upstash
- [ ] `Dockerfile.cloud` exists and is correct
- [ ] Requirements files exist (`requirements-base.txt`, `requirements-cloud.txt`)
- [ ] Alembic migrations are up to date
- [ ] Health endpoint exists (`/health`)

**Verify**: Run `python verify_render_config.py` in backend directory

---

## Deployment Steps

### 1. Commit and Push

- [ ] Commit all changes
  ```bash
  git add backend/deployment/render.yaml
  git add backend/deployment/Dockerfile.cloud
  git commit -m "Configure Render free tier deployment"
  ```

- [ ] Push to GitHub
  ```bash
  git push origin main
  ```

### 2. Create Render Service

- [ ] Go to https://dashboard.render.com
- [ ] Click **"New +"** → **"Web Service"**
- [ ] Connect GitHub repository
- [ ] Select `pharos` repository
- [ ] Verify Render detects `render.yaml`

### 3. Configure Service

- [ ] **Name**: `pharos-cloud-api`
- [ ] **Region**: Oregon (or closest)
- [ ] **Branch**: `main`
- [ ] **Root Directory**: `backend`
- [ ] **Runtime**: Docker
- [ ] **Plan**: Free

### 4. Verify Environment Variables

- [ ] `DATABASE_URL` (NeonDB connection string)
- [ ] `UPSTASH_REDIS_REST_URL`
- [ ] `UPSTASH_REDIS_REST_TOKEN`
- [ ] `PHAROS_ADMIN_TOKEN` (auto-generated)
- [ ] `JWT_SECRET_KEY` (auto-generated)

### 5. Deploy

- [ ] Click **"Create Web Service"**
- [ ] Wait for build (10-15 minutes)
- [ ] Monitor build logs for errors

---

## Post-Deployment Verification

### 1. Test Health Endpoint

- [ ] Get service URL from Render dashboard
- [ ] Test health endpoint:
  ```bash
  curl https://pharos-cloud-api.onrender.com/health
  ```
- [ ] Verify response:
  ```json
  {
    "status": "healthy",
    "database": "connected",
    "redis": "connected"
  }
  ```

### 2. Test API Documentation

- [ ] Visit `https://pharos-cloud-api.onrender.com/docs`
- [ ] Verify Swagger UI loads
- [ ] Check all endpoints are listed

### 3. Copy API Token

- [ ] Go to Render dashboard → Environment
- [ ] Copy `PHAROS_ADMIN_TOKEN` value
- [ ] Save securely (you'll need it for Ronin)

### 4. Run Test Suite

- [ ] Update `test_render_deployment.py` with:
  - Service URL
  - API token
- [ ] Run tests:
  ```bash
  python test_render_deployment.py
  ```
- [ ] Verify all tests pass

---

## Keep-Alive Setup (Optional but Recommended)

### 1. Sign Up for UptimeRobot

- [ ] Go to https://uptimerobot.com
- [ ] Create free account
- [ ] Verify email

### 2. Create Monitor

- [ ] Click **"Add New Monitor"**
- [ ] **Type**: HTTP(s)
- [ ] **Name**: Pharos Keep-Alive
- [ ] **URL**: `https://pharos-cloud-api.onrender.com/health`
- [ ] **Interval**: 5 minutes
- [ ] Click **"Create Monitor"**

### 3. Verify Keep-Alive

- [ ] Wait 5 minutes
- [ ] Check Render logs for health check requests
- [ ] Verify service stays warm (no cold starts)

**Full Guide**: See `UPTIMEROBOT_SETUP.md`

---

## Ronin Integration Setup

### 1. Configure Ronin

- [ ] Set environment variables:
  ```bash
  PHAROS_API_URL=https://pharos-cloud-api.onrender.com
  PHAROS_API_KEY=<YOUR_PHAROS_ADMIN_TOKEN>
  PHAROS_TIMEOUT=5000
  ```

### 2. Test Connection

- [ ] Run test script:
  ```python
  import requests
  
  response = requests.get(
      "https://pharos-cloud-api.onrender.com/health"
  )
  print(response.json())
  ```

### 3. Ingest Test Repository

- [ ] Ingest a small test repo:
  ```bash
  curl -X POST https://pharos-cloud-api.onrender.com/api/ingest/github \
    -H "X-API-Key: YOUR_TOKEN" \
    -d '{"repo_url": "https://github.com/octocat/Hello-World"}'
  ```

### 4. Test Context Retrieval

- [ ] Ask Ronin a question about the test repo
- [ ] Verify Ronin calls Pharos API
- [ ] Verify context is returned
- [ ] Verify Ronin generates answer with context

---

## Monitoring Setup

### 1. Render Dashboard

- [ ] Bookmark service URL
- [ ] Check logs regularly
- [ ] Monitor metrics (CPU, RAM)
- [ ] Set up email alerts (optional)

### 2. NeonDB Dashboard

- [ ] Check database size
- [ ] Monitor connection count
- [ ] Review query performance

### 3. Upstash Dashboard

- [ ] Check command count
- [ ] Monitor storage usage
- [ ] Review latency metrics

---

## Troubleshooting Checklist

### If Health Check Fails

- [ ] Check Render logs for errors
- [ ] Verify DATABASE_URL is correct
- [ ] Verify UPSTASH credentials are correct
- [ ] Check if migrations ran successfully
- [ ] Restart service

### If Build Fails

- [ ] Check build logs for errors
- [ ] Verify Dockerfile.cloud is correct
- [ ] Verify requirements files exist
- [ ] Check for syntax errors in code
- [ ] Verify alembic.ini exists

### If API Returns 401

- [ ] Verify PHAROS_ADMIN_TOKEN is correct
- [ ] Check X-API-Key header is included
- [ ] Verify token hasn't been rotated

### If Context Retrieval is Slow

- [ ] Check if service is cold starting
- [ ] Enable keep-alive monitoring
- [ ] Reduce max_chunks parameter
- [ ] Check Render logs for performance issues

### If Out of Memory

- [ ] Check RAM usage in Render dashboard
- [ ] Reduce MAX_QUEUE_SIZE
- [ ] Disable CHUNK_ON_RESOURCE_CREATE
- [ ] Consider upgrading to paid tier

---

## Success Criteria

- ✅ Health endpoint returns 200 OK
- ✅ API documentation accessible
- ✅ Database connected (NeonDB)
- ✅ Redis connected (Upstash)
- ✅ Context retrieval works (<2s)
- ✅ Keep-alive prevents cold starts
- ✅ Ronin can call Pharos API
- ✅ No errors in Render logs

---

## Next Steps After Deployment

1. **Ingest Your Repositories**
   - Start with small repos (<100 files)
   - Monitor storage usage
   - Test context retrieval

2. **Test Ronin Integration**
   - Ask questions about your code
   - Verify context quality
   - Measure response times

3. **Monitor Performance**
   - Check logs daily
   - Monitor RAM usage
   - Track API response times

4. **Plan for Scale**
   - If storage >400MB, plan upgrade
   - If RAM usage >400MB, plan upgrade
   - If cold starts problematic, upgrade to paid tier

---

## Cost Tracking

### Current (Free Tier)
- Render Free: $0/month
- NeonDB Free: $0/month
- Upstash Free: $0/month
- UptimeRobot Free: $0/month
- **Total**: $0/month

### When to Upgrade
- Storage >512MB → NeonDB Scale ($19/mo)
- RAM usage >400MB → Render Starter ($7/mo)
- Redis >10K commands/day → Upstash Pro ($10/mo)
- Cold starts problematic → Render Starter ($7/mo)

### Estimated Paid Tier Cost
- Render Starter: $7/month
- NeonDB Scale: $19/month (if needed)
- Upstash Pro: $10/month (if needed)
- **Total**: $7-36/month (depending on usage)

---

## Documentation References

- **Full Deployment Guide**: `RENDER_FREE_DEPLOYMENT.md`
- **Keep-Alive Setup**: `UPTIMEROBOT_SETUP.md`
- **Test Suite**: `test_render_deployment.py`
- **Verification Script**: `verify_render_config.py`
- **Pharos + Ronin Vision**: `../PHAROS_RONIN_VISION.md`
- **Quick Reference**: `../.kiro/steering/PHAROS_RONIN_QUICK_REFERENCE.md`

---

**Status**: Ready to deploy  
**Estimated Time**: 30 minutes (first time)  
**Difficulty**: Easy

**Let's deploy Pharos to Render!** 🚀
