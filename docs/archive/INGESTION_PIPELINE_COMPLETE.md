# Complete Ingestion Pipeline Documentation

## Overview

This document traces the ENTIRE automatic pipeline from calling the ingestion endpoint to having fully embedded, searchable chunks in the database.

---

## Pipeline 1: GitHub Repository Ingestion (Hybrid Storage)

### Entry Point
```bash
POST https://pharos-cloud-api.onrender.com/api/v1/ingestion/ingest/github.com/langchain-ai/langchain
Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74
```

### Step-by-Step Flow

#### 1. API Endpoint Receives Request
**File**: `backend/app/routers/ingestion.py`
**Function**: `ingest_github_repo()`

```python
@router.post("/ingest/{repo_path:path}")
async def ingest_github_repo(
    repo_path: str,
    force_reingest: bool = False,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
):
    # Validates repo URL
    # Checks if already ingested (unless force_reingest=true)
    # Queues ingestion task
```

**What it does**:
- Parses `github.com/langchain-ai/langchain` into owner/repo
- Checks if repo already exists in database
- If `force_reingest=true`, deletes existing resources
- Queues ingestion job to Redis queue `ingest_queue`

**Output**: Returns `{"status": "queued", "repo_id": "uuid"}`

---

#### 2. Repo Worker Picks Up Task
**File**: `backend/app/workers/repo.py`
**Function**: `main()` → polls `ingest_queue`

```python
def main():
    while True:
        # Poll Redis queue: ingest_queue
        task = redis.lpop("ingest_queue")
        if task:
            process_repo_ingestion(task)
        time.sleep(2)
```

**What it does**:
- Polls `ingest_queue` every 2 seconds
- Picks up ingestion task
- Calls `HybridIngestionPipeline.ingest_github_repo()`

---

#### 3. Hybrid Ingestion Pipeline Executes
**File**: `backend/app/modules/ingestion/ast_pipeline.py`
**Class**: `HybridIngestionPipeline`
**Function**: `ingest_github_repo()`

```python
async def ingest_github_repo(
    self,
    git_url: str,
    branch: str = "main",
    file_extensions: tuple[str, ...] = (".py", ".js", ".ts", ...),
    batch_size: int = 50,
) -> IngestionResult:
    # 1. Clone repo to temp directory
    # 2. Parse .gitignore
    # 3. Walk file tree
    # 4. For each code file:
    #    a. Create Resource row (metadata only, NO code content)
    #    b. Parse AST (Python only for now)
    #    c. Extract symbols (functions, classes, methods)
    #    d. Create DocumentChunk for each symbol with:
    #       - github_uri (raw.githubusercontent.com URL)
    #       - branch_reference (commit SHA)
    #       - start_line / end_line
    #       - semantic_summary (signature + docstring)
    #       - NO embedding yet (embedding=None)
    # 5. Batch commit to database (50 chunks at a time)
    # 6. Emit events for each resource
```

**What gets stored in PostgreSQL**:

**Resource Table**:
```sql
INSERT INTO resources (
    id,
    title,  -- file path
    description,  -- JSON with repo_id, file_path, imports, functions, classes
    type,  -- "code"
    format,  -- "text/x-python"
    identifier,  -- "repo:uuid:file_path"
    source,  -- "github.com/owner/repo/blob/main/file.py"
    url,  -- same as source
    ingestion_status,  -- "pending"
    created_at,
    updated_at
)
```

**DocumentChunk Table** (one per function/class/method):
```sql
INSERT INTO document_chunks (
    id,
    resource_id,  -- FK to resources
    content,  -- semantic_summary (NOT full code)
    chunk_index,  -- 0, 1, 2, ...
    chunk_metadata,  -- JSON with github_uri, branch_reference, start_line, end_line, ast_node_type, symbol_name
    embedding,  -- NULL (not generated yet)
    created_at
)
```

**Example semantic_summary** (what gets embedded):
```
[python] def authenticate_user(username: str, password: str) -> User:
    'Authenticate a user with credentials.'
    deps: [verify_password, db.query, User]
```

**What does NOT get stored**:
- ❌ Raw source code content
- ❌ Full file bodies
- ❌ Binary artifacts

---

#### 4. Events Emitted After Ingestion
**File**: `backend/app/modules/ingestion/ast_pipeline.py`

For each resource created:
```python
await event_bus.emit(Event(
    type="resource.created",
    data={
        "resource_id": str(resource.id),
        "resource_type": "code",
        "source": "github",
    }
))
```

For each batch of chunks created:
```python
await event_bus.emit(Event(
    type="resource.chunked",
    data={
        "resource_id": str(resource.id),
        "chunk_count": len(chunks),
        "strategy": "ast",
    }
))
```

---

#### 5. Event Handler: Queue Embedding Tasks
**File**: `backend/app/modules/resources/handlers.py`
**Function**: `handle_resource_chunked()`

```python
@event_bus.on("resource.chunked")
def handle_resource_chunked(event: Event):
    resource_id = event.data["resource_id"]
    chunk_count = event.data["chunk_count"]
    
    # Fetch all chunks for this resource
    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.resource_id == resource_id,
        DocumentChunk.embedding == None  # Only chunks without embeddings
    ).all()
    
    # Queue embedding task to Redis for EACH chunk
    for chunk in chunks:
        task = {
            "task_id": str(uuid.uuid4()),
            "resource_id": str(chunk.resource_id),
            "chunk_id": str(chunk.id),
            "content": chunk.content,  # semantic_summary
            "task_type": "embedding",
        }
        redis.rpush("pharos:tasks", json.dumps(task))
    
    logger.info(f"Queued {len(chunks)} embedding tasks for resource {resource_id}")
```

**What it does**:
- Listens for `resource.chunked` event
- Fetches all chunks without embeddings
- Queues embedding task to Redis `pharos:tasks` queue
- One task per chunk

---

#### 6. Edge Worker Picks Up Embedding Tasks
**File**: `backend/app/workers/edge.py`
**Function**: `main()` → polls `pharos:tasks`

```python
async def main():
    # Load embedding model on GPU
    embedding_service = EmbeddingService(device="cuda")
    
    while True:
        # Poll Redis queue: pharos:tasks
        task_json = await redis.lpop("pharos:tasks")
        if task_json:
            task = json.loads(task_json)
            await process_embedding_task(task, embedding_service)
        await asyncio.sleep(2)
```

**What it does**:
- Polls `pharos:tasks` every 2 seconds
- Picks up embedding task
- Generates embedding using local GPU
- Updates chunk in database with embedding

---

#### 7. Generate Embedding and Update Database
**File**: `backend/app/workers/edge.py`
**Function**: `process_embedding_task()`

```python
async def process_embedding_task(task: dict, embedding_service: EmbeddingService):
    chunk_id = task["chunk_id"]
    content = task["content"]  # semantic_summary
    
    # Generate embedding on GPU
    embedding = embedding_service.generate_embedding(content)
    # Returns: numpy array of shape (768,) for nomic-embed-text-v1
    
    # Update chunk in database
    async with get_async_db() as db:
        chunk = await db.get(DocumentChunk, chunk_id)
        chunk.embedding = embedding.tolist()  # Convert to list for JSON storage
        await db.commit()
    
    logger.info(f"Generated embedding for chunk {chunk_id}")
    
    # Emit event
    await event_bus.emit(Event(
        type="chunk.embedded",
        data={
            "chunk_id": chunk_id,
            "resource_id": task["resource_id"],
        }
    ))
```

**What gets updated in PostgreSQL**:
```sql
UPDATE document_chunks
SET embedding = '[0.123, -0.456, 0.789, ...]'  -- 768-dimensional vector
WHERE id = 'chunk_id';
```

---

#### 8. Update Resource Ingestion Status
**File**: `backend/app/modules/resources/handlers.py`
**Function**: `handle_chunk_embedded()`

```python
@event_bus.on("chunk.embedded")
async def handle_chunk_embedded(event: Event):
    resource_id = event.data["resource_id"]
    
    # Check if all chunks have embeddings
    pending_chunks = db.query(DocumentChunk).filter(
        DocumentChunk.resource_id == resource_id,
        DocumentChunk.embedding == None
    ).count()
    
    if pending_chunks == 0:
        # All chunks embedded, mark resource as complete
        resource = db.get(Resource, resource_id)
        resource.ingestion_status = "completed"
        resource.ingestion_completed_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Resource {resource_id} ingestion completed")
        
        # Emit completion event
        await event_bus.emit(Event(
            type="resource.ingestion_completed",
            data={"resource_id": resource_id}
        ))
```

---

### Complete GitHub Ingestion Flow Summary

```
1. POST /api/v1/ingestion/ingest/github.com/owner/repo
   ↓
2. Queue task to Redis: ingest_queue
   ↓
3. Repo Worker polls ingest_queue
   ↓
4. HybridIngestionPipeline.ingest_github_repo()
   - Clone repo
   - Parse AST
   - Create Resource rows (metadata only)
   - Create DocumentChunk rows (semantic_summary, NO embedding)
   - Emit resource.created events
   - Emit resource.chunked events
   ↓
5. Event Handler: handle_resource_chunked()
   - Queue embedding tasks to Redis: pharos:tasks
   - One task per chunk
   ↓
6. Edge Worker polls pharos:tasks
   ↓
7. Generate embeddings on GPU
   - Update DocumentChunk.embedding
   - Emit chunk.embedded events
   ↓
8. Event Handler: handle_chunk_embedded()
   - Check if all chunks embedded
   - Update Resource.ingestion_status = "completed"
   - Emit resource.ingestion_completed event
   ↓
9. DONE: Resource fully ingested, chunked, and embedded
   - Searchable via /api/search/advanced
```

---

## Pipeline 2: Solo Repository Ingestion (Local Upload)

### Entry Point
```bash
POST https://pharos-cloud-api.onrender.com/api/resources/upload
Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74
Content-Type: multipart/form-data

file: <zip file of repository>
title: "My Local Repo"
type: "code"
```

### Step-by-Step Flow

#### 1. API Endpoint Receives Upload
**File**: `backend/app/modules/resources/router.py`
**Function**: `upload_resource()`

```python
@router.post("/upload")
async def upload_resource(
    file: UploadFile,
    title: str,
    type: str = "code",
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_sync_db),
):
    # 1. Save uploaded file to temp directory
    # 2. Extract if zip/tar
    # 3. Create Resource row
    # 4. Queue ingestion task
```

**What it does**:
- Saves uploaded file to temp directory
- Extracts if archive (zip, tar.gz)
- Creates Resource row with `ingestion_status="pending"`
- Queues ingestion task to Redis `ingest_queue`

---

#### 2. Repo Worker Picks Up Task
**Same as GitHub ingestion** - polls `ingest_queue`

---

#### 3. Local Ingestion Pipeline Executes
**File**: `backend/app/modules/ingestion/ast_pipeline.py`
**Class**: `HybridIngestionPipeline`
**Function**: `ingest_local_repo()`

```python
async def ingest_local_repo(
    self,
    repo_path: Path,
    repo_name: str,
    batch_size: int = 50,
) -> IngestionResult:
    # Same as GitHub ingestion but:
    # - No git clone (already have files)
    # - No github_uri (use local file paths)
    # - branch_reference = "local"
    
    # 1. Walk file tree
    # 2. For each code file:
    #    a. Create Resource row
    #    b. Parse AST
    #    c. Create DocumentChunk rows
    # 3. Emit events
```

**Differences from GitHub ingestion**:
- ✅ No git clone
- ✅ No github_uri (chunks reference local file paths)
- ✅ branch_reference = "local"
- ✅ Code content stored in archive (optional)

---

#### 4-8. Same Event-Driven Flow
**Same as GitHub ingestion**:
- Emit `resource.chunked` events
- Queue embedding tasks to `pharos:tasks`
- Edge worker generates embeddings
- Update chunks with embeddings
- Mark resource as completed

---

### Complete Solo Ingestion Flow Summary

```
1. POST /api/resources/upload (multipart/form-data)
   ↓
2. Save file to temp directory
   ↓
3. Create Resource row (ingestion_status="pending")
   ↓
4. Queue task to Redis: ingest_queue
   ↓
5. Repo Worker polls ingest_queue
   ↓
6. HybridIngestionPipeline.ingest_local_repo()
   - Walk file tree
   - Parse AST
   - Create Resource rows
   - Create DocumentChunk rows (NO embedding)
   - Emit resource.chunked events
   ↓
7. Event Handler: handle_resource_chunked()
   - Queue embedding tasks to Redis: pharos:tasks
   ↓
8. Edge Worker generates embeddings
   ↓
9. Update Resource.ingestion_status = "completed"
   ↓
10. DONE: Resource fully ingested, chunked, and embedded
```

---

## Key Components

### Redis Queues

1. **`ingest_queue`** - Repository ingestion tasks
   - Polled by: Repo Worker (`backend/app/workers/repo.py`)
   - Task format:
     ```json
     {
       "repo_url": "github.com/owner/repo",
       "branch": "main",
       "force_reingest": false
     }
     ```

2. **`pharos:tasks`** - Embedding generation tasks
   - Polled by: Edge Worker (`backend/app/workers/edge.py`)
   - Task format:
     ```json
     {
       "task_id": "uuid",
       "resource_id": "uuid",
       "chunk_id": "uuid",
       "content": "semantic_summary",
       "task_type": "embedding"
     }
     ```

### Event Bus

**Events emitted during ingestion**:

1. `resource.created` - New resource created
2. `resource.chunked` - Resource chunked into DocumentChunks
3. `chunk.embedded` - Chunk embedding generated
4. `resource.ingestion_completed` - All chunks embedded

**Event handlers**:

1. `handle_resource_chunked()` - Queues embedding tasks
2. `handle_chunk_embedded()` - Updates ingestion status

### Workers

1. **Repo Worker** (`backend/app/workers/repo.py`)
   - Polls: `ingest_queue`
   - Does: Clone repo, parse AST, create resources/chunks
   - Runs: Cloud API (Render) or locally

2. **Edge Worker** (`backend/app/workers/edge.py`)
   - Polls: `pharos:tasks`
   - Does: Generate embeddings on GPU
   - Runs: Locally (requires GPU)

---

## Current Issues

### Issue 1: Task Format Mismatch
**Problem**: Edge worker expects `resource_id` field but task has different format

**Error**:
```
Task e97f1679-6c48-4017-9b9d-ee789fc35bff missing resource_id
```

**Root Cause**: Event handler queuing tasks with wrong format

**Fix**: Update `handle_resource_chunked()` to use correct task format

---

### Issue 2: Redis Key Type Error
**Problem**: `WRONGTYPE Operation against a key holding the wrong kind of value`

**Root Cause**: Redis key `ingest_queue` or `pharos:tasks` has wrong data type (not a list)

**Fix**: Clear Redis keys and restart workers
```bash
redis-cli DEL ingest_queue pharos:tasks
```

---

### Issue 3: Chunks Not Created During Ingestion
**Problem**: Resources created but chunks are empty

**Root Cause**: AST parsing only works for Python files, other languages skipped

**Fix**: Implement AST parsers for JavaScript, TypeScript, etc.

---

## Testing the Pipeline

### Test GitHub Ingestion
```bash
# 1. Start edge worker
cd backend
python worker.py edge

# 2. Trigger ingestion
curl -X POST "https://pharos-cloud-api.onrender.com/api/v1/ingestion/ingest/github.com/langchain-ai/langchain?force_reingest=true" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74"

# 3. Monitor edge worker logs
# Should see:
# - "Received task: <task_id>"
# - "Generated embedding for chunk <chunk_id>"
# - "Resource <resource_id> ingestion completed"

# 4. Test search
curl -X POST "https://pharos-cloud-api.onrender.com/api/search/advanced" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "message translator",
    "strategy": "parent-child",
    "top_k": 5,
    "include_code": true
  }'

# Should return results with code chunks
```

### Test Solo Ingestion
```bash
# 1. Create test repo zip
cd /tmp
mkdir test-repo
cd test-repo
echo "def hello(): print('hello')" > main.py
zip -r ../test-repo.zip .

# 2. Upload
curl -X POST "https://pharos-cloud-api.onrender.com/api/resources/upload" \
  -H "Authorization: Bearer 4bad61a35f5d570014f9fa2a74ac51c19a35e9185c6f1e2987f96e49eefd3c74" \
  -F "file=@/tmp/test-repo.zip" \
  -F "title=Test Repo" \
  -F "type=code"

# 3. Monitor edge worker logs
# 4. Test search
```

---

## Files to Check

### Ingestion Entry Points
- `backend/app/routers/ingestion.py` - GitHub ingestion endpoint
- `backend/app/modules/resources/router.py` - Solo upload endpoint

### Workers
- `backend/app/workers/repo.py` - Repository ingestion worker
- `backend/app/workers/edge.py` - Embedding generation worker

### Pipeline
- `backend/app/modules/ingestion/ast_pipeline.py` - AST parsing and chunking

### Event Handlers
- `backend/app/modules/resources/handlers.py` - Chunking and embedding handlers

### Services
- `backend/app/shared/embeddings.py` - Embedding generation
- `backend/app/shared/upstash_redis.py` - Redis queue management

---

## Expected Timeline

For LangChain repository (3,302 files):

1. **Ingestion** (Repo Worker): ~5-10 minutes
   - Clone repo
   - Parse AST for all Python files
   - Create 3,302 Resource rows
   - Create ~50,000 DocumentChunk rows (estimate)

2. **Embedding** (Edge Worker): ~2-4 hours
   - Generate embeddings for 50,000 chunks
   - ~0.3s per chunk on GPU
   - Batch processing: 10 chunks at a time

3. **Total**: ~2-4 hours for complete ingestion

---

## Monitoring

### Check Ingestion Progress
```bash
# Count resources
curl "https://pharos-cloud-api.onrender.com/api/resources?limit=1" | jq '.total'

# Count chunks
curl "https://pharos-cloud-api.onrender.com/api/resources/<resource_id>/chunks" | jq '.total'

# Check ingestion status
curl "https://pharos-cloud-api.onrender.com/api/resources/<resource_id>" | jq '.ingestion_status'
```

### Check Queue Sizes
```bash
# Redis CLI
redis-cli LLEN ingest_queue
redis-cli LLEN pharos:tasks
```

### Check Worker Logs
```bash
# Edge worker
tail -f backend/edge_worker.log

# Repo worker
tail -f backend/repo_worker.log
```

---

## Summary

**The pipeline is FULLY AUTOMATIC**:
1. Call ingestion endpoint
2. Workers poll queues
3. Resources created
4. Chunks created
5. Embeddings generated
6. Search works

**No manual intervention needed** - just call the endpoint and wait.

**Current blocker**: Task format mismatch between event handler and edge worker.
