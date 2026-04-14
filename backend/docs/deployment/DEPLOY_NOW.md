# 🚀 Deploy Pharos to Render - Quick Start

**Status**: ✅ All checks passed - Ready to deploy!  
**Time**: 30 minutes total (15 min build + 15 min setup)  
**Cost**: $0/month (Free tier)

---

## ✅ Pre-Deployment Verification Complete

All configuration checks passed:
- ✅ render.yaml configured with NeonDB and Upstash
- ✅ Dockerfile.cloud ready
- ✅ Requirements files present
- ✅ Alembic migrations ready
- ✅ App structure verified

---

## 🎯 Deploy in 3 Steps

### Step 1: Push to GitHub (2 minutes)

```bash
# Commit configuration
git add backend/deployment/render.yaml backend/deployment/Dockerfile.cloud
git add backend/RENDER_FREE_DEPLOYMENT.md backend/RENDER_DEPLOYMENT_CHECKLIST.md
git add backend/UPTIMEROBOT_SETUP.md backend/verify_render_config.py
git add backend/test_render_deployment.py RENDER_DEPLOYMENT_SUMMARY.md
git commit -m "Configure Render free tier deployment with NeonDB and Upstash"

# Push to GitHub
git push origin main
```

### Step 2: Create Render Service (3 minutes)

1. Go to **https://dashboard.render.com**
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Select **"pharos"** repository
5. Render auto-detects `render.yaml` ✨
6. Verify settings:
   - Name: `pharos-cloud-api`
   - Region: `Oregon`
   - Branch: `main`
   - Plan: `Free`
7. Click **"Create Web Service"**

### Step 3: Wait for Build (10-15 minutes)

Render will:
- Clone repository
- Build Docker image
- Run database migrations
- Start the service

Monitor progress in the **Logs** tab.

---

## 🧪 Test Deployment (2 minutes)

Once deployed, test the health endpoint:

```bash
curl https://pharos-cloud-api.onrender.com/health
```

Expected response:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "version": "2.0.0"
}
```

---

## 🔑 Get Your API Token

1. In Render dashboard, go to **Environment** tab
2. Find `PHAROS_ADMIN_TOKEN`
3. Click **"Show"** to reveal the token
4. **Copy and save it** - you'll need it for Ronin

---

## 🔥 Set Up Keep-Alive (5 minutes - Optional but Recommended)

Prevents 50-second cold starts:

1. Sign up at **https://uptimerobot.com** (free)
2. Click **"Add New Monitor"**
3. Configure:
   - Type: `HTTP(s)`
   - Name: `Pharos Keep-Alive`
   - URL: `https://pharos-cloud-api.onrender.com/health`
   - Interval: `5 minutes`
4. Click **"Create Monitor"**

**Full guide**: `backend/UPTIMEROBOT_SETUP.md`

---

## 🤖 Configure Ronin (2 minutes)

In your Ronin configuration:

```bash
# .env or config file
PHAROS_API_URL=https://pharos-cloud-api.onrender.com
PHAROS_API_KEY=<paste your PHAROS_ADMIN_TOKEN here>
PHAROS_TIMEOUT=5000  # 5 seconds (accounts for cold start)
```

---

## 🧪 Test Ronin Integration (5 minutes)

### 1. Ingest a Test Repository

```bash
curl -X POST https://pharos-cloud-api.onrender.com/api/ingest/github \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_PHAROS_ADMIN_TOKEN" \
  -d '{
    "repo_url": "https://github.com/octocat/Hello-World",
    "branch": "master"
  }'
```

### 2. Test Context Retrieval

```bash
curl -X POST https://pharos-cloud-api.onrender.com/api/context/retrieve \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_PHAROS_ADMIN_TOKEN" \
  -d '{
    "query": "How does this code work?",
    "codebase": "Hello-World",
    "max_chunks": 5
  }'
```

### 3. Ask Ronin a Question

```
You: "Explain the Hello-World repository"
```

Ronin will:
1. Call Pharos context retrieval API
2. Receive relevant code chunks
3. Generate explanation with context

---

## 📊 What You Get

### Free Tier Resources
- **Render**: 512MB RAM, 100GB bandwidth/month
- **NeonDB**: 512MB PostgreSQL storage
- **Upstash**: 256MB Redis, 10K commands/day
- **UptimeRobot**: 50 monitors, 5-min intervals

### Performance
- **Cold Start**: ~50 seconds (first request after 15 min idle)
- **Warm Requests**: <1 second
- **Context Retrieval**: 800ms - 2s
- **GitHub Ingestion**: 30-60s per repo

### Capacity
- **Storage**: ~100MB per 10 repositories
- **Concurrent Requests**: 2-3 (512MB RAM limit)
- **Daily Requests**: ~400 (10K Redis commands/day)

---

## 📖 Documentation

### Quick References
- **This Guide**: `DEPLOY_NOW.md` (you are here)
- **Checklist**: `backend/RENDER_DEPLOYMENT_CHECKLIST.md`
- **Summary**: `RENDER_DEPLOYMENT_SUMMARY.md`

### Detailed Guides
- **Complete Deployment**: `backend/RENDER_FREE_DEPLOYMENT.md`
- **Keep-Alive Setup**: `backend/UPTIMEROBOT_SETUP.md`
- **Pharos + Ronin Vision**: `PHAROS_RONIN_VISION.md`

### Scripts
- **Verify Config**: `backend/verify_render_config.py`
- **Test Deployment**: `backend/test_render_deployment.py`
- **Deploy Helper**: `deploy_to_render.bat` (Windows) or `deploy_to_render.sh` (Linux/Mac)

---

## 🆘 Troubleshooting

### Issue: 502 Bad Gateway
**Cause**: Cold start (service spinning up)  
**Solution**: Wait 50 seconds and retry, or set up keep-alive

### Issue: Database Connection Error
**Cause**: NeonDB connection string incorrect  
**Solution**: Verify `DATABASE_URL` in Render environment variables

### Issue: Redis Connection Error
**Cause**: Upstash credentials incorrect  
**Solution**: Verify `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`

### Issue: 401 Unauthorized
**Cause**: Missing or incorrect API key  
**Solution**: Include `X-API-Key` header with `PHAROS_ADMIN_TOKEN`

### Issue: Build Failed
**Cause**: Docker build error  
**Solution**: Check Render logs, verify Dockerfile.cloud is correct

---

## 💰 Cost Tracking

### Current (Free Tier)
- Render: $0/month
- NeonDB: $0/month
- Upstash: $0/month
- UptimeRobot: $0/month
- **Total: $0/month**

### When to Upgrade
- Storage >512MB → NeonDB Scale ($19/mo)
- RAM >400MB → Render Starter ($7/mo)
- Redis >10K/day → Upstash Pro ($10/mo)
- Cold starts problematic → Render Starter ($7/mo)

---

## ✅ Success Checklist

After deployment, verify:

- [ ] Health endpoint returns 200 OK
- [ ] API docs accessible at `/docs`
- [ ] Database connected (NeonDB)
- [ ] Redis connected (Upstash)
- [ ] API token copied and saved
- [ ] Keep-alive monitor created
- [ ] Ronin configured with Pharos URL and token
- [ ] Test repository ingested
- [ ] Context retrieval works
- [ ] Ronin can answer questions with context

---

## 🎉 You're Done!

Once all checks pass, you have:
- ✅ Pharos deployed to Render Free tier
- ✅ NeonDB PostgreSQL connected
- ✅ Upstash Redis connected
- ✅ Keep-alive preventing cold starts
- ✅ Ronin integrated with Pharos
- ✅ End-to-end workflow tested

**Total Cost**: $0/month  
**Total Time**: ~30 minutes

---

## 🚀 Next Steps

### Immediate
1. Ingest your actual repositories
2. Test with real queries
3. Monitor performance in Render dashboard

### This Week
1. Test Ronin integration thoroughly
2. Measure context quality and relevance
3. Identify any performance bottlenecks

### Next 2 Weeks
1. Plan for Phase 5 (Hybrid GitHub Storage)
2. Optimize query performance
3. Scale to more repositories

---

## 📞 Support

If you encounter issues:
1. Check troubleshooting section above
2. Review Render logs for errors
3. Verify environment variables
4. Check service status pages:
   - Render: https://status.render.com
   - NeonDB: https://neonstatus.com
   - Upstash: https://status.upstash.com

---

**Ready to deploy? Let's go!** 🚀

**First command**:
```bash
git add backend/deployment/render.yaml
git commit -m "Configure Render free tier deployment"
git push origin main
```

**Then**: Go to https://dashboard.render.com and create the web service!
