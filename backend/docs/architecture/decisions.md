# Architecture Decision Records

Key architectural decisions for Pharos.

## ADR-001: Vertical Slice Architecture

**Status:** Accepted (Phase 13.5)

**Context:**
The original layered architecture (routers → services → models) led to:
- Tight coupling between components
- Circular import issues
- Difficult testing
- Hard to understand feature boundaries

**Decision:**
Adopt vertical slice architecture where each feature is a self-contained module with all layers.

**Consequences:**
- ✅ High cohesion within modules
- ✅ Low coupling between modules
- ✅ Easier to understand and test
- ✅ Modules can be extracted to microservices
- ⚠️ Some code duplication between modules
- ⚠️ Requires discipline to maintain boundaries

---

## ADR-002: Event-Driven Communication

**Status:** Accepted (Phase 12.5)

**Context:**
Direct service-to-service calls created:
- Circular dependencies
- Tight coupling
- Difficult to add new features

**Decision:**
Use publish-subscribe event bus for inter-module communication.

**Consequences:**
- ✅ Loose coupling between modules
- ✅ Easy to add new subscribers
- ✅ Supports async processing
- ⚠️ Eventual consistency (not immediate)
- ⚠️ Harder to trace execution flow
- ⚠️ Need to handle event failures

---

## ADR-003: Dual Database Support

**Status:** Accepted (Phase 13)

**Context:**
SQLite is convenient for development but has limitations:
- Single writer (no concurrent writes)
- No advanced indexing
- Not suitable for production

**Decision:**
Support both SQLite (development) and PostgreSQL (production) with automatic detection.

**Consequences:**
- ✅ Easy local development
- ✅ Production-grade database option
- ✅ Automatic configuration
- ⚠️ Must maintain compatibility
- ⚠️ Some features PostgreSQL-only
- ⚠️ Migration scripts needed

---

## ADR-004: Domain Objects for Business Logic

**Status:** Accepted (Phase 11)

**Context:**
Business logic was scattered across services with primitive types, making it hard to:
- Validate business rules
- Reuse logic
- Test in isolation

**Decision:**
Create domain objects (value objects, entities) to encapsulate business logic.

**Consequences:**
- ✅ Centralized validation
- ✅ Reusable business logic
- ✅ Self-documenting code
- ✅ Easier testing
- ⚠️ More classes to maintain
- ⚠️ Mapping between layers

---

## ADR-005: Hybrid Search Strategy

**Status:** Accepted (Phase 4, enhanced Phase 8)

**Context:**
Pure keyword search misses semantic meaning. Pure vector search misses exact matches.

**Decision:**
Implement hybrid search combining:
- FTS5 keyword search (BM25)
- Dense vector search (semantic)
- Sparse vector search (SPLADE) - Phase 8
- Reciprocal Rank Fusion for combining results

**Consequences:**
- ✅ Best of both approaches
- ✅ Configurable weighting
- ✅ Better search quality
- ⚠️ Higher latency
- ⚠️ More complex implementation
- ⚠️ Requires embedding generation

---

## ADR-006: Aggregate Embeddings for Collections

**Status:** Accepted (Phase 7)

**Context:**
Collections needed semantic representation for:
- Finding similar collections
- Recommending resources to add
- Collection-based search

**Decision:**
Compute aggregate embedding as normalized mean of member resource embeddings.

**Consequences:**
- ✅ Enables collection similarity
- ✅ Supports recommendations
- ✅ Simple algorithm
- ⚠️ Must recompute on membership changes
- ⚠️ Large collections may dilute signal

---

## ADR-007: Multi-Dimensional Quality Assessment

**Status:** Accepted (Phase 9)

**Context:**
Single quality score didn't capture different aspects of resource quality.

**Decision:**
Implement 5-dimensional quality assessment:
- Accuracy (30%)
- Completeness (25%)
- Consistency (20%)
- Timeliness (15%)
- Relevance (10%)

**Consequences:**
- ✅ Granular quality insights
- ✅ Actionable improvement suggestions
- ✅ Configurable weights
- ⚠️ More complex computation
- ⚠️ Requires more storage

---

## ADR-008: Strategy Pattern for Recommendations

**Status:** Superseded / Physically Removed (Phase 21)

**Context:**
Different recommendation approaches work better for different scenarios.

**Original Decision:**
Use strategy pattern with multiple recommendation strategies:
- Collaborative filtering (NCF)
- Content-based
- Graph-based
- Hybrid (combines all)

**Supersession Rationale:**
Neural Collaborative Filtering (NCF) is mathematically useless for N=1 users — it requires a matrix of multiple users to compute collaborative signals. For a single-tenant deployment, the entire recommendations module (NCF, strategy pattern, user profile service, interaction tracking) was burning GPU cycles and codebase complexity for zero value. The module was physically removed from the codebase.

**Consequences:**
- ✅ Reduced codebase complexity (removed ~15 files, 2 celery tasks, 1 event hook)
- ✅ Eliminated PyTorch dependency for EDGE mode recommendations
- ✅ No functional loss — N=1 collaborative filtering produces identity results

---

## ADR-009: Materialized Paths for Taxonomy

**Status:** Superseded / Physically Removed (Phase 21)

**Context:**
Hierarchical taxonomy queries (ancestors, descendants) were slow with recursive queries.

**Original Decision:**
Use materialized path pattern storing full path in each node (e.g., `/science/computer-science/ml`).

**Supersession Rationale:**
The Taxonomy module (ML-based classification with active learning, BERT/DistilBERT) was physically removed alongside Recommendations and Curation as part of the single-tenant optimization. For a personal second brain, the ML classification overhead is unjustified — the Authority module's subject trees provide sufficient categorization, and the CLI provides manual tagging.

**Consequences:**
- ✅ Removed ML classification pipeline (BERT model loading, training, inference)
- ✅ Reduced startup time and memory footprint
- ✅ Authority module provides adequate categorization for N=1

---

## ADR-010: Async Ingestion Pipeline

**Status:** Accepted (Phase 3.5)

**Context:**
Content ingestion involves slow operations:
- HTTP fetching
- PDF extraction
- AI summarization
- Embedding generation

**Decision:**
Make ingestion asynchronous with status tracking.

**Consequences:**
- ✅ Fast API response
- ✅ Can process in background
- ✅ Supports batch ingestion
- ⚠️ Need status polling
- ⚠️ Error handling complexity

---

## ADR-011: Local-Heavy Edge Inference and Hybrid Code Storage for Single-Tenant Deployments

**Status:** Accepted (Phase 19-20)

**Context:**

Pharos is a single-tenant code intelligence backend designed as the memory layer for the Ronin LLM. Its core workloads — dense embedding generation, sparse vector computation, GNN training, and AST parsing — are GPU-intensive operations that would incur substantial recurring costs on cloud infrastructure. Simultaneously, its database stores metadata for hundreds of codebases, and naively including source code alongside AST summaries and embeddings would push storage requirements beyond cheap cloud database tiers.

The system needed a deployment architecture that achieves maximum retrieval accuracy while minimizing monthly cloud spend to the $7-30/mo range.

**Decision:**

Split the system into two deployment planes:

### 1. Cloud API (Control Plane) — Render Starter Tier

The FastAPI application server, PostgreSQL database (with pgvector), and Redis cache run on Render. This plane handles:

- API routing, authentication, and rate limiting
- Database queries (metadata, embeddings, graph edges)
- Context retrieval assembly (semantic search, GraphRAG traversal)
- Pattern learning endpoint serving
- GitHub API code fetching with Redis caching

**Critical constraint**: No ML libraries (PyTorch, Tree-sitter, Transformers) are loaded on the cloud instance. Memory footprint stays under 512MB.

### 2. Edge Worker (Compute Plane) — Local RTX 4070

A GPU-accelerated Python worker runs on the developer's local machine. This plane handles:

- Repository cloning and Tree-sitter AST parsing
- Dense embedding generation (nomic-embed-text-v1, 768 dimensions)
- Sparse vector computation (SPLADE)
- GNN training (PyTorch Geometric Node2Vec, 64-dim structural embeddings)
- Batch upload of computed metadata and embeddings to the cloud database

The Edge Worker polls the Cloud API for queued ingestion jobs and processes them locally at 70-90% GPU utilization.

### 3. Hybrid GitHub Storage Model

PostgreSQL stores only:
- AST node summaries (function signatures, class hierarchies, dependency edges)
- Vector embeddings (dense + sparse)
- Quality scores, graph relationships, chunk boundaries (file path, line range)

Actual source code is **not stored** in the database. When Ronin needs code content during context retrieval, Pharos fetches it from the GitHub API with parallel requests and caches results in Redis (1-hour TTL).

**Financial Analysis:**

| Component | With Cloud GPU + Full Storage | With Edge Worker + Hybrid Storage |
|-----------|-------------------------------|-----------------------------------|
| GPU compute (20 repos/mo) | $110+/mo (A10G spot) | $0 (local hardware) |
| Database storage (100 repos) | $50-100/mo (170GB+ with code) | $7-20/mo (10GB metadata only) |
| Redis | $10/mo | $0 (Upstash free tier) |
| **Monthly total** | **$170-210+/mo** | **$7-20/mo** |

**Performance Analysis:**

| Metric | Cloud GPU | Local RTX 4070 |
|--------|-----------|-----------------|
| Embedding throughput | ~500 chunks/sec (A10G) | ~450 chunks/sec (RTX 4070) |
| GNN training (1K nodes) | ~8 sec | ~10 sec |
| Network latency to DB | 0ms (co-located) | ~50ms (upload after batch) |
| Code fetch (cached) | N/A (stored locally) | <5ms (Redis hit) |
| Code fetch (uncached) | N/A | ~100ms (GitHub API) |

The RTX 4070 achieves ~90% of cloud A10G throughput at zero marginal cost. The 50ms network penalty for uploading results is amortized across batch uploads and is invisible to end-user query latency.

**Consequences:**

- ✅ **10x cost reduction**: $7-20/mo vs. $170-210+/mo for equivalent capability
- ✅ **17x storage reduction**: Metadata-only PostgreSQL fits within cheap cloud tiers
- ✅ **Zero marginal compute cost**: Local GPU handles all heavy inference
- ✅ **Near-equivalent throughput**: RTX 4070 achieves ~90% of cloud GPU performance
- ✅ **Clean separation of concerns**: Cloud handles routing and queries; Edge handles compute
- ✅ **Resilient**: Cloud API functions without Edge Worker (serves cached data); Edge Worker functions without Cloud (can queue locally)
- ⚠️ **Requires local GPU**: System depends on developer workstation for ingestion workloads
- ⚠️ **First-access code latency**: Uncached GitHub API calls add ~100ms to context retrieval (negligible within 800ms budget)
- ⚠️ **GitHub API rate limits**: 5,000 requests/hour (authenticated) — sufficient for single-tenant use, but would constrain multi-tenant deployments
- ⚠️ **Operational complexity**: Two deployment targets instead of one (mitigated by MODE-aware configuration and shared requirements base)

**Alternatives Considered:**

1. **Full cloud deployment with GPU instances**: Rejected due to $170+/mo cost for a single-tenant system. The cost-accuracy ratio is indefensible when free local hardware is available.

2. **Store all source code in PostgreSQL**: Rejected due to 17x storage inflation. A 100-repository deployment would require 170GB+ of database storage, pushing costs to $50-100/mo for PostgreSQL alone.

3. **Use a separate object store (S3) for code**: Rejected due to added infrastructure complexity and cost ($5-10/mo for S3 + egress) when GitHub already stores the code for free with an API that supports parallel fetching.

4. **ML-based pattern extraction instead of 14-Day Temporal Sieve**: Rejected due to zero available labeled training data, ongoing MLOps overhead, and the availability of a deterministic signal (git commit timestamps + diff sizes) that achieves 90%+ accuracy with zero maintenance cost.

---

## ADR-012: Perimeter Defense Auth for Single-Tenant React SPA

**Status:** Accepted (Phase 21)

**Context:**
After removing Recommendations, Curation, and Taxonomy, the Auth module's original purpose — user management, tiered access, public signups — no longer applies. However, Pharos serves a React SPA frontend on the public internet via Render, exposing the FastAPI backend to bots, scrapers, and unauthorized API consumers that could drain database connections and rack up costs.

**Decision:**
Keep the Auth module but repurpose it strictly as **perimeter defense**:
- Disable the `/auth/register` (signup) route — no public registration
- Keep the `/auth/login` route for the single admin account
- Keep JWT token validation middleware on all non-public endpoints
- Keep rate limiting via Redis to prevent abuse
- Keep OAuth2 (Google, GitHub) as optional admin login methods

The Auth module no longer manages tiers, roles, or multiple user accounts. It exists solely to ensure that only authenticated requests from the admin account can reach the API.

**Consequences:**
- ✅ API is protected from public internet traffic (bots, scrapers, unauthorized access)
- ✅ Database connections cannot be drained by unauthenticated requests
- ✅ Zero additional infrastructure cost — reuses existing JWT + Redis stack
- ✅ React SPA has a clean auth flow (login → token → authenticated API calls)
- ⚠️ Single point of failure if the admin account is compromised (mitigated by bcrypt + OAuth2 + token rotation)

---

## ADR-013: Edge-Funnel Query Embedding via Tailscale

**Status:** Accepted (2026-04-18)

**Context:**

ADR-011 established that Render's 512 MB instance cannot load ML libraries.
The ingestion path (edge → Redis → NeonDB) works correctly, but the search
query path was broken: `_execute_dense_search` called
`EmbeddingService.generate_embedding(query)` on the cloud instance, which
returned an empty list in CLOUD mode because `_ensure_loaded()` skips model
loading. This produced silent zero-result searches.

A `force_load_in_cloud` stopgap parameter was added to bypass the CLOUD guard
for query embeddings, but this caused the cloud instance to attempt loading
`nomic-embed-text-v1` (~600 MB), OOM-killing the process.

The system needed a way for Render to get query embeddings on demand without
loading any ML library locally.

**Decision:**

Run a standalone FastAPI process (`embed_server.py`) on the developer's laptop
that loads `nomic-ai/nomic-embed-text-v1` once at startup and serves
`POST /embed {"text":"…"} → {"embedding":[768 floats]}` on port 8001.

Expose this endpoint publicly via **Tailscale Funnel** at a stable
`https://<machine>.<tailnet>.ts.net` hostname. Render's search service calls
this URL synchronously during query handling (5 s timeout), then runs cosine
similarity against stored NeonDB vectors.

Key implementation details:

- `embed_server.py` is a separate process from both ingestion workers; it does
  not touch Redis or the task queue. The model is loaded once at uvicorn
  startup, shared across all requests.
- `EDGE_EMBEDDING_URL` env var on Render holds the Funnel hostname. Missing or
  unreachable → HTTP 503 surfaced to the caller (not silent empty results).
- The outer `except Exception: return []` in `_execute_dense_search` was
  removed. DB/network/Funnel failures now raise `HTTPException(503)` so Ronin
  sees a clear error rather than an empty result set.
- `force_load_in_cloud` removed from `EmbeddingGenerator` and `EmbeddingService`.
  CLOUD mode always skips local model loading; all query embeddings go through
  the Funnel endpoint.

**Nomic prefix note:** `nomic-embed-text-v1` supports `search_document:` /
`search_query:` prefixes for improved retrieval performance. However, documents
in NeonDB were ingested without any prefix (raw composite text). Query
embeddings must therefore also omit the prefix to land in the same embedding
space. Adding prefixes would require re-embedding all stored documents.

**Tailscale Funnel over Cloudflare Tunnel:** Cloudflare's free stable hostname
requires a paid registered domain. Tailscale Funnel provides a free
`*.ts.net` hostname with no domain purchase. Funnel configuration persists
in `tailscaled` state across reboots; the `tailscale funnel 8001` CLI command
is a one-time setup step, not a persistent process to manage.

**Consequences:**

- ✅ **Search works in production**: queries return real results instead of silent []
- ✅ **Zero ML dependencies added to Render**: `requirements-cloud.txt` unchanged
- ✅ **Clear errors on Funnel outage**: 503 propagates to Ronin; no silent failures
- ✅ **Same model both sides**: embedding space consistency guaranteed
- ✅ **Cost**: $0 — Tailscale Funnel free tier, local hardware
- ⚠️ **Laptop dependency for search**: queries fail if laptop is off or asleep
  (acceptable: Ronin is only used when the developer is active)
- ⚠️ **Cold start**: first query after `PharosEmbedServer` restart takes ~5 s
  (model load); subsequent queries ~50 ms
- ⚠️ **Funnel is a dependency**: if Tailscale services are down, search is down

**Alternatives Considered:**

1. **Hosted embedding API (OpenAI, Voyage AI, Cohere)**: Rejected — per-request
   cost at query time, vendor dependency, and documents would need re-embedding
   with the hosted model to maintain embedding space consistency.

2. **Small CPU-only model on Render**: Rejected — a model small enough to fit
   in 512 MB (e.g., `all-MiniLM-L6-v2`, 384 dims) produces a different
   embedding space than the `nomic-embed-text-v1` vectors already stored.
   Re-embedding all documents would be required, and search quality would
   degrade.

3. **Cloudflare Tunnel**: Rejected — free stable hostnames require a paid
   registered domain. Tailscale Funnel provides the same capability at zero
   cost via `*.ts.net`.

4. **Bolt HTTP onto existing ingestion workers**: Rejected — both
   `backend/edge_worker.py` (sync polling loop) and `backend/app/edge_worker.py`
   (asyncio polling loop) have no HTTP server in their event loop. Attaching
   uvicorn would require invasive restructuring of both workers' run loops.
   A separate 60-line FastAPI file is the minimal, clean solution.

---

## ADR-014: Data Structures & Algorithms Applied (Existing)

**Status:** Accepted (documented 2026-04-20)

**Context:**

Several hot paths in Pharos already rely on classic DSA primitives. These were introduced incrementally as the ingestion, search, and graph modules grew. Recording them here preserves the reasoning so future refactors don't regress the complexity guarantees.

**Existing Applications:**

### 1. Hash maps / sets — O(1) score accumulation and deduplication

- [modules/search/rrf.py:49](../../app/modules/search/rrf.py#L49) — `defaultdict(float)` accumulates RRF contributions across ranked lists in a single pass. Without it, repeated linear scans of each list would make fusion O(N²).
- [modules/search/service.py](../../app/modules/search/service.py) — `seen_resources` / `seen_chunks` sets dedupe parent resources and synthetic-question matches in O(1) per probe.
- [modules/graph/service.py](../../app/modules/graph/service.py) — chunk-score dicts in GraphRAG walks accumulate the best score seen per chunk without re-sorting.

### 2. BFS with visited set — multi-hop graph traversal

- [modules/graph/service.py:1054](../../app/modules/graph/service.py#L1054) — `_get_two_hop_neighbors` maintains `visited = {resource_id}` to avoid revisiting nodes while expanding the citation / call graph. Textbook BFS idea: each node is processed at most once, so 2-hop expansion stays O(V + E) within the reachable frontier.

### 3. Recursive tree traversal (pre-order DFS) — AST walking

- [modules/graph/logic/static_analysis.py](../../app/modules/graph/logic/static_analysis.py) — the `traverse(node)` closures used for import / definition / call extraction are recursive pre-order DFS walks over the Tree-Sitter AST. Recursion mirrors the natural recursive structure of syntax trees.

### 4. Adjacency-list graph representation — NetworkX

- [modules/graph/service.py:1152](../../app/modules/graph/service.py#L1152) — `build_multilayer_graph` returns a `networkx.MultiDiGraph`, which stores edges as adjacency lists under the hood. This is the representation we studied for sparse graphs; it makes neighbor iteration O(deg(v)) rather than O(V) as a matrix would.
- Centrality methods (`compute_degree_centrality`, `compute_betweenness_centrality`) ride on top of this representation and use Dijkstra-style priority-queue algorithms inside NetworkX for weighted shortest paths.

### 5. FIFO queue — task dispatch

- [services/queue_service.py](../../app/services/queue_service.py) — ingestion jobs are queued via Redis `rpush` and consumed via `lpop`, giving standard FIFO queue semantics for the edge worker.

### 6. Sort-by-score — result ranking

- [modules/search/rrf.py:56](../../app/modules/search/rrf.py#L56), [modules/search/service.py:239](../../app/modules/search/service.py#L239), [:484](../../app/modules/search/service.py#L484), [:797](../../app/modules/search/service.py#L797) — candidate lists are ranked with `sorted(..., reverse=True)`. Timsort runs in O(N log N). See ADR-015 for the follow-up optimization that replaces sort-then-slice with a bounded heap for top-K workloads.

**Consequences:**

- ✅ Every query-time hot loop that needs membership / dedup / accumulation uses a hash-backed container (O(1) per probe) rather than linear scans.
- ✅ The graph layer uses the right representation (adjacency list) and the right traversal primitive (BFS with visited set) for citation / call expansion.
- ✅ NetworkX handles the weighted-graph algorithms (Dijkstra-backed centrality) so we don't reimplement them.
- ⚠️ Recursive AST traversal is bounded by Python's default recursion limit (~1000). Superseded by ADR-015 §3 (iterative DFS).
- ⚠️ Sort-then-slice for top-K pays O(N log N) when only O(N log K) is needed. Superseded by ADR-015 §1.

---

## ADR-015: DSA-Driven Performance Optimizations (Search, Queue, AST)

**Status:** Accepted (2026-04-20)

**Context:**

ADR-014 audited the existing DSA footprint and surfaced three places where the complexity characteristics of the code did not match the workload:

1. **Top-K ranking** — search and RRF code paths called `sorted(...)` on the full candidate list and then sliced `[:top_k]`. For N candidates and top_k = K, this is O(N log N) when O(N log K) is sufficient.
2. **Job-status lookup** — `QueueService.get_job_status`, `update_job_status`, and `get_queue_position` each did `LRANGE 0 -1` and linearly scanned every JSON blob in the Redis queue looking for a matching `job_id`. Cost: O(n) per lookup, n = queue size.
3. **AST traversal** — every per-language import / definition / call extractor in `static_analysis.py` used a recursive `traverse(node)` closure. On deeply nested inputs (long JSX trees, chained method calls, macro-expanded Rust) this can exceed Python's default recursion limit of ~1000 frames and raise `RecursionError`.

Each of these maps cleanly onto a DSA primitive studied in a standard DSA course.

**Decision:**

### 1. Heap-based top-K ranking

Replace `sorted(items, key=..., reverse=True)[:k]` with `heapq.nlargest(k, items, key=...)` in the three hot paths:

- `ReciprocalRankFusionService.fuse` ([modules/search/rrf.py](../../app/modules/search/rrf.py)) — accepts an optional `top_k` parameter; when set, returns the K highest-scoring fused results without sorting the full dict.
- `SearchService.parent_child_search` ([modules/search/service.py:239](../../app/modules/search/service.py#L239)) — uses `heapq.nlargest` over `(chunk, score)` pairs.
- GraphRAG chunk-score ranking ([modules/search/service.py:484](../../app/modules/search/service.py#L484)) — uses `heapq.nlargest` over the chunk-score dict items.
- Synthetic-question ranking ([modules/search/service.py:797](../../app/modules/search/service.py#L797)) — same transformation.

`heapq.nlargest(k, ...)` maintains a size-K min-heap: O(N log K) time, O(K) space. This is the priority-queue / downward-heapify pattern — when a new element beats the current root, sift down once.

### 2. Redis hash for O(1) job-status lookup

Introduce a secondary Redis hash `pharos:jobs` keyed by `job_id` containing the latest JSON representation of each job. The queue list continues to hold job order for FIFO dispatch; the hash provides O(1) metadata access:

- `submit_job` — `HSET pharos:jobs {job_id} {json}` alongside `RPUSH pharos:tasks`.
- `get_job_status` — `HGET pharos:jobs {job_id}` first (O(1)); only fall back to the history list on miss.
- `update_job_status` — `HGET` the job, mutate, `HDEL` on terminal status, `LREM` from queue, `LPUSH` to history.
- `get_queue_position` — still O(n) (position is an ordering property), but the hash lookup short-circuits when the job has already completed.
- `clear_queue` — also deletes the hash.

This is the classic "secondary hash index" pattern: keep the ordered structure for iteration, add a hash for constant-time random access by key.

### 3. Iterative DFS for AST traversal

Replace the recursive `traverse(node)` closures in `StaticAnalysisService` with an explicit-stack iterative DFS via a shared `_iter_nodes(root_node)` helper. Each extractor becomes a single `for node in self._iter_nodes(root_node): ...` loop. The traversal order is unchanged (pre-order), but Python's recursion limit no longer bounds the usable AST depth.

This is the textbook "convert recursion to iteration with an explicit stack" transform: `stack = [root]; while stack: node = stack.pop(); stack.extend(reversed(node.children))`.

**Consequences:**

- ✅ **Top-K search ranking is O(N log K) instead of O(N log N)**. For N ≈ 2000 chunks and K = 10, theoretical speedup ~2× on the ranking step; measured dominates when paired with the avoided full-materialization of sorted output.
- ✅ **Job-status lookup is O(1) instead of O(n)** in queue size. Pending queues of 100+ jobs no longer pay a linear-scan penalty on every Ronin status probe.
- ✅ **AST traversal no longer raises RecursionError** on deep syntax trees. Long JSX / TSX files and deeply nested Rust macros parse reliably.
- ✅ Every optimization maps 1:1 to a named DSA primitive (min-heap / priority queue, hash table, iterative DFS with explicit stack), so the reasoning is teachable and the complexity claims are auditable.
- ⚠️ The Redis hash adds one extra write per submit / update. The amortized write cost (~O(1) per op) is negligible compared to the O(1) read savings on every Ronin status poll.
- ⚠️ `heapq.nlargest` is marginally slower than `sorted(...)[:k]` when K ≈ N (i.e., top_k asks for almost everything). All Pharos call sites have K ≪ N, so this edge case does not apply.

**Alternatives Considered:**

1. **Keep `sorted(...)[:k]` and rely on Timsort's fast path for mostly-sorted input**: rejected. The input is the output of score accumulation, which is unordered; there is no fast path.
2. **Paginate the Redis queue (`LRANGE 0 99`) instead of adding a hash**: rejected. This caps worst-case latency but still makes the common case O(n) for jobs past the page boundary, and misses genuinely old pending jobs entirely.
3. **Raise Python's `sys.setrecursionlimit`**: rejected. It papers over the issue, still risks C-stack overflow on very deep trees, and burns memory per-frame. Explicit-stack iteration is the correct fix.

---

## Decision Template

```markdown
## ADR-XXX: [Title]

**Status:** [Proposed | Accepted | Deprecated | Superseded]

**Context:**
[What is the issue that we're seeing that is motivating this decision?]

**Decision:**
[What is the change that we're proposing and/or doing?]

**Consequences:**
[What becomes easier or more difficult to do because of this change?]
- ✅ Positive consequence
- ⚠️ Trade-off or risk
```

## Related Documentation

- [Architecture Overview](overview.md) - System design
- [Modules](modules.md) - Vertical slice details
- [Event System](event-system.md) - Event-driven communication
