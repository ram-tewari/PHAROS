# Code Repository Ingestion Guide

## Overview

Pharos includes code intelligence capabilities that allow you to ingest and analyze code repositories. This guide explains how to use the repository ingestion features to analyze local directories and remote Git repositories.

## Features

### Repository Ingestion
- **Local Directories**: Scan and analyze code in local directories
- **Git Repositories**: Clone and analyze remote Git repositories (HTTPS/SSH)
- **Gitignore Support**: Automatically respects .gitignore patterns
- **Binary Detection**: Excludes binary files from analysis

### Code Analysis
- **AST Parsing**: Tree-Sitter-based parsing for 6 languages
- **Logical Chunking**: Chunks code by functions, classes, and methods
- **Static Analysis**: Extracts imports, definitions, and function calls
- **Graph Relationships**: Builds dependency graph with IMPORTS, DEFINES, CALLS

### Supported Languages

| Language | Extension | Features |
|----------|-----------|----------|
| Python | .py | Functions, classes, methods, imports, calls |
| JavaScript | .js | Functions, classes, methods, imports, calls |
| TypeScript | .ts | Functions, classes, methods, imports, calls |
| Rust | .rs | Functions, structs, traits, imports, calls |
| Go | .go | Functions, structs, interfaces, imports, calls |
| Java | .java | Classes, methods, interfaces, imports, calls |

## Quick Start

### Prerequisites

1. **Authentication**: Obtain a JWT token
```bash
# Login to get access token
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "your_username", "password": "your_password"}'

# Save the access_token from the response
export TOKEN="your_access_token_here"
```

2. **Rate Limits**: Check your tier limits
- Free tier: 5 ingestions/hour
- Premium tier: 20 ingestions/hour
- Admin tier: Unlimited

### Ingest a Local Directory

```bash
# Start ingestion
curl -X POST http://127.0.0.1:8000/resources/ingest-repo \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"path": "/path/to/your/project"}'

# Response
{
  "task_id": "celery-task-uuid",
  "status": "pending",
  "message": "Repository ingestion started"
}
```

### Ingest a Git Repository

```bash
# Start ingestion from Git URL
curl -X POST http://127.0.0.1:8000/resources/ingest-repo \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"git_url": "https://github.com/user/repo.git"}'

# Response
{
  "task_id": "celery-task-uuid",
  "status": "pending",
  "message": "Repository ingestion started"
}
```

### Check Ingestion Status

```bash
# Poll for status (every 2-5 seconds)
curl "http://127.0.0.1:8000/resources/ingest-repo/celery-task-uuid/status" \
  -H "Authorization: Bearer $TOKEN"

# Response (in progress)
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

# Response (completed)
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

## How It Works

### 1. Repository Access

**Local Directory:**
- Recursively scans directory using `Path.rglob()`
- Respects .gitignore patterns using pathspec library
- Detects and excludes binary files (null byte check)

**Git Repository:**
- Clones repository to temporary directory
- Extracts commit hash and branch name
- Stores metadata in Resource
- Cleans up temporary directory after ingestion

### 2. File Classification

Files are automatically classified into three categories:

**PRACTICE (Code Files):**
- Python (.py)
- JavaScript (.js)
- TypeScript (.ts)
- Rust (.rs)
- Go (.go)
- Java (.java)

**THEORY (Documentation):**
- PDF files (.pdf)
- Markdown files with academic keywords (.md)
- Research papers and documentation

**GOVERNANCE (Configuration):**
- CONTRIBUTING.md
- CODE_OF_CONDUCT.md
- .eslintrc, .prettierrc
- Configuration files

### 3. AST-Based Code Chunking

For code files, the system uses Tree-Sitter to parse the Abstract Syntax Tree (AST):

**Logical Unit Extraction:**
- Functions
- Classes
- Methods
- Modules

**Chunk Metadata:**
```json
{
  "function_name": "calculate_score",
  "class_name": "ScoreCalculator",
  "start_line": 42,
  "end_line": 67,
  "language": "python",
  "type": "method"
}
```

**Fallback Strategy:**
- If AST parsing fails, falls back to character-based chunking
- Ensures all files are processed even with syntax errors

### 4. Static Analysis

The system extracts code relationships without executing code:

**Import Relationships (IMPORTS):**
```python
# Example: main.py imports utils.py
import utils

# Creates relationship:
# main.py IMPORTS utils.py
# Metadata: {source_file: "main.py", target_module: "utils", line_number: 1}
```

**Definition Relationships (DEFINES):**
```python
# Example: utils.py defines calculate_score
def calculate_score(data):
    return sum(data) / len(data)

# Creates relationship:
# utils.py DEFINES calculate_score
# Metadata: {source_file: "utils.py", symbol_name: "calculate_score", 
#            symbol_type: "function", line_number: 1}
```

**Call Relationships (CALLS):**
```python
# Example: main() calls calculate_score()
def main():
    score = calculate_score(data)

# Creates relationship:
# main CALLS calculate_score
# Metadata: {source_function: "main", target_function: "calculate_score",
#            line_number: 2, confidence: 0.9}
```

### 5. Graph Construction

All relationships are stored in the knowledge graph:

**Query Examples:**

Find all imports in a file:
```bash
curl "http://127.0.0.1:8000/api/graph/entities/file-entity-id/relationships?relation_type=IMPORTS&direction=outgoing" \
  -H "Authorization: Bearer $TOKEN"
```

Find all functions defined in a file:
```bash
curl "http://127.0.0.1:8000/api/graph/entities/file-entity-id/relationships?relation_type=DEFINES&direction=outgoing" \
  -H "Authorization: Bearer $TOKEN"
```

Find all callers of a function:
```bash
curl "http://127.0.0.1:8000/api/graph/entities/function-entity-id/relationships?relation_type=CALLS&direction=incoming" \
  -H "Authorization: Bearer $TOKEN"
```

Traverse dependency graph:
```bash
curl "http://127.0.0.1:8000/api/graph/traverse?start_entity_id=file-entity-id&relation_types=IMPORTS&max_hops=3" \
  -H "Authorization: Bearer $TOKEN"
```

## Advanced Usage

### Batch Processing

The system processes files in batches of 50 to prevent memory exhaustion:

```python
# Automatic batch processing
# - Processes 50 files per database transaction
# - Commits after each batch
# - Continues on individual file errors
```

### Error Handling

**File-Level Errors:**
- Individual file failures don't stop the entire ingestion
- Errors are logged and tracked in task metadata
- Failed files are reported in the final result

**Transaction Management:**
- Batch commits every 50 files
- Rollback on database errors
- Task marked as FAILED on critical errors

### Performance Optimization

**Caching:**
- Tree-Sitter parsers cached per language
- .gitignore patterns cached per repository
- File classification rules cached

**Concurrency:**
- Maximum 3 concurrent ingestion tasks per user
- Celery worker pool size configurable
- Task timeout: 30 minutes for 1000 files

**Performance Targets:**
- AST parsing: <2s per file (P95)
- Static analysis: <1s per file (P95)
- Total ingestion: ~5-10 seconds per file (including I/O)

## Troubleshooting

### Common Issues

**1. Authentication Error (401)**
```json
{
  "detail": "Not authenticated"
}
```
**Solution:** Ensure you're passing a valid JWT token in the Authorization header.

**2. Rate Limit Exceeded (429)**
```json
{
  "detail": "Rate limit exceeded"
}
```
**Solution:** Wait for the rate limit window to reset or upgrade your tier.

**3. Invalid Path**
```json
{
  "detail": "Path does not exist: /invalid/path"
}
```
**Solution:** Verify the path exists and is accessible by the server.

**4. Git Clone Failed**
```json
{
  "error": "Failed to clone repository: authentication required"
}
```
**Solution:** 
- Use HTTPS URLs for public repositories
- For private repositories, configure SSH keys or use access tokens
- Verify the repository URL is correct

**5. Parse Errors**
```json
{
  "error": "Failed to parse file: syntax error at line 42"
}
```
**Solution:** 
- The system will fall back to character-based chunking
- Check the file for syntax errors if you need AST-based chunking
- Individual file failures don't stop the entire ingestion

### Debugging

**Check Task Status:**
```bash
# Get detailed task information
curl "http://127.0.0.1:8000/resources/ingest-repo/task-id/status" \
  -H "Authorization: Bearer $TOKEN"
```

**Check Logs:**
```bash
# Backend logs
tail -f backend/logs/app.log

# Celery worker logs
docker-compose logs -f celery-worker
```

**Verify Resources Created:**
```bash
# List resources from the repository
curl "http://127.0.0.1:8000/resources?limit=100" \
  -H "Authorization: Bearer $TOKEN"
```

## Best Practices

### 1. Repository Size

**Small Repositories (<100 files):**
- Ingest directly without concerns
- Typical completion time: 1-2 minutes

**Medium Repositories (100-1000 files):**
- Monitor progress via status endpoint
- Typical completion time: 5-15 minutes

**Large Repositories (>1000 files):**
- Consider ingesting subdirectories separately
- Monitor task timeout (30 minutes)
- Typical completion time: 15-30 minutes

### 2. Gitignore Configuration

Ensure your .gitignore excludes:
- Build artifacts (dist/, build/, target/)
- Dependencies (node_modules/, vendor/)
- Generated files (*.pyc, *.class)
- Large binary files

### 3. Private Repositories

**HTTPS with Token:**
```bash
# Use personal access token in URL
curl -X POST http://127.0.0.1:8000/resources/ingest-repo \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"git_url": "https://token@github.com/user/private-repo.git"}'
```

**SSH:**
- Configure SSH keys on the server
- Use SSH URLs: `git@github.com:user/repo.git`

### 4. Incremental Updates

To update an existing repository:
1. Delete old resources (optional)
2. Re-ingest the repository
3. The system will create new resources with updated content

### 5. Search and Discovery

After ingestion, use the search API to find code:

**Semantic Search:**
```bash
curl -X POST http://127.0.0.1:8000/api/search/advanced \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "authentication middleware",
    "strategy": "parent-child",
    "limit": 10
  }'
```

**Graph Traversal:**
```bash
# Find all dependencies of a module
curl "http://127.0.0.1:8000/api/graph/traverse?start_entity_id=module-id&relation_types=IMPORTS&max_hops=3" \
  -H "Authorization: Bearer $TOKEN"
```

## API Reference

### POST /resources/ingest-repo

**Request:**
```json
{
  "path": "/path/to/local/repo",  // Optional
  "git_url": "https://github.com/user/repo.git"  // Optional
}
```

**Response:**
```json
{
  "task_id": "celery-task-uuid",
  "status": "pending",
  "message": "Repository ingestion started"
}
```

### GET /resources/ingest-repo/{task_id}/status

**Response:**
```json
{
  "task_id": "celery-task-uuid",
  "status": "processing|completed|failed",
  "progress": {
    "files_processed": 45,
    "total_files": 100,
    "current_file": "src/main.py"
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

## Related Documentation

- [Resources API](../api/resources.md) - Complete API reference
- [Graph API](../api/graph.md) - Graph relationship queries
- [Architecture: Modules](../architecture/modules.md) - Code intelligence pipeline
- [Testing Guide](testing.md) - Testing code intelligence features

## Support

For issues or questions:
- Check the [Troubleshooting](#troubleshooting) section
- Review backend logs for detailed error messages
- Open an issue on GitHub with reproduction steps

---

## Hybrid Retrieval Workflow

When code chunks are ingested from a GitHub repository, Pharos stores only the **metadata** for remote chunks (URI, commit SHA, line range) rather than duplicating the raw source in the database. Source code is fetched on demand via the GitHub module.

### How it works

```
Search query
    │
    ▼
POST /api/search/advanced  { "include_code": true }
    │
    ├── Search Service (semantic + keyword retrieval)
    │       returns result dicts with chunk IDs
    │
    ├── DB re-query: fetch ORM DocumentChunk objects by ID
    │
    └── resolve_code_for_chunks(orm_chunks)
            │
            ├── is_remote=False → read chunk.content  (source: "local")
            │
            └── is_remote=True  → GitHubFetcher.fetch_chunk()
                    │
                    ├── Redis HIT  → return cached code   (cache_hit: true)
                    └── Redis MISS → GET raw GitHub URL
                                     slice lines
                                     store in Redis (TTL 1h)
                                     return code            (cache_hit: false)
```

### Attach code inline (search response)

```bash
curl -X POST http://127.0.0.1:8000/api/search/advanced \
  -H "Content-Type: application/json" \
  -d '{
    "query": "bubble sort implementation",
    "strategy": "parent-child",
    "top_k": 5,
    "include_code": true
  }'
```

Each `chunk` in the response gains three extra fields:
- `code` — the resolved source code string (or `null` on fetch error)
- `source` — `"local"` or `"github"`
- `cache_hit` — `true` / `false` / `null` (null for local chunks)

The response also includes a top-level `code_metrics` object with aggregate stats.

### Fetch code directly (GitHub API)

For ad-hoc lookups without a search query:

```bash
# Single chunk
curl -X POST http://127.0.0.1:8000/api/github/fetch \
  -H "Content-Type: application/json" \
  -d '{
    "github_uri": "https://raw.githubusercontent.com/owner/repo/abc123/src/sort.py",
    "start_line": 10,
    "end_line": 40
  }'

# Batch (up to 50)
curl -X POST http://127.0.0.1:8000/api/github/fetch-batch \
  -H "Content-Type: application/json" \
  -d '{
    "chunks": [
      { "github_uri": "https://raw.githubusercontent.com/owner/repo/main/a.py", "start_line": 1, "end_line": 30 },
      { "github_uri": "https://raw.githubusercontent.com/owner/repo/main/b.py", "start_line": 50, "end_line": 80 }
    ]
  }'
```

### Performance considerations

| Scenario | Typical latency |
|----------|----------------|
| Local chunk (no fetch) | < 1 ms |
| Remote chunk, cache HIT | < 10 ms |
| Remote chunk, cache MISS | 100–300 ms |
| 10 remote chunks (parallel) | ~300 ms |
| 50 remote chunks (parallel) | ~500 ms |

Set `GITHUB_API_TOKEN` in your environment to raise the GitHub rate limit from 60 to 5,000 requests/hour.
