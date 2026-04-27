# Pharos Worker Architecture

**Last Updated**: 2026-04-27  
**Status**: Production-ready

---

## Overview

Pharos uses a **unified edge worker** that handles all GPU-bound operations (embeddings, SPLADE, LLM extraction) on a local RTX 4070 GPU. The worker serves a FastAPI `/embed` endpoint and polls two Redis queues with a single multi-key BLPOP.

---

## Process Inventory

### 1. Cloud API (Render)
- **Location**: `https://pharos-cloud-api.onrender.com`
- **Mode**: `MODE=CLOUD`
- **Purpose**: Serves REST API, never loads ML models
- **Resources**: 512 MB RAM, 0.5 CPU, $7/mo
- **Startup**: `gunicorn -c gunicorn_conf.py app.main:app`

### 2. Unified Edge Worker (Local)
- **Location**: `backend/app/workers/main_worker.py`
- **Mode**: `MODE=EDGE`
- **Purpose**: 
  - Loads embedding model (nomic-embed-text-v1) on RTX 4070
  - Serves FastAPI `/embed` endpoint on port 8001
  - Polls **both** Redis queues with single BLPOP
- **Queues**: 
  - `pharos:tasks` → single-resource ingestion
  - `ingest_queue` → repo-level clone/parse/embed/store
- **Startup**: 
  ```bash
  bash start_worker.sh    # Linux/WSL/Git Bash
  python start_worker.py  # Windows
  python worker.py        # legacy dispatcher (thin wrapper)
  ```

### 3. Embed Server (WSL2, Optional)
- **Location**: `backend/embed_server.py`
- **Purpose**: Standalone embedding HTTP server (zero `app.*` imports)
- **Port**: 8001
- **Exposed via**: Tailscale Funnel (`https://pc.tailf7b210.ts.net`)
- **Used by**: Cloud API for query embeddings
- **Startup**: `bash start_embed_wsl.sh`

---

## Unified Worker Architecture

### Single Process, Two Queues

The unified worker (`main_worker.py`) uses **one Redis connection** to block on **both queues simultaneously**:

```python
BLPOP pharos:tasks ingest_queue 30
```

**Routing by source queue**:
- `pharos:tasks` → `handle_resource_task()` → calls `process_ingestion(resource_id)`
- `ingest_queue` → `RepositoryIngestor.ingest()` → clone → AST parse → embed → persist

**Poison-pill containment**: Each handler is wrapped in try/except. A bad task is logged, marked `failed` in Redis, and the loop continues.

**Outer guard**: The dispatch loop itself is wrapped in try/except with a 2s sleep on transport errors, so a network blip never kills the worker.

---

## BLPOP Timeout: 30 Seconds

**Why 30 seconds?**

Upstash free tier allows **100,000 commands/month** (~3,200/day). The unified worker uses a **30-second** server-side BLPOP timeout:

```
86400 seconds/day ÷ 30 seconds/cycle = 2,880 idle commands/day
```

This leaves **~320 commands/day** headroom for actual task throughput and other operations.

**Previous configuration** (9 seconds): ~9,600 idle cmds/day, burning through the quota.

**DO NOT lower the timeout below 30s without redoing this math.**

---

## Queue Semantics

### `pharos:tasks` (Single-Resource Ingestion)

**Task format**:
```json
{
  "task_id": "uuid",
  "resource_id": "uuid"
}
```

**Handler**: `handle_resource_task()` in `main_worker.py`

**Pipeline**:
1. Fetch URL / read archived PDF
2. Extract text (trafilatura / readability / pdfplumber)
3. AI summary + tags (transformer call, local GPU)
4. Archive raw content
5. Generate 768-dim resource embedding (nomic-embed-text-v1)
6. ChunkingService: split content into DocumentChunks
7. For code: AST chunking, generate semantic_summary
8. Embed each chunk
9. Compute quality scores (5-dim + overall)
10. Extract citations
11. Emit events (resource.created, resource.chunked, chunk.embedded)
12. Mark `ingestion_status='completed'`

**Time**: ~30-60 seconds per resource

---

### `ingest_queue` (Repository Ingestion)

**Task format**:
```json
{
  "repo_url": "github.com/owner/repo",
  "submitted_at": "...",
  "ttl": 86400
}
```

**Handler**: `RepositoryIngestor.ingest()` in `main_worker.py`

**Pipeline**:
1. Clone repo to temp directory (`git clone --depth 1`)
2. Parse .gitignore, walk file tree
3. Apply path exclusions (migrations/, alembic/, __generated__, lockfiles, .min.*, _pb2.py)
4. For each code file:
   - Create Resource (metadata only, no source stored)
   - Run Tree-Sitter AST parse (Python fully supported)
   - Extract symbols: functions, classes, methods
   - Create DocumentChunk per symbol with:
     - `content = NULL`
     - `github_uri = raw.githubusercontent.com URL`
     - `branch_reference = commit SHA or "HEAD"`
     - `semantic_summary = "[lang] signature: 'docstring.' deps: [...]"`
     - `embedding = NULL` (async later)
5. Batch-commit every 50 chunks
6. Emit `resource.created` and `resource.chunked` events
7. Mark old resources as stale (`is_stale=TRUE`)
8. Mark new resources as fresh (`is_stale=FALSE`, `last_indexed_sha=commit_sha`)

**Time**: ~45-90 seconds per repo (depends on size)

---

## Startup Sequence

### Unified Worker Boot

1. **Environment check**: Validates `MODE=EDGE`, `UPSTASH_REDIS_REST_URL`, `DATABASE_URL`
2. **GPU check**: Logs CUDA availability (RTX 4070), falls back to CPU if unavailable
3. **Load embedding model**: `nomic-embed-text-v1` on GPU (~400 MB VRAM)
4. **Connect to Redis**: Upstash PING test
5. **Connect to database**: PostgreSQL on NeonDB
6. **Print banner**: Shows active queues, BLPOP timeout, embed endpoint
7. **Start two async tasks**:
   - `run_embed_server()` → FastAPI on port 8001
   - `poll_and_dispatch()` → BLPOP loop

**Boot time**: ~10-15 seconds (model loading is the bottleneck)

---

## Launchers

### `start_worker.sh` (Bash)

**Purpose**: Bulletproof launcher for Linux/WSL/Git Bash

**Guarantees**:
- cwd is `backend/`
- `.env` is loaded
- `MODE=EDGE` is forced (overrides .env)
- Banner prints active queues + 30s BLPOP timeout

**Usage**:
```bash
cd backend
bash start_worker.sh
```

---

### `start_worker.py` (Python)

**Purpose**: Cross-platform launcher for Windows

**Guarantees**:
- cwd is `backend/`
- `.env` is loaded (via python-dotenv)
- `MODE=EDGE` is forced
- Python 3.13 WMI workaround applied
- Banner prints active queues + 30s BLPOP timeout

**Usage**:
```bash
cd backend
python start_worker.py
```

---

### `worker.py` (Legacy Dispatcher)

**Purpose**: Thin wrapper around `main_worker.py`

**Status**: Kept for backward compatibility, but `start_worker.sh` / `start_worker.py` are preferred

**Usage**:
```bash
cd backend
python worker.py
```

---

## Failure Modes and Recovery

### Edge Worker Offline

**Symptom**: Resources stuck in `ingestion_status='pending'`

**Recovery**:
```bash
cd backend
python scripts/queue_pending_resources.py
```

This re-pushes every pending resource to `pharos:tasks`.

---

### Upstash Rate Limit Exceeded

**Symptom**: BLPOP returns errors, worker logs "rate limit exceeded"

**Cause**: BLPOP timeout too low (generating >3,200 idle cmds/day)

**Fix**: Increase `BLPOP_TIMEOUT_SECONDS` in `main_worker.py` (currently 30s)

---

### Poison-Pill Task

**Symptom**: Worker logs "Handler crash on queue=X task=Y"

**Behavior**: Task is marked `failed` in Redis, loop continues

**Recovery**: Inspect logs, fix the bug, re-queue the task manually

---

### GPU Out of Memory

**Symptom**: Worker crashes with CUDA OOM error

**Cause**: Batch size too large, or multiple workers running

**Fix**: 
- Reduce batch size in embedding calls
- Ensure only one worker is running
- Restart worker to clear GPU memory

---

## Monitoring

### Check Queue Sizes

```bash
curl -X POST "$UPSTASH_REDIS_REST_URL" \
  -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '["LLEN","pharos:tasks"]'
```

### Check Worker Status

```bash
# Linux/WSL
ps aux | grep main_worker

# Windows
tasklist | findstr python
```

### Tail Worker Logs

```bash
# If running via start_worker.sh (redirects to file)
tail -f backend/worker.log

# If running directly (stdout)
# Logs appear in terminal
```

---

## Performance Metrics

| Operation | Time | Notes |
|-----------|------|-------|
| Worker boot | ~10-15s | Model loading |
| Single resource ingestion | ~30-60s | Depends on content size |
| Repo ingestion | ~45-90s | Depends on repo size |
| Embedding generation | ~50-200ms | Per chunk, GPU |
| BLPOP idle cycle | 30s | Upstash quota-safe |

---

## Related Documentation

- [Architecture Overview](architecture/overview.md)
- [Ingestion Pipeline](../notebooklm/04_INGESTION_AND_SEARCH.md)
- [Deployment Guide](deployment/render.md)
- [Troubleshooting](guides/troubleshooting.md)

---

**Key Takeaway**: The unified worker is a single long-running process that handles all GPU-bound work, serves embeddings via HTTP, and polls two Redis queues with one BLPOP. The 30-second timeout is carefully tuned to stay under Upstash's free-tier quota.
