# Pharos Serverless Architecture Diagram

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PHAROS SERVERLESS STACK                             │
│                         Cost: $7/mo | Capacity: 1000+ repos                 │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐       │
│  │    Ronin     │         │   IDE/CLI    │         │   Browser    │       │
│  │  LLM Agent   │         │   Plugins    │         │   Frontend   │       │
│  └──────┬───────┘         └──────┬───────┘         └──────┬───────┘       │
│         │                        │                        │               │
│         └────────────────────────┴────────────────────────┘               │
│                                  │                                         │
│                                  │ HTTPS (TLS 1.3)                         │
│                                  │ X-API-Key: <pharos-api-key>             │
│                                  ▼                                         │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          API / CONTROL PLANE                                │
│                          Render Web Service ($7/mo)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                      Gunicorn (Master Process)                        │ │
│  │                      Workers: 2 | Timeout: 60s                        │ │
│  ├───────────────────────────────────────────────────────────────────────┤ │
│  │                                                                       │ │
│  │  ┌─────────────────────┐         ┌─────────────────────┐            │ │
│  │  │   Worker 1          │         │   Worker 2          │            │ │
│  │  │   (Uvicorn ASGI)    │         │   (Uvicorn ASGI)    │            │ │
│  │  │   RAM: ~150MB       │         │   RAM: ~150MB       │            │ │
│  │  ├─────────────────────┤         ├─────────────────────┤            │ │
│  │  │                     │         │                     │            │ │
│  │  │  FastAPI App        │         │  FastAPI App        │            │ │
│  │  │  ├─ Resources       │         │  ├─ Resources       │            │ │
│  │  │  ├─ Search          │         │  ├─ Search          │            │ │
│  │  │  ├─ Collections     │         │  ├─ Collections     │            │ │
│  │  │  ├─ Graph           │         │  ├─ Graph           │            │ │
│  │  │  ├─ PDF Ingestion   │         │  ├─ PDF Ingestion   │            │ │
│  │  │  ├─ Context (P7)    │         │  ├─ Context (P7)    │            │ │
│  │  │  └─ Patterns (P6)   │         │  └─ Patterns (P6)   │            │ │
│  │  │                     │         │                     │            │ │
│  │  │  Connection Pool:   │         │  Connection Pool:   │            │ │
│  │  │  ├─ Size: 3         │         │  ├─ Size: 3         │            │ │
│  │  │  ├─ Overflow: 7     │         │  ├─ Overflow: 7     │            │ │
│  │  │  └─ Total: 10       │         │  └─ Total: 10       │            │ │
│  │  │                     │         │                     │            │ │
│  │  └─────────┬───────────┘         └─────────┬───────────┘            │ │
│  │            │                               │                        │ │
│  └────────────┼───────────────────────────────┼────────────────────────┘ │
│               │                               │                          │
│               │ Total: 20 connections         │                          │
│               │                               │                          │
└───────────────┼───────────────────────────────┼──────────────────────────┘
                │                               │
                │                               │
                ▼                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          STATE / DATA LAYER                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────┐       ┌──────────────────────────────┐  │
│  │       NeonDB PostgreSQL      │       │      Upstash Redis           │  │
│  │       (Free Tier: $0/mo)     │       │      (Free Tier: $0/mo)      │  │
│  ├──────────────────────────────┤       ├──────────────────────────────┤  │
│  │                              │       │                              │  │
│  │  Storage: 500MB              │       │  Requests: 10K/day           │  │
│  │  Connections: 100 max        │       │  Storage: 256MB              │  │
│  │  Used: 20 (safe)             │       │  Latency: <50ms              │  │
│  │                              │       │                              │  │
│  │  ┌────────────────────────┐  │       │  ┌────────────────────────┐  │  │
│  │  │  Metadata               │  │       │  │  Cache                 │  │  │
│  │  │  ├─ Resources           │  │       │  │  ├─ Embeddings (1h)   │  │  │
│  │  │  ├─ Collections         │  │       │  │  ├─ Queries (5m)      │  │  │
│  │  │  ├─ Annotations         │  │       │  │  ├─ Quality (30m)     │  │  │
│  │  │  ├─ Graph entities      │  │       │  │  └─ Code (1h, P5)     │  │  │
│  │  │  └─ Quality scores      │  │       │  │                        │  │  │
│  │  │                          │  │       │  │  ┌────────────────────┐│  │
│  │  │  Embeddings (pgvector)  │  │       │  │  │  Task Queue        ││  │
│  │  │  ├─ Code chunks          │  │       │  │  ├─ Embedding jobs   ││  │
│  │  │  ├─ PDF chunks           │  │       │  │  ├─ Extraction jobs  ││  │
│  │  │  └─ Annotations          │  │       │  │  └─ Pattern learning ││  │
│  │  │                          │  │       │  │                        │  │  │
│  │  │  SSL: Required           │  │       │  │  SSL: Required         │  │  │
│  │  │  Timeout: 60s            │  │       │  │  Timeout: 10s          │  │  │
│  │  │  Pool pre-ping: Yes      │  │       │  │  Retry: Yes            │  │  │
│  │  │                          │  │       │  │                        │  │  │
│  │  └────────────────────────┘  │       │  └────────────────────────┘  │  │
│  │                              │       │                              │  │
│  └──────────────────────────────┘       └──────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          COMPUTE / EDGE LAYER                               │
│                          Local RTX 4070 ($0/mo)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                      Edge Worker Process                              │ │
│  ├───────────────────────────────────────────────────────────────────────┤ │
│  │                                                                       │ │
│  │  ┌─────────────────────┐         ┌─────────────────────┐            │ │
│  │  │   SPLADE Embeddings │         │   LLM Extraction    │            │ │
│  │  │   (GPU-accelerated) │         │   (Local Inference) │            │ │
│  │  │   RTX 4070          │         │   RTX 4070          │            │ │
│  │  └─────────────────────┘         └─────────────────────┘            │ │
│  │                                                                       │ │
│  │  Connects to: Upstash Redis (task queue)                             │ │
│  │  Processes: Embedding jobs, extraction jobs, pattern learning        │ │
│  │  Cost: $0/mo (your hardware)                                         │ │
│  │                                                                       │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL SERVICES                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────┐       ┌──────────────────────────────┐  │
│  │       GitHub API             │       │      OpenAI API (Optional)   │  │
│  │       (Free: 5000 req/hr)    │       │      (Pay-per-use)           │  │
│  ├──────────────────────────────┤       ├──────────────────────────────┤  │
│  │                              │       │                              │  │
│  │  Hybrid Storage (Phase 5):   │       │  Cloud Embeddings:           │  │
│  │  ├─ Fetch code on-demand     │       │  ├─ text-embedding-3-small   │  │
│  │  ├─ Cache in Redis (1h)      │       │  ├─ Faster than local        │  │
│  │  └─ 17x storage reduction    │       │  └─ No GPU required          │  │
│  │                              │       │                              │  │
│  └──────────────────────────────┘       └──────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Request Flow Diagram

### 1. Context Retrieval Request (Phase 7)

```
┌─────────┐
│  Ronin  │ "How does authentication work?"
└────┬────┘
     │
     │ POST /api/context/retrieve
     │ X-API-Key: <pharos-api-key>
     │ {"query": "authentication", "codebase": "myapp"}
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Render (Gunicorn Worker)                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Authenticate (M2M API key)                              │
│  2. Rate limit check (Redis)                                │
│  3. Context retrieval pipeline:                             │
│                                                             │
│     ┌─────────────────────────────────────────────┐        │
│     │  Semantic Search (250ms)                    │        │
│     │  ├─ Generate query embedding                │        │
│     │  ├─ HNSW vector search (pgvector)           │        │
│     │  └─ Top 10 code chunks                      │        │
│     └─────────────────────────────────────────────┘        │
│                      │                                      │
│                      ▼                                      │
│     ┌─────────────────────────────────────────────┐        │
│     │  GraphRAG Traversal (200ms)                 │        │
│     │  ├─ Find auth-related entities              │        │
│     │  ├─ Multi-hop graph traversal               │        │
│     │  └─ Dependency graph                        │        │
│     └─────────────────────────────────────────────┘        │
│                      │                                      │
│                      ▼                                      │
│     ┌─────────────────────────────────────────────┐        │
│     │  Pattern Matching (100ms)                   │        │
│     │  ├─ Find similar code from history          │        │
│     │  ├─ Successful patterns (quality > 0.8)     │        │
│     │  └─ Failed patterns (bugs, refactorings)    │        │
│     └─────────────────────────────────────────────┘        │
│                      │                                      │
│                      ▼                                      │
│     ┌─────────────────────────────────────────────┐        │
│     │  Research Retrieval (150ms)                 │        │
│     │  ├─ Find relevant papers                    │        │
│     │  ├─ PDF annotations                         │        │
│     │  └─ Linked concepts                         │        │
│     └─────────────────────────────────────────────┘        │
│                      │                                      │
│                      ▼                                      │
│     ┌─────────────────────────────────────────────┐        │
│     │  Code Fetching (100ms, cached)              │        │
│     │  ├─ Check Redis cache                       │        │
│     │  ├─ Fetch from GitHub if miss               │        │
│     │  └─ Cache for 1 hour                        │        │
│     └─────────────────────────────────────────────┘        │
│                                                             │
│  4. Assemble context (code + graph + patterns + papers)    │
│  5. Return JSON response                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
     │
     │ Total time: ~800ms
     │
     ▼
┌─────────┐
│  Ronin  │ Receives context, generates explanation
└─────────┘
```

### 2. PDF Ingestion Request (Phase 4)

```
┌─────────┐
│  User   │ Upload research paper
└────┬────┘
     │
     │ POST /api/resources/pdf/ingest
     │ Content-Type: multipart/form-data
     │ file: paper.pdf
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Render (Gunicorn Worker)                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Authenticate (M2M API key)                              │
│  2. Validate PDF file                                       │
│  3. PDF extraction pipeline:                                │
│                                                             │
│     ┌─────────────────────────────────────────────┐        │
│     │  PyMuPDF Extraction (10s for 10 pages)      │        │
│     │  ├─ Extract text with coordinates           │        │
│     │  ├─ Detect equations (heuristic)            │        │
│     │  ├─ Detect tables (grid structure)          │        │
│     │  └─ Detect figures (image blocks)           │        │
│     └─────────────────────────────────────────────┘        │
│                      │                                      │
│                      ▼                                      │
│     ┌─────────────────────────────────────────────┐        │
│     │  Semantic Chunking (5s)                     │        │
│     │  ├─ Split by sections/paragraphs            │        │
│     │  ├─ Preserve context (parent-child)         │        │
│     │  └─ Generate chunk metadata                 │        │
│     └─────────────────────────────────────────────┘        │
│                      │                                      │
│                      ▼                                      │
│     ┌─────────────────────────────────────────────┐        │
│     │  Embedding Generation (15s)                 │        │
│     │  ├─ Queue job to Upstash Redis              │        │
│     │  ├─ Edge worker picks up job                │        │
│     │  ├─ Generate embeddings (GPU)               │        │
│     │  └─ Store in PostgreSQL (pgvector)          │        │
│     └─────────────────────────────────────────────┘        │
│                      │                                      │
│                      ▼                                      │
│     ┌─────────────────────────────────────────────┐        │
│     │  Store Metadata (1s)                        │        │
│     │  ├─ Create resource record                  │        │
│     │  ├─ Create chunk records                    │        │
│     │  └─ Emit resource.created event             │        │
│     └─────────────────────────────────────────────┘        │
│                                                             │
│  4. Return resource ID and chunk count                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
     │
     │ Total time: ~30s
     │
     ▼
┌─────────┐
│  User   │ PDF ingested, ready for annotation
└─────────┘
```

---

## Connection Pool Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    POSTGRESQL CONNECTION POOL                               │
│                    (Per Worker: 3 base + 7 overflow = 10)                   │
└─────────────────────────────────────────────────────────────────────────────┘

Worker 1:
┌─────────────────────────────────────────────────────────────────────────────┐
│  Base Pool (3 connections)                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                                  │
│  │  Conn 1  │  │  Conn 2  │  │  Conn 3  │                                  │
│  │  Active  │  │  Idle    │  │  Idle    │                                  │
│  └──────────┘  └──────────┘  └──────────┘                                  │
│                                                                             │
│  Overflow Pool (7 connections, created on demand)                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  Conn 4  │  │  Conn 5  │  │  Conn 6  │  │  Conn 7  │  │  Conn 8  │    │
│  │  (empty) │  │  (empty) │  │  (empty) │  │  (empty) │  │  (empty) │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│  ┌──────────┐  ┌──────────┐                                                │
│  │  Conn 9  │  │  Conn 10 │                                                │
│  │  (empty) │  │  (empty) │                                                │
│  └──────────┘  └──────────┘                                                │
└─────────────────────────────────────────────────────────────────────────────┘

Worker 2:
┌─────────────────────────────────────────────────────────────────────────────┐
│  Base Pool (3 connections)                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                                  │
│  │  Conn 1  │  │  Conn 2  │  │  Conn 3  │                                  │
│  │  Idle    │  │  Idle    │  │  Idle    │                                  │
│  └──────────┘  └──────────┘  └──────────┘                                  │
│                                                                             │
│  Overflow Pool (7 connections, created on demand)                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  Conn 4  │  │  Conn 5  │  │  Conn 6  │  │  Conn 7  │  │  Conn 8  │    │
│  │  (empty) │  │  (empty) │  │  (empty) │  │  (empty) │  │  (empty) │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│  ┌──────────┐  ┌──────────┐                                                │
│  │  Conn 9  │  │  Conn 10 │                                                │
│  │  (empty) │  │  (empty) │                                                │
│  └──────────┘  └──────────┘                                                │
└─────────────────────────────────────────────────────────────────────────────┘

Total Connections: 2 workers × 10 max = 20 connections
NeonDB Free Tier Limit: 100 connections
Usage: 20% (safe)
```

---

## Memory Layout Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RENDER STARTER (512MB RAM)                               │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  OS & System (100MB)                                                        │
│  ├─ Linux kernel                                                            │
│  ├─ System libraries                                                        │
│  └─ Render agent                                                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  Gunicorn Master (50MB)                                                     │
│  ├─ Master process                                                          │
│  ├─ Shared libraries                                                        │
│  └─ Configuration                                                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  Worker 1 (150MB)                                                           │
│  ├─ Python interpreter (50MB)                                               │
│  ├─ FastAPI + dependencies (50MB)                                           │
│  ├─ SQLAlchemy + asyncpg (20MB)                                             │
│  ├─ Redis client (10MB)                                                     │
│  ├─ Request buffers (10MB)                                                  │
│  └─ Embeddings cache (10MB)                                                 │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  Worker 2 (150MB)                                                           │
│  ├─ Python interpreter (50MB)                                               │
│  ├─ FastAPI + dependencies (50MB)                                           │
│  ├─ SQLAlchemy + asyncpg (20MB)                                             │
│  ├─ Redis client (10MB)                                                     │
│  ├─ Request buffers (10MB)                                                  │
│  └─ Embeddings cache (10MB)                                                 │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  Headroom (62MB)                                                            │
│  ├─ Request spikes                                                          │
│  ├─ Temporary buffers                                                       │
│  └─ Safety margin                                                           │
└─────────────────────────────────────────────────────────────────────────────┘

Total: 512MB
Usage: ~450MB (88%)
Headroom: ~62MB (12%)
Status: Safe (no OOM risk)
```

---

## Scaling Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SCALING PATH                                        │
└─────────────────────────────────────────────────────────────────────────────┘

Stage 1: Solo Dev ($7/mo)
┌─────────────────────────────────────────────────────────────────────────────┐
│  Render Starter (512MB, 0.5 CPU)                                            │
│  ├─ 2 workers                                                               │
│  ├─ 20 database connections                                                 │
│  ├─ <100 requests/min                                                       │
│  └─ 10-100 repos                                                            │
│                                                                             │
│  NeonDB Free (500MB)                                                        │
│  Upstash Free (10K req/day)                                                 │
└─────────────────────────────────────────────────────────────────────────────┘

Stage 2: Small Team ($25/mo)
┌─────────────────────────────────────────────────────────────────────────────┐
│  Render Standard (2GB, 1 CPU)                                               │
│  ├─ 3 workers                                                               │
│  ├─ 30 database connections                                                 │
│  ├─ <500 requests/min                                                       │
│  └─ 100-500 repos                                                           │
│                                                                             │
│  NeonDB Free (500MB)                                                        │
│  Upstash Free (10K req/day)                                                 │
└─────────────────────────────────────────────────────────────────────────────┘

Stage 3: Startup ($50/mo)
┌─────────────────────────────────────────────────────────────────────────────┐
│  Render Standard (2GB, 1 CPU)                                               │
│  ├─ 3 workers                                                               │
│  ├─ 30 database connections                                                 │
│  ├─ <500 requests/min                                                       │
│  └─ 500-1000 repos                                                          │
│                                                                             │
│  NeonDB Pro (3GB, $19/mo)                                                   │
│  Upstash Pro (1M req/mo, $10/mo)                                            │
└─────────────────────────────────────────────────────────────────────────────┘

Stage 4: Scale-up ($200/mo)
┌─────────────────────────────────────────────────────────────────────────────┐
│  Render Pro (4GB, 2 CPU)                                                    │
│  ├─ 4 workers                                                               │
│  ├─ 40 database connections                                                 │
│  ├─ <2000 requests/min                                                      │
│  └─ 1000-5000 repos                                                         │
│                                                                             │
│  NeonDB Scale (10GB, $69/mo)                                                │
│  Upstash Pro (1M req/mo, $10/mo)                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

**Pharos Serverless Architecture**: Production-ready, cost-optimized, infinitely scalable.
