# Pharos Backend - Complete Technical Documentation

> **Version**: 2.3.0 | **Last Updated**: 2026-04-08 | **Status**: Production-Ready

Pharos is a distributed code intelligence backend - a "second brain" for your code. It ingests repositories, research papers, and technical docs, builds knowledge graphs and semantic embeddings, and exposes everything through a fast REST API designed to be queried by local LLM assistants (e.g., Ronin).

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Setup & Installation](#2-setup--installation)
3. [Configuration Reference](#3-configuration-reference)
4. [API Reference](#4-api-reference)
5. [Vector & Code Parsing Pipeline](#5-vector--code-parsing-pipeline)
6. [Deployment](#6-deployment)

---

## 1. Architecture Overview

### System Diagram

```
                           +----------------------------+
                           |      Ronin (LLM Client)    |
                           |  (Local Desktop Assistant) |
                           +-----------+----------------+
                                       | HTTP/REST + Bearer JWT
                                       v
                +--------------------------------------------------+
                |              Pharos FastAPI Backend              |
                |                                                  |
                |  +----------+  +---------+  +------------------+ |
                |  |   Auth   |  | Search  |  |    Resources     | |
                |  | (JWT/    |  | (FTS5 +  |  |  (Ingest, CRUD,  | |
                |  |  OAuth2) |  |  Dense + | |   Chunking)     | |
                |  +----------+  |  Sparse) |  +------------------+ |
                |                +---------+                       |
                |  +----------+  +---------+  +------------------+ |
                |  |  Graph   |  |   MCP   |  |   Collections    | |
                |  | (KG +    |  | (Tool   |  |  (Groups, Tags)  | |
                |  | Citations|  |  Invoke) |  +------------------+ |
                |  +----------+  +---------+                       |
                |  +----------+  +---------+  +------------------+ |
                |  | Scholarly |  | Quality |  |  Annotations     | |
                |  | (Papers) |  | (Scoring|  |  (Highlights)    | |
                |  +----------+  +---------+  +------------------+ |
                |  +----------+  +---------+  +------------------+ |
                |  | Planning |  | Taxonomy|  | Recommendations  | |
                |  | (AI Plan)|  |(Classify|  |  (NCF Model)     | |
                |  +----------+  +---------+  +------------------+ |
                +-------+----------+-----------+-------------------+
                        |          |           |
           +------------+   +------+------+    +----------+
           |                |             |               |
      +----v-----+   +-----v----+  +-----v------+  +-----v-----+
      | PostgreSQL|   |  Redis   |  |  Qdrant    |  |  Celery   |
      | (NeonDB)  |   | (Cache + |  | (Vectors)  |  | (Workers) |
      | SQLite    |   |  Queue)  |  +------------+  +-----------+
      +-----------+   +----------+
```

### Design Principles

- **Vertical Slice Architecture**: Each domain module (auth, search, resources, etc.) is self-contained with its own router, service, schema, and model layers.
- **Event-Driven Communication**: Modules communicate via an internal event bus. When a resource is created, events trigger chunking, graph extraction, and classification automatically.
- **Hybrid Edge-Cloud**: Runs in two modes:
  - `CLOUD`: Lightweight API server (no torch, no GPU). Uses Upstash Redis, NeonDB, Qdrant Cloud.
  - `EDGE`: Full ML stack with CUDA support. Local embeddings, repository parsing, recommendation engine.
- **Shared Kernel**: Cross-cutting concerns (database, security, caching, rate limiting) live in `app/shared/`.

### Module Summary

| Module | Prefix | Purpose |
|--------|--------|---------|
| **Auth** | `/api/auth` | JWT login, OAuth2 (Google/GitHub), token refresh |
| **Resources** | `/api/resources` | URL/file ingestion, CRUD, background processing |
| **Search** | `/api/search` | FTS5, dense vectors, sparse vectors, hybrid RRF |
| **Collections** | `/api/collections` | Group resources, manage membership |
| **Annotations** | `/api/annotations` | Highlights, notes on resources |
| **Graph** | `/api/graph` | Knowledge graph, citations, discovery |
| **Scholarly** | `/api/scholarly` | Research paper metadata extraction |
| **Quality** | `/api/quality` | Quality scoring, review queues |
| **Taxonomy** | `/taxonomy` | Classification, tagging |
| **Curation** | `/api/curation` | Review queue, batch operations |
| **Planning** | `/api/v1/ai-planning` | AI-driven implementation planning |
| **MCP** | `/api/v1/mcp` | Model Context Protocol tool invocation |
| **Monitoring** | `/api/monitoring` | Health checks, system metrics |
| **Ingestion** | `/api/v1/ingestion` | Edge-cloud task dispatch (CLOUD mode) |
| **Recommendations** | `/recommendations` | Personalized recommendations (EDGE only) |

---

## 2. Setup & Installation

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ (production) or SQLite (development)
- Redis 7+ (for caching, rate limiting, Celery)
- Docker & Docker Compose (recommended)
- 4GB+ RAM (8GB for EDGE mode with GPU)

### Option A: Docker (Recommended)

```bash
# 1. Clone and configure
cd backend
cp config/.env.example config/.env
# Edit config/.env with your values (see Configuration Reference)

# 2. Build and run
cd deployment
docker compose up -d --build

# 3. Verify
curl http://localhost:8000/api/monitoring/health
# Expected: {"status": "healthy", ...}
```

### Option B: Local Development (SQLite)

```bash
# 1. Create virtual environment
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# 2. Install dependencies
pip install -r requirements.txt
# For EDGE mode with ML:
# pip install -r requirements-edge.txt

# 3. Configure
cp config/.env.example config/.env
# Edit config/.env - SQLite works out of the box for dev

# 4. Run
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 5. View API docs
# Open: http://localhost:8000/docs
```

### Option C: Local Development (PostgreSQL)

```bash
# 1. Same as Option B steps 1-2

# 2. Configure PostgreSQL in config/.env
DATABASE_URL=postgresql://user:pass@localhost:5432/pharos
POSTGRES_SERVER=localhost
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
POSTGRES_DB=pharos

# 3. Run
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### First API Call

```bash
# 1. Register (via database seeding or OAuth2)
# 2. Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=your_user&password=your_pass"

# Response:
# {"access_token": "eyJ...", "refresh_token": "eyJ...", "token_type": "bearer"}

# 3. Search your knowledge base
export TOKEN="eyJ..."
curl http://localhost:8000/api/search/search/three-way-hybrid?query=dependency+injection \
  -H "Authorization: Bearer $TOKEN"
```

---

## 3. Configuration Reference

All configuration is via environment variables (loaded from `config/.env`).

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ENV` | `dev` | Environment: `dev`, `staging`, `prod` |
| `DATABASE_URL` | `sqlite:///./backend.db` | Database connection string |
| `MODE` | `CLOUD` | Deployment mode: `CLOUD` or `EDGE` |
| `JWT_SECRET_KEY` | (dev default) | **Must change in production.** Min 32 chars. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token TTL |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |

### Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker |

### Cloud Services (CLOUD mode)

| Variable | Required | Description |
|----------|----------|-------------|
| `UPSTASH_REDIS_REST_URL` | If PHASE19 | Upstash Redis REST endpoint (HTTPS) |
| `UPSTASH_REDIS_REST_TOKEN` | If PHASE19 | Upstash Redis auth token |
| `NEON_DATABASE_URL` | No | NeonDB PostgreSQL URL |
| `QDRANT_URL` | EDGE mode | Qdrant vector DB URL (HTTPS) |
| `QDRANT_API_KEY` | EDGE mode | Qdrant API key |
| `PHAROS_ADMIN_TOKEN` | If PHASE19 | Bearer token for ingestion endpoint |

### OAuth2 (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | None | Google OAuth2 client ID |
| `GOOGLE_CLIENT_SECRET` | None | Google OAuth2 client secret |
| `GITHUB_CLIENT_ID` | None | GitHub OAuth2 client ID |
| `GITHUB_CLIENT_SECRET` | None | GitHub OAuth2 client secret |

### RAG Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CHUNKING_STRATEGY` | `semantic` | `semantic` or `fixed` |
| `CHUNK_SIZE` | `500` | Words (semantic) or chars (fixed) |
| `CHUNK_OVERLAP` | `50` | Overlap between chunks |
| `GRAPH_EXTRACTION_ENABLED` | `true` | Enable knowledge graph extraction |
| `DEFAULT_RETRIEVAL_STRATEGY` | `parent-child` | `parent-child`, `graphrag`, `hybrid` |

### Rate Limiting

| Tier | Default Limit |
|------|---------------|
| `free` | 100 req/min |
| `premium` | 1,000 req/min |
| `admin` | 10,000 req/min |

---

## 4. API Reference

**Base URL**: `http://localhost:8000`
**Auth**: All endpoints (except `/api/auth/*`, `/docs`, `/api/monitoring/health`) require `Authorization: Bearer <JWT>`.

### 4.1 Authentication (`/api/auth`)

#### `POST /api/auth/login`
OAuth2 password flow. Rate limited: 5 attempts / 15 min per IP.

**Request** (`application/x-www-form-urlencoded`):
```
username=<string>&password=<string>&scope=<optional>
```

**Response** `200`:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

#### `POST /api/auth/refresh`
Refresh an expired access token.

**Request** (`application/json`):
```json
{ "refresh_token": "eyJ..." }
```

**Response** `200`: Same as login.

#### `POST /api/auth/logout`
Revokes the current access token. Requires auth.

**Response** `200`:
```json
{ "message": "Successfully logged out" }
```

#### `GET /api/auth/me`
Get current user profile. Requires auth.

**Response** `200`:
```json
{
  "id": "uuid",
  "username": "string",
  "email": "string",
  "tier": "free|premium|admin",
  "is_active": true
}
```

#### `GET /api/auth/rate-limit`
Get current rate limit status. Requires auth.

**Response** `200`:
```json
{
  "limit": 100,
  "remaining": 87,
  "reset": 1712582400,
  "tier": "free"
}
```

#### `GET /api/auth/google` / `GET /api/auth/github`
Initiate OAuth2 flow. Returns authorization URL.

#### `GET /api/auth/google/callback` / `GET /api/auth/github/callback`
OAuth2 callback. Sets HTTP-only cookies and redirects to frontend.

---

### 4.2 Resources (`/api/resources`)

#### `POST /api/resources`
Ingest a URL. Returns 202 (new) or 200 (existing). Processing happens in background.

**Request**:
```json
{
  "url": "https://example.com/article",
  "title": "Optional title",
  "description": "Optional description",
  "creator": "Author name",
  "language": "en",
  "type": "article",
  "source": "web"
}
```

**Response** `202`:
```json
{
  "id": "uuid",
  "status": "pending",
  "title": "Page Title",
  "ingestion_status": "pending"
}
```

#### `POST /api/resources/upload`
Upload a file directly (PDF, HTML, TXT). Max 50MB. `multipart/form-data`.

#### `GET /api/resources`
List resources with filtering and pagination.

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| `limit` | int | Page size (default: 20, max: 100) |
| `offset` | int | Pagination offset |
| `sort_by` | string | Sort field: `created_at`, `title`, `quality_score` |
| `sort_order` | string | `asc` or `desc` |
| `type` | string | Filter by resource type |
| `language` | string | Filter by language |
| `classification` | string | Filter by classification code |
| `min_quality` | float | Minimum quality score (0.0-1.0) |

**Response** `200`:
```json
{
  "items": [
    {
      "id": "uuid",
      "url": "https://...",
      "title": "Resource Title",
      "description": "...",
      "creator": "Author",
      "type": "article",
      "language": "en",
      "quality_score": 0.85,
      "ingestion_status": "completed",
      "created_at": "2026-04-08T10:00:00Z"
    }
  ],
  "total": 150,
  "limit": 20,
  "offset": 0
}
```

#### `GET /api/resources/{id}`
Get a single resource by ID.

#### `PUT /api/resources/{id}`
Update resource metadata.

#### `DELETE /api/resources/{id}`
Delete a resource (cascades to chunks, annotations, graph edges).

---

### 4.3 Search (`/api/search`)

#### `POST /api/search/search`
Standard search with FTS5, filters, and pagination.

**Request**:
```json
{
  "text": "dependency injection patterns",
  "limit": 20,
  "offset": 0,
  "hybrid_weight": 0.5,
  "type": "article",
  "language": "en"
}
```

**Response** `200`:
```json
{
  "total": 42,
  "items": [ { "id": "uuid", "title": "...", ... } ],
  "facets": { "type": {"article": 30, "code": 12}, "language": {"en": 42} },
  "snippets": { "uuid": "...matched text..." }
}
```

#### `GET /api/search/search/three-way-hybrid`
**The primary search endpoint for Ronin.** Combines FTS5 + dense vectors + sparse vectors with Reciprocal Rank Fusion.

**Query Parameters**:
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | string | required | Search query text |
| `limit` | int | 20 | Results (1-100) |
| `offset` | int | 0 | Pagination offset |
| `enable_reranking` | bool | true | Apply ColBERT reranking |
| `adaptive_weighting` | bool | true | Query-adaptive RRF weights |

**Response** `200`:
```json
{
  "total": 35,
  "items": [ { "id": "uuid", "title": "...", "quality_score": 0.9, ... } ],
  "facets": {},
  "snippets": {},
  "latency_ms": 125.4,
  "method_contributions": {
    "fts5": 0.3,
    "dense": 0.5,
    "sparse": 0.2
  },
  "weights_used": [0.33, 0.34, 0.33]
}
```

#### `POST /api/v1/search/advanced`
Advanced RAG search with parent-child or GraphRAG strategies.

**Request**:
```json
{
  "query": "how does the auth middleware work",
  "strategy": "hybrid",
  "top_k": 10,
  "context_window": 2,
  "relation_types": ["USES", "DEPENDS_ON"]
}
```

**Response** `200`:
```json
{
  "query": "...",
  "strategy": "hybrid",
  "results": [
    {
      "chunk": { "id": "uuid", "resource_id": "uuid", "content": "...", "chunk_index": 3 },
      "parent_resource": { "id": "uuid", "title": "..." },
      "surrounding_chunks": [ ... ],
      "graph_path": [
        { "entity_id": "uuid", "entity_name": "AuthMiddleware", "entity_type": "class", "relation_type": "USES" }
      ],
      "score": 0.92
    }
  ],
  "total": 10,
  "latency_ms": 89.3
}
```

#### `GET /api/search/search/compare-methods`
Debug endpoint: runs all search methods side-by-side and returns latency comparison.

---

### 4.4 Collections (`/api/collections`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/collections` | Create a collection |
| `GET` | `/api/collections` | List collections |
| `GET` | `/api/collections/{id}` | Get collection details |
| `PUT` | `/api/collections/{id}` | Update collection |
| `DELETE` | `/api/collections/{id}` | Delete collection |
| `POST` | `/api/collections/{id}/resources` | Add resource to collection |
| `DELETE` | `/api/collections/{id}/resources/{rid}` | Remove resource |

---

### 4.5 Annotations (`/api/annotations`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/annotations` | Create annotation on a resource |
| `GET` | `/api/annotations` | List annotations (filterable) |
| `GET` | `/api/annotations/{id}` | Get annotation |
| `PUT` | `/api/annotations/{id}` | Update annotation |
| `DELETE` | `/api/annotations/{id}` | Delete annotation |

---

### 4.6 Knowledge Graph (`/api/graph`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/graph/overview` | Get graph overview (nodes + edges) |
| `GET` | `/api/graph/neighbors/{id}` | Get neighbors of a node |
| `GET` | `/api/graph/path` | Find path between two nodes |
| `POST` | `/api/graph/citations/extract` | Extract citations from a resource |
| `GET` | `/api/graph/citations/{id}` | Get citations for a resource |

---

### 4.7 MCP - Model Context Protocol (`/api/v1/mcp`)

MCP allows Ronin to invoke Pharos tools programmatically.

#### `GET /api/v1/mcp/tools`
List all available MCP tools.

**Response** `200`:
```json
{
  "tools": [
    {
      "name": "search_knowledge_base",
      "description": "Search across all ingested resources",
      "input_schema": { "type": "object", "properties": { "query": {"type": "string"} } },
      "requires_auth": true
    }
  ],
  "total": 5
}
```

#### `POST /api/v1/mcp/invoke`
Invoke an MCP tool.

**Request**:
```json
{
  "session_id": "optional-session-uuid",
  "tool_name": "search_knowledge_base",
  "arguments": { "query": "authentication patterns" }
}
```

**Response** `200`:
```json
{
  "tool_name": "search_knowledge_base",
  "result": { ... },
  "execution_time_ms": 45.2,
  "success": true
}
```

#### `POST /api/v1/mcp/sessions`
Create a session for multi-turn MCP interactions.

---

### 4.8 Scholarly (`/api/scholarly`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/scholarly/extract` | Extract metadata from a research paper |
| `GET` | `/api/scholarly/{id}` | Get scholarly metadata for a resource |

---

### 4.9 Quality & Curation

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/quality/scores` | Get quality scores for resources |
| `POST` | `/api/quality/evaluate` | Evaluate resource quality |
| `GET` | `/api/curation/review-queue` | Get resources pending review |
| `POST` | `/api/curation/batch-update` | Batch update curation status |

---

### 4.10 AI Planning (`/api/v1/ai-planning`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/ai-planning/generate` | Generate implementation plan |
| `PUT` | `/api/v1/ai-planning/{id}/refine` | Refine plan with feedback |
| `GET` | `/api/v1/ai-planning/{id}` | Get plan by ID |

---

### 4.11 Ingestion - Edge-Cloud (`/api/v1/ingestion`) [CLOUD mode]

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/v1/ingestion/ingest/{repo_url}` | Bearer | Queue repo for edge processing |
| `GET` | `/api/v1/ingestion/worker/status` | Public | Edge worker status |
| `GET` | `/api/v1/ingestion/jobs/history` | Public | Job history |
| `GET` | `/api/v1/ingestion/health` | Public | Service health |

---

### 4.12 Monitoring (`/api/monitoring`)

#### `GET /api/monitoring/health`
Public health check. No auth required.

**Response** `200`:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "uptime_seconds": 86400
}
```

---

### Common Response Patterns

**Error responses** always follow this format:
```json
{
  "detail": "Human-readable error message"
}
```

**HTTP Status Codes**:
| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 202 | Accepted (async processing) |
| 400 | Bad request / validation error |
| 401 | Not authenticated |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not found |
| 422 | Validation error (request body) |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
| 503 | Service unavailable |

**Rate Limit Headers** (on all authenticated responses):
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1712582460
```

---

## 5. Vector & Code Parsing Pipeline

### How Ingestion Works

```
 User submits URL/file
         |
         v
 +------------------+
 | Resource Created  |  (status: pending)
 | in Database       |
 +--------+---------+
          |
          v  (BackgroundTask)
 +------------------+
 | Content Fetched   |  HTTP fetch or file read
 | & Extracted       |  (HTML->text, PDF->text)
 +--------+---------+
          |
          v
 +------------------+
 | Chunking          |  Semantic (sentence boundaries)
 | (configurable)    |  or Fixed (char count)
 +--------+---------+
          |
          v
 +------------------+
 | Embedding         |  nomic-embed-text-v1 (768-dim)
 | Generation        |  Dense + Sparse vectors
 +--------+---------+
          |
          v
 +------------------+
 | Graph Extraction  |  Entity + relationship extraction
 | (if enabled)      |  via LLM, spaCy, or hybrid
 +--------+---------+
          |
          v
 +------------------+
 | Quality Scoring   |  Multi-factor score (0.0-1.0)
 | & Classification  |  Taxonomy assignment
 +--------+---------+
          |
          v
 +------------------+
 | Resource Updated  |  (status: completed)
 | Searchable        |
 +------------------+
```

### Repository Parsing (EDGE mode)

For code repositories (`/api/v1/ingestion/ingest/{repo_url}`):

1. **Clone**: Shallow `git clone --depth=1` to isolated temp directory
2. **Parse**: Tree-sitter AST parsing for Python, JavaScript, TypeScript
3. **Extract**: Import statements, function signatures, class definitions, docstrings
4. **Build Graph**: Dependency graph as PyTorch edge tensors (file -> imported file)
5. **Detect Patterns**: Error handling, documentation coverage, test file ratios
6. **Embed**: Generate vector embeddings for code chunks
7. **Cleanup**: Temp directory removed after processing

### Search Pipeline

The three-way hybrid search (primary Ronin endpoint):

1. **FTS5 / tsvector**: Keyword matching via SQLite FTS5 or PostgreSQL full-text
2. **Dense Vector**: Semantic similarity via nomic-embed-text embeddings
3. **Sparse Vector**: Learned keyword importance via SPLADE-style embeddings
4. **RRF Fusion**: Reciprocal Rank Fusion merges the three ranked lists
5. **Adaptive Weights**: Query characteristics (length, specificity) adjust fusion weights
6. **ColBERT Reranking** (optional): Cross-encoder reranks top-K results for precision

---

## 6. Deployment

### Docker Compose (Production)

```bash
cd backend/deployment
docker compose up -d --build
```

Services:
- `backend`: FastAPI on port 8000
- `redis`: Cache + Celery broker
- `celery_worker`: Background task processing

### Environment Checklist for Production

- [ ] `ENV=prod`
- [ ] `JWT_SECRET_KEY` changed from default (32+ chars, generated via `python -c "import secrets; print(secrets.token_hex(32))"`)
- [ ] `DATABASE_URL` pointing to PostgreSQL (not SQLite)
- [ ] `REDIS_HOST` / `CELERY_BROKER_URL` configured
- [ ] `ALLOWED_REDIRECT_URLS` uses HTTPS only
- [ ] `ALLOWED_ORIGINS` restricted to your domains
- [ ] `TEST_MODE=false` and `TESTING` env var not set
- [ ] If using OAuth2: `GOOGLE_CLIENT_ID`, `GITHUB_CLIENT_ID` etc. configured
- [ ] If PHASE19: `UPSTASH_REDIS_REST_URL`, `PHAROS_ADMIN_TOKEN` set

### Structured Logging

In production (`ENV=prod`) or when `JSON_LOGGING=true`, all logs emit as structured JSON:

```json
{
  "timestamp": "2026-04-08T10:30:00.123Z",
  "level": "INFO",
  "logger": "app.modules.search.router",
  "message": "Three-way hybrid search completed",
  "module": "router",
  "function": "three_way_hybrid_search_endpoint",
  "line": 142,
  "extra": { "latency_ms": 125.4, "results": 35 }
}
```

### Health Monitoring

- `GET /api/monitoring/health` - Overall system health
- `GET /api/v1/ingestion/health` - Redis + DB + Qdrant connectivity
- `GET /api/auth/health` - Auth module health
- `GET /api/resources/health` - Resources module health
- `GET /api/search/search/health` - Search module health

---

## Appendix: Ronin Integration Checklist

See the final section of the audit output for the complete checklist of what Ronin needs to send to Pharos.
