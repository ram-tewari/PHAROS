# Pharos — Ingestion and Search Pipelines

> File 4 of 6. Walks through how data enters Pharos (ingestion) and how it comes back out (search/retrieval). Includes a frank "documented vs actual" section because earlier docs over-promised on the GitHub-repo ingestion path. See File 6 for evolution history.

---

## Two Redis Queues — What They Actually Do

- **`pharos:tasks`** — single-resource embedding / full-ingestion tasks. Polled by `backend/app/workers/edge.py` (and also by `backend/embed_server.py` in WSL2). Task format:
  ```json
  {"task_id": "uuid", "resource_id": "uuid"}
  ```
  When a task pops off this queue, the edge worker calls `process_ingestion(resource_id)` — the monolithic ingestion function — which does fetching, chunking, embedding, quality, and citations in one pass.

- **`ingest_queue`** — GitHub-repo bulk-ingestion tasks. Pushed by `app/routers/ingestion.py`. Task format:
  ```json
  {"repo_url": "github.com/owner/repo", "submitted_at": "...", "ttl": 86400}
  ```
  **⚠ No worker reliably consumes this queue end-to-end today.** The `backend/app/workers/repo.py` file exists but the full path from queue → clone → Resource rows → `pharos:tasks` fan-out is not wired. Documented flows that claim otherwise are aspirational.

---

## Pipeline A: Single Resource (URL / PDF / text) — WORKS

This is the pipeline that actually runs in production.

```
1. POST /api/resources  { "url": "...", "title": "..." }
      │
      ▼
2. resources/service.py creates Resource row with ingestion_status="pending"
      │
      ▼
3. Push to pharos:tasks:  {"task_id": uuid, "resource_id": uuid}
      │
      ▼
4. Edge worker (local) polls pharos:tasks  →  pulls task
      │
      ▼
5. process_ingestion(resource_id)  — monolithic, does EVERYTHING:
      • Fetch URL / read archived PDF
      • Extract text (trafilatura / readability / pdfplumber)
      • AI summary + tags (transformer call, local GPU)
      • Archive raw content
      • Generate 768-dim resource embedding  (nomic-embed-text-v1)
      • ChunkingService:
          – Split content into DocumentChunks
          – For code (if it's a repo-ingested resource): AST chunking
          – Generate per-chunk semantic_summary
          – Embed each chunk; write embedding via CAST(:p AS vector)
      • Compute quality scores (5-dim + overall)
      • Extract citations (regex + scholarly heuristics)
      • Emit events (resource.created, resource.chunked, chunk.embedded…)
      │
      ▼
6. Resource.ingestion_status = "completed"
```

Key points:
- No separate chunking worker. No per-chunk queue. Everything is done by one function inside one process (the edge worker).
- If the edge worker is offline, resources sit in `pending` state forever. There is no retry worker.
- Recovery: `backend/scripts/queue_pending_resources.py` re-pushes every pending resource onto `pharos:tasks`.

---

## Pipeline B: GitHub Repository (Bulk) — ✅ WORKING

**Status**: FULLY IMPLEMENTED AND OPERATIONAL

The actual working flow:

```
POST /api/v1/ingestion/ingest/github.com/owner/repo
      │
      ▼
Ingestion router pushes to ingest_queue
      │
      ▼
Repo worker (backend/app/workers/repo.py) polls ingest_queue
      │
      ▼
Worker clones repo, parses AST (Tree-Sitter for Python),
creates one Resource per file + one DocumentChunk per function/class/method
      │
      ▼
Chunks stored with:
  - content = NULL (no code stored)
  - github_uri = raw.githubusercontent.com URL
  - branch_reference = commit SHA or "HEAD"
  - semantic_summary = signature + docstring + deps
  - embedding = NULL (async later)
      │
      ▼
Emits resource.chunked events
      │
      ▼
Event handler queues embedding tasks to pharos:tasks
      │
      ▼
Edge worker generates embeddings on GPU
      │
      ▼
Resource.ingestion_status = "completed"
```

**Key Implementation Details**:
- Repo worker is in `backend/app/workers/repo.py` (fully functional)
- Uses Tree-Sitter for AST parsing (Python fully supported, JS/TS partial)
- Batch commits every 50 chunks for performance
- No raw code stored (17x storage reduction achieved)
- Code fetched on-demand via `/api/github/fetch` endpoint

---

## AST Pipeline — `HybridIngestionPipeline.ingest_github_repo`

Location: `backend/app/modules/ingestion/ast_pipeline.py`

Signature (approx.):

```python
async def ingest_github_repo(
    self,
    git_url: str,
    branch: str = "main",
    file_extensions: tuple[str, ...] = (".py", ".js", ".ts", ...),
    batch_size: int = 50,
) -> IngestionResult:
    # 1. Clone repo to temp dir
    # 2. Parse .gitignore; walk file tree
    # 3. Apply path exclusions (migrations/, alembic/, __generated__, lockfiles, .min.*, _pb2.py)
    # 4. For each code file:
    #    a. Create a Resource (metadata only — no source stored)
    #    b. Run Tree-Sitter parse (Python fully supported; others partial)
    #    c. Extract symbols: functions, classes, methods, top-level assignments
    #    d. For each symbol create DocumentChunk with:
    #         content        = None
    #         github_uri     = raw.githubusercontent.com URL
    #         branch_reference = commit SHA if available, else "HEAD"
    #         start_line / end_line
    #         semantic_summary = "[lang] signature: 'docstring.' deps: [...]"
    #         embedding      = None (async later)
    # 5. Batch-commit every 50 chunks
    # 6. Emit resource.created and resource.chunked events
    # 7. Mark old resources as stale (is_stale=TRUE) for this repo
    # 8. Mark newly created resources as fresh (is_stale=FALSE, last_indexed_sha=commit_sha)
```

**Path Exclusions** (added 2026-04-27): Centralized in `backend/app/utils/path_exclusions.py`:
- Directories: `migrations/`, `alembic/`, `__generated__/`, `node_modules/`, `.git/`, etc.
- File patterns: `*.lock`, `*.min.js`, `*.min.css`, `*_pb2.py`, `.generated.*`, etc.
- Wired into all three ingest paths: `repo_parser.py`, `ast_pipeline.py`, `repo_ingestion.py`

**AST Density Gate** (added 2026-04-27): Before queueing for feedback, files are checked for:
- Control-flow nodes (if/for/while/try): minimum 3 (configurable via `FEEDBACK_MIN_CONTROL_FLOW_NODES`)
- AST density: minimum 0.01 (configurable via `FEEDBACK_MIN_AST_DENSITY`)
- Drops flat dataclasses, config files, and other low-complexity code from feedback queue

**Staleness Tracking** (added 2026-04-27): At end of ingestion:
- `mark_repo_stale_by_sha(db, git_url, commit_sha)` — marks all resources from this repo with different SHA as stale
- `mark_resources_fresh(db, resource_ids, commit_sha)` — marks newly created resources as fresh with current SHA
- Search queries automatically filter out stale resources

The AST pipeline itself works (it has produced the 3 302 LangChain Resource rows). The gap is the queue consumer orchestrating when it gets called.

---

## Embedding Details

- **Model**: `nomic-ai/nomic-embed-text-v1`, 768-dim.
- **Where loaded**:
  - In **CLOUD** mode (Render): not loaded at all. Query embeddings fetched over HTTPS from the edge server.
  - In **EDGE** mode: loaded into CUDA on the RTX 4070.
- **Standalone embed server** (`backend/embed_server.py`, runs in WSL2):
  - `/embed` POST endpoint — takes `{"texts": [...]}` returns 768-dim float arrays.
  - `/health` — status.
  - Zero `app.*` imports (standalone to survive Python 3.13 Windows WMI issues and keep WSL dependency closure tight).
  - Also polls `pharos:tasks` via Upstash REST with BLPOP timeout=9 s to stay ≤10k req/day.
  - **BLPOP math**: With BLPOP timeout=9s and POLL_INTERVAL=1s, idle polling generates ~8.6k req/day (86 400 s / 10 s per cycle). Prior cycle (BLPOP=5s, POLL_INTERVAL=0.1s) generated ~21k req/day, exceeding Upstash's 10k free-tier limit.
- **Prefixes**: nomic-embed-text-v1 supports `search_document:` / `search_query:` prefixes. Pharos **does not use them** — resources in NeonDB were ingested without prefixes, so the embed server sends raw text for queries too, keeping doc and query vectors in the same space. This is documented at the top of `embed_server.py`.
- **Storage format**: embedding is a JSON list stored in a `Text` column. Read back via `CAST(embedding AS vector)` for pgvector ops. **Never use the `::vector` shorthand with SQLAlchemy + asyncpg** — it silently writes zero rows. This was the root cause of `rows_updated=1` failures in `embed_server.py`. The fix: replace all `:p::vector` with `CAST(:p AS vector)` and `CAST(:p AS uuid)` for parameter binding. Rowcount is now logged after every embedding write to catch regressions. (See `feedback_asyncpg_casts.md` for details.)
- **Sparse embeddings**: SPLADE, only in EDGE mode. Populated into `resources.sparse_embedding` and `document_chunks.sparse_embedding`. Used in the three-way hybrid search path.

---

## Search Endpoints

### `POST /api/search/search` — standard search (basic)

Handles keyword search with filters and facets.

Request body (Pydantic `SearchQuery`):
```json
{
  "query": "authentication middleware",
  "filters": {
    "classification": "004",
    "type": "code",
    "language": "python",
    "min_quality": 0.7
  },
  "sort": "-created_at",
  "limit": 20,
  "offset": 0
}
```

Backend:
- Postgres: `tsvector` + `plainto_tsquery`.
- SQLite: FTS5 virtual table.

Response: `SearchResults` with items, total, facets.

### `POST /api/search/advanced` — three-way hybrid search (primary Ronin surface)

This is the most important endpoint. Ronin hits this for context retrieval.

Request body (Pydantic `AdvancedSearchRequest`):
```json
{
  "query": "how does the auth middleware work",
  "strategy": "parent-child",
  "top_k": 5,
  "include_code": true,
  "filters": {"language": "python"}
}
```

Pipeline inside:

1. **Query embedding** (150 ms): HTTP POST to `EDGE_EMBEDDING_URL/embed`.
2. **Dense retrieval** (250 ms): pgvector HNSW cosine on `resources.embedding` (not `document_chunks.embedding`).
   - **Key change (commit c6000080)**: Prior to this commit, the code pulled every chunk and did pure-Python cosine similarity, causing 2+ minute hangs. Now uses pgvector's native HNSW index on Neon.
   - Query: `SELECT * FROM resources r WHERE r.embedding IS NOT NULL AND EXISTS (SELECT 1 FROM document_chunks WHERE resource_id = r.id) AND (r.is_stale IS NULL OR r.is_stale = FALSE) ORDER BY r.embedding <=> query_vector LIMIT 50`
   - **Why resources.embedding?** Chunks inherit their parent resource's embedding. Top-K-resources is equivalent to dedup(top-K-chunks-by-parent).
   - **EXISTS filter**: Skips stale test-ingest rows that have embeddings but no chunks (e.g., the 3 302 LangChain resources before chunking was run).
   - **Staleness filter** (added 2026-04-27): `(r.is_stale IS NULL OR r.is_stale = FALSE)` excludes outdated code from search results.
   - **Test-path penalty**: paths containing `/tests/` get +0.10 added to cosine distance to down-rank noisy test-file hits.
   - Top 50 candidates.
3. **Sparse retrieval** (parallel, if available): SPLADE lookup — currently EDGE-only.
4. **Keyword retrieval**: FTS5/tsvector for literal matches.
5. **RRF fusion** (`search/rrf.py`): merge the three ranked lists.
6. **GraphRAG expansion** (200 ms): JOIN top-k chunks → their `GraphEntity` nodes → multi-hop relationships → return top-N related chunks.
7. **Pattern matching** (100 ms): find chunks with structurally similar ASTs / imports from the user's other indexed repos.
8. **Reranker** (EDGE only, optional): cross-encoder reranks final top-20 before trimming to `top_k`.
9. **Parent-child expansion**: if `strategy="parent-child"`, for each retrieved chunk also include its parent chunk (from `ChunkLink` table) to give the LLM more surrounding context.

**Note on document_chunks.embedding**: The aspirational path is to embed each chunk individually and query `document_chunks.embedding` directly. However, the current working implementation uses resource-level embeddings with a chunk-existence gate. The 3 302 LangChain resources have `resources.embedding` populated but `document_chunks` is mostly empty, so they won't appear in search results until chunking is run for them.

**Why resource-level embeddings?**
- **Performance**: One embedding per file vs. 10-50 embeddings per file (one per function/class)
- **Storage**: 768 floats × 3 302 resources = ~10 MB vs. 768 floats × 50 000 chunks = ~150 MB
- **Query speed**: Top-K over 3 302 vectors is faster than top-K over 50 000 vectors
- **Deduplication**: Multiple chunks from the same file would otherwise dominate results

**When will chunk-level embeddings be implemented?**
- When storage/performance constraints are relaxed (e.g., move to dedicated vector DB)
- When per-chunk precision is needed (e.g., "find the exact function that does X")
- For now, resource-level + EXISTS(chunks) filter is "good enough" for Ronin's use case

**Performance implications**:
- Current: ~250ms for top-50 resources via pgvector HNSW
- Chunk-level: ~500-800ms for top-50 chunks (estimated, 15x more vectors)
- Trade-off accepted: slightly less precision for 2-3x faster retrieval

Response: `AdvancedSearchResponse` with:
- `results: list[AdvancedSearchResult]` each containing:
  - `chunk: DocumentChunkResult` (id, content / semantic_summary, metadata, github_uri, start_line, end_line, embedding_distance, rank_contribution)
  - `resource: ResourceRead`
  - `graph_path: list[GraphPathNode]` (the entities traversed)
  - `pattern_matches: list[...]` (optional)
- `method_contributions: MethodContributions` (how many items came from dense vs sparse vs keyword vs graph)

### `POST /api/context/retrieve` — Ronin-facing alias

Thin wrapper over `/api/search/advanced` with defaults tuned for the Ronin LLM context (smaller `top_k`, parent-child always on, code always included).

### Search Method Comparison and Evaluation

- `POST /api/search/compare` — runs query through all methods and returns each result set separately (for debugging / evaluation).
- `POST /api/search/evaluate` — runs a set of `EvaluationRequest` queries against ground-truth and returns `EvaluationMetrics` (MRR, nDCG, recall@k, precision@k).
- `POST /api/search/sparse/batch` — generate / refresh SPLADE sparse embeddings for a batch of resources.

---

## Quality-Assessment Pipeline (inside ingestion)

When `process_ingestion` runs, after embedding it computes five dimensions:

- `quality_accuracy` — heuristic alignment of content vs. title/summary.
- `quality_completeness` — presence of expected fields (abstract, references for papers).
- `quality_consistency` — internal consistency (ROUGE-style self-agreement).
- `quality_timeliness` — how recent the content is.
- `quality_relevance` — relevance to user's declared interests (from `UserProfile`).
- `quality_overall` — weighted sum (weights stored in `quality_weights` JSON).

Then outlier detection flags resources > 2 std deviations from the cohort mean → `is_quality_outlier=True`.

Scholarly summaries additionally get a four-dim RAG-style summary quality: coherence, consistency, fluency, relevance (stored on the Resource row).

---

## Citation Extraction

Inside `process_ingestion`, for documents that look scholarly:
- Regex + spaCy NER to find in-text citations and reference-list entries.
- Resolve DOIs / arXiv IDs via CrossRef / arXiv API.
- Store normalized records in `citations` table.
- Create `GraphEdge` rows for `CITES` relationships between resources.

---

## Known Quality Improvements (Recent Commits)

From recent git history:

- **Embed `semantic_summary` not the JSON metadata blob.** Earlier, the code was embedding the whole `chunk_metadata` JSON string (`{"github_uri": ..., "ast_node_type": ...}`) which was ~50% noise. Switching to embedding the semantic summary (signature + docstring + deps line) improved retrieval precision noticeably.
- **Test-path penalty +0.10.** `/tests/` files were dominating top-k for queries that shouldn't have returned test code. Distance penalty pushes them below production code for identical queries.
  - **Why +0.10 specifically?** Empirically determined: large enough to down-rank tests below production code for most queries, small enough that tests still appear if they're the only match.
  - **How to adjust**: Change the constant in `vector_search_real.py`: `distance = distance + 0.10 if '/tests/' in path else distance`
  - **How to disable for diagnostics**: Set penalty to `0.0` or comment out the conditional.
  - **Impact on search results**: For a query like "authentication middleware", without the penalty, 8/10 top results were test files. With the penalty, 2/10 are tests (only when they're highly relevant).
- **Windows backslash normalization.** `github_uri` was being written with `\\` on Windows ingestion runs, breaking raw.githubusercontent.com URLs. Normalized to POSIX at write time.
  - **The bug**: On Windows, `Path.as_posix()` wasn't being called, so paths like `src\\auth\\middleware.py` were stored in `chunk_metadata.github_uri`.
  - **Why this breaks URLs**: `https://raw.githubusercontent.com/owner/repo/main/src\\auth\\middleware.py` returns 404 (backslashes aren't valid URL path separators).
  - **The fix**: `github_uri = str(Path(file_path).as_posix())` at ingestion time in `ast_pipeline.py`.
  - **Impact**: All 3 302 LangChain resources had broken URLs until this fix. Re-ingestion required.
- **Non-SHA → HEAD rewrite.** Branch references like `"main"` or empty strings don't resolve on raw.githubusercontent.com for all repos; rewriting to `HEAD` always resolves to the default branch.
  - **The problem**: `https://raw.githubusercontent.com/owner/repo/main/file.py` works for public repos with a "main" branch, but fails for:
    - Repos with "master" as default branch
    - Private repos (branch names aren't public)
    - Repos where the branch was renamed or deleted
  - **The solution**: `https://raw.githubusercontent.com/owner/repo/HEAD/file.py` always resolves to the default branch, regardless of its name.
  - **Edge case**: If the branch is deleted after ingestion, the URL will 404. Accepted trade-off — we don't track branch deletions.
  - **Implementation**: In `ast_pipeline.py`, if `branch_reference` is not a 40-char hex SHA, rewrite to `"HEAD"`.
- **CAST(:p AS vector) everywhere.** The ingestion write path was using `:p::vector` postfix casts through SQLAlchemy + asyncpg, which silently wrote zero rows. Replaced with `CAST(:p AS vector)`; rowcount is now logged after every embedding write to catch regressions.

---

## Frequently-Needed Operational Commands

### Re-queue pending resources (the most common recovery)
```bash
cd backend
python scripts/queue_pending_resources.py
```

### Count pending / completed resources
```bash
curl "https://pharos-cloud-api.onrender.com/api/resources?limit=1" \
  -H "Authorization: Bearer $PHAROS_ADMIN_TOKEN" | jq '.total'
```

### Check queue sizes via Upstash REST
```bash
curl -X POST "$UPSTASH_REDIS_REST_URL" \
  -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '["LLEN","pharos:tasks"]'
```

### Start edge worker (local, consumes pharos:tasks)
```bash
cd backend
python worker.py edge
```

### Start embed server (WSL2)
```bash
cd backend
bash start_embed_wsl.sh
# or: EDGE_EMBED_PORT=8001 python embed_server.py
```

### Tail worker logs
```bash
tail -f backend/edge_worker.log
tail -f backend/embed_server.log
```

### Test search end-to-end
```bash
curl -X POST "https://pharos-cloud-api.onrender.com/api/search/advanced" \
  -H "Authorization: Bearer $PHAROS_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"authentication middleware","strategy":"parent-child","top_k":5}'
```

---

## Diagnostic Scripts

Located under `backend/scripts/`:

- `queue_pending_resources.py` — re-push every `pending` Resource to `pharos:tasks`.
- `backfill_chunk_embeddings.py` — regenerate missing chunk embeddings.
- `corpus_audit.py` — sanity-check: how many resources, how many chunks, how many with embeddings, how many with `ingestion_status='completed'`.
- `diagnose_langchain_ingestion.py` — targeted check for the LangChain bulk-ingestion test dataset.
- `check_module_isolation.py` — enforces the "zero circular dependencies between modules" rule.
- `test_app_startup.py` (in `backend/`) — verifies the app boots without ML imports in CLOUD mode.
