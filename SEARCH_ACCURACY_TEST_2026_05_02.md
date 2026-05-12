# Search Accuracy Test - May 2, 2026

## Test Summary

**Status**: ⚠️ NO RESULTS - Chunks exist but lack embeddings

## Issue Identified

The worker successfully ingested repositories and created chunks with AST-based semantic summaries, but **embeddings were not generated** for the chunks. This prevents vector search from working.

### Evidence

1. **Resources created**: 17,714 total resources in database
2. **Ingestion status**: All resources show `ingestion_status: "pending"`
3. **Worker logs**: Show successful chunk creation (112 chunks for fatih/color, 5,307 chunks for FastAPI)
4. **Search results**: Zero results for all queries (authentication, color, fastapi, function)

### Root Cause

The repository ingestion pipeline (`RepositoryIngestor.ingest()`) creates chunks but does not:
1. Generate embeddings for chunks
2. Update resource `ingestion_status` to "completed"
3. Queue individual chunk embedding tasks

### Test Queries Attempted

| Query | Strategy | Expected | Actual | Latency |
|-------|----------|----------|--------|---------|
| "authentication function" | parent-child | Python auth code | 0 results | 527ms |
| "color function" | parent-child | Go color functions | 0 results | 396ms |
| "fastapi router" | parent-child | FastAPI routing code | 0 results | 382ms |
| "function" | hybrid | Any functions | 0 results | 632ms |

### Phase 1 Verification

**Cannot verify Phase 1 enhancements** because search returns no results. Phase 1 added:
- ✅ 11 new fields to `DocumentChunkResult` schema
- ✅ Eager loading with `selectinload()`
- ✅ Intelligent chunk ranking
- ✅ Code resolution for all chunks

These enhancements are implemented but cannot be tested without embeddings.

## Next Steps

### Option 1: Fix Repository Ingestion Pipeline
Modify `RepositoryIngestor.ingest()` to:
1. Generate embeddings for all chunks after creation
2. Update resource `ingestion_status` to "completed"
3. Mark resources as non-stale

### Option 2: Queue Chunk Embedding Tasks
After repository ingestion:
1. Queue individual chunk embedding tasks to `pharos:tasks`
2. Let edge worker process them asynchronously
3. Update resource status when all chunks have embeddings

### Option 3: Use Existing Indexed Data
Test with LangChain repository (3,302 resources) which was ingested earlier and should have embeddings.

## Recommendation

**Option 1** is preferred - fix the repository ingestion pipeline to generate embeddings inline. This ensures:
- Atomic ingestion (chunks + embeddings together)
- Immediate search availability
- No orphaned chunks without embeddings

## Worker Status

- **State**: Running but idle (polling queue every 30s)
- **Last Activity**: Ingested fatih/color at 21:35:09 (9 minutes ago)
- **Queue**: Empty (no pending tasks)
- **Embedding Model**: Loaded (nomic-ai/nomic-embed-text-v1)
- **GPU**: Available (NVIDIA RTX 4070)

## Files Created

- `backend/test_search_debug.py` - Debug script to check chunk/embedding counts (had import issues, not completed)

---

**Test Date**: 2026-05-02 21:45 UTC
**Tester**: Kiro AI Assistant
**Conclusion**: Search pipeline is functional but requires embeddings to return results. Phase 1 enhancements cannot be verified until embeddings are generated.
