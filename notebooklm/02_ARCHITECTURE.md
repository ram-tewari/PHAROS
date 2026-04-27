# Pharos — System Architecture

> File 2 of 6. Covers high-level topology, the cloud/edge split, the vertical-slice module pattern, event-driven communication, and the defense of key architectural decisions. See File 6 for evolution history.

---

## High-Level Topology

Pharos runs as a distributed system with **three deployment targets** and **three persistence layers**:

```
                     ┌─────────────────────────┐
                     │   Ronin (Local LLM)     │
                     │   desktop assistant     │
                     └────────────┬────────────┘
                                  │  HTTPS + Bearer (PHAROS_ADMIN_TOKEN)
                                  ▼
┌────────────────────────────────────────────────────────────────┐
│  RENDER — Cloud API (pharos-cloud-api.onrender.com)            │
│  FastAPI (app.main:app) via Gunicorn, 1–2 workers              │
│  Starter plan: 512 MB RAM, 0.5 CPU, $7/mo                      │
│                                                                │
│  MODE=CLOUD → torch & embedding modules NOT loaded             │
│  Query embeddings: HTTP → Tailscale Funnel → edge embed server │
└────┬─────────────────┬─────────────────────┬──────────────────┘
     │                 │                     │
     │ SQL             │ Redis REST          │ HTTP (Tailscale)
     ▼                 ▼                     ▼
┌──────────┐   ┌────────────────┐   ┌─────────────────────────┐
│ NeonDB   │   │ Upstash Redis  │   │  LOCAL MACHINE (RTX 4070)│
│ Postgres │   │  (REST + tcp)  │   │  - WSL2: embed_server.py │
│ +pgvector│   │  - pharos:tasks│   │    (port 8001)           │
│ Free     │   │  - ingest_queue│   │  - Windows: edge worker  │
│ 500 MB   │   │  10k req/day   │   │  - Optional: SPLADE GPU  │
└──────────┘   └────────────────┘   └─────────────────────────┘
```

### Process inventory

1. **Cloud API** — FastAPI on Render. Serves REST. Never touches a GPU.
2. **Edge embed server** — `backend/embed_server.py`, runs in WSL2 on Ram's local machine on port 8001. Zero `app.*` imports (standalone to avoid dependency hell). Exposes `/embed` and `/health`. Used as the Tailscale-funneled embedding backend for cloud-mode queries.
3. **Unified edge worker** — `backend/app/workers/main_worker.py`. Single long-running process that:
   - Loads the local embedding model on the RTX 4070.
   - Serves the FastAPI `/embed` endpoint on port `EDGE_EMBED_PORT` (default 8001).
   - Blocks on **both** Redis queues with a single connection:
     ```
     BLPOP pharos:tasks ingest_queue 30
     ```
     Routing by source queue:
     - `pharos:tasks` → `process_ingestion(resource_id)` (single-resource pipeline)
     - `ingest_queue` → `RepositoryIngestor.ingest()` (clone → AST parse → embed → persist)
   - Wraps each handler in try/except so a poison-pill task is logged and marked `failed` in Redis without taking the loop down.

   Launch from `backend/`:
   ```
   bash start_worker.sh    # Linux / WSL / Git Bash
   python start_worker.py  # Windows
   python worker.py        # legacy dispatcher, now a thin wrapper around main_worker
   ```
   The launcher forces `MODE=EDGE`, loads `.env`, and prints a banner showing the two active queues and the 30 s BLPOP timeout so a successful boot is unambiguous.

   The previous trio of files — `edge.py`, `repo.py`, `combined.py` — has been **deleted**; `main_worker.py` is the only worker entrypoint.

#### Upstash quota optimization

Upstash free tier allows **100,000 commands/month** (~3,200/day). The unified worker uses a single multi-key `BLPOP` with a **30-second** server-side timeout, which means an idle worker issues only `86400 / 30 = 2,880` commands/day — comfortably under the daily budget with headroom for actual task throughput. The previous 9-second timeout (≈9,600 idle cmds/day) was burning through the quota; **do not lower the timeout below 30 s without redoing this math.**

### Tailscale Funnel

The edge embed server is made reachable from Render via **Tailscale Funnel**, which gives a public `https://pc.tailf7b210.ts.net` URL that forwards into the user's tailnet to the WSL2 service. The cloud API reads the URL from env var `EDGE_EMBEDDING_URL` and issues an HTTP POST to `/embed` for every query embedding.

---

## Module Architecture — Vertical Slices

All domain logic under `backend/app/modules/<module_name>/`. Each slice is **self-contained**: router + service + schema + handlers + model re-export + tests. Cross-module interaction happens **only** through the event bus (`app/shared/event_bus.py`).

### Currently registered modules (see `backend/app/__init__.py`)

**Base modules** (loaded in both EDGE and CLOUD mode):
- `collections` — Hierarchical resource organization; batch add/remove
- `resources` — Core CRUD for Resource; URL ingestion; chunking router lives here too
- `search` — Standard FTS5 search + three-way hybrid router + advanced search router
- `annotations` — Character-offset highlighting, notes, tags, semantic annotation search
- `scholarly` — Paper metadata extraction (DOI, arXiv, citations, equations, tables); document-intelligence router
- `authority` — Normalization of subject/creator/publisher names
- `quality` — Multi-dimensional quality scoring + RAG evaluation router
- `graph` — Knowledge graph with three routers: `graph_router`, `citations_router`, `discovery_router`
- `auth` — JWT + OAuth2 (Google / GitHub) - **Note**: Over-engineered for single-tenant

**Additional routers**:
- `planning.ai_planning_router`
- `mcp.mcp_router` (Model Context Protocol)
- `patterns.patterns_router`
- `pdf_ingestion.router`
- `github.github_router` — on-demand code fetch from raw.githubusercontent.com

**Conditional**:
- `monitoring` — Requires Redis
- `ingestion` router (top-level, `app/routers/ingestion.py`) — Only added in CLOUD mode

**Edge-only (ML-heavy, torch required)**: currently empty list but the scaffold exists.

### Deployment-mode gate

In `app/__init__.py`:

```python
deployment_mode = settings.MODE  # "CLOUD" or "EDGE"
if deployment_mode == "EDGE" or is_test_mode:
    # Load all modules including ML-heavy ones
else:
    # Cloud mode: skip torch-dependent modules; add ingestion router
```

This is how Render stays under 512 MB RAM: `MODE=CLOUD` prevents importing modules that would drag in `torch`, `transformers`, `sentence-transformers`, etc.

---

## The Shared Kernel

`backend/app/shared/` — cross-cutting infrastructure used by every module. It contains:

| File | Responsibility |
|---|---|
| `database.py` | SQLAlchemy engine creation, pool config, sync + async sessions, `get_sync_db` / `get_async_db` FastAPI deps |
| `base_model.py` | `Base` declarative class, `GUID` type (UUID compatible with both SQLite and Postgres) |
| `event_bus.py` | In-process pub/sub for cross-module communication. <1 ms emission (P95). |
| `embeddings.py` | Embedding service; in CLOUD mode it HTTPs out to `EDGE_EMBEDDING_URL`; in EDGE mode loads `nomic-embed-text-v1` locally |
| `cache.py` + `upstash_redis.py` | Redis clients (rediss:// native + Upstash REST) |
| `circuit_breaker.py` | Fail-fast wrapper for external calls |
| `rate_limiter.py` | Tiered rate limiting (Free 100/hr, Premium 1 000/hr, Admin 10 000/hr) - **Note**: Unnecessary for single-tenant |
| `security.py` | Password hashing (bcrypt), JWT create/verify |
| `oauth2.py` | Google / GitHub OAuth2 flows |
| `ai_core.py` | Shared transformer model wrappers |

All modules depend on `shared/`; `shared/` depends on nothing in `modules/`. This acyclic rule is enforced by `backend/scripts/check_module_isolation.py`.

---

## Event-Driven Communication

In-process event bus — fast (<1 ms P95) and simple. Example flow:

```python
# resources/service.py (emitter)
await event_bus.emit(Event(
    type="resource.created",
    data={"resource_id": str(r.id), "resource_type": "code"},
))

# quality/handlers.py (listener, another module)
@event_bus.on("resource.created")
async def recompute_quality_on_create(event):
    ...
```

Current event vocabulary (not exhaustive):
- `resource.created`
- `resource.chunked`
- `chunk.embedded`
- `resource.ingestion_completed`
- `resource.updated`
- `resource.deleted`

**Important**: The bus is single-process only. It is NOT a replacement for the Redis queue — Redis queues carry work across machines (cloud → edge), while the event bus carries domain events within one Python process.

---

## Deployment Topology — Three Environments

### Development (local-only)
```
Developer machine → SQLite backend.db → in-process event bus
Optional: docker-compose up postgres + redis
```

### Hybrid (current production default)
```
Render (cloud API, MODE=CLOUD)  ──►  NeonDB (SQL), Upstash (queue)
                                 ──►  Tailscale → WSL2 embed server (GPU)
                                 ──►  Upstash pharos:tasks ← edge worker (local)
```

### Full-edge (one-box dev)
```
Local machine runs everything, MODE=EDGE, loads torch, uses SQLite or local Postgres.
```

The Render service is configured to fail at startup if `EDGE_EMBEDDING_URL` is unset in CLOUD mode (required for query embeddings).

---

## Data-Flow: Context Retrieval (~800 ms)

```
POST /api/context/retrieve or POST /api/search/advanced
      │
      │ (1) Parse query, extract filters
      ▼
┌──────────────────────────────────────────────────────┐
│ Render (FastAPI)                                     │
│  • Cloud API process                                 │
└──────┬───────────────────────────────────────────────┘
       │ (2) Embed query (150 ms)
       ▼
 HTTPS POST {EDGE_EMBEDDING_URL}/embed   ← Tailscale Funnel
       │
       ▼
┌──────────────────────────────────────────────────────┐
│ WSL2 embed_server.py (port 8001)                     │
│  • nomic-embed-text-v1 on RTX 4070                   │
│  • Returns 768-dim float array                       │
└──────┬───────────────────────────────────────────────┘
       │ (3) Vector search (250 ms) — runs on Neon via pgvector
       ▼
┌──────────────────────────────────────────────────────┐
│ NeonDB + pgvector                                    │
│  • HNSW cosine on resources.embedding (not chunks)   │
│  • WHERE embedding IS NOT NULL AND EXISTS (chunks)   │
│  • Test-path penalty: +0.10 distance for /tests/     │
│  • Returns top-50 resource candidates                │
│  • Note: Chunks inherit parent resource embedding    │
│  • Commit c6000080: migrated from O(N) Python cosine │
└──────┬───────────────────────────────────────────────┘
       │ (4) GraphRAG multi-hop traversal (200 ms)
       ▼
       joins on graph_entities, graph_relationships
       │
       │ (5) Pattern matching (100 ms) — AST similarity
       ▼
       returns code patterns from user's other repos
       │
       │ (6) RRF fusion + rerank
       ▼
 JSON response: ranked chunks + entities + patterns
```

---

## Defense of Key Architectural Decisions

### Why SQLAlchemy + Postgres instead of a purpose-built vector DB (Pinecone, Weaviate, Qdrant)?
- **Cost**: NeonDB free tier gives 500 MB + 0.25 vCPU; adequate for a single user.
- **Simplicity**: Vectors, relational rows, and graph edges live in **one transactional store**. Graph traversals can JOIN against vector similarity in a single SQL query.
- **pgvector**: With HNSW indexes, cosine similarity latency for 768-dim vectors at Pharos's scale (< 1 M chunks) is sub-50 ms — good enough.
- Migration escape hatch exists: all embeddings stored as `Text` (JSON-serialized list of floats) with `CAST(... AS vector)` at query time, so swapping to a dedicated vector DB later is a schema change, not a rewrite.

### Why embeddings served by a local GPU, not Render?
- Render Starter has 512 MB RAM. Loading `nomic-embed-text-v1` takes ~400 MB. Adding `sentence-transformers` + `torch` would push the container to 1–2 GB. Going to Standard plan ($25/mo) blows the cost budget.
- Ram owns an RTX 4070. Marginal GPU cost = $0. Latency via Tailscale Funnel is ~20–40 ms.
- Render spec note: `MODE=CLOUD` disables torch-related imports entirely; the app boots in <10 s with ~180 MB footprint.

### Why Upstash Redis instead of Render's managed Redis?
- Upstash free: 10 000 req/day, 256 MB storage, $0/mo.
- Render Redis: $10/mo.
- Cost delta: $10/mo for a single-tenant use case is unjustifiable.
- Upstash provides both `rediss://` (native protocol) and HTTPS REST. Edge workers use native; cloud workers can use REST to avoid Render's outbound connection costs.
- Trade-off: BLPOP timeout tuned to **30 seconds** in `main_worker.py` so an idle worker issues only ~2,880 commands/day, well under Upstash's 100k/month free quota.

### Why a monolithic event bus instead of, say, Kafka?
- Single tenant, single Python process. Kafka solves cross-service event durability; Pharos has one service per node.
- <1 ms in-process dispatch beats any network queue for the common case.
- For *cross-machine* work (cloud → edge embedding), Redis queues already fill the gap.

### Why vertical-slice modules instead of layered architecture (controllers / services / repositories)?
- With 29+ models and 13+ domains, layered architectures create "god packages": one giant `services/` folder with 100 files and no locality. Slices keep related code co-located.
- Ram is solo; onboarding cost isn't a constraint. Locality-of-behavior **is** — when fixing the search module, all relevant code is in one folder.

### Why hybrid GitHub storage for code?
- Copying source code into Pharos would (a) duplicate what GitHub already indexes, (b) create licensing / distribution concerns, (c) bloat NeonDB's 500 MB limit after the first mid-size repo.
- Storing `github_uri` + `branch_reference` (commit SHA when available, else `HEAD`) lets Pharos fetch the live source on demand and embed only the semantic summary.
- Trade-off: Retrieval now requires a GitHub raw fetch to show code. Addressed with a 1-hour cache (`GITHUB_CACHE_TTL=3600`) and the on-demand `github_router`.

---

## Performance Targets

| Operation | P95 Target | Status |
|---|---|---|
| `/api/search/advanced` total latency | < 800 ms | verified |
| Query embedding (Render → edge) | < 200 ms | ~150 ms |
| pgvector HNSW top-50 cosine | < 300 ms | ~250 ms |
| Per-file AST parse (Python) | < 2 s | verified |
| Event bus emit → handler call | < 1 ms | verified |
| Startup time (Render, CLOUD mode) | < 15 s | ~10 s |

---

## Failure Modes and Safeguards

- **Edge embed server offline** → Cloud API returns a 503 for search. No silent fallback: a stale keyword-only result would be worse than an honest error.
- **Upstash rate limit exceeded** → BLPOP 30 s in `main_worker.py` keeps idle load ~2.9k cmds/day, well under the 100k/month free quota.
- **NeonDB suspends free compute** → First request after idle incurs a cold-start (~500 ms). Accepted.
- **AST parse exception** → Logged; resource marked `ingestion_status='failed'` with `ingestion_error` populated.
- **Known Python 3.13 Windows WMI hang** when `platform.*()` is called on import. Workaround: `platform.uname` is monkey-patched before the app imports anything. Edge embed server runs in WSL2 to avoid the issue entirely.
