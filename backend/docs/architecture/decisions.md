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
