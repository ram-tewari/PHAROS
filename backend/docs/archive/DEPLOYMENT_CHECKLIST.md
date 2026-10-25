# Phase 1 & 2 Deployment Checklist

## Pre-Deployment Verification ✅

- [x] Unit tests pass: `python test_fixes.py`
- [x] All files compile: `python -m py_compile ...`
- [x] Dependencies installed locally
- [ ] API integration tests pass: `python test_api_fixes.py`
- [ ] Manual smoke test on localhost

## Dependency Updates

### Add to `requirements.txt` or `requirements-base.txt`:
```txt
# Tree-sitter core (already present)
tree-sitter>=0.23.0

# Language parsers (NEW - add these)
tree-sitter-c>=0.24.0
tree-sitter-cpp>=0.23.0
tree-sitter-go>=0.23.0
tree-sitter-rust>=0.23.0
tree-sitter-javascript>=0.23.0
tree-sitter-typescript>=0.23.0
tree-sitter-python>=0.23.0
```

## Deployment Steps

### 1. Update Requirements File
```bash
cd backend
# Add tree-sitter packages to config/requirements-base.txt
# (they're needed for both cloud and edge)
```

### 2. Commit Changes
```bash
git add backend/app/modules/search/schema.py
git add backend/app/modules/search/service.py
git add backend/app/modules/search/router.py
git add backend/app/modules/ingestion/language_parser.py
git add backend/app/modules/ingestion/ast_pipeline.py
git add backend/config/requirements-base.txt
git add backend/test_fixes.py
git add backend/test_api_fixes.py
git add PHASE_1_2_IMPLEMENTATION_COMPLETE.md

git commit -m "feat: Phase 1 & 2 - Fix search serialization + polyglot AST

Phase 1: Search Serialization Pipeline
- Enhanced DocumentChunkResult with file_name, github_uri, start_line, end_line
- Rewrote parent_child_search with SQLAlchemy 2.0 selectinload
- Fixed code resolution for both primary and surrounding chunks
- Added from_orm_chunk classmethod for clean ORM mapping

Phase 2: Polyglot AST Support
- Added LanguageParser factory for C, C++, Go, Rust, JS, TS
- Tree-sitter queries for imports, functions, classes, calls
- Integrated with ast_pipeline.py for seamless multi-language support
- Graceful fallback to line-chunking for unsupported languages

Tests: 6/6 unit tests passed
Dependencies: tree-sitter-c, tree-sitter-cpp (+ existing)
Backward compatible: No breaking API changes"
```

### 3. Push to GitHub
```bash
git push origin main
```

### 4. Render Auto-Deploy
- Render will detect the push
- Auto-install dependencies from requirements.txt
- Deploy new version
- Monitor logs for errors

### 5. Post-Deployment Verification

#### Test 1: Health Check
```bash
curl https://pharos-cloud-api.onrender.com/health
```

Expected: `{"status": "healthy", "database": "connected"}`

#### Test 2: Search with include_code
```bash
curl -X POST https://pharos-cloud-api.onrender.com/api/search/advanced \
  -H "Authorization: Bearer $PHAROS_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "authentication",
    "strategy": "parent-child",
    "top_k": 3,
    "include_code": true
  }'
```

Expected fields in response:
- ✅ `results[0].chunk.file_name`
- ✅ `results[0].chunk.github_uri`
- ✅ `results[0].chunk.start_line`
- ✅ `results[0].chunk.end_line`
- ✅ `results[0].chunk.code`
- ✅ `results[0].surrounding_chunks[0].code`
- ✅ `code_metrics.total_chunks`

#### Test 3: Re-ingest Non-Python Repo
```bash
# Ingest a Go repo (e.g., a small CLI tool)
curl -X POST https://pharos-cloud-api.onrender.com/api/v1/ingestion/ingest/github.com/spf13/cobra \
  -H "Authorization: Bearer $PHAROS_ADMIN_TOKEN"

# Wait for ingestion to complete (~2-5 minutes)

# Search for Go code
curl -X POST https://pharos-cloud-api.onrender.com/api/search/advanced \
  -H "Authorization: Bearer $PHAROS_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "command",
    "strategy": "parent-child",
    "top_k": 5
  }'
```

Expected:
- ✅ Results include `.go` files
- ✅ `ast_node_type` is "function" or "method" (not "block")
- ✅ `symbol_name` is qualified (e.g., "cobra.Command.Execute")

## Rollback Plan

If deployment fails:

### Option 1: Revert Commit
```bash
git revert HEAD
git push origin main
```

### Option 2: Render Manual Rollback
1. Go to Render Dashboard
2. Select pharos-cloud-api service
3. Click "Rollback" to previous deployment
4. Confirm rollback

### Option 3: Emergency Fix
If only tree-sitter packages are missing:
1. SSH into Render instance (if available)
2. `pip install tree-sitter-c tree-sitter-cpp`
3. Restart service

## Monitoring

### Key Metrics to Watch (First 24 Hours)

1. **Error Rate**
   - Target: <1% (same as before)
   - Alert if: >5%

2. **Search Latency (P95)**
   - Target: <500ms (same as before)
   - Alert if: >1000ms

3. **Code Fetch Success Rate**
   - Target: >95%
   - Alert if: <80%

4. **Memory Usage**
   - Expected increase: ~50MB (tree-sitter grammars)
   - Alert if: >1GB total

5. **Ingestion Time**
   - Expected: Same as before (~45s per repo)
   - Alert if: >2x slower

### Logs to Monitor

```bash
# Render logs
# Look for:
# - "Failed to load X grammar" (tree-sitter issues)
# - "Code resolution failed" (GitHub fetch issues)
# - "parent_child_search → N results" (search working)
# - "Chunk eager-load failed" (SQLAlchemy issues)
```

## Known Issues & Workarounds

### Issue 1: Tree-sitter Package Missing
**Symptom**: `ImportError: No module named 'tree_sitter_X'`  
**Fix**: Add to requirements.txt and redeploy

### Issue 2: Code Field Still None
**Symptom**: `code: null` in response despite `include_code: true`  
**Possible Causes**:
- Chunk has no `github_uri` (local-only content)
- GitHub API rate limit exceeded
- GitHub token expired/invalid

**Debug**:
```python
# Check code_metrics in response
{
  "code_metrics": {
    "errors": 5,  // <-- Non-zero means fetch failed
    "error_details": ["Rate limit exceeded", ...]
  }
}
```

### Issue 3: Wrong ast_node_type
**Symptom**: `ast_node_type: "block"` for Go/Rust files  
**Cause**: LanguageParser not being used (fallback to line-chunking)  
**Fix**: Check logs for "Failed to load X grammar"

## Success Criteria

### Must Have (Blocking)
- [ ] API responds to /health
- [ ] Search returns results
- [ ] No increase in error rate
- [ ] No increase in latency (P95)

### Should Have (Non-Blocking)
- [ ] `file_name` populated in search results
- [ ] `code` field populated when `include_code=true`
- [ ] `code_metrics` present in response
- [ ] Surrounding chunks have code

### Nice to Have (Future)
- [ ] Go/Rust repos ingested with AST
- [ ] `ast_node_type` is "function"/"class" for non-Python
- [ ] Multi-language search works correctly

## Communication

### Deployment Announcement
```
🚀 Pharos Phase 1 & 2 Deployed

Changes:
- ✅ Fixed search response serialization (file_name, github_uri, code)
- ✅ Added polyglot AST support (C, C++, Go, Rust, JS, TS)
- ✅ Improved code resolution for surrounding chunks
- ✅ Enhanced search relevance (correct representative chunk)

Impact:
- No breaking changes (backward compatible)
- Same performance (<500ms search latency)
- Better search results (correct metadata)

Testing:
- 6/6 unit tests passed
- API integration tests ready

Next:
- Monitor error rates and latency
- Re-ingest non-Python repos to test polyglot AST
- Gather feedback on search quality
```

## Post-Deployment Tasks

### Week 1
- [ ] Monitor error rates daily
- [ ] Check search latency (P95, P99)
- [ ] Verify code fetch success rate
- [ ] Re-ingest 2-3 non-Python repos
- [ ] Gather user feedback

### Week 2
- [ ] Analyze search quality improvements
- [ ] Optimize tree-sitter queries if needed
- [ ] Add more language support (C#, Ruby, PHP)
- [ ] Update documentation with examples

### Month 1
- [ ] Performance tuning based on metrics
- [ ] Add monitoring dashboards
- [ ] Write blog post about polyglot AST
- [ ] Plan Phase 3 features

---

**Deployment Owner**: [Your Name]  
**Date**: May 2, 2026  
**Estimated Downtime**: 0 (rolling deployment)  
**Rollback Time**: <5 minutes
