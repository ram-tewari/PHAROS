# Docker Development Infrastructure Setup Guide

This guide explains how to set up and use the Docker-based development infrastructure for Pharos.

## Overview

The development infrastructure provides PostgreSQL 15 and Redis 7 as containerized backing services. The application runs locally (not in Docker) for easier debugging and hot-reload during development.

## Build Time Information

When using the production Docker setup (`docker-compose.yml`):

| Operation | Duration | Why |
|-----------|----------|-----|
| **First build** | 10-15 minutes | Downloads ~1GB of ML libraries (PyTorch 797MB, transformers, spaCy, etc.) |
| **Subsequent starts** | 10-30 seconds | Uses cached Docker image |
| **After code changes** | 30-60 seconds | Only rebuilds changed layers |
| **After dependency changes** | 5-10 minutes | Re-downloads changed packages |

**Why is the first build slow?**
- PyTorch alone is 797MB
- Transformers, sentence-transformers, spaCy add ~300MB
- Tree-sitter, scikit-learn, and other ML libraries
- Docker downloads and installs everything from scratch

**Why are subsequent starts fast?**
- Docker caches all layers (system deps, Python packages)
- Only application code is copied fresh
- Containers start in seconds

## Prerequisites

- Docker Desktop installed and running
- Docker Compose (included with Docker Desktop)
- Python 3.8+ installed locally
- Git

## Quick Start

### 1. Start Backing Services

From the `backend` directory:

```bash
docker-compose -f docker-compose.dev.yml up -d
```

This starts:
- **PostgreSQL 15** on port 5432
- **Redis 7** on port 6379

### 2. Verify Services are Running

```bash
docker-compose -f docker-compose.dev.yml ps
```

Expected output:
```
NAME                          STATUS                    PORTS
neo-alexandria-postgres-dev   Up (healthy)              0.0.0.0:5432->5432/tcp
neo-alexandria-redis-dev      Up (healthy)              0.0.0.0:6379->6379/tcp
```

### 3. Configure Application

Create or update `backend/.env`:

```bash
# Database Configuration
DATABASE_URL=postgresql+asyncpg://postgres:devpassword@localhost:5432/neo_alexandria_dev

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_CACHE_DB=0

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# JWT Authentication (Phase 17)
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# OAuth2 Providers (Phase 17)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback

# Rate Limiting (Phase 17)
RATE_LIMIT_FREE_TIER=100
RATE_LIMIT_PREMIUM_TIER=1000
RATE_LIMIT_ADMIN_TIER=10000

# Testing Mode (Phase 17)
TEST_MODE=false
```

**Important:** Generate a secure JWT secret key for production:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 4. Run Database Migrations

```bash
cd backend
alembic upgrade head
```

### 5. Start Application Locally

```bash
uvicorn app.main:app --reload
```

The application will be available at http://localhost:8000

## Environment Variables

### Default Values

The following environment variables are used by `docker-compose.dev.yml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_DB` | `neo_alexandria_dev` | Database name |
| `POSTGRES_USER` | `postgres` | Database user |
| `POSTGRES_PASSWORD` | `devpassword` | Database password |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `REDIS_PORT` | `6379` | Redis port |

### Phase 17 Authentication Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | (required) | Secret key for JWT signing |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token expiration |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token expiration |
| `GOOGLE_CLIENT_ID` | (optional) | Google OAuth2 client ID |
| `GOOGLE_CLIENT_SECRET` | (optional) | Google OAuth2 client secret |
| `GOOGLE_REDIRECT_URI` | (optional) | Google OAuth2 redirect URI |
| `GITHUB_CLIENT_ID` | (optional) | GitHub OAuth2 client ID |
| `GITHUB_CLIENT_SECRET` | (optional) | GitHub OAuth2 client secret |
| `GITHUB_REDIRECT_URI` | (optional) | GitHub OAuth2 redirect URI |
| `RATE_LIMIT_FREE_TIER` | `100` | Requests per hour for free tier |
| `RATE_LIMIT_PREMIUM_TIER` | `1000` | Requests per hour for premium tier |
| `RATE_LIMIT_ADMIN_TIER` | `10000` | Requests per hour for admin tier |
| `TEST_MODE` | `false` | Bypass authentication for testing |

### Customizing Values

Create a `.env` file in the `backend` directory:

```bash
# Custom PostgreSQL settings
POSTGRES_DB=my_custom_db
POSTGRES_USER=myuser
POSTGRES_PASSWORD=mypassword
POSTGRES_PORT=5433

# Custom Redis settings
REDIS_PORT=6380
```

Then start services:

```bash
docker-compose -f docker-compose.dev.yml --env-file .env up -d
```

## Common Operations

### View Logs

```bash
# All services
docker-compose -f docker-compose.dev.yml logs -f

# PostgreSQL only
docker-compose -f docker-compose.dev.yml logs -f postgres

# Redis only
docker-compose -f docker-compose.dev.yml logs -f redis
```

### Stop Services

```bash
docker-compose -f docker-compose.dev.yml down
```

**Note:** This preserves data in volumes.

### Stop and Remove Data

```bash
docker-compose -f docker-compose.dev.yml down -v
```

**Warning:** This deletes all data in PostgreSQL and Redis!

### Restart Services

```bash
docker-compose -f docker-compose.dev.yml restart
```

### Check Service Health

```bash
# PostgreSQL
docker exec neo-alexandria-postgres-dev pg_isready -U postgres -d neo_alexandria_dev

# Redis
docker exec neo-alexandria-redis-dev redis-cli ping
```

## Database Operations

### Connect to PostgreSQL

```bash
# Using psql in container
docker exec -it neo-alexandria-postgres-dev psql -U postgres -d neo_alexandria_dev

# Using local psql client
psql -h localhost -U postgres -d neo_alexandria_dev
# Password: devpassword
```

### Backup Database

```bash
docker exec neo-alexandria-postgres-dev pg_dump -U postgres neo_alexandria_dev > backup.sql
```

### Restore Database

```bash
docker exec -i neo-alexandria-postgres-dev psql -U postgres neo_alexandria_dev < backup.sql
```

### Create New Database

```bash
docker exec neo-alexandria-postgres-dev psql -U postgres -c "CREATE DATABASE my_new_db;"
```

### List Databases

```bash
docker exec neo-alexandria-postgres-dev psql -U postgres -c "\l"
```

## Redis Operations

### Connect to Redis

```bash
# Using redis-cli in container
docker exec -it neo-alexandria-redis-dev redis-cli

# Using local redis-cli
redis-cli -h localhost -p 6379
```

### Common Redis Commands

```bash
# Set a key
docker exec neo-alexandria-redis-dev redis-cli SET mykey "myvalue"

# Get a key
docker exec neo-alexandria-redis-dev redis-cli GET mykey

# List all keys
docker exec neo-alexandria-redis-dev redis-cli KEYS "*"

# Delete a key
docker exec neo-alexandria-redis-dev redis-cli DEL mykey

# Flush all data (WARNING: deletes everything!)
docker exec neo-alexandria-redis-dev redis-cli FLUSHALL
```

## Data Persistence

### How It Works

Data is persisted in Docker named volumes:
- `neo-alexandria-postgres-dev-data` - PostgreSQL data
- `neo-alexandria-redis-dev-data` - Redis data

These volumes survive container restarts and removals (unless you use `down -v`).

### View Volumes

```bash
docker volume ls | grep neo-alexandria
```

### Inspect Volume

```bash
docker volume inspect neo-alexandria-postgres-dev-data
```

### Backup Volume

```bash
# PostgreSQL volume
docker run --rm -v neo-alexandria-postgres-dev-data:/data -v $(pwd):/backup alpine tar czf /backup/postgres-backup.tar.gz /data

# Redis volume
docker run --rm -v neo-alexandria-redis-dev-data:/data -v $(pwd):/backup alpine tar czf /backup/redis-backup.tar.gz /data
```

## Troubleshooting

### Authentication Issues (Phase 17)

**Problem:** 401 Unauthorized errors

**Solution:**
```bash
# Check JWT_SECRET_KEY is set
echo $JWT_SECRET_KEY

# Verify Redis is running (required for token revocation)
docker exec neo-alexandria-redis-dev redis-cli ping

# Enable TEST_MODE for development
# In .env file:
TEST_MODE=true
```

**Problem:** OAuth2 callback errors

**Solution:**
```bash
# Verify redirect URIs match OAuth2 provider configuration
# Google: https://console.cloud.google.com/apis/credentials
# GitHub: https://github.com/settings/developers

# Check callback URLs in .env:
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback
```

**Problem:** Rate limiting errors (429 Too Many Requests)

**Solution:**
```bash
# Check Redis connection (rate limiting requires Redis)
docker exec neo-alexandria-redis-dev redis-cli ping

# Increase rate limits in .env:
RATE_LIMIT_FREE_TIER=1000

# Or disable rate limiting temporarily:
# Set very high limits for development
RATE_LIMIT_FREE_TIER=999999
```

### Port Already in Use

**Problem:** Error: "Bind for 0.0.0.0:5432 failed: port is already allocated"

**Solution 1:** Stop conflicting service
```bash
# Check what's using the port
netstat -ano | findstr "5432"

# Stop Docker containers using the port
docker ps | grep 5432
docker stop <container_id>
```

**Solution 2:** Use different port
```bash
# In .env file
POSTGRES_PORT=5433
REDIS_PORT=6380

# Update DATABASE_URL accordingly
DATABASE_URL=postgresql+asyncpg://postgres:devpassword@localhost:5433/neo_alexandria_dev
```

### Services Won't Start

**Check logs:**
```bash
docker-compose -f docker-compose.dev.yml logs
```

**Common issues:**
- Docker Desktop not running
- Insufficient disk space
- Corrupted volumes (solution: `docker-compose -f docker-compose.dev.yml down -v`)

### Health Check Failing

**Wait for initialization:**
```bash
# PostgreSQL takes 10-15 seconds on first start
# Redis takes 5-10 seconds

# Check status
docker-compose -f docker-compose.dev.yml ps
```

**Force restart:**
```bash
docker-compose -f docker-compose.dev.yml restart
```

### Connection Refused

**Verify services are healthy:**
```bash
docker-compose -f docker-compose.dev.yml ps
```

**Test connectivity:**
```bash
# PostgreSQL
docker exec neo-alexandria-postgres-dev pg_isready -U postgres

# Redis
docker exec neo-alexandria-redis-dev redis-cli ping
```

**Check firewall:**
- Ensure ports 5432 and 6379 are not blocked
- Check Docker Desktop network settings

### Data Not Persisting

**Verify volumes exist:**
```bash
docker volume ls | grep neo-alexandria
```

**Check volume mounts:**
```bash
docker inspect neo-alexandria-postgres-dev | grep -A 10 Mounts
```

**If volumes are missing:**
```bash
# Recreate with volumes
docker-compose -f docker-compose.dev.yml down
docker-compose -f docker-compose.dev.yml up -d
```

## Performance Tuning

### PostgreSQL

Edit `docker-compose.dev.yml` to add performance settings:

```yaml
postgres:
  environment:
    # ... existing vars ...
  command: >
    postgres
    -c shared_buffers=256MB
    -c effective_cache_size=1GB
    -c maintenance_work_mem=64MB
    -c checkpoint_completion_target=0.9
    -c wal_buffers=16MB
    -c default_statistics_target=100
    -c random_page_cost=1.1
    -c effective_io_concurrency=200
```

### Redis

Redis is already configured with:
- AOF persistence (appendonly yes)
- 512MB max memory
- LRU eviction policy
- Snapshot every 60 seconds if 1000+ keys changed

## Migration from SQLite

### Export SQLite Data

```bash
# Using provided migration script
python backend/scripts/migrate_sqlite_to_postgresql.py \
  --source sqlite:///./backend.db \
  --target postgresql://postgres:devpassword@localhost:5432/neo_alexandria_dev \
  --validate
```

### Manual Migration

```bash
# 1. Dump SQLite schema
sqlite3 backend.db .schema > schema.sql

# 2. Convert to PostgreSQL (manual editing required)
# Edit schema.sql to use PostgreSQL syntax

# 3. Import to PostgreSQL
docker exec -i neo-alexandria-postgres-dev psql -U postgres neo_alexandria_dev < schema.sql

# 4. Export/import data (per table)
sqlite3 backend.db ".mode csv" ".output data.csv" "SELECT * FROM resources;"
docker exec -i neo-alexandria-postgres-dev psql -U postgres neo_alexandria_dev -c "\COPY resources FROM STDIN CSV"
```

## Production Deployment

For production, use the full `docker-compose.yml` which includes:
- Application container
- Celery workers
- Monitoring (Prometheus, Grafana)
- Production-grade settings

See `backend/docker/README.md` for production deployment guide.

## Additional Resources

- [PostgreSQL Documentation](https://www.postgresql.org/docs/15/)
- [Redis Documentation](https://redis.io/documentation)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Pharos Architecture](./docs/architecture/overview.md)

## Support

For issues or questions:
1. Check this guide's troubleshooting section
2. Review logs: `docker-compose -f docker-compose.dev.yml logs`
3. Check Docker Desktop status
4. Consult project documentation in `backend/docs/`
