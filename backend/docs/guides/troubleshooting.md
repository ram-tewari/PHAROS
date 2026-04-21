# Troubleshooting Guide

Common issues and solutions for Pharos.

## Installation Issues

### Import Errors

**Symptom:** `ModuleNotFoundError: No module named 'app'`

**Solution:**
```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Verify Python path
which python  # Should show .venv/bin/python

# Reinstall dependencies
pip install -r requirements.txt
```

### Dependency Conflicts

**Symptom:** `ERROR: Cannot install package due to conflicting dependencies`

**Solution:**
```bash
# Create fresh virtual environment
rm -rf .venv
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Model Download Fails

**Symptom:** `OSError: Can't load tokenizer for 'nomic-ai/nomic-embed-text-v1'`

**Solution:**
```bash
# Check internet connection
ping huggingface.co

# Check disk space (models need ~2GB)
df -h

# Try manual download
python -c "from transformers import AutoModel; AutoModel.from_pretrained('nomic-ai/nomic-embed-text-v1')"
```

## Database Issues

### Database Locked (SQLite)

**Symptom:** `sqlite3.OperationalError: database is locked`

**Cause:** SQLite doesn't support concurrent writes.

**Solutions:**
1. Use single process for development
2. Switch to PostgreSQL for multi-user scenarios
3. Increase timeout:
```python
connect_args={"timeout": 30}
```

### Migration Fails

**Symptom:** `alembic.util.exc.CommandError: Can't locate revision`

**Solution:**
```bash
# Check current state
alembic current

# Stamp to known state
alembic stamp head

# Re-run migrations
alembic upgrade head
```

### Connection Pool Exhausted

**Symptom:** `QueuePool limit of size X overflow Y reached`

**Solution:**
```python
# Increase pool size in database configuration
postgresql_params = {
    'pool_size': 30,      # Increase from 20
    'max_overflow': 60,   # Increase from 40
}
```

### PostgreSQL Connection Refused

**Symptom:** `psycopg2.OperationalError: could not connect to server`

**Solution:**
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check connection string
psql -h localhost -U postgres -d neo_alexandria

# Verify pg_hba.conf allows connections
sudo cat /etc/postgresql/15/main/pg_hba.conf
```

## API Issues

### 403 Forbidden (CSRF Errors)

**Symptom:** `{"detail": "CSRF validation failed: Missing Origin or Referer header"}`

**Root Cause:** CSRF middleware was blocking API requests without Origin/Referer headers (which API clients like curl don't send)

**Solution:** CSRF middleware has been disabled for API-only service. Bearer token authentication provides sufficient protection.

**Verification:**
```bash
# Test with admin token (should work)
curl -X POST "https://pharos-cloud-api.onrender.com/api/github/fetch" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"github_uri": "...", "start_line": 1, "end_line": 20}'
```

**Note:** If you see CSRF errors, ensure:
1. CSRF middleware is commented out in `backend/app/__init__.py`
2. You're using Bearer token authentication for protected endpoints
3. Environment variable `PHAROS_ADMIN_TOKEN` is set on Render

### 422 Validation Error

**Symptom:** `{"detail":[{"loc":["body","field"],"msg":"field required"}]}`

**Solution:**
- Check request body matches schema
- Verify Content-Type header is `application/json`
- Check for typos in field names

### 500 Internal Server Error

**Symptom:** Generic server error with no details

**Solution:**
```bash
# Enable debug mode
DEBUG=true uvicorn app.main:app --reload

# Check application logs
tail -f /var/log/neo-alexandria/error.log
```

### Slow API Responses

**Symptom:** Requests take >1 second

**Solutions:**
1. Check database query performance:
```sql
EXPLAIN ANALYZE SELECT * FROM resources WHERE ...;
```

2. Add missing indexes:
```sql
CREATE INDEX idx_resources_subject ON resources USING GIN (subject);
```

3. Enable query logging:
```python
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

## Search Issues

### No Search Results

**Symptom:** Search returns empty results for known content

**Root Causes:**
1. **Using keyword overlap instead of vector similarity** - Search was using simple keyword matching instead of cosine similarity with embeddings
2. **Embeddings stored as strings** - Embeddings stored as space-separated strings need parsing to float lists
3. **Model not loaded in CLOUD mode** - Embedding model not loaded on API server for query embeddings
4. **Missing ML dependencies** - PyTorch/transformers not installed in cloud requirements

**Solutions:**

1. **Verify vector similarity is being used:**
```python
# In backend/app/modules/search/service.py
# Should use _cosine_similarity(), not _compute_similarity_score()
for chunk in all_chunks:
    if chunk.embedding:
        score = self._cosine_similarity(query_embedding, chunk.embedding)
```

2. **Check embedding string parsing:**
```python
# Embeddings stored as space-separated strings must be parsed
if isinstance(embedding_str, str):
    embedding = [float(x) for x in embedding_str.split()]
```

3. **Verify model loads for queries in CLOUD mode:**
```python
# In backend/app/shared/embeddings.py
query_embedding = embedding_service.generate_embedding(
    query, 
    force_load_in_cloud=True  # Force load for queries
)
```

4. **Check ML dependencies are installed:**
```bash
# requirements-cloud.txt should include:
sentence-transformers==3.3.1
torch==2.5.1
transformers==4.47.1
```

5. **Verify embeddings exist in correct location:**
```sql
-- Embeddings should be in resources.embedding, not chunk metadata
SELECT COUNT(*) FROM resources WHERE embedding IS NOT NULL;

-- Check sample embedding
SELECT id, title, 
       CASE WHEN embedding IS NOT NULL THEN 'YES' ELSE 'NO' END as has_embedding
FROM resources WHERE type = 'code' LIMIT 5;
```

6. **Rebuild search index if needed:**
```bash
python -c "from app.services.search_service import rebuild_fts_index; rebuild_fts_index()"
```

### Search Quality Issues

**Symptom:** Irrelevant results ranked highly

**Solutions:**
1. Adjust hybrid weight:
```json
{"text": "query", "hybrid_weight": 0.7}  // More semantic
{"text": "query", "hybrid_weight": 0.3}  // More keyword
```

2. Check embedding model is loaded:
```python
from app.services.ai_core import AICore
ai = AICore()
print(ai.embedding_model)  # Should not be None
```

3. Verify cosine similarity scores are reasonable (0.7-0.95 for good matches):
```bash
curl -X POST "https://pharos-cloud-api.onrender.com/api/search/search/advanced" \
  -H "Content-Type: application/json" \
  -d '{"query": "authentication", "limit": 5}'
# Check that results have similarity_score > 0.7
```

## AI/ML Issues

### Out of Memory

**Symptom:** `RuntimeError: CUDA out of memory` or system OOM

**Solutions:**
1. Reduce batch size:
```python
batch_size = 8  # Reduce from 32
```

2. Use CPU instead of GPU:
```python
device = "cpu"  # Instead of "cuda"
```

3. Increase system RAM to 8GB+

### Model Loading Slow

**Symptom:** First request takes 30+ seconds

**Cause:** Models loaded lazily on first use.

**Solutions:**
1. Pre-load models at startup:
```python
# In main.py
@app.on_event("startup")
async def load_models():
    ai_core = AICore()
    ai_core.load_embedding_model()
```

2. Use smaller models for development

### Classification Accuracy Low

**Symptom:** ML classification gives wrong categories

**Solutions:**
1. Retrain with more labeled data
2. Adjust confidence threshold:
```python
min_confidence = 0.5  # Increase from 0.3
```

3. Use active learning to improve model

## Event System Issues

### Events Not Firing

**Symptom:** Event handlers not called

**Solutions:**
1. Verify handler is registered:
```python
print(event_bus._subscribers)  # Check handlers
```

2. Check for exceptions in handlers:
```python
def handle_event(event):
    try:
        # handler code
    except Exception as e:
        logger.error(f"Handler error: {e}")
```

### Circular Import Errors

**Symptom:** `ImportError: cannot import name 'X' from partially initialized module`

**Solution:**
- Use string-based relationships in models
- Import inside functions, not at module level
- Use event bus instead of direct imports

## Performance Issues

### High CPU Usage

**Symptom:** CPU at 100% during normal operation

**Solutions:**
1. Profile the application:
```python
import cProfile
cProfile.run('function_to_profile()')
```

2. Check for infinite loops in event handlers
3. Optimize database queries

### High Memory Usage

**Symptom:** Memory grows over time

**Solutions:**
1. Check for memory leaks:
```python
import tracemalloc
tracemalloc.start()
# ... run code ...
snapshot = tracemalloc.take_snapshot()
```

2. Clear embedding cache periodically
3. Use streaming for large responses

## Docker Issues

### Container Won't Start

**Symptom:** Container exits immediately

**Solution:**
```bash
# Check logs
docker logs container_name

# Run interactively
docker run -it neo-alexandria /bin/bash
```

### Volume Permission Errors

**Symptom:** `PermissionError: [Errno 13] Permission denied`

**Solution:**
```bash
# Fix ownership
sudo chown -R 1000:1000 ./storage

# Or run as root (not recommended)
docker run --user root ...
```

## Getting Help

### Repository Ingestion Issues

**Symptom:** Repository ingestion fails or returns 0 results

**Common Issues:**

1. **Worker not running:**
```bash
# Start the edge worker
cd backend
python worker.py repo
```

2. **Missing embeddings after ingestion:**
```bash
# Check embedding coverage
python -c "
from app.shared.database import init_database, get_db
from sqlalchemy import text
import asyncio

async def check():
    init_database()
    async for db in get_db():
        result = await db.execute(text('SELECT COUNT(*) FROM resources WHERE embedding IS NOT NULL'))
        with_emb = result.scalar()
        result = await db.execute(text('SELECT COUNT(*) FROM resources'))
        total = result.scalar()
        print(f'Embeddings: {with_emb}/{total} ({with_emb/total*100:.1f}%)')
        break

asyncio.run(check())
"
```

3. **Simplified ingestion architecture:**
   - Worker now creates resources/chunks directly (no separate converter needed)
   - Single transaction for reliability
   - 3x faster than previous two-step process

**Expected Performance:**
- Parsing: ~5.3 files/second
- Embedding: ~5.3 embeddings/second (GPU)
- Total: ~2 seconds per file (including storage)

### Collect Debug Information

```bash
# System info
python --version
pip freeze > requirements_actual.txt

# Database info
alembic current
psql -c "SELECT version();"

# Application logs
tail -100 /var/log/neo-alexandria/app.log
```

### Report Issues

Include:
1. Error message and stack trace
2. Steps to reproduce
3. Environment details (OS, Python version)
4. Relevant configuration

## Related Documentation

- [Setup Guide](setup.md) - Installation
- [Testing Guide](testing.md) - Running tests
- [Deployment Guide](deployment.md) - Production setup
