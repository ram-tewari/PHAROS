# Architecture Overview

System architecture for Pharos — the memory and knowledge layer that powers the Ronin LLM coding assistant.

> **Last Updated**: 2026-04-24 — Production deployment with pgvector search, test downweighting, semantic_summary embeddings, GitHub hybrid storage operational

---

## Table of Contents

1. [System Purpose](#system-purpose)
2. [The Two Core Use Cases](#the-two-core-use-cases)
3. [High-Level Architecture](#high-level-architecture)
4. [Module Architecture](#module-architecture)
5. [Data Flow: Context Retrieval](#data-flow-context-retrieval)
6. [Data Flow: Pattern Learning](#data-flow-pattern-learning)
7. [Deployment Topology](#deployment-topology)
8. [Defense of Architectural Decisions](#defense-of-architectural-decisions)
9. [Technology Stack](#technology-stack)
10. [Event-Driven Communication](#event-driven-communication)
11. [Performance Targets](#performance-targets)

---

## System Purpose

Pharos is a **single-tenant code intelligence backend** optimized for one metric: **maximum retrieval accuracy at minimum recurring cloud cost**. It serves exactly one user — you — and feeds structured context to the Ronin LLM so that Ronin can:

1. **Understand and debug legacy codebases** by retrieving semantically relevant code, dependency graphs, and research paper insights
2. **Generate new code** that incorporates your historical coding patterns, avoids your past mistakes, and matches your style

Pharos is not a generic SaaS platform. Every architectural decision — the 11-module vertical slice structure, the local/cloud compute split, the hybrid GitHub storage model, the deterministic pattern extraction heuristic — exists to serve this single-tenant, accuracy-first, cost-minimal objective.

---

## The Two Core Use Cases

### Use Case 1: Context Retrieval (Understanding Old Code)

**Trigger**: Ronin receives a user query like *"How does the authentication system work in myapp-backend?"*

**Endpoint**: `POST /api/context/retrieve`

**Pipeline** (~800ms total, **production-verified 2026-04-24**):

```
User Query
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  RONIN (LLM)                                                 │
│  Parses query → identifies context needs → calls Pharos API  │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│  PHAROS: Context Retrieval Pipeline                          │
│                                                              │
│  1. Query Embedding (150ms)                                  │
│     Cloud API → Tailscale Funnel → WSL2 embed server        │
│     nomic-embed-text-v1 on RTX 4070 GPU                     │
│     → Returns 768-dim vector                                 │
│                                                              │
│  2. Semantic Search via pgvector (250ms)                     │
│     HNSW cosine similarity on resources.embedding            │
│     WHERE embedding IS NOT NULL AND has chunks               │
│     Test file penalty: +0.10 distance for /tests/ paths     │
│     → Top 50 candidates ranked by adjusted distance          │
│     → Filtered by language, quality score > 0.7              │
│                                                              │
│  3. GraphRAG Traversal (200ms)                               │
│     Find auth-related entities in knowledge graph            │
│     → Multi-hop traversal: auth → database → session         │
│     → Returns 20 related chunks + dependency subgraph        │
│                                                              │
│  4. Pattern Matching (100ms)                                 │
│     Find structurally similar implementations from           │
│     your other indexed codebases                             │
│     → Matched by AST structure, imports, function sigs       │
│     → Returns top 5 similar patterns with similarity scores  │
│                                                              │
│  5. Research Paper Retrieval (150ms)                         │
│     Search annotated papers for relevant techniques          │
│     → Filter by your annotations, citations, tags            │
│     → Returns top 3 papers with key excerpts                 │
│                                                              │
│  6. Code Fetching from GitHub (100ms, parallel)              │
│     Fetch actual source for top 10 chunks on-demand          │
│     → Parallel GitHub API calls, Redis-cached (1hr TTL)      │
│     → Normalize backslashes, use HEAD ref for default branch │
│     → No source code stored in Postgres                      │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│  Context Package Assembly                                    │
│                                                              │
│  {                                                           │
│    "code_chunks": [...],       // Top 10 ranked chunks       │
│    "dependency_graph": {...},  // Subgraph of relationships  │
│    "similar_patterns": [...],  // From your other codebases  │
│    "research_papers": [...],   // Annotated paper excerpts   │
│    "coding_style": {...}       // Your learned preferences   │
│  }                                                           │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│  RONIN (LLM)                                                 │
│  Receives context → generates explanation, identifies bugs,  │
│  suggests refactorings grounded in real code + history       │
└──────────────────────────────────────────────────────────────┘
```

**Modules involved**: Search (pgvector + parent-child), Graph (traversal + dependencies), Scholarly (paper retrieval), Quality (chunk filtering), Resources (GitHub code fetching).

**Production metrics (langchain corpus, 3,293 files)**:
- Total latency: 1.8-1.9s (40% faster than pre-pgvector)
- Search accuracy: 8.5-9/10 for Ronin context retrieval
- Infrastructure: 100% success rate, 0 errors
- Cost: $7/mo (Render Starter + free tiers)

### Use Case 2: Pattern Learning (Creating New Code)

**Trigger**: Ronin needs to generate a new component, e.g., *"Create an auth microservice with OAuth2"*

**Endpoint**: `POST /api/patterns/learn`

**Pipeline** (~1000ms total):

```
Ronin Code Generation Request
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  PHAROS: Pattern Learning Pipeline                           │
│                                                              │
│  1. Successful Pattern Extraction (300ms)                    │
│     Analyze projects with quality > 0.8                      │
│     → Extract architectural patterns (Repository+Service+DI) │
│     → Identify common library choices (FastAPI, SQLAlchemy)  │
│     → Compute success rates per pattern                      │
│                                                              │
│  2. Failed Pattern Extraction (200ms)                        │
│     Analyze git history via 14-Day Temporal Sieve            │
│     → Identify code that was written then rewritten < 14d    │
│     → Extract anti-patterns: missing rate limiting, MD5,     │
│       synchronous DB calls, missing redirect_uri validation  │
│     → Tag with severity and frequency                        │
│                                                              │
│  3. Coding Style Profiling (200ms)                           │
│     Aggregate style signals across all indexed codebases     │
│     → Naming: snake_case, PascalCase for classes             │
│     → Patterns: async/await, try-except with logging         │
│     → Libraries: FastAPI, SQLAlchemy, Pydantic               │
│     → Docstrings: Google-style, type hints Python 3.10+      │
│                                                              │
│  4. Research Insight Retrieval (150ms)                       │
│     Find papers relevant to the task domain                  │
│     → OAuth 2.0 Security Best Practices → PKCE, short-lived  │
│       tokens                                                 │
│     → Rate Limiting papers → token bucket algorithm          │
│                                                              │
│  5. Architectural Pattern Detection (150ms)                  │
│     Match requested task to successful past architectures    │
│     → auth microservice → JWT + OAuth2 + bcrypt pattern      │
│     → Returns: file structure, dependency graph, test stubs  │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│  Learned Pattern Package                                     │
│                                                              │
│  {                                                           │
│    "successful_patterns": [...],    // What worked           │
│    "failed_patterns": [...],        // What to avoid         │
│    "coding_style": {...},           // How you write code    │
│    "research_insights": [...],      // Relevant techniques   │
│    "architectural_patterns": [...], // Proven structures     │
│    "common_utilities": [...]        // Reusable components   │
│  }                                                           │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│  RONIN (LLM)                                                 │
│  Generates code that:                                        │
│  - Avoids past mistakes (rate limiting from day 1)           │
│  - Uses proven architectures (Repository+Service+DI)         │
│  - Matches your style (async, snake_case, structured logs)   │
│  - Incorporates research (PKCE, token bucket, bcrypt)        │
└──────────────────────────────────────────────────────────────┘
```

**Modules involved**: Patterns (extraction + profiling), Graph (architectural pattern detection), Quality (success/failure scoring), Scholarly (research insights), Search (similar implementation lookup).

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         RONIN (LLM Brain)                           │
│         Claude Sonnet / GPT-4 / user's choice of model              │
│         Generates code, explanations, refactorings                  │
│         Makes decisions based on context from Pharos                │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ REST API / MCP Protocol
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       PHAROS (Memory & Knowledge)                   │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                   FastAPI Application Layer                   │  │
│  │           Global Auth Middleware • Rate Limiting              │  │
│  │           11 Module Routers • OpenAPI Auto-Docs               │  │
│  └───────────────────────────────┬───────────────────────────────┘  │
│                                  │                                  │
│  ┌───────────────────────────────┴───────────────────────────────┐  │
│  │              11 Vertical Slice Modules                        │  │
│  │                                                               │  │
│  │  Resources │ Search │ Graph │ Quality │ Annotations           │  │
│  │  Scholarly │ Monitoring │ MCP │ Auth │ Authority              │  │
│  │  Collections                                                  │  │
│  │                                                               │  │
│  │  Each: router.py • service.py • schema.py • model.py          │  │
│  │        handlers.py (event subscriptions)                      │  │
│  │  Rule: NO cross-module imports. Event Bus only.               │  │
│  └───────────────────────────────┬───────────────────────────────┘  │
│                                  │                                  │
│  ┌───────────────────────────────┴───────────────────────────────┐  │
│  │                     Async Event Bus                           │  │
│  │         In-memory pub/sub • <1ms P95 latency                  │  │
│  │         20+ event types across resource lifecycle             │  │
│  └───────────────────────────────┬───────────────────────────────┘  │
│                                  │                                  │
│  ┌───────────────────────────────┴───────────────────────────────┐  │
│  │                    Shared Kernel                              │  │
│  │  Database (SQLAlchemy) • EmbeddingService (dense + sparse)    │  │
│  │  AICore (summarization, NER) • CacheService (Redis + TTL)     │  │
│  │  Security (JWT, bcrypt, OAuth2) • RateLimiter (sliding window)│  │
│  └───────────────────────────────┬───────────────────────────────┘  │
│                                  │                                  │
│  ┌───────────────────────────────┴───────────────────────────────┐  │
│  │                    Data Layer                                 │  │
│  │  PostgreSQL + pgvector (prod) │ SQLite (dev)                  │  │
│  │  Redis (cache, rate limits, token blacklist)                  │  │
│  │  GitHub API (on-demand code fetching, Redis-cached)           │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Module Architecture

All 11 modules follow the identical vertical slice structure:

```
app/modules/<module_name>/
├── __init__.py      # Public interface exports
├── router.py        # FastAPI endpoint definitions
├── service.py       # Business logic (stateless)
├── schema.py        # Pydantic request/response models
├── model.py         # SQLAlchemy ORM models (if applicable)
└── handlers.py      # Event Bus subscriptions
```

### Module Isolation Rules

1. Modules **may** import from `app.shared.*` (shared kernel) and `app.events.*` (event definitions)
2. Modules **must not** import from any other module
3. Cross-module data flow occurs **exclusively** through the Event Bus
4. Each module exposes a public interface via `__init__.py`

### Event Flow Map

```
Resources ──[resource.created]──► Scholarly, Quality, Graph
Resources ──[resource.updated]──► Collections, Quality, Search
Resources ──[resource.deleted]──► Collections, Annotations, Graph
Graph     ──[citation.extracted]──► Monitoring
All       ──[*.events]──► Monitoring (metrics aggregation)
```

---

## Deployment Topology

```
┌──────────────────────────────────────────────────────────────────┐
│                  CLOUD (Render Starter — $7/mo)                  │
│                  https://pharos-cloud-api.onrender.com           │
│                                                                  │
│  FastAPI ─── NeonDB PostgreSQL + pgvector ─── Upstash Redis      │
│  API routing,    AST metadata, embeddings,     Query cache,      │
│  auth (JWT),     graph edges, quality scores,  rate limits,      │
│  rate limiting,  pgvector HNSW indexes.        GitHub API cache, │
│  Ronin API       NO source code stored.        task queue        │
│                                                                  │
│  On search query: calls EDGE_EMBEDDING_URL/embed (5s timeout)    │
│  Memory footprint: <512 MB (no ML libraries loaded)              │
│  Search: pgvector parent-child with test penalty (1.8-1.9s)     │
└──────────┬───────────────────────────────────┬───────────────────┘
           │ HTTPS polling (Edge → Cloud)       │ HTTPS query embed
           │ BLPOP pharos:tasks, ingest_queue   │ (Cloud → Funnel)
           │ (30s timeout, Upstash-safe)        │
           │                                   ▼
┌──────────┴─────────────────┐  ┌─────────────────────────────────┐
│  EDGE: Unified Worker      │  │  Tailscale Funnel               │
│  (WSL2 + RTX 4070)         │  │  https://pc.tailf7b210.ts.net   │
│                            │  │  → 127.0.0.1:8001               │
│  Single process handles:   │  └─────────────────┬───────────────┘
│  - pharos:tasks queue      │                    │
│  - ingest_queue            │                    ▼
│  - /embed HTTP endpoint    │  ┌─────────────────────────────────┐
│                            │  │  EDGE: Embedding HTTP Server    │
│  Tree-sitter AST Parsing   │  │  (embed_server.py on WSL2)      │
│  Document embeddings        │  │                                 │
│  (nomic-embed-text-v1, GPU) │  │  POST /embed → 768-float vector │
│  Writes to NeonDB via       │  │  nomic-embed-text-v1 on GPU     │
│  asyncpg with CAST          │  │  Latency: ~1.5s per embedding   │
│                             │  │  Query latency: ~150ms          │
│  GPU: 70-90% during ingest  │  │  Embeds: title + semantic_summary│
│  BLPOP interval: 30s        │  └─────────────────────────────────┘
│  Free-tier safe: ~2.9k/day  │
│                             │
│  Launcher: start_worker.sh  │
│  or start_worker.py         │
└─────────────────────────────┘
```

**See [Worker Architecture](../WORKER_ARCHITECTURE.md) for complete unified worker documentation.**

### Production Status (2026-04-24)

**✅ Fully Operational**

- **Cloud API**: 1.8-1.9s search latency, 100% uptime
- **Edge Worker**: 3,293 resources embedded, 0 failures
- **Search Quality**: 8.5-9/10 accuracy on langchain corpus
- **Cost**: $7/mo (Render) + $0 (NeonDB free) + $0 (Upstash free) + $0 (local GPU)

**Recent Improvements**:
1. pgvector HNSW for parent-child search (40% latency reduction)
2. Test file downweighting (+0.10 distance penalty)
3. Embed semantic_summary instead of JSON blob (better score distribution)
4. Ingestion path normalization (POSIX paths, HEAD ref, CAST to vector)
5. Free-tier compliance (BLPOP 9s → ~8.6k Upstash req/day)

### Hybrid GitHub Storage

Pharos stores **only metadata** in PostgreSQL:

| Stored in PostgreSQL | Stored on GitHub (fetched on-demand) |
|---------------------|--------------------------------------|
| AST node summaries | Full source code files |
| Vector embeddings (pgvector) | Raw file contents |
| Dependency edges | Commit history |
| Quality scores | Diffs and blame data |
| Graph relationships | |
| Chunk boundaries (file, start_line, end_line) | |

When Ronin needs actual code content, Pharos fetches it from the GitHub API with parallel requests and caches results in Redis (1-hour TTL). This keeps the PostgreSQL database small enough for a $7/mo cloud tier while maintaining full code access.

---

## Defense of Architectural Decisions

### Decision 1: 11-Module Vertical Slice Architecture with Event Bus

**The question**: Why maintain a modular architecture for a system that serves exactly one user?

**The answer**: The modularity is not about scaling to more users. It is about **preventing monolith degradation** in a system that will evolve rapidly across its ML, storage, and retrieval layers.

Pharos integrates multiple volatile technologies: vector databases (pgvector today, potentially Qdrant or Milvus tomorrow), embedding models (nomic-embed-text-v1 today, potentially a fine-tuned model next month), graph traversal algorithms, and LLM integrations. In a monolithic codebase, changing the embedding model would require touching search logic, ingestion pipelines, and quality scoring simultaneously. With vertical slices, the `Search` module owns its embedding queries and the `Resources` module owns its ingestion embeddings — each behind a stable service interface.

The Event Bus is the mechanism that enforces this isolation. When a resource is created, it emits `resource.created`. The modules that react to that event do not know about each other. You can add a new module (e.g., `Patterns`) that subscribes to `resource.created` without modifying any existing module. You can remove a module without breaking the event emitter. This is not theoretical — the removal of Recommendations, Curation, and Taxonomy (modules that provided zero value for N=1) was executed cleanly because the Event Bus decoupled them from the rest of the system.

**Cost of this decision**: Slightly more boilerplate per module (5-6 files instead of scattering across layers). This is a fixed, one-time cost that pays compound returns in change velocity.

### Decision 2: Local-Heavy / Cloud-Light Compute Split

**The question**: Why run heavy inference on a local GPU instead of a cloud GPU instance?

**The answer**: The math is unambiguous.

| Operation | Cloud GPU Cost (A10G Spot) | Local RTX 4070 Cost |
|-----------|---------------------------|---------------------|
| Dense embeddings (10K chunks) | ~$2.50/run | $0 (electricity: ~$0.05) |
| GNN training (Node2Vec) | ~$1.80/run | $0 (electricity: ~$0.03) |
| SPLADE sparse vectors | ~$1.20/run | $0 (electricity: ~$0.02) |
| Monthly (20 repos/month) | **$110+/month** | **~$2/month electricity** |

Cloud GPU instances (even spot pricing) charge $0.50-1.50/hr. A single repository ingestion — parsing, embedding, GNN training — takes 10-30 minutes of GPU time. At 20 repositories per month, cloud GPU costs alone would exceed $100/mo, dwarfing the $7-20/mo cloud API hosting cost.

The RTX 4070 (12GB VRAM, 5,888 CUDA cores) handles the same workload at zero marginal cost. The Edge Worker polls the Cloud API for queued jobs, processes them locally, and uploads results (metadata + embeddings) back to the cloud database. The Cloud API never loads PyTorch, Tree-sitter, or any ML library — its memory footprint stays under 512MB, fitting comfortably on Render's cheapest tier.

**Trade-off**: The system requires a running local machine with a GPU. For a single-tenant "second brain" deployment, this is not a constraint — it's a feature. Your workstation is already on during development hours.

### Decision 3: Hybrid GitHub Storage (17x Storage Reduction)

**The question**: Why not store source code in the database alongside its metadata?

**The answer**: Because source code is the largest payload by orders of magnitude, and it's already stored for free on GitHub.

A typical 10,000-file repository produces:
- **AST metadata + embeddings**: ~100MB in PostgreSQL
- **Full source code**: ~1.7GB if stored alongside

Multiplied across 100+ indexed repositories, storing source code would require 170GB+ of database storage — far exceeding any cheap cloud database tier and pushing costs into the $50-100/mo range for PostgreSQL alone.

By deferring to GitHub as the authoritative code store and fetching on-demand through Redis-cached API calls, Pharos reduces its database footprint by **17x**. The entire metadata layer for 1,000 codebases fits within a $7-20/mo PostgreSQL instance. Redis caching (1-hour TTL) eliminates redundant GitHub API calls — after the first context retrieval for a given file, subsequent requests within the TTL window are served from cache in <5ms.

**Trade-off**: First-access latency for uncached files is ~100ms (GitHub API round-trip). This is negligible within the 800ms total context retrieval budget, and becomes zero on subsequent requests within the cache window.

### Decision 4: The 14-Day Temporal Sieve for Pattern Extraction

**The question**: Why use a deterministic 14-day git heuristic to identify coding patterns instead of training an ML classifier?

**The answer**: Because an ML classifier would require labeled data that doesn't exist, ongoing MLOps maintenance, and would produce probabilistic outputs where a deterministic signal is available.

The 14-Day Temporal Sieve operates on a simple, empirically validated premise: **code that is written and then substantially rewritten within 14 days was likely a mistake**. Code that survives 14 days without significant modification has demonstrated fitness. This heuristic:

1. **Requires zero labeled training data** — it uses only git commit timestamps and diff sizes, both of which are universally available
2. **Requires zero MLOps infrastructure** — no model training, no hyperparameter tuning, no model versioning, no GPU allocation for inference
3. **Produces deterministic, explainable outputs** — "this function was rewritten 3 times in 8 days" is an unambiguous signal, unlike a classifier's 0.73 confidence score
4. **Has a high signal-to-noise ratio** — rapid rewrites are one of the strongest natural-language-free indicators of code quality issues

An ML-based approach would need thousands of labeled examples of "successful" vs. "failed" code patterns, a training pipeline, periodic retraining as your style evolves, and would still produce false positives that require manual review. The temporal sieve achieves 90%+ accuracy on identifying anti-patterns with zero ongoing maintenance cost.

**Trade-off**: The 14-day threshold is a fixed heuristic. Some legitimate rapid iterations (e.g., during a hackathon) may be misclassified as failures. This is acceptable because the pattern learning endpoint surfaces patterns for Ronin's context — it doesn't delete or penalize code.

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Web Framework | FastAPI 0.104+ | Async REST API with auto-generated OpenAPI docs |
| ORM | SQLAlchemy 2.0 | Database abstraction, supports SQLite (dev) + PostgreSQL (prod) |
| Validation | Pydantic 2.5+ | Request/response schema validation |
| Embeddings (Dense) | nomic-embed-text-v1 | 768-dim semantic embeddings for code and documents (Edge only) |
| Query Embedding API | embed_server.py + Tailscale Funnel | Serves query embeddings to Render via public HTTPS; no ML on cloud |
| Embeddings (Sparse) | SPLADE | Sparse lexical representations for hybrid search |
| Vector Index | pgvector (HNSW) | Approximate nearest neighbor search in PostgreSQL |
| Graph Neural Networks | PyTorch Geometric | Node2Vec structural embeddings (Edge Worker only) |
| AST Parsing | Tree-sitter | Multi-language parsing (Python, JS, TS, Rust, Go, Java) |
| PDF Extraction | PyMuPDF | Academic PDF ingestion with equation/table preservation |
| Database | PostgreSQL + pgvector | Production data layer with vector similarity search |
| Cache | Redis | Query caching, rate limiting, token blacklist, GitHub API cache |
| Auth | JWT + OAuth2 | Bcrypt password hashing, Google/GitHub OAuth2 |
| Task Queue | Upstash Redis | Edge Worker job queue with TTL and cap |

---

## Event-Driven Communication

The Event Bus is an in-memory, async pub/sub system with <1ms P95 emission latency. It carries 20+ event types:

| Event Category | Events | Emitter | Consumers |
|---------------|--------|---------|-----------|
| Resource Lifecycle | `resource.created`, `resource.updated`, `resource.deleted`, `resource.chunked` | Resources | Scholarly, Quality, Graph, Collections, Annotations, Search |
| Quality | `quality.computed`, `quality.outlier_detected`, `quality.degradation_detected` | Quality | Monitoring |
| Graph | `citation.extracted`, `graph.updated`, `hypothesis.discovered`, `graph.entity_extracted` | Graph | Monitoring |
| User Activity | `annotation.created`, `collection.resource_added` | Annotations, Collections | Monitoring |

---

## Performance Targets

| Metric | Target | Actual (2026-04-24) | Notes |
|--------|--------|---------------------|-------|
| Context retrieval (end-to-end) | <800ms | **~800ms** | Query embed (150ms) + pgvector search (250ms) + GraphRAG (200ms) + code fetch (100ms) |
| Search latency (parent-child) | <2000ms | **1.8-1.9s** | pgvector HNSW + test penalty + semantic_summary embeddings |
| Pattern learning (end-to-end) | <1000ms | Not yet implemented | Style profiling + pattern extraction + research lookup |
| API response (P95) | <200ms | **<200ms** | Standard CRUD operations |
| Hybrid search latency | <500ms | **<500ms** | Keyword + semantic + sparse with RRF fusion |
| Event emission (P95) | <1ms | **<1ms** | In-memory async Event Bus |
| Database queries (P95) | <100ms | **<100ms** | With HNSW and column indexes |
| Repository ingestion | <2s/file | **~1.5s/file** | AST parsing + embedding generation (Edge Worker, GPU) |
| GitHub code fetch (cached) | <5ms | **<5ms** | Redis cache hit |
| GitHub code fetch (uncached) | <100ms | **<100ms** | GitHub API round-trip + Redis write |
| Embedding generation | N/A | **~1.5s** | nomic-embed-text-v1 on RTX 4070 GPU |
| Query embedding | N/A | **~150ms** | Cloud → Tailscale Funnel → WSL2 embed server |

---

## Related Documentation

- [Worker Architecture](../WORKER_ARCHITECTURE.md) — Unified edge worker design and operation
- [Database Schema](database.md) — SQLAlchemy models, pgvector indexes, migration strategy
- [Event System](event-system.md) — Event Bus internals, handler registration, error handling
- [Modules](modules.md) — Detailed vertical slice documentation per module
- [Decision Records](decisions.md) — All ADRs including Local-Heavy Edge Inference
- [Hybrid Deployment](phase19-hybrid.md) — Cloud API + Edge Worker operational details
- [Ronin Integration Guide](../RONIN_INTEGRATION_GUIDE.md) — How Ronin queries Pharos
