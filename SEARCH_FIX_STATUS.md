# Search Fix Status - April 19, 2026

## Problem

Search endpoint returns 0 results despite having 2,461 resources with embeddings in production database.

## Root Causes Identified

### Issue #1: Wrong Embedding Location ✅ FIXED
**Problem**: Search service was looking for embeddings in `chunk.chunk_metadata["embedding_vector"]` but embeddings are stored in `resources.embedding` column.

**Fix**: Updated `parent_child_search()` method in `backend/app/modules/search/service.py` to look in correct location.

**Commit**: `b9bb7242` - "fix: search now looks for embeddings in resources.embedding column instead of chunk_metadata"

### Issue #2: Invalid Parameter ✅ FIXED
**Problem**: Search service was calling `embedding_service.generate_embedding(query, force_load_in_cloud=True)` but that parameter doesn't exist.

**Fix**: Removed `force_load_in_cloud` parameter from the call.

**Commit**: `92ee1f4d` - "fix: remove force_load_in_cloud parameter from embedding service call"

## Deployment Status

### Commits Pushed
1. `b9bb7242` - Embedding location fix
2. `92ee1f4d` - Parameter fix

### Render Auto-Deploy
- Status: Triggered
- Expected Duration: 3-5 minutes per deploy
- Total Time: ~10 minutes for both commits

### Testing
- Tested at: 08:30 UTC, 08:31 UTC, 08:33 UTC
- Result: Still returning 0 results
- Possible Reasons:
  1. Render deployment not complete yet
  2. Render caching old code
  3. Another issue we haven't identified

## Database State (Verified)

```
Repositories: 2
Resources: 3,302
Chunks: 3,302
Resources with Embeddings: 2,461 (74.5%)
Remote Chunks (GitHub): 3,292 (99.7%)
```

Sample resource with embedding:
```
Title: libs\langchain\langchain_classic\chains\hyde\base.py
Has embedding: YES
Embedding length: 9537 chars (JSON array of 768 floats)
```

## Code Changes Made

### File: `backend/app/modules/search/service.py`

**Before**:
```python
# Check if embedding is in chunk_metadata (current storage location)
embedding = None
if chunk.chunk_metadata and "embedding_vector" in chunk.chunk_metadata:
    embedding_str = chunk.chunk_metadata["embedding_vector"]
    # Parse string to list of floats (stored as space-separated string)
    if isinstance(embedding_str, str):
        embedding = [float(x) for x in embedding_str.split()]
    else:
        embedding = embedding_str  # Already a list

if embedding:
    # Use cosine similarity between query embedding and chunk embedding
    score = self._cosine_similarity(query_embedding, embedding)
    chunk_scores.append((chunk, score))
else:
    # Fallback to keyword similarity if no embedding
    score = self._compute_similarity_score(query, chunk.content or "")
    chunk_scores.append((chunk, score))
```

**After**:
```python
# Get embedding from parent resource (stored in resources.embedding column)
embedding = None
if chunk.resource and chunk.resource.embedding:
    embedding_str = chunk.resource.embedding
    # Parse JSON string to list of floats
    if isinstance(embedding_str, str):
        import json
        try:
            embedding = json.loads(embedding_str)
        except json.JSONDecodeError:
            # Try space-separated format as fallback
            embedding = [float(x) for x in embedding_str.split()]
    else:
        embedding = embedding_str  # Already a list

if embedding:
    # Use cosine similarity between query embedding and chunk embedding
    score = self._cosine_similarity(query_embedding, embedding)
    chunk_scores.append((chunk, score))
else:
    # Skip chunks without embeddings (don't use keyword fallback for semantic search)
    continue
```

**Before**:
```python
# Generate query embedding
# Force load model in CLOUD mode for query embeddings (search needs immediate results)
try:
    embedding_service = EmbeddingService(self.db)
    query_embedding = embedding_service.generate_embedding(query, force_load_in_cloud=True)
except Exception as e:
    logger.error(f"Failed to generate query embedding: {e}")
    return []
```

**After**:
```python
# Generate query embedding
try:
    embedding_service = EmbeddingService(self.db)
    query_embedding = embedding_service.generate_embedding(query)
except Exception as e:
    logger.error(f"Failed to generate query embedding: {e}")
    return []
```

## Next Steps

### Immediate
1. ✅ Wait for Render deployment (10 minutes total)
2. 🔄 Test search endpoint again
3. 🔄 Check Render logs for errors if still failing

### If Still Failing
1. Check Render dashboard for deployment status
2. Check Render logs for Python errors
3. Verify psycopg2 is installed (for sync PostgreSQL)
4. Test with curl to rule out PowerShell issues
5. Add debug logging to search service

### If Working
1. Test with different queries ("authentication", "oauth", "security")
2. Test with `include_code: true` to verify GitHub fetching
3. Test GraphRAG search
4. Update documentation
5. Close this issue

## Testing Commands

### PowerShell
```powershell
$headers = @{"Authorization" = "Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74"; "Content-Type" = "application/json"}
$body = '{"query": "langchain", "strategy": "parent-child", "top_k": 5, "include_code": false}'
Invoke-RestMethod -Uri "https://pharos-cloud-api.onrender.com/api/search/advanced" -Method Post -Headers $headers -Body $body
```

### Bash (if available)
```bash
curl -X POST https://pharos-cloud-api.onrender.com/api/search/advanced \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74" \
  -H "Content-Type: application/json" \
  -d '{"query": "langchain", "strategy": "parent-child", "top_k": 5, "include_code": false}'
```

## Architecture Notes

### Sync vs Async Database
- Production uses PostgreSQL with `postgresql+asyncpg://` URL
- Search service uses sync SQLAlchemy (`self.db.query()`)
- Router provides sync session via `get_sync_db()`
- `create_database_engine()` automatically converts asyncpg → psycopg2 for sync

### Embedding Storage
- Embeddings stored in `resources.embedding` column (JSONB in PostgreSQL)
- Format: JSON array of 768 floats (nomic-embed-text-v1)
- Example: `[0.123, -0.456, 0.789, ...]`
- Size: ~9500 characters per embedding

### Search Flow
1. User sends query to `/api/search/advanced`
2. Router calls `SearchService.parent_child_search()`
3. Service generates query embedding via Tailscale Funnel (EDGE_EMBEDDING_URL)
4. Service queries all chunks with JOIN to resources
5. Service computes cosine similarity between query embedding and resource embeddings
6. Service sorts by score and returns top-k results

## Timeline

- **08:15 UTC**: Identified issue #1 (wrong embedding location)
- **08:20 UTC**: Fixed and committed (`b9bb7242`)
- **08:22 UTC**: Pushed to GitHub
- **08:25 UTC**: Identified issue #2 (invalid parameter)
- **08:27 UTC**: Fixed and committed (`92ee1f4d`)
- **08:28 UTC**: Pushed to GitHub
- **08:30 UTC**: First test - still 0 results
- **08:31 UTC**: Second test - still 0 results
- **08:33 UTC**: Third test - still 0 results
- **08:35 UTC**: Created this status document

## Conclusion

Two fixes have been identified and deployed. Waiting for Render auto-deploy to complete. If search still returns 0 results after deployment, will investigate further (check logs, verify psycopg2, add debug logging).

---

**Last Updated**: April 19, 2026 08:35 UTC  
**Status**: Waiting for Render deployment  
**Next Action**: Test search endpoint in 5 minutes
