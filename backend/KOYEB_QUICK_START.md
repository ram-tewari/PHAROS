# Koyeb Quick Start - 5 Minute Deployment

## Prerequisites (5 minutes)

### 1. Create NeonDB Database
```
1. Go to https://neon.tech
2. Sign up (free, no credit card)
3. Create project: "pharos-db"
4. Copy connection string
```

### 2. Create Upstash Redis
```
1. Go to https://upstash.com
2. Sign up (free, no credit card)
3. Create database: "pharos-cache"
4. Copy connection string
```

### 3. Create Koyeb Account
```
1. Go to https://www.koyeb.com
2. Sign up (free, no credit card)
```

## Deployment (5 minutes)

### Step 1: Create Secrets (2 minutes)

Go to https://app.koyeb.com/secrets and create:

**Secret 1: database-url**
```
Value: postgresql://user:password@host/database?sslmode=require
```

**Secret 2: redis-url**
```
Value: rediss://default:password@host:6379
```

**Secret 3: pharos-api-key**
```
Value: your-secure-random-key-here
```

### Step 2: Deploy Service (3 minutes)

1. Go to https://app.koyeb.com/services
2. Click "Create Service"
3. Select "Docker"
4. Configure:

```yaml
Repository: https://github.com/yourusername/pharos
Branch: main
Dockerfile: backend/Dockerfile
Build context: backend
Region: Frankfurt
Instance: nano (512MB)
Port: 8000
Health check: /health
```

5. Add environment variables:
```
ENVIRONMENT=production
PORT=8000
WEB_CONCURRENCY=2
LOG_LEVEL=info
JSON_LOGGING=true
```

6. Link secrets:
```
DATABASE_URL → database-url
REDIS_URL → redis-url
PHAROS_API_KEY → pharos-api-key
```

7. Click "Deploy"

### Step 3: Verify (1 minute)

```bash
# Wait for deployment (~2 minutes)
# Check health
curl https://your-app.koyeb.app/health

# Expected:
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected"
}
```

## Done! 🎉

Your API is now live at: `https://your-app.koyeb.app`

## Next Steps

- View docs: `https://your-app.koyeb.app/docs`
- Monitor logs: https://app.koyeb.com/services/pharos-api/logs
- Test endpoints: See KOYEB_DEPLOYMENT_GUIDE.md

## Troubleshooting

**Build failed?**
- Check Dockerfile exists: `backend/Dockerfile`
- Check requirements exist: `backend/config/requirements-cloud.txt`

**Health check failed?**
- Check secrets are linked correctly
- View logs: https://app.koyeb.com/services/pharos-api/logs
- Common issue: DATABASE_URL or REDIS_URL incorrect

**Out of memory?**
- Reduce workers: `WEB_CONCURRENCY=1`
- Or upgrade to micro instance (1GB RAM, $5/month)

## Files Created

✅ `backend/Dockerfile` - Production container image  
✅ `backend/entrypoint.sh` - Startup script (migrations + server)  
✅ `backend/koyeb.yaml` - Infrastructure as Code  
✅ `backend/KOYEB_DEPLOYMENT_GUIDE.md` - Complete guide  
✅ `backend/KOYEB_QUICK_START.md` - This file  

## Important Notes

**Make entrypoint.sh executable:**
```bash
chmod +x backend/entrypoint.sh
git add backend/entrypoint.sh
git commit -m "Add Koyeb deployment files"
git push
```

**Free Tier Limits:**
- 1 service
- 512MB RAM
- 100GB bandwidth/month
- Perfect for MVP, side projects, solo dev

**Cost: $0/month** (Koyeb + NeonDB + Upstash all free tier)

---

**Status**: Production Ready  
**Deployment Time**: ~10 minutes total  
**Uptime**: 24/7 (no cold starts)
