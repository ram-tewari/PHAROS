# Documentation Update - April 27, 2026

## Summary

This document tracks the major documentation updates made on April 27, 2026, to align backend/docs/ with the authoritative notebooklm/ documentation and reflect the unified worker architecture.

---

## What Changed

### 1. Worker Architecture Consolidation

**Old State**:
- Three separate worker files: `edge.py`, `repo.py`, `combined.py`
- Multiple start scripts: `start_edge_worker.ps1`, `start_combined_worker.ps1`, `start_embed_simple.ps1`, etc.
- 9-second BLPOP timeout (burning through Upstash quota)
- Scattered documentation

**New State**:
- **Single unified worker**: `app/workers/main_worker.py`
- **Two bulletproof launchers**: `start_worker.sh` (bash), `start_worker.py` (Python)
- **30-second BLPOP timeout** (Upstash quota-safe: ~2,880 idle cmds/day)
- **Centralized documentation**: `docs/WORKER_ARCHITECTURE.md`

**Files Deleted**:
- `backend/app/workers/edge.py`
- `backend/app/workers/repo.py`
- `backend/app/workers/combined.py`
- `backend/start_edge_worker.ps1`
- `backend/start_edge_worker_simple.ps1`
- `backend/start_edge_worker.bat`
- `backend/start_combined_worker.ps1`
- `backend/start_embed_simple.ps1`
- `backend/start_embed_wsl.sh`
- `backend/start_worker_simple.ps1`
- `backend/embed_server.py` (moved to WSL2-only)

**Files Kept**:
- `backend/start_worker.sh` (NEW - bash launcher)
- `backend/start_worker.py` (NEW - Python launcher)
- `backend/worker.py` (UPDATED - thin wrapper)
- `backend/app/workers/main_worker.py` (NEW - unified worker)

**Log Files Cleaned**:
- `combined_worker_err.log`
- `combined_worker.log`
- `edge_worker.log`
- `embed_server.err.log`
- `embed_server.log`
- `embed_server.out.log`

---

### 2. Upstash Quota Optimization

**Problem**: Previous BLPOP timeout (9s) generated ~9,600 idle commands/day, exceeding Upstash's 10,000 req/day free tier.

**Solution**: Increased BLPOP timeout to **30 seconds**:
```
86400 seconds/day ÷ 30 seconds/cycle = 2,880 idle commands/day
```

**Headroom**: ~320 commands/day for actual task throughput.

**Implementation**:
- `backend/app/shared/upstash_redis.py`: New `pop_from_queues()` method with 30s timeout
- `backend/app/workers/main_worker.py`: Uses 30s BLPOP, documents the math
- `notebooklm/02_ARCHITECTURE.md`: Updated "Upstash quota optimization" section

---

### 3. Documentation Alignment

**Authoritative Source**: `notebooklm/` directory (6 files, completely up-to-date)

**Files Updated**:
- `notebooklm/02_ARCHITECTURE.md` - Process inventory rewritten, Upstash quota section added
- `backend/docs/WORKER_ARCHITECTURE.md` - NEW comprehensive worker guide
- `backend/docs/DOCUMENTATION_UPDATE_2026_04_27.md` - THIS FILE

**Files To Update** (see Action Items below):
- `backend/docs/index.md`
- `backend/docs/README.md`
- `backend/docs/architecture/overview.md`
- `backend/docs/guides/setup.md`
- `backend/docs/guides/workflows.md`
- `backend/docs/deployment/render.md`

---

## Key Architectural Changes

### Unified Worker Design

**Before**:
```
edge.py       → polls pharos:tasks
repo.py       → polls ingest_queue
combined.py   → polls both (but separate connections)
```

**After**:
```
main_worker.py → polls BOTH with single BLPOP
  ├─ pharos:tasks   → handle_resource_task()
  └─ ingest_queue   → RepositoryIngestor.ingest()
```

**Benefits**:
- One process, one connection, one BLPOP
- Poison-pill containment (bad task doesn't kill worker)
- Outer guard (network blip doesn't kill worker)
- Simpler deployment (one launcher, one log file)

---

### BLPOP Multi-Key Blocking

**New Redis Method** (`upstash_redis.py`):
```python
async def pop_from_queues(
    self,
    keys: list[str],
    timeout: int = 30
) -> tuple[str, dict] | None:
    """
    Block on multiple queues, return (queue_key, task) when one pops.
    
    Returns:
        (queue_key, task) if a task was popped
        None if timeout elapsed with no tasks
    """
```

**Usage**:
```python
popped = await redis_client.pop_from_queues(
    ["pharos:tasks", "ingest_queue"],
    timeout=30
)
if popped:
    queue_key, task = popped
    if queue_key == "pharos:tasks":
        await handle_resource_task(task)
    elif queue_key == "ingest_queue":
        await repo_ingestor.ingest(task)
```

---

## Action Items

### Immediate (Done)

- [x] Delete old worker files (`edge.py`, `repo.py`, `combined.py`)
- [x] Delete old start scripts (PowerShell, batch, WSL)
- [x] Clean up log files
- [x] Create unified worker (`main_worker.py`)
- [x] Create bulletproof launchers (`start_worker.sh`, `start_worker.py`)
- [x] Update `upstash_redis.py` with `pop_from_queues()` method
- [x] Update `notebooklm/02_ARCHITECTURE.md` with new process inventory
- [x] Create `backend/docs/WORKER_ARCHITECTURE.md`
- [x] Create this update summary

### Next (To Do)

- [x] Update `backend/docs/index.md` with worker architecture link
- [x] Update `backend/docs/README.md` with new structure
- [x] Update `backend/docs/architecture/overview.md` with unified worker
- [x] Update `backend/docs/guides/setup.md` with new launchers
- [x] Update `backend/docs/guides/workflows.md` with new commands
- [ ] Update `backend/docs/deployment/render.md` with new env vars (if exists)
- [ ] Update `backend/docs/guides/troubleshooting.md` with new failure modes (if exists)
- [ ] Sync all API docs with notebooklm/05_API_DEPLOYMENT_OPS.md (future)
- [ ] Sync all data model docs with notebooklm/03_DATA_MODEL_AND_MODULES.md (future)
- [ ] Sync all ingestion docs with notebooklm/04_INGESTION_AND_SEARCH.md (future)

---

## Migration Guide for Developers

### If You Were Running `edge.py`

**Old**:
```bash
cd backend
python worker.py edge
```

**New**:
```bash
cd backend
bash start_worker.sh    # Linux/WSL/Git Bash
python start_worker.py  # Windows
```

---

### If You Were Running `repo.py`

**Old**:
```bash
cd backend
python worker.py repo
```

**New**:
```bash
cd backend
bash start_worker.sh    # Same launcher, handles both queues
```

---

### If You Were Running `combined.py`

**Old**:
```bash
cd backend
python worker.py combined
```

**New**:
```bash
cd backend
bash start_worker.sh    # Same launcher, now the only option
```

---

### If You Have Custom Scripts

**Search for**:
- `python worker.py edge`
- `python worker.py repo`
- `python worker.py combined`
- `start_edge_worker.ps1`
- `start_combined_worker.ps1`

**Replace with**:
- `bash start_worker.sh` (Linux/WSL/Git Bash)
- `python start_worker.py` (Windows)

---

## Testing Checklist

### Verify Worker Boot

```bash
cd backend
bash start_worker.sh
```

**Expected output**:
```
================================================================
  Pharos Unified Edge Worker
================================================================
  Mode             : EDGE
  Queues (BLPOP)   : pharos:tasks, ingest_queue
  BLPOP timeout    : 30s  (~2,880 idle cmds/day, Upstash-safe)
  Embed endpoint   : http://127.0.0.1:8001/embed
  Working dir      : /path/to/backend
  Python           : 3.13.x
================================================================
```

---

### Verify Resource Ingestion

```bash
curl -X POST "https://pharos-cloud-api.onrender.com/api/resources" \
  -H "Authorization: Bearer $PHAROS_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/article",
    "title": "Test Article"
  }'
```

**Expected**: Resource created with `ingestion_status='pending'`, worker picks it up within 30s, status changes to `completed`.

---

### Verify Repo Ingestion

```bash
curl -X POST "https://pharos-cloud-api.onrender.com/api/v1/ingestion/ingest/github.com/owner/repo" \
  -H "Authorization: Bearer $PHAROS_ADMIN_TOKEN"
```

**Expected**: Task queued to `ingest_queue`, worker picks it up within 30s, repo cloned and parsed.

---

### Verify Upstash Quota

**Check commands/day**:
```bash
# Monitor for 24 hours, count BLPOP commands
# Should be ~2,880 idle commands + actual task throughput
```

**Expected**: <3,200 commands/day total.

---

## Related Documentation

- [Worker Architecture](WORKER_ARCHITECTURE.md) - Complete worker guide
- [NotebookLM Architecture](../notebooklm/02_ARCHITECTURE.md) - Authoritative source
- [NotebookLM Ingestion](../notebooklm/04_INGESTION_AND_SEARCH.md) - Pipeline details
- [NotebookLM Deployment](../notebooklm/05_API_DEPLOYMENT_OPS.md) - Ops guide

---

## Questions?

- **Worker not starting?** Check `MODE=EDGE` in `.env`
- **Tasks not processing?** Check Upstash dashboard for queue sizes
- **GPU errors?** Check CUDA availability with `nvidia-smi`
- **Quota exceeded?** Verify BLPOP timeout is 30s in `main_worker.py`

---

**Last Updated**: 2026-04-27  
**Author**: Kiro AI Assistant  
**Status**: Complete


---

## Update Completion Summary

**Date**: 2026-04-27  
**Status**: Core documentation updates complete ✅

### Files Updated

1. **backend/docs/index.md**
   - Added Worker Architecture link to Developer Guides section
   - Updated Hybrid Edge-Cloud Architecture section with worker reference

2. **backend/docs/README.md**
   - Added Worker Architecture to Architecture table
   - Added Worker Architecture to Developer Guides table

3. **backend/docs/architecture/overview.md**
   - Updated Deployment Topology diagram with unified worker details
   - Changed BLPOP timeout from 9s to 30s in documentation
   - Updated queue polling description to show both queues
   - Added reference to Worker Architecture document
   - Added Worker Architecture to Related Documentation

4. **backend/docs/guides/setup.md**
   - Added Step 7: Start Edge Worker with new launchers
   - Added reference to Worker Architecture document
   - Added Worker Architecture to Related Documentation

5. **backend/docs/guides/workflows.md**
   - Added Worker Commands section to Quick Reference
   - Added reference to Worker Architecture document
   - Added Worker Architecture to Related Documentation

### Key Changes Reflected

- **Unified Worker**: All documentation now references the single `main_worker.py` instead of separate edge/repo/combined workers
- **New Launchers**: `start_worker.sh` and `start_worker.py` are now the recommended way to start the worker
- **30s BLPOP Timeout**: Updated from 9s to 30s for Upstash quota compliance (~2,880 idle cmds/day)
- **Dual Queue Polling**: Documentation now shows worker polls both `pharos:tasks` and `ingest_queue` with single BLPOP

### Remaining Tasks (Future)

The following items are marked for future updates when those files are created or when comprehensive sync is needed:

- Update `backend/docs/deployment/render.md` (if it exists)
- Update `backend/docs/guides/troubleshooting.md` (if it exists)
- Comprehensive sync with notebooklm/ authoritative docs (Phase 20+)

### Verification

All updated files have been verified to:
- Reference the unified worker architecture
- Point to `WORKER_ARCHITECTURE.md` for detailed worker documentation
- Use correct BLPOP timeout (30s)
- Show correct launcher commands (`start_worker.sh`, `start_worker.py`)

---

**Documentation Update Complete**: 2026-04-27 23:45 UTC
