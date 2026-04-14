# Pharos Serverless Deployment Checklist
## $7/mo Ultimate Cost-Optimized Stack

**Quick Reference**: Complete this checklist to deploy Pharos in under 30 minutes.

---

## ☑️ Pre-Deployment (10 minutes)

### 1. Create NeonDB Project
- [ ] Sign up at [neon.tech](https://neon.tech)
- [ ] Create project: `pharos-db`
- [ ] Run SQL: `CREATE EXTENSION vector;`
- [ ] Copy **Pooled Connection String** (must contain `-pooler`)
- [ ] Verify URL contains `?sslmode=require`
- [ ] Save as `DATABASE_URL`

### 2. Create Upstash Redis
- [ ] Sign up at [upstash.com](https://upstash.com)
- [ ] Create database: `pharos-cache`
- [ ] Copy **Redis URL** (must start with `rediss://` - two S's)
- [ ] Verify URL starts with `rediss://` (not `redis://`)
- [ ] Save as `REDIS_URL`

### 3. Generate API Key
- [ ] Run: `openssl rand -hex 32`
- [ ] Save as `PHAROS_API_KEY`

### 4. (Optional) Create GitHub Token
- [ ] Go to GitHub Settings → Developer Settings
- [ ] Generate token with `repo` scope
- [ ] Save as `GITHUB_TOKEN`

---

## ☑️ Deployment (10 minutes)

### 5. Deploy to Render
- [ ] Sign up at [render.com](https://render.com)
- [ ] Connect GitHub account
- [ ] Create new Web Service
- [ ] Select Pharos repository
- [ ] Branch: `main`
- [ ] Root Directory: `backend`
- [ ] Build Command: `pip install -r requirements-cloud.txt && alembic upgrade head`
- [ ] Start Command: `gunicorn -c gunicorn_conf.py app.main:app`
- [ ] Plan: Starter ($7/mo)

### 6. Set Environment Variables
- [ ] `DATABASE_URL` = <NeonDB pooled connection string>
- [ ] `REDIS_URL` = <Upstash Redis URL>
- [ ] `PHAROS_API_KEY` = <Generated API key>
- [ ] `GITHUB_TOKEN` = <GitHub PAT> (optional)
- [ ] Click "Create Web Service"

---

## ☑️ Verification (10 minutes)

### 7. Test Health Endpoint
```bash
curl https://pharos-api.onrender.com/health
```
- [ ] Status: `healthy`
- [ ] Database: `connected`
- [ ] Cache: `connected`

### 8. Test API Documentation
- [ ] Open: https://pharos-api.onrender.com/docs
- [ ] Verify all endpoints listed
- [ ] Test interactive API

### 9. Test Context Retrieval
```bash
curl -X POST https://pharos-api.onrender.com/api/context/retrieve \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"query": "authentication", "codebase": "myapp", "max_chunks": 10}'
```
- [ ] Response received
- [ ] No errors in logs

### 10. Monitor Logs
- [ ] Go to Render Dashboard → Logs
- [ ] Check for errors or warnings
- [ ] Verify workers started (2 workers)
- [ ] Verify database connection successful

---

## ☑️ Post-Deployment (Optional)

### 11. Set Up Local Edge Worker
- [ ] Install dependencies: `pip install -r requirements-edge.txt`
- [ ] Configure Upstash queue connection
- [ ] Start worker: `python worker.py`
- [ ] Verify connection in logs

### 12. Configure Monitoring
- [ ] Set up Render alerts (email/Slack)
- [ ] Monitor pool status: `GET /api/monitoring/pool-status`
- [ ] Monitor cache stats: `GET /api/monitoring/cache-stats`
- [ ] Set up uptime monitoring (UptimeRobot, Pingdom)

### 13. Security Hardening
- [ ] Rotate API keys quarterly
- [ ] Enable IP allowlist (if needed)
- [ ] Review rate limiting settings
- [ ] Enable 2FA on all accounts

---

## 📊 Expected Results

| Metric | Target | Status |
|--------|--------|--------|
| Deployment time | <30 min | ⏱️ |
| Health check | Healthy | ✅ |
| Response time | <200ms | ✅ |
| Cost | $7/mo | ✅ |
| Uptime | 99.9% | ✅ |

---

## 🚨 Troubleshooting

### Database Connection Failed
- Check NeonDB is not suspended
- Verify DATABASE_URL format: `postgresql://...?sslmode=require`
- Verify using **Pooled Connection** (contains `-pooler`)
- Check SSL configuration
- Review [SERVERLESS_GOTCHAS.md](SERVERLESS_GOTCHAS.md) for details

### Redis Connection Failed
- Verify REDIS_URL uses `rediss://` (two S's, not one)
- Check Upstash dashboard for errors
- Review request count (free tier: 10K/day)
- Verify SSL is enabled
- Review [SERVERLESS_GOTCHAS.md](SERVERLESS_GOTCHAS.md) for details

### Out of Memory (OOM)
- Reduce workers: `WEB_CONCURRENCY=1`
- Upgrade to Render Standard (2GB RAM)
- Monitor memory: `ps aux | grep gunicorn`

### Slow Requests
- Check pool status: `GET /api/monitoring/pool-status`
- Review slow query logs (>1s)
- Optimize queries (add indexes)

---

## 📚 Documentation

- [Full Deployment Guide](SERVERLESS_DEPLOYMENT_GUIDE.md)
- [Pharos + Ronin Vision](../PHAROS_RONIN_VISION.md)
- [Quick Reference](../.kiro/steering/PHAROS_RONIN_QUICK_REFERENCE.md)

---

## ✅ Deployment Complete!

**Total Time**: ~30 minutes  
**Total Cost**: $7/mo  
**Capacity**: 1000+ codebases, 100+ requests/min  
**Savings**: 71% vs native Render stack

**Next Steps**:
1. Implement Phase 5 (Hybrid GitHub Storage)
2. Implement Phase 6 (Pattern Learning)
3. Implement Phase 7 (Ronin Integration)

---

**Questions?** Review the [Full Deployment Guide](SERVERLESS_DEPLOYMENT_GUIDE.md) or check the [Troubleshooting](#-troubleshooting) section.
