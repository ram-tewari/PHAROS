# Enable Chunking and Graph Extraction

**Date**: 2026-04-17  
**Status**: ⚠️ **ACTION REQUIRED**

---

## Issue

The graph endpoints are returning empty results because:
1. **Chunking is disabled** - Resources are not being split into chunks
2. **Graph extraction is disabled** - Entities and relationships are not being extracted

---

## Solution

Enable automatic chunking and graph extraction by setting these environment variables to `true`.

---

## Changes Made

### 1. Updated Default Settings ✅

**File**: `backend/app/config/settings.py`

```python
# BEFORE
CHUNK_ON_RESOURCE_CREATE: bool = False
GRAPH_EXTRACT_ON_CHUNK: bool = False

# AFTER
CHUNK_ON_RESOURCE_CREATE: bool = True
GRAPH_EXTRACT_ON_CHUNK: bool = True
```

### 2. Add Environment Variables to Render

Go to Render Dashboard → pharos-cloud-api → Environment

Add these two variables:

```bash
CHUNK_ON_RESOURCE_CREATE=true
GRAPH_EXTRACT_ON_CHUNK=true
```

---

## How It Works

### Current Flow (Broken)
```
Resource Created → Embedding Generated → DONE
                                          ↓
                                    No chunks created
                                    No graph entities
                                    Empty graph
```

### New Flow (Fixed)
```
Resource Created → Embedding Generated → Chunks Created → Graph Extraction
                                              ↓                  ↓
                                         Semantic chunks    Entities extracted
                                         Parent-child       Relationships found
                                         relationships      Graph populated
```

---

## What Will Happen

### When Enabled

1. **Resource Created** → Triggers `resource.created` event
2. **Chunking Service** → Subscribes to event, creates chunks
3. **Chunks Created** → Emits `resource.chunked` event
4. **Graph Service** → Subscribes to event, extracts entities
5. **Graph Populated** → Entities and relationships stored

### For Existing Resources

Existing resources (like FastAPI) won't be automatically processed. You'll need to either:

**Option A**: Delete and re-ingest
```powershell
# Delete existing resource
Invoke-RestMethod -Uri "https://pharos-cloud-api.onrender.com/api/resources/0811a2fc-b05d-4b0d-91ad-91c44e2ed4df" -Method DELETE

# Re-ingest FastAPI
$payload = @{
    url = "https://github.com/fastapi/fastapi"
    title = "FastAPI - Modern Python Web Framework"
    resource_type = "code_repository"
} | ConvertTo-Json

Invoke-RestMethod -Uri "https://pharos-cloud-api.onrender.com/api/resources" -Method POST -Body $payload -ContentType "application/json"
```

**Option B**: Manually trigger chunking (if endpoint exists)
```powershell
# Trigger chunking for existing resource
Invoke-RestMethod -Uri "https://pharos-cloud-api.onrender.com/api/resources/0811a2fc-b05d-4b0d-91ad-91c44e2ed4df/chunk" -Method POST
```

---

## Expected Results

### After Enabling

When you ingest a new resource:

1. ✅ **Resource created** with metadata
2. ✅ **Embedding generated** (768 dims)
3. ✅ **Chunks created** (semantic chunking, ~500 words each)
4. ✅ **Graph entities extracted** (concepts, methods, classes)
5. ✅ **Relationships extracted** (imports, calls, dependencies)

### Graph Endpoints

```bash
# Graph Overview - Should show nodes and edges
GET /api/graph/overview
Response: {
  "nodes": [
    {"id": "...", "name": "FastAPI", "type": "concept"},
    {"id": "...", "name": "async", "type": "concept"},
    ...
  ],
  "edges": [
    {"source": "...", "target": "...", "type": "mentions"},
    ...
  ]
}

# Resource Neighbors - Should show related entities
GET /api/graph/resource/{id}/neighbors
Response: {
  "nodes": [...],
  "edges": [...]
}
```

---

## Performance Impact

### Chunking
- **Time**: ~2-5 seconds per resource (depends on size)
- **Storage**: ~10KB per chunk (metadata + embedding)
- **Chunks**: ~10-50 chunks per typical repository

### Graph Extraction
- **Time**: ~1-3 seconds per chunk (LLM-based extraction)
- **Storage**: ~5KB per entity + relationship
- **Entities**: ~5-20 entities per chunk

### Total Impact
- **Processing Time**: +5-10 seconds per resource
- **Storage**: +100KB-500KB per resource
- **Worth It**: YES - enables GraphRAG, better search, knowledge discovery

---

## Deployment Steps

### 1. Commit Changes ✅
```bash
cd backend
git add app/config/settings.py
git commit -m "Enable automatic chunking and graph extraction"
git push origin master
```

### 2. Add Environment Variables to Render

1. Go to https://dashboard.render.com/
2. Select `pharos-cloud-api` service
3. Go to "Environment" tab
4. Click "Add Environment Variable"
5. Add:
   - Key: `CHUNK_ON_RESOURCE_CREATE`, Value: `true`
   - Key: `GRAPH_EXTRACT_ON_CHUNK`, Value: `true`
6. Click "Save Changes"
7. Render will auto-deploy

### 3. Wait for Deployment
- Render will rebuild and redeploy (~2-5 minutes)
- Check deployment logs for success

### 4. Test with New Resource
```powershell
# Ingest a new test resource
$payload = @{
    url = "https://github.com/tiangolo/fastapi"
    title = "FastAPI Test - With Chunking"
    resource_type = "code_repository"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "https://pharos-cloud-api.onrender.com/api/resources" -Method POST -Body $payload -ContentType "application/json"

# Wait 10-15 seconds for processing
Start-Sleep -Seconds 15

# Check graph
Invoke-RestMethod -Uri "https://pharos-cloud-api.onrender.com/api/graph/overview" -Method GET
```

---

## Verification

### Check if Enabled

```powershell
# Check settings endpoint (if available)
Invoke-RestMethod -Uri "https://pharos-cloud-api.onrender.com/api/monitoring/health" -Method GET

# Or check by ingesting a test resource and seeing if chunks are created
$resourceId = "..." # from ingestion response
Invoke-RestMethod -Uri "https://pharos-cloud-api.onrender.com/api/resources/$resourceId/chunks" -Method GET
# Should return chunks (not empty array)
```

### Expected Behavior

**Before**:
- Chunks endpoint returns `[]`
- Graph overview returns `{"nodes": [], "edges": []}`

**After**:
- Chunks endpoint returns array of chunks
- Graph overview returns nodes and edges
- Search works better (parent-child retrieval)

---

## Rollback Plan

If issues arise:

### 1. Disable in Render
1. Go to Render Dashboard
2. Delete or set to `false`:
   - `CHUNK_ON_RESOURCE_CREATE=false`
   - `GRAPH_EXTRACT_ON_CHUNK=false`
3. Save and redeploy

### 2. Revert Code
```bash
git revert HEAD
git push origin master
```

---

## Next Steps

1. ✅ Commit settings changes
2. ⏳ Add environment variables to Render
3. ⏳ Wait for deployment
4. ⏳ Test with new resource ingestion
5. ⏳ Verify graph has data
6. ⏳ Re-run endpoint tests

---

## Status

- [x] Settings file updated
- [ ] Environment variables added to Render
- [ ] Deployment complete
- [ ] Tested with new resource
- [ ] Graph populated
- [ ] Endpoints verified

---

**Action Required**: Add environment variables to Render and redeploy.

