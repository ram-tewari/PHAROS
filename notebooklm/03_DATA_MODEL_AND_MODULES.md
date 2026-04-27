# Pharos — Data Model and Module Reference

> File 3 of 6. Covers the SQLAlchemy data model (the ~30 tables in `backend/app/database/models.py`, which is ~1 864 lines and the single source of truth) and a deep-dive on each vertical-slice module. See File 6 for evolution history.

---

## Database Philosophy

One file (`backend/app/database/models.py`) defines every table. Module-level `model.py` files only *re-export* those classes. This rule exists because earlier attempts at distributed models caused unavoidable circular imports when modules grew relationships to each other.

- **Base class**: `app.shared.base_model.Base` (SQLAlchemy 2.x `DeclarativeBase`).
- **UUID type**: Custom `GUID` type from `base_model.py` — uses native `UUID` on Postgres, `String(36)` on SQLite. All primary keys are UUIDs.
- **Default timestamps**: `created_at` / `updated_at` use `func.current_timestamp()` and `onupdate=func.current_timestamp()`.
- **JSON columns**: Postgres `JSONB` (where supported) else SQLite `JSON`.
- **Vector columns**: Stored as `Text` (a JSON list of floats). Cast to `vector` via `CAST(:p AS vector)` in queries. Reason: SQLAlchemy + asyncpg silently writes zero rows when `::vector` postfix casts are used instead of the explicit `CAST(... AS vector)` form (see "asyncpg uuid/vector casts" feedback note).

---

## Table Inventory (complete list, in file order)

Line numbers below are from the current `backend/app/database/models.py`.

| Line | Class | Purpose |
|---:|---|---|
| 77 | `Repository` | GitHub hybrid-storage metadata |
| 129 | `Resource` | Core content entity (Dublin Core + scholarly + quality + embedding) |
| 316 | `DocumentChunk` | Retrievable unit (function / class / page) with embedding |
| 406 | `ChunkLink` | Parent-child chunk relationships for hierarchical retrieval |
| 466 | `PlanningSession` | AI planning module session records |
| 515 | `CollectionResource` | M2M between Collection and Resource |
| 539 | `Collection` | Hierarchical grouping of resources |
| 600 | `Annotation` | Character-offset highlight + note + tags + semantic embedding |
| 657 | `GraphEntity` | Node in the knowledge graph (concept, person, organization, …) |
| 704 | `GraphRelationship` | Typed edge in the knowledge graph |
| 773 | `Citation` | Parsed citations from scholarly documents |
| 815 | `GraphEdge` | Legacy graph edge (IMPORTS / DEFINES / CALLS for code) |
| 865 | `GraphEmbedding` | Embeddings of graph nodes (for GraphRAG) |
| 903 | `GraphCentralityCache` | Pre-computed PageRank / centrality |
| 939 | `CommunityAssignment` | Louvain / Leiden community IDs for entities |
| 977 | `DiscoveryHypothesis` | Hypothesis-generation feature output |
| 1023 | `SyntheticQuestion` | Auto-generated eval questions for RAG |
| 1073 | `UserProfile` | Recommender-system profile (embedding of user interests) |
| 1155 | `UserInteraction` | View/read/click events for recommender |
| 1250 | `ClassificationCode` | UDC-inspired taxonomy lookup |
| 1273 | `AuthoritySubject` | Controlled-vocab subject |
| 1300 | `AuthorityCreator` | Controlled-vocab author |
| 1327 | `AuthorityPublisher` | Controlled-vocab publisher |
| 1363 | `RAGEvaluation` | Stored RAG quality evaluations |
| 1409 | `User` | Authentication (JWT subjects) |
| 1469 | `ModelVersion` | ML model registry |
| 1503 | `ABTestExperiment` | A/B testing configuration |
| 1545 | `PredictionLog` | ML prediction audit log |
| 1581 | `RetrainingRun` | ML retraining tracking |
| 1621 | `DeveloperProfileRecord` | Per-user coding-style profile (for Ronin) |

---

## Central Tables — Deep Dive

### `Resource` (line 129) — the central content entity

One row per ingested thing: a web page, a PDF, a research paper, a code *file*, a repo-level record, etc. Key columns:

**Dublin Core**: `title` (NOT NULL), `description`, `creator`, `publisher`, `contributor`, `date_created`, `date_modified`, `type`, `format`, `identifier`, `source`, `language`, `coverage`, `rights`.

**JSON arrays**: `subject: list[str]`, `relation: list[str]`.

**Custom**:
- `classification_code` — UDC-ish code.
- `read_status` — `"unread" | "in_progress" | "done"` (string).
- `quality_score` — Float 0–1.

**Ingestion workflow**:
- `ingestion_status: str` — `"pending" | "processing" | "completed" | "failed"` (string, not enum-typed in DB).
- `ingestion_error`, `ingestion_started_at`, `ingestion_completed_at`.

**Staleness Tracking** (added 2026-04-27):
- `is_stale: bool | None` — TRUE when a repo is re-ingested with a newer commit SHA (indexed for fast filtering).
- `last_indexed_sha: str(64) | None` — Git commit SHA from last ingestion.
- `last_indexed_at: DateTime | None` — Timestamp of last ingestion.
- **Search behavior**: All search queries filter `(r.is_stale IS NULL OR r.is_stale = FALSE)` to exclude outdated code.

**Embeddings**:
- `embedding: Text` — JSON-serialized 768-dim list (nullable). Nullable because embedding is async.
- `sparse_embedding: Text` — SPLADE sparse rep.
- `sparse_embedding_model: str(100)`, `sparse_embedding_updated_at`.
- `search_vector: Text` — precomputed full-text search vector (tsvector on Postgres or FTS5 column elsewhere).

**Scholarly** (lines 200–240): `authors`, `affiliations`, `doi`, `pmid`, `arxiv_id`, `isbn`, `journal`, `conference`, `volume`, `issue`, `pages`, `publication_year`, `funding_sources`, `acknowledgments`, `equation_count`, `table_count`, `figure_count`, `reference_count`, `equations`, `tables`, `figures`, `metadata_completeness_score`, `extraction_confidence`, `requires_manual_review`.

**Quality** (multi-dimensional): `quality_accuracy`, `quality_completeness`, `quality_consistency`, `quality_timeliness`, `quality_relevance`, `quality_overall`, `quality_weights`, `quality_last_computed`, `quality_computation_version`, `is_quality_outlier`, `outlier_score`, `outlier_reasons`, `needs_quality_review`.

**Summary coherence**: `summary_coherence`, `summary_consistency`, `summary_fluency`, `summary_relevance` (four-dim RAG-eval-style scoring of AI-generated summaries).

**OCR**: `is_ocr_processed`, `ocr_confidence`, `ocr_corrections_applied`.

**Concurrency**: `version: int` — optimistic lock.

**Relationships**: `collections` (M2M via `collection_resources`), `annotations` (1-to-N, cascade delete), `centrality_cache` (1-to-1), `community_assignments` (1-to-N).

---

### `DocumentChunk` (line 316) — the retrieval unit

One row per retrievable chunk. For PDFs: a page-ish slice with populated `content`. For code: a function/class/method with `content=NULL` and a pointer to GitHub in `chunk_metadata`.

Key columns:
- `id: UUID` (PK)
- `resource_id: UUID` (FK → resources, ON DELETE CASCADE, indexed)
- `embedding_id: UUID | None` — async-generated external reference (rare usage)
- `content: Text | None` — **NULL for code chunks** (code lives on GitHub); populated for PDF / text chunks
- `chunk_index: int`
- `chunk_metadata: JSON` — polymorphic:
  - PDFs: `{"page": 1, "coordinates": [x, y]}`
  - Code: `{"github_uri": "...", "branch_reference": "<sha or HEAD>", "start_line": 12, "end_line": 40, "ast_node_type": "function_definition", "symbol_name": "authenticate_user", "imports": [...]}`
- `embedding: Text | None` — 768-dim JSON list (nullable until edge worker populates it)
- `semantic_summary: Text | None` — what actually gets embedded for code (signature + docstring + deps)
- `content_hash`, `parent_chunk_id`, etc.

**Semantic Summary Format** (for code chunks):
```
[language] signature: 'docstring.' deps: [imports]
```

Example:
```
[python] def authenticate_user(username: str, password: str) -> User:
    'Authenticate a user with credentials.'
    deps: [verify_password, db.query, User]
```

This is the **exact string** that gets embedded — not the raw source code, not the JSON metadata blob. The format is:
1. Language tag in brackets
2. Function/class signature with type hints
3. Docstring in single quotes (first line only)
4. Dependencies list (imports, function calls, class references)

**Crucial semantics**:
- For code, the embedded string is `semantic_summary`, NOT `content`, and NOT a JSON blob. A recent fix changed the pipeline from "embed the whole chunk-metadata JSON" to "embed just the semantic summary" — this dramatically improved retrieval quality.
- `github_uri` must be a **POSIX path** (Windows backslashes were breaking raw.githubusercontent.com URLs; normalization is done at write time). The fix: `github_uri.replace("\\", "/")` at ingestion time.
- Non-SHA `branch_reference` values are rewritten to `HEAD` so raw URLs resolve against the repo's default branch. Why: branch names like "main" or "master" don't always resolve on raw.githubusercontent.com for all repos (especially private repos or deleted branches). `HEAD` always resolves to the default branch. Edge case: if the branch is deleted after ingestion, the URL will 404 — accepted trade-off.

---

### `ChunkLink` (line 406) — Parent-child chunk relationships

Stores hierarchical relationships between chunks for parent-child retrieval strategy.

Key columns:
- `id: UUID` (PK)
- `parent_chunk_id: UUID` (FK → document_chunks)
- `child_chunk_id: UUID` (FK → document_chunks)
- `relationship_type: str` — e.g., "contains", "follows", "implements"

**Purpose**: When a search result returns a specific function chunk, the parent-child strategy can also retrieve:
- The parent class chunk (for context about the class this method belongs to)
- The parent module chunk (for context about imports and module-level setup)
- Sibling chunks (other methods in the same class)

**Why this matters for LLM context**: A function like `authenticate_user()` makes more sense when you also see:
- The `User` class it returns
- The `verify_password()` helper it calls
- The module-level imports (`from bcrypt import hashpw`)

**How relationships are established**: During AST chunking, the pipeline creates links:
```python
# Class chunk
class_chunk = DocumentChunk(content="class User: ...")

# Method chunk
method_chunk = DocumentChunk(content="def authenticate_user(): ...")

# Link: method is child of class
ChunkLink(parent_chunk_id=class_chunk.id, child_chunk_id=method_chunk.id, relationship_type="contains")
```

**Query-time expansion**: When `strategy="parent-child"` in `/api/search/advanced`, for each retrieved chunk, the system also fetches its parent and includes both in the response. This gives the LLM ~2-3x more context per hit.

---

### `Repository` (line 77) — GitHub hybrid storage

Tracks each ingested code repo (distinct from `Resource` rows which represent files within the repo).
- `id: UUID` PK
- `url: String(2048)` (unique, indexed)
- `name: String(255)`
- `repo_metadata: JSON` — `{files, imports, functions, classes, embeddings_count}`
- `total_files: int`, `total_lines: int`
- indexed on url, name, created_at

---

### Graph Tables

The graph is **dual-implementation** — legacy code-only edges + modern knowledge-graph entities & relationships:

- **`GraphEntity`** — A node. Has `name`, `entity_type` (e.g. "person", "concept", "function"), `description`, `properties: JSON`, and an `embedding` for semantic entity search.
- **`GraphRelationship`** — Typed directed edge between entities. `source_entity_id`, `target_entity_id`, `relationship_type`, `properties`, `confidence`.
- **`Citation`** — Parsed scholarly citations (separate from generic graph).
- **`GraphEdge`** — Legacy code-specific edges (IMPORTS / DEFINES / CALLS) between resources.
- **`GraphEmbedding`** — Node2Vec / TransE style node embeddings for GraphRAG retrieval.
- **`GraphCentralityCache`** — Pre-computed PageRank per entity.
- **`CommunityAssignment`** — Louvain / Leiden cluster IDs.

GraphRAG retrieval JOINs `document_chunks` → `graph_entities` → `graph_relationships` to expand a hit into its semantic neighborhood during context retrieval.

---

### Auth and User

- **`User`** — `email`, `hashed_password` (bcrypt), `role` (`"free" | "premium" | "admin"`), `is_active`, `oauth_provider`, `oauth_id`, token-revocation list columns.
- JWT: short-lived access token + long-lived refresh token; secrets in `SECRET_KEY`.
- **`DeveloperProfileRecord`** — per-user coding-style profile (for Ronin to personalize generation). Stores extracted patterns, preferred idioms, detected antipatterns.

---

## Module-by-Module Reference

Each module lives at `backend/app/modules/<name>/` and follows the same layout:

```
module/
├── __init__.py      # exports router(s) + register_handlers()
├── router.py        # FastAPI APIRouter with prefix /api/<name>
├── service.py       # business logic (no FastAPI imports)
├── schema.py        # Pydantic request/response models
├── handlers.py      # event_bus listeners (cross-module integration)
├── model.py         # re-exports models from app/database/models.py
└── tests/           # module-local pytest tests
```

### `resources/`
- **Purpose**: Core Resource CRUD + URL ingestion orchestration.
- **Key endpoint**: `POST /api/resources` (create) — creates row, queues `pharos:tasks`.
- **Key function**: `process_ingestion(resource_id)` in `resources/service.py`. This is the **monolithic ingestion pipeline** — fetches URL, extracts text, AI summarizes, archives, embeds resource, chunks content via ChunkingService, embeds chunks, scores quality, extracts citations. Called by the edge worker.
- **Sub-logic dir**: `resources/logic/` contains ChunkingService and related helpers.
- **Additional routers**: `chunking_router` (at `/api/chunks`), `repository_converter.py` (convert repo-level resources to their chunk rollup).

### `search/`
- **Purpose**: All retrieval endpoints.
- **Routers**: `search_router` (`/api/search/search` — basic FTS5 + filters), `advanced_search_router` (`/api/search/advanced` — three-way hybrid with RRF, parent-child strategy).
- **Key files**:
  - `hybrid_methods.py` — combine dense + sparse + keyword results.
  - `rrf.py` — Reciprocal Rank Fusion implementation.
  - `reranking.py` — cross-encoder reranker (EDGE mode only).
  - `sparse_embeddings.py` / `sparse_embeddings_real.py` — SPLADE.
  - `vector_search_real.py` — pgvector HNSW cosine similarity query builder.

### `graph/`
- **Purpose**: Knowledge graph, citations, dependency traversal.
- **Routers**: `graph_router` (entities, relationships, traversal), `citations_router`, `discovery_router` (hypothesis generation).
- **Services**: `service.py` (basic), `advanced_service.py` (multi-hop, community-aware), `neural_service.py` (graph neural net scoring).
- **Features**: entity extraction, PageRank caching, Louvain communities, Node2Vec embeddings, contradiction detection.

### `annotations/`
- **Purpose**: Precise character-offset highlights on resource text, plus notes and tags. Annotations themselves have embeddings (`annotation.embedding`) enabling semantic search across the user's highlight history.

### `collections/`
- **Purpose**: Hierarchical folders of resources. Visibility: `"private" | "shared" | "public"`. Aggregate embeddings at the collection level. Batch ops: add / remove up to 100 resources per call.
- **Note (2026-04-27)**: This module IS the recommendation system. Provides `find_similar_resources()` and `find_similar_collections()` using content-based semantic similarity (cosine distance on embeddings). Collaborative filtering (NCF) was removed, but content-based recommendations remain and are appropriate for single-tenant use.

### `quality/`
- **Purpose**: Multi-dimensional quality scoring (accuracy, completeness, consistency, timeliness, relevance → overall). Outlier detection. **`rag_evaluation_router`** at `/api/rag-evaluation` evaluates RAG pipeline quality using stored ground-truth.

### `auth/`
- **Purpose**: JWT + OAuth2. Endpoints: `/api/auth/register`, `/login`, `/refresh`, `/logout`, `/me`, `/oauth/google`, `/oauth/github`.
- **Note (2026-04-27)**: Over-engineered for single-tenant. OAuth2 and rate limiting unnecessary. See `ACTUAL_STATUS_2026_04_27.md`.

### `authority/`
- **Purpose**: Name normalization. Prevents "Jane Doe" / "J. Doe" / "Doe, Jane" from being treated as three different creators.

### `scholarly/`
- **Purpose**: Paper-specific metadata extraction and document intelligence. Extracts DOI, arXiv ID, PMID, citations, equations, tables, figures. `document_intelligence_router` provides question-answering over documents.

### `ingestion/` (module, not the router)
- Contains `ast_pipeline.py` with `HybridIngestionPipeline` class. In principle this drives GitHub-repo bulk ingestion. In practice it is **not wired to any worker today** — see file 4 for the actual pipeline.

### `mcp/`
- **Purpose**: Implements the Model Context Protocol — exposes Pharos as an MCP server so MCP-aware clients (Claude Desktop, IDEs) can query it directly.

### `patterns/` - ✅ COMPLETE (Phase 6 + Phase 8)
- **Purpose**: Extracts coding patterns from a user's indexed repos (preferred imports, error-handling styles, test patterns). Feeds Ronin's code generation prompt.
- **Key endpoints**:
  - `POST /api/patterns/learn` - Analyze repo and extract patterns (AST + Git analysis)
  - `GET /api/patterns/profiles` - List all developer profiles
  - `GET /api/patterns/profiles/{id}` - Get specific profile
  - `POST /api/patterns/propose` - Receive rule proposals from local extraction worker
  - `GET /api/patterns/rules` - List proposed rules (with status filter)
  - `PATCH /api/patterns/rules/{id}` - Accept/reject rules
- **Self-Improving Loop**: Local extraction worker polls `pharos_extraction_jobs` queue, sends diffs to local LLM, extracts structured rules, POSTs to `/api/patterns/propose`. Human reviews via `/api/patterns/rules`. Accepted rules become ACTIVE and influence code generation.
- **Tables**: `DeveloperProfileRecord`, `CodingProfile`, `ProposedRule`

### `planning/`
- **Purpose**: AI planning module. Stores multi-step planning sessions in `PlanningSession` table.

### `github/` - ✅ COMPLETE (Phase 5)
- **Purpose**: On-demand fetch of code from GitHub raw URLs. Wraps the hybrid-storage model: when a search result includes a code chunk, this module fetches the actual bytes from `github_uri`, with a 1-hour cache (`GITHUB_CACHE_TTL=3600`). Optional `GITHUB_TOKEN` to avoid rate limits.
- **Key endpoints**:
  - `POST /api/github/fetch` - Fetch single code chunk from GitHub
  - `POST /api/github/fetch-batch` - Fetch up to 50 chunks in parallel
  - `GET /api/github/health` - Module health check
- **Features**:
  - Redis caching (1-hour TTL)
  - SSRF protection (validates GitHub URLs)
  - Concurrent fetching (10 parallel requests)
  - Line range extraction (start_line to end_line)
  - Branch reference support (commit SHA or "HEAD")
- **Performance**: ~50ms per fetch (cached), ~200ms (uncached)
- **Storage savings**: 17x reduction (metadata only, code fetched on-demand)

### `pdf_ingestion/`
- **Purpose**: PDF-specific ingestion (marker / pdfplumber). Separate from web-URL ingestion because PDFs need OCR, layout parsing, equation/table extraction.

### `monitoring/`
- **Purpose**: `/api/monitoring/*` endpoints — pool-status, cache-stats, queue-sizes. Requires Redis. Conditionally registered.

---

## Models Module Registry

`backend/app/MODEL_FIELDS_REGISTRY.py` is a generated/curated file that documents every column of every model for other modules (typically LLM-facing features) to consult without importing SQLAlchemy. Used by the `/api/mcp/*` endpoints to answer "what fields does Resource have?" queries.

---

## Migrations

- Alembic config: `backend/config/alembic.ini` (and a root `backend/alembic/` directory with `versions/`).
- Apply: `alembic upgrade head -c config/alembic.ini` (auto-runs on Render deploy via `buildCommand`).
- Create: `alembic revision --autogenerate -m "desc" -c config/alembic.ini`.
- Multi-head handling: `alembic upgrade heads` (plural) is used in `render.yaml` because divergent feature branches occasionally produce multiple heads.
