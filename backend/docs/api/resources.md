# Resources API

Resource management endpoints for content ingestion, retrieval, and curation.

## Overview

The Resources API provides CRUD operations for managing knowledge resources. Resources are the core content units in Pharos, representing articles, papers, documents, and other knowledge artifacts.

## Endpoints

### POST /resources

Creates a new resource by ingesting content from a URL with AI-powered asynchronous processing.

**Request Body:**
```json
{
  "url": "string (required)",
  "title": "string (optional)",
  "description": "string (optional)",
  "creator": "string (optional)",
  "language": "string (optional)",
  "type": "string (optional)",
  "source": "string (optional)"
}
```

**Response (202 Accepted):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "title": "Resource Title",
  "ingestion_status": "pending"
}
```

**Background Processing:**
1. Fetch content from the provided URL
2. Extract text from HTML/PDF content
3. Generate AI-powered summary using transformers
4. Generate intelligent tags using zero-shot classification
5. Normalize metadata using authority control
6. Classify content using the classification system
7. Calculate quality score
8. Archive content locally
9. Update resource status to "completed" or "failed"

**Example:**
```bash
curl -X POST http://127.0.0.1:8000/resources \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/article"}'
```

---

### GET /resources/{resource_id}/status

Monitor the ingestion status of a resource.

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "ingestion_status": "completed",
  "ingestion_error": null,
  "ingestion_started_at": "2024-01-01T10:00:00Z",
  "ingestion_completed_at": "2024-01-01T10:02:30Z"
}
```

**Status Values:**
- `pending` - Request received, processing not started
- `processing` - Content is being processed
- `completed` - Processing finished successfully
- `failed` - Processing failed with error

---

### GET /resources

List resources with filtering, sorting, and pagination.

**Query Parameters:**

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `q` | string | Keyword search on title/description | - |
| `classification_code` | string | Filter by classification code | - |
| `type` | string | Filter by resource type | - |
| `format` | string | Filter by resource format | - |
| `language` | string | Filter by language | - |
| `read_status` | string | Filter by read status | - |
| `min_quality` | float | Minimum quality score (0.0-1.0) | - |
| `created_from` | datetime | Filter by creation date (ISO 8601) | - |
| `created_to` | datetime | Filter by creation date (ISO 8601) | - |
| `updated_from` | datetime | Filter by update date (ISO 8601) | - |
| `updated_to` | datetime | Filter by update date (ISO 8601) | - |
| `subject_any` | string[] | Filter by any of these subjects | - |
| `subject_all` | string[] | Filter by all of these subjects | - |
| `creator` | string | Filter by creator | - |
| `limit` | integer | Number of results (1-100) | 25 |
| `offset` | integer | Number of results to skip | 0 |
| `sort_by` | string | Sort field | updated_at |
| `sort_dir` | string | Sort direction (asc/desc) | desc |

**Response:**
```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "Machine Learning Fundamentals",
      "description": "Comprehensive guide to ML concepts",
      "creator": "John Doe",
      "publisher": "Tech Publications",
      "source": "https://example.com/ml-guide",
      "language": "en",
      "type": "article",
      "subject": ["Machine Learning", "Artificial Intelligence"],
      "classification_code": "004",
      "quality_score": 0.85,
      "read_status": "unread",
      "created_at": "2024-01-01T10:00:00Z",
      "updated_at": "2024-01-01T10:02:30Z",
      "ingestion_status": "completed"
    }
  ],
  "total": 1
}
```

**Example:**
```bash
curl "http://127.0.0.1:8000/resources?limit=5&classification_code=004&min_quality=0.8"
```

---

### GET /resources/{resource_id}

Retrieve a specific resource by ID.

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Machine Learning Fundamentals",
  "description": "Comprehensive guide to ML concepts",
  "creator": "John Doe",
  "publisher": "Tech Publications",
  "source": "https://example.com/ml-guide",
  "language": "en",
  "type": "article",
  "subject": ["Machine Learning", "Artificial Intelligence"],
  "classification_code": "004",
  "quality_score": 0.85,
  "read_status": "unread",
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-01T10:02:30Z",
  "ingestion_status": "completed"
}
```

---

### PUT /resources/{resource_id}

Update a resource with partial data. Only provided fields are modified.

**Request Body:**
```json
{
  "title": "Updated Title",
  "description": "Updated description",
  "read_status": "in_progress",
  "subject": ["Updated", "Tags"]
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Updated Title",
  "description": "Updated description",
  "read_status": "in_progress",
  "subject": ["Updated", "Tags"],
  "updated_at": "2024-01-01T11:00:00Z"
}
```

---

### DELETE /resources/{resource_id}

Delete a resource by ID.

**Response:** `204 No Content`

---

### PUT /resources/{resource_id}/classify

Override the classification code for a specific resource.

**Request Body:**
```json
{
  "code": "004"
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Resource Title",
  "classification_code": "004",
  "updated_at": "2024-01-01T11:00:00Z"
}
```

---

### POST /resources/{resource_id}/chunks

**Phase 17.5** - Chunk a resource into smaller, searchable pieces.

**Request Body:**
```json
{
  "strategy": "semantic",
  "chunk_size": 512,
  "overlap": 50,
  "parser_type": "text"
}
```

**Parameters:**
- `strategy` (required): Chunking strategy - `semantic` or `fixed`
- `chunk_size` (required): Target chunk size in tokens
- `overlap` (required): Overlap between chunks in tokens
- `parser_type` (optional): Parser type (default: "text")

**Response:**
```json
{
  "resource_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Chunking started",
  "strategy": "semantic",
  "chunk_size": 512,
  "overlap": 50
}
```

**Example:**
```bash
curl -X POST http://127.0.0.1:8000/resources/550e8400-e29b-41d4-a716-446655440000/chunks \
  -H "Content-Type: application/json" \
  -d '{"strategy": "semantic", "chunk_size": 512, "overlap": 50}'
```

---

### GET /resources/{resource_id}/chunks

**Phase 17.5** - List all chunks for a resource.

**Query Parameters:**
- `limit` (optional): Number of results (default: 25)
- `offset` (optional): Number of results to skip (default: 0)

**Response:**
```json
{
  "items": [
    {
      "id": "chunk-uuid-1",
      "resource_id": "550e8400-e29b-41d4-a716-446655440000",
      "content": "Machine learning is a subset of artificial intelligence...",
      "chunk_index": 0,
      "chunk_metadata": {
        "page": 1,
        "coordinates": [100, 200]
      },
      "created_at": "2024-01-01T10:00:00Z"
    }
  ],
  "total": 15
}
```

**Example:**
```bash
curl "http://127.0.0.1:8000/resources/550e8400-e29b-41d4-a716-446655440000/chunks?limit=10"
```

---

### GET /chunks/{chunk_id}

**Phase 17.5** - Retrieve a specific chunk by ID.

**Response:**
```json
{
  "id": "chunk-uuid-1",
  "resource_id": "550e8400-e29b-41d4-a716-446655440000",
  "content": "Machine learning is a subset of artificial intelligence...",
  "chunk_index": 0,
  "chunk_metadata": {
    "page": 1,
    "coordinates": [100, 200]
  },
  "embedding_id": "embedding-uuid-1",
  "created_at": "2024-01-01T10:00:00Z"
}
```

**Example:**
```bash
curl "http://127.0.0.1:8000/chunks/chunk-uuid-1"
```

---

### POST /resources/ingest-repo

**Phase 18** - Ingest a local directory or Git repository for code analysis.

Triggers asynchronous ingestion of code repositories with AST-based chunking and static analysis. Supports local directories and remote Git repositories.

**Request Body:**
```json
{
  "path": "/path/to/local/repo",
  "git_url": "https://github.com/user/repo.git"
}
```

**Parameters:**
- `path` (optional): Absolute path to local directory
- `git_url` (optional): Git repository URL (HTTPS or SSH)
- **Note**: Provide either `path` or `git_url`, not both

**Response (202 Accepted):**
```json
{
  "task_id": "celery-task-uuid",
  "status": "pending",
  "message": "Repository ingestion started"
}
```

**Background Processing:**
1. Clone Git repository (if git_url provided) or scan local directory
2. Parse .gitignore and exclude ignored files
3. Detect binary files and exclude them
4. Classify files by type (PRACTICE for code, THEORY for docs, GOVERNANCE for config)
5. Parse code files using Tree-Sitter AST
6. Chunk code by logical units (functions, classes, methods)
7. Extract static analysis relationships (imports, definitions, calls)
8. Create Resources, DocumentChunks, and GraphRelationships
9. Update task status to "completed" or "failed"

**Supported Languages:**
- Python (.py)
- JavaScript (.js)
- TypeScript (.ts)
- Rust (.rs)
- Go (.go)
- Java (.java)

**Example (Local Directory):**
```bash
curl -X POST http://127.0.0.1:8000/resources/ingest-repo \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"path": "/home/user/my-project"}'
```

**Example (Git Repository):**
```bash
curl -X POST http://127.0.0.1:8000/resources/ingest-repo \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"git_url": "https://github.com/user/repo.git"}'
```

**Rate Limiting:**
- Free tier: 5 ingestions/hour
- Premium tier: 20 ingestions/hour
- Admin tier: Unlimited

**Requirements:** 6.1, 6.3, 6.4, 6.5

---

### GET /resources/ingest-repo/{task_id}/status

**Phase 18** - Check the status of a repository ingestion task.

**Path Parameters:**
- `task_id` (required): Celery task ID returned from POST /resources/ingest-repo

**Response:**
```json
{
  "task_id": "celery-task-uuid",
  "status": "processing",
  "progress": {
    "files_processed": 45,
    "total_files": 100,
    "current_file": "src/main.py"
  },
  "result": null,
  "error": null
}
```

**Status Values:**
- `pending` - Task queued, not started
- `processing` - Ingestion in progress
- `completed` - Ingestion finished successfully
- `failed` - Ingestion failed with error

**Response (Completed):**
```json
{
  "task_id": "celery-task-uuid",
  "status": "completed",
  "progress": {
    "files_processed": 100,
    "total_files": 100,
    "current_file": null
  },
  "result": {
    "resources_created": 100,
    "chunks_created": 1250,
    "relationships_created": 3400,
    "duration_seconds": 45.3
  },
  "error": null
}
```

**Response (Failed):**
```json
{
  "task_id": "celery-task-uuid",
  "status": "failed",
  "progress": {
    "files_processed": 45,
    "total_files": 100,
    "current_file": "src/broken.py"
  },
  "result": null,
  "error": "Failed to parse file: syntax error at line 42"
}
```

**Example:**
```bash
curl "http://127.0.0.1:8000/resources/ingest-repo/celery-task-uuid/status" \
  -H "Authorization: Bearer <token>"
```

**Polling Recommendation:**
- Poll every 2-5 seconds during processing
- Stop polling when status is "completed" or "failed"
- Task results expire after 1 hour

**Requirements:** 6.2, 6.6

---

## Data Models

### Resource Model

The core resource model follows Dublin Core metadata standards with custom extensions:

```json
{
  "id": "uuid",
  "title": "string (required)",
  "description": "string",
  "creator": "string",
  "publisher": "string",
  "contributor": "string",
  "source": "string",
  "language": "string",
  "type": "string",
  "format": "string",
  "identifier": "string",
  "subject": ["string"],
  "relation": ["string"],
  "coverage": "string",
  "rights": "string",
  "classification_code": "string",
  "read_status": "unread|in_progress|completed|archived",
  "quality_score": "float (0.0-1.0)",
  "created_at": "datetime (ISO 8601)",
  "updated_at": "datetime (ISO 8601)",
  "ingestion_status": "pending|processing|completed|failed",
  "ingestion_error": "string",
  "ingestion_started_at": "datetime",
  "ingestion_completed_at": "datetime"
}
```

## Module Structure

The Resources module is implemented as a self-contained vertical slice:

**Module**: `app.modules.resources`  
**Router Prefix**: `/resources`  
**Version**: 1.0.0

```python
from app.modules.resources import (
    resources_router,
    ResourceService,
    ResourceCreate,
    ResourceUpdate,
    ResourceResponse
)
```

### Events

**Emitted Events:**
- `resource.created` - When a new resource is ingested
- `resource.updated` - When resource metadata is updated
- `resource.deleted` - When a resource is removed
- `resource.chunked` - When a resource is chunked (Phase 17.5)

**Subscribed Events:**
- None (Resources is a foundational module)

## Code Intelligence Features (Phase 18)

The Resources module includes code repository ingestion capabilities:

**Repository Ingestion:**
- Local directory scanning with .gitignore support
- Git repository cloning from HTTPS/SSH URLs
- Binary file detection and exclusion
- File classification (PRACTICE, THEORY, GOVERNANCE)

**AST-Based Code Chunking:**
- Tree-Sitter parsing for 6 languages (Python, JS, TS, Rust, Go, Java)
- Logical unit extraction (functions, classes, methods)
- Chunk metadata includes: function_name, class_name, start_line, end_line, language
- Fallback to character-based chunking on parse errors

**Static Analysis:**
- Import statement extraction
- Function/class definition detection
- Basic function call detection
- Graph relationships: IMPORTS, DEFINES, CALLS
- Relationship metadata: source_file, target_symbol, line_number, confidence

**Performance:**
- AST parsing: <2s per file (P95)
- Static analysis: <1s per file (P95)
- Batch processing: 50 files per transaction
- Concurrent ingestion: 3 tasks per user

**Supported Languages:**
- Python (.py)
- JavaScript (.js)
- TypeScript (.ts)
- Rust (.rs)
- Go (.go)
- Java (.java)

## Related Documentation

- [Search API](search.md) - Search and discovery
- [Collections API](collections.md) - Organize resources into collections
- [Quality API](quality.md) - Quality assessment details
- [Architecture: Modules](../architecture/modules.md) - Module architecture
- [Architecture: Events](../architecture/events.md) - Event system
- [API Overview](overview.md) - Authentication, errors, pagination
