# Prompt for Claude Opus: Build Complete GitHub Ingestion Pipeline & Test with LangChain

## Context

The Pharos codebase has a PARTIAL ingestion pipeline. Your job is to:
1. **Create the missing repo worker** to connect AST pipeline to edge worker
2. **Test end-to-end** with LangChain repository (github.com/langchain-ai/langchain)
3. **Verify search works** after ingestion completes

## Goal: The Ideal Pipeline

When finished, this should work:

```bash
# 1. Call ingestion endpoint
POST https://pharos-cloud-api.onrender.com/api/v1/ingestion/ingest/github.com/langchain-ai/langchain

# 2. Automatic pipeline executes:
#    Cloud API: AST parsing (lightweight, no GPU)
#      - Clone repo
#      - Parse AST for Python files
#      - Create Resource rows (metadata only, NO code content)
#      - Create DocumentChunk rows (semantic_summary, github_uri, NO embedding)
#      - Queue to pharos:tasks
#    
#    Edge Worker: ML processing (GPU required)
#      - Fetch code from GitHub using github_uri
#      - Generate embeddings (GPU)
#      - Create graph entities
#      - Compute quality scores
#      - Mark ingestion_status="completed"

# 3. Search works
POST /api/search/advanced
{"query": "message translator", "strategy": "parent-child", "top_k": 5}
# Returns: Relevant code chunks from LangChain
```

**Timeline**: 2-4 hours for 3,302 files (automatic, no manual intervention)

---

## Phase 1: Understand Current State (30 minutes)

### What EXISTS and works:

1. **Edge Worker** (`backend/app/workers/edge.py`)
   - ✅ Polls `pharos:tasks` queue
   - ✅ Expects: `{"task_id": "uuid", "resource_id": "uuid"}`
   - ✅ Calls `process_ingestion(resource_id)` for each task
   - ✅ Runs on local GPU
   - ✅ Generates embeddings, creates graph, computes quality

2. **process_ingestion()** (`backend/app/modules/resources/service.py` line 439+)
   - ✅ Fetches URL content (or GitHub code)
   - ✅ Extracts text
   - ✅ Generates AI summary/tags
   - ✅ Archives content
   - ✅ **Chunks content automatically** (ChunkingService)
   - ✅ **Generates embeddings** (GPU required)
   - ✅ Computes quality scores
   - ✅ Creates graph entities
   - ✅ Marks ingestion_status="completed"

3. **AST Pipeline** (`backend/app/modules/ingestion/ast_pipeline.py`)
   - ✅ `HybridIngestionPipeline` class exists
   - ✅ `ingest_github_repo()` method clones and parses repos
   - ✅ Creates Resource + DocumentChunk rows (metadata only, NO embeddings)
   - ✅ Stores github_uri in chunk metadata for later code fetching
   - ❌ **NOT CONNECTED** to any worker

4. **Ingestion Router** (`backend/app/routers/ingestion.py`)
   - ✅ POST `/api/v1/ingestion/ingest/{repo_url}` endpoint exists
   - ✅ Validates repo URL
   - ✅ Queues to `ingest_queue`
   - ❌ **NO WORKER** polls `ingest_queue`

### What's MISSING:

1. **Repo Worker** (`backend/app/workers/repo.py`) - DOES NOT EXIST
   - Should poll `ingest_queue`
   - Should call `HybridIngestionPipeline.ingest_github_repo()`
   - Should queue resources to `pharos:tasks` for edge worker

### Current LangChain Status:

```bash
# Check current state
curl "https://pharos-cloud-api.onrender.com/api/resources?limit=1" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74"
# Shows: 3,302 resources with ingestion_status="pending"

# Try search
curl -X POST "https://pharos-cloud-api.onrender.com/api/search/advanced" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74" \
  -H "Content-Type: application/json" \
  -d '{"query": "message translator", "strategy": "parent-child", "top_k": 5}'
# Returns: No results (no chunks/embeddings)
```

**Problem**: Resources exist but `process_ingestion()` was never called, so no embeddings or graph.

---

## Phase 2: Architecture Understanding (CRITICAL)

### Why We Need TWO Workers:

**Repo Worker (Cloud API - Render)**:
- Lightweight AST parsing (no GPU needed)
- Clones repo temporarily
- Parses Python files
- Creates Resource rows (metadata: file_path, imports, functions, classes)
- Creates DocumentChunk rows (semantic_summary, github_uri, start_line, end_line)
- **NO embeddings generated** (no GPU on cloud)
- **NO code content stored** (only metadata)
- Queues each resource to `pharos:tasks`
- Deletes cloned repo

**Edge Worker (Local GPU)**:
- Heavy ML processing (requires GPU)
- Polls `pharos:tasks`
- For each resource:
  * Fetches code from GitHub using github_uri in chunk metadata
  * Generates embeddings (GPU required)
  * Creates graph entities
  * Computes quality scores
  * Marks ingestion_status="completed"

### Why Can't We Run Everything on Cloud?

❌ **Cloud API (Render) limitations**:
- No GPU available
- CPU embedding generation is 100x slower
- 30-second request timeout
- Would fail for large repos

✅ **Must use edge worker for embeddings**:
- Has GPU (NVIDIA RTX 4070)
- Fast embedding generation (~0.3s per chunk)
- No timeout limits
- Can process 3,302 files in 2-4 hours

### The Required Flow:

```
1. POST /api/v1/ingestion/ingest/github.com/langchain-ai/langchain
   ↓
2. Ingestion router queues to ingest_queue
   ↓
3. Repo Worker (NEW - YOU MUST CREATE THIS) polls ingest_queue
   ↓
4. Repo Worker calls HybridIngestionPipeline.ingest_github_repo()
   - Clones repo to /tmp
   - Parses AST for all .py files
   - Creates Resource rows (metadata only)
   - Creates DocumentChunk rows (semantic_summary, github_uri, NO embedding)
   - Returns list of resource IDs
   ↓
5. Repo Worker queues each resource to pharos:tasks
   Task format: {"task_id": "uuid", "resource_id": "uuid"}
   ↓
6. Edge Worker polls pharos:tasks
   ↓
7. Edge Worker calls process_ingestion(resource_id)
   - Fetches code from GitHub (using github_uri from chunk metadata)
   - Generates embeddings (GPU)
   - Creates graph entities
   - Computes quality
   - Marks ingestion_status="completed"
   ↓
8. DONE - Resource fully ingested, chunked, embedded, searchable
```

---

## Phase 3: Implement Repo Worker (1-2 hours)

### Step 1: Create backend/app/workers/repo.py

```python
"""
Pharos Repo Worker - GitHub Repository Ingestion

This worker polls Upstash Redis for repository ingestion tasks and processes them
using the HybridIngestionPipeline. It runs on the cloud API (Render) and handles
lightweight AST parsing, then queues resources to the edge worker for GPU-based
embedding generation.

Usage:
    python worker.py repo

Environment Variables:
    UPSTASH_REDIS_REST_URL (required)
    UPSTASH_REDIS_REST_TOKEN (required)
    DATABASE_URL (required)
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("repo_worker.log"),
    ],
)
logger = logging.getLogger(__name__)


def check_environment():
    """Validate required environment variables."""
    required_vars = [
        "UPSTASH_REDIS_REST_URL",
        "UPSTASH_REDIS_REST_TOKEN",
        "DATABASE_URL",
    ]

    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)

    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        logger.error("Please set these variables before starting the repo worker.")
        sys.exit(1)

    logger.info("Environment variables validated")


async def process_repo_task(task: dict, redis_client, db_session):
    """Process a single repository ingestion task."""
    repo_url = task.get("repo_url")
    job_id = task.get("job_id", "unknown")
    
    if not repo_url:
        logger.error(f"Task {job_id} missing repo_url")
        return False
    
    logger.info(f"Processing repository: {repo_url}")
    start_time = time.time()
    
    try:
        # Import pipeline
        from app.modules.ingestion.ast_pipeline import HybridIngestionPipeline
        
        # Create pipeline
        pipeline = HybridIngestionPipeline(db_session)
        
        # Ingest repository
        logger.info(f"Starting AST ingestion for {repo_url}")
        result = await pipeline.ingest_github_repo(
            git_url=f"https://{repo_url}",
            branch="main"
        )
        
        logger.info(
            f"AST ingestion completed: {result.resources_created} resources, "
            f"{result.chunks_created} chunks created"
        )
        
        # Queue each resource to pharos:tasks for edge worker
        logger.info(f"Queuing {result.resources_created} resources to pharos:tasks")
        
        from app.shared.upstash_redis import UpstashRedisClient
        edge_redis = UpstashRedisClient()
        
        try:
            for resource_id in result.resource_ids:
                task_data = {
                    "task_id": str(uuid.uuid4()),
                    "resource_id": str(resource_id)
                }
                await edge_redis.push_task(task_data)
            
            logger.info(f"Successfully queued {len(result.resource_ids)} resources")
        finally:
            await edge_redis.close()
        
        elapsed = time.time() - start_time
        logger.info(f"Repository ingestion completed in {elapsed:.1f}s")
        
        return True
    
    except Exception as e:
        logger.error(f"Repository ingestion failed for {repo_url}: {e}", exc_info=True)
        return False


async def poll_and_process():
    """Poll Redis for repository ingestion tasks and process them."""
    from app.shared.upstash_redis import UpstashRedisClient
    from app.shared.database import get_async_db
    
    redis_client = UpstashRedisClient()
    poll_interval = int(os.getenv("WORKER_POLL_INTERVAL", "2"))
    
    logger.info(f"Starting task polling (interval: {poll_interval}s)")
    logger.info("Press Ctrl+C to stop")
    
    processed = 0
    failed = 0
    
    try:
        while True:
            try:
                # Poll ingest_queue
                task_json = await redis_client._execute(["LPOP", "ingest_queue"])
                
                if task_json:
                    try:
                        task = json.loads(task_json)
                        logger.info(f"Received task: {task.get('repo_url', 'unknown')}")
                        
                        # Get database session
                        async with get_async_db() as db:
                            success = await process_repo_task(task, redis_client, db)
                            
                            if success:
                                processed += 1
                                logger.info(f"Task completed (total: {processed} processed, {failed} failed)")
                            else:
                                failed += 1
                                logger.error(f"Task failed (total: {processed} processed, {failed} failed)")
                    
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid task JSON: {e}")
                        failed += 1
                    except Exception as e:
                        logger.error(f"Error processing task: {e}", exc_info=True)
                        failed += 1
                
                # Sleep before next poll
                await asyncio.sleep(poll_interval)
            
            except Exception as e:
                logger.error(f"Error in polling loop: {e}", exc_info=True)
                await asyncio.sleep(poll_interval)
    
    finally:
        await redis_client.close()
        logger.info(f"Repo worker stopped (processed: {processed}, failed: {failed})")


async def main():
    """Main entry point for repo worker."""
    logger.info("============================================================")
    logger.info("Pharos Repo Worker - GitHub Repository Ingestion")
    logger.info("============================================================")
    
    # Check environment
    check_environment()
    
    # Connect to database
    logger.info("Connecting to database...")
    from app.shared.database import init_db
    init_db()
    logger.info("Connected to database")
    
    # Start polling
    logger.info("============================================================")
    logger.info("Repo worker ready - waiting for tasks...")
    logger.info("============================================================")
    
    await poll_and_process()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Repo worker stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
```

### Step 2: Update worker.py dispatcher

Edit `backend/worker.py` to add repo worker:

```python
def main():
    parser = argparse.ArgumentParser(
        prog="worker.py",
        description="Pharos worker dispatcher",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    subparsers.add_parser(
        "edge",
        help="Run the edge ingestion worker (GPU, polls pharos:tasks queue)",
    )
    subparsers.add_parser(
        "repo",
        help="Run the GitHub repository ingestion worker (polls ingest_queue)",
    )

    args = parser.parse_args()

    if args.command == "edge":
        import asyncio
        from app.workers.edge import main as edge_main
        try:
            asyncio.run(edge_main())
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception as e:
            print(f"[ERROR] Fatal error: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "repo":
        import asyncio
        from app.workers.repo import main as repo_main
        try:
            asyncio.run(repo_main())
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception as e:
            print(f"[ERROR] Fatal error: {e}", file=sys.stderr)
            sys.exit(1)
```

### Step 3: Update HybridIngestionPipeline to return resource IDs

Edit `backend/app/modules/ingestion/ast_pipeline.py`:

```python
@dataclass
class IngestionResult:
    """Aggregate statistics returned after a repository is ingested."""
    repo_url: str
    branch: str
    commit_sha: str
    resources_created: int = 0
    chunks_created: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    ingestion_time_seconds: float = 0.0
    estimated_storage_saved_bytes: int = 0
    resource_ids: list[str] = field(default_factory=list)  # ADD THIS
    errors: list[dict[str, str]] = field(default_factory=list)
```

In `ingest_github_repo()` method, collect resource IDs:

```python
# After creating resource
resource = Resource(...)
self.db.add(resource)
await self.db.flush()

result.resource_ids.append(str(resource.id))  # ADD THIS
result.resources_created += 1
```

---

## Phase 4: Test with Small Repo (30 minutes)

### Step 1: Start Both Workers

```bash
# Terminal 1: Start edge worker
cd backend
python worker.py edge

# Terminal 2: Start repo worker
cd backend
python worker.py repo
```

### Step 2: Trigger Small Repo Ingestion

```bash
# Test with psf/requests (small repo, ~50 files)
curl -X POST "https://pharos-cloud-api.onrender.com/api/v1/ingestion/ingest/github.com/psf/requests" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74"
```

### Step 3: Monitor Both Workers

```bash
# Terminal 3: Watch repo worker logs
tail -f backend/repo_worker.log

# Terminal 4: Watch edge worker logs
tail -f backend/edge_worker.log
```

### Step 4: Verify Results

```bash
# Check resources created
curl "https://pharos-cloud-api.onrender.com/api/resources?limit=5" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74"

# Check chunks created
curl "https://pharos-cloud-api.onrender.com/api/resources/{resource_id}/chunks" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74"

# Test search
curl -X POST "https://pharos-cloud-api.onrender.com/api/search/advanced" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74" \
  -H "Content-Type: application/json" \
  -d '{"query": "http request", "strategy": "parent-child", "top_k": 5}'
```

---

## Phase 5: Test with LangChain (2-4 hours)

### Step 1: Clear Existing Data (Optional)

```bash
# If you want to start fresh, delete existing LangChain resources
# Or use force_reingest=true
```

### Step 2: Trigger LangChain Ingestion

```bash
curl -X POST "https://pharos-cloud-api.onrender.com/api/v1/ingestion/ingest/github.com/langchain-ai/langchain?force_reingest=true" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74"
```

### Step 3: Monitor Progress

```bash
# Watch repo worker (AST parsing)
tail -f backend/repo_worker.log
# Should show: "AST ingestion completed: 3302 resources, ~50000 chunks"

# Watch edge worker (embedding generation)
tail -f backend/edge_worker.log
# Should show: "Generated embedding for chunk {id}" repeatedly

# Check queue size
curl -X POST "$UPSTASH_REDIS_REST_URL" \
  -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '["LLEN","pharos:tasks"]'

# Check resources
curl "https://pharos-cloud-api.onrender.com/api/resources?limit=1" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74" \
  | jq '.total'

# Check ingestion status
curl "https://pharos-cloud-api.onrender.com/api/resources?limit=10" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74" \
  | jq '.items[] | {title, ingestion_status}'
```

### Step 4: Verify Search Works (After 2-4 hours)

```bash
# Test semantic search
curl -X POST "https://pharos-cloud-api.onrender.com/api/search/advanced" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "message translator",
    "strategy": "parent-child",
    "top_k": 5,
    "include_code": true
  }'

# Should return: Code chunks from LangChain with message translator functionality

# Test another query
curl -X POST "https://pharos-cloud-api.onrender.com/api/search/advanced" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "openai chat completion",
    "strategy": "parent-child",
    "top_k": 5,
    "include_code": true
  }'

# Should return: OpenAI integration code from LangChain
```

---

## Phase 6: Document Results (30 minutes)

Create these documents:

### 1. IMPLEMENTATION.md
- What you created (repo worker)
- How it connects AST pipeline to edge worker
- Code snippets of key changes
- Any issues encountered and solutions

### 2. PIPELINE_FLOW.md
- Complete flow diagram from endpoint to search
- Exact function calls at each step
- Queue names and formats
- Timeline for LangChain (expected vs actual)

### 3. TEST_RESULTS.md
- Small repo test results (psf/requests)
- LangChain test results
- Search query results (with actual responses)
- Performance metrics (time, resources, chunks, embeddings)

### 4. TROUBLESHOOTING.md
- Common issues and solutions
- How to monitor progress
- How to debug failures
- How to restart if needed

---

## Success Criteria

After your implementation, these should ALL work:

1. ✅ **Ingestion Endpoint**
   ```bash
   POST /api/v1/ingestion/ingest/github.com/langchain-ai/langchain
   # Returns: {"status": "dispatched", "job_id": 12345}
   ```

2. ✅ **Repo Worker Processes Task**
   ```bash
   # repo_worker.log shows:
   # "Processing repository: github.com/langchain-ai/langchain"
   # "AST ingestion completed: 3302 resources, 50000 chunks"
   # "Queued 3302 resources to pharos:tasks"
   ```

3. ✅ **Edge Worker Processes Resources**
   ```bash
   # edge_worker.log shows:
   # "Processing task ... for resource ..."
   # "Generated embedding for chunk ..."
   # "Resource ... ingestion completed"
   ```

4. ✅ **Search Works**
   ```bash
   POST /api/search/advanced {"query": "message translator"}
   # Returns: Relevant code chunks from LangChain
   ```

5. ✅ **Complete Pipeline**
   - Repo worker: ~10 minutes (AST parsing)
   - Edge worker: ~2-4 hours (embedding generation)
   - Total: ~2-4 hours for 3,302 files
   - No manual intervention required
   - All resources marked ingestion_status="completed"

---

## Key Files Reference

### Files You'll Create
- `backend/app/workers/repo.py` - NEW repo worker

### Files You'll Modify
- `backend/worker.py` - Add repo worker to dispatcher
- `backend/app/modules/ingestion/ast_pipeline.py` - Add resource_ids to IngestionResult

### Files You'll Read (Don't Modify)
- `backend/app/workers/edge.py` - Understand edge worker behavior
- `backend/app/modules/resources/service.py` - Understand process_ingestion()
- `backend/app/routers/ingestion.py` - Understand ingestion endpoint
- `backend/app/shared/upstash_redis.py` - Understand queue operations

---

## Important Notes

### Do's:
- ✅ Create repo worker that polls `ingest_queue`
- ✅ Test with small repo first (psf/requests)
- ✅ Monitor both workers continuously
- ✅ Verify each step works before moving to next
- ✅ Document actual timings and metrics
- ✅ Show actual curl responses in documentation

### Don'ts:
- ❌ Don't run embeddings on cloud API (no GPU)
- ❌ Don't test LangChain first (too big, too slow)
- ❌ Don't assume code works without testing
- ❌ Don't skip documentation
- ❌ Don't modify process_ingestion() (it works fine)
- ❌ Don't modify edge worker (it works fine)

---

## Timeline Estimate

- Phase 1 (Understand): 30 minutes
- Phase 2 (Architecture): 30 minutes
- Phase 3 (Implement): 1-2 hours
- Phase 4 (Test small repo): 30 minutes
- Phase 5 (Test LangChain): 2-4 hours (mostly waiting)
- Phase 6 (Document): 30 minutes

**Total**: 5-8 hours (including LangChain ingestion time)

---

## Starting Checklist

Before you begin:
- [ ] Read `backend/app/routers/ingestion.py` completely
- [ ] Read `backend/app/workers/edge.py` completely
- [ ] Read `backend/app/modules/ingestion/ast_pipeline.py` completely
- [ ] Understand what `process_ingestion()` does
- [ ] Verify edge worker is running locally
- [ ] Verify cloud API is accessible
- [ ] Have admin token ready

---

**Now begin Phase 1: Read the code and understand what exists. Then create the repo worker in Phase 3.**
