# Pharos — The Memory & Knowledge Layer for Ronin

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-009688)
![Coverage](https://img.shields.io/badge/coverage-85%25-yellowgreen)
![Endpoints](https://img.shields.io/badge/endpoints-97%2B-blue)

Pharos is the **memory and knowledge backend** that powers Ronin, your LLM coding brain. It ingests codebases, research papers, and technical documentation, then serves structured context — code chunks, dependency graphs, learned patterns, and research insights — so Ronin can understand legacy code and generate new code informed by your entire engineering history.

**One-line summary**: Pharos remembers everything you've ever built so Ronin never starts from zero.

---

## Quick Navigation

| Resource | Description |
|----------|-------------|
| [Product Vision](../.kiro/steering/product.md) | What we're building and why |
| [Tech Stack](../.kiro/steering/tech.md) | How we're building it |
| [Repository Structure](../.kiro/steering/structure.md) | Where things are located |
| [API Reference](docs/index.md) | Complete API documentation |
| [Architecture Overview](docs/architecture/overview.md) | System architecture deep-dive |
| [ADRs](docs/architecture/decisions.md) | Architectural Decision Records |
| [Developer Setup](docs/guides/setup.md) | Getting started |
| [Deployment Guide](docs/guides/deployment.md) | Cloud + Edge deployment |
| [Ronin Integration Guide](docs/RONIN_INTEGRATION_GUIDE.md) | How Ronin queries Pharos |

---

## The Two Core Use Cases

### Use Case 1: Understanding & Debugging Old Codebases

You point Pharos at a legacy repository. You ask Ronin: *"How does the authentication system work?"*

Pharos executes a **Context Retrieval Pipeline** in ~800ms:

1. **Semantic Search** — HNSW vector search across all indexed code chunks, ranked by embedding similarity
2. **GraphRAG Traversal** — Traces dependency edges (auth -> database -> session -> cookies) through the knowledge graph
3. **Pattern Matching** — Finds structurally similar implementations from your other indexed codebases
4. **Research Paper Retrieval** — Surfaces relevant papers you've annotated (e.g., OAuth 2.0 Security Best Practices)
5. **Code Fetching** — Pulls actual source from GitHub on-demand via Redis-cached API calls

Ronin receives the assembled context package and generates explanations, identifies bugs, and suggests refactorings grounded in your real code and history.

**Endpoint**: `POST /api/context/retrieve`

### Use Case 2: Creating New Code (The Self-Improving Loop)

When Ronin writes new code, Pharos feeds it your **learned pattern profile**:

- **Successful Patterns** — Architectural decisions that worked across your past projects (e.g., Repository + Service + DI)
- **Failed Patterns** — Mistakes you've fixed before (e.g., missing rate limiting, MD5 password hashing, synchronous DB calls)
- **Coding Style** — Preferences extracted from your history (async/await, snake_case, try-except with logging, FastAPI + SQLAlchemy stack)
- **Research Insights** — Techniques from papers you've annotated, linked to concrete implementations

The result: Ronin generates production-ready code that avoids your past mistakes, matches your style, and incorporates techniques from your research — on the first pass.

**Endpoint**: `POST /api/patterns/learn`

---

## Deployment Architecture: Local-Heavy, Cloud-Light

Pharos is engineered for **maximum accuracy at minimum recurring cloud cost** through a split deployment:

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLOUD (Render Free/Starter)                  │
│                                                                 │
│  FastAPI API Server ──── PostgreSQL + pgvector ──── Redis       │
│  Control plane, routing,   Metadata, embeddings,    Query cache,│
│  auth, rate limiting       graph, AST summaries     rate limits │
│                                                                 │
│  Cost: ~$7-20/mo          No source code stored.                │
│  Memory: <512MB           Code stays on GitHub.                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTPS polling
┌──────────────────────────────┴──────────────────────────────────┐
│                    EDGE WORKER (Local RTX 4070)                 │
│                                                                 │
│  Tree-sitter AST parsing ── Dense/Sparse Embeddings ── GNN     │
│  Repository cloning,        nomic-embed-text-v1,      Node2Vec │
│  dependency extraction      SPLADE sparse vectors     training  │
│                                                                 │
│  Cost: $0/mo (your GPU)   GPU utilization: 70-90%              │
│  Handles all heavy inference locally.                           │
└─────────────────────────────────────────────────────────────────┘
```

**Why this split?** Dense embedding generation and GNN training are compute-intensive operations that would cost $50-200/mo on cloud GPU instances. By offloading them to your local RTX 4070, you get the same (or better) inference quality at zero marginal cost. The cloud tier handles only lightweight API routing, authentication, and database queries — operations that fit comfortably within a $7/mo Render Starter plan.

### Hybrid GitHub Storage

Pharos stores **only metadata** (AST nodes, embeddings, dependency edges, quality scores) in PostgreSQL. Actual source code remains on GitHub and is fetched on-demand through Redis-cached API calls (1-hour TTL). This achieves a **17x storage reduction**, keeping the database small enough for cheap cloud tiers while still providing full code context when Ronin needs it.

---

## The 11 Domain Modules

Pharos is built as a **modular monolith** using vertical slice architecture. Each module is fully self-contained (router, service, schema, model, event handlers) and communicates with other modules exclusively through the async Event Bus. No module imports from another module.

| Module | Purpose | Role in the Ronin Ecosystem |
|--------|---------|----------------------------|
| **Resources** | CRUD operations for code files, documents, URLs | Primary ingestion entry point; emits lifecycle events consumed by downstream modules |
| **Search** | Hybrid search (BM25 keyword + dense semantic + SPLADE sparse) | Powers Ronin's context retrieval — the core query pathway |
| **Graph** | Knowledge graph, dependency edges, citation networks, PageRank | Enables GraphRAG multi-hop traversal for architectural understanding |
| **Quality** | Multi-dimensional scoring (accuracy, completeness, consistency, timeliness, relevance) | Filters low-quality chunks before they reach Ronin; surfaces outliers |
| **Annotations** | Character-offset highlights and rich notes with semantic embeddings | Your personal marginalia — searchable context that enriches Ronin's responses |
| **Scholarly** | Academic metadata extraction (equations, tables, citations, references) | Connects research papers to code implementations via structured metadata |
| **Monitoring** | System health, metrics aggregation, event bus diagnostics | Observability for the single-tenant deployment; consumes all event types |
| **MCP** | Model Context Protocol sessions and tool management | Enables Ronin to interact with Pharos as an MCP tool server |
| **Auth** | JWT authentication, OAuth2 (Google, GitHub), token revocation | Perimeter defense — secures the React SPA and API from public internet traffic. Public signup is disabled; only the admin account can authenticate. Rate limiting via Redis. |
| **Authority** | Subject authority trees and classification hierarchies | Domain-specific taxonomies that ground Ronin's understanding |
| **Collections** | Grouping resources with aggregate embeddings | Organizes codebases and paper sets; enables collection-level similarity |

**Removed modules (single-tenant optimization):** Recommendations (NCF is mathematically useless for N=1), Curation (community moderation queues unnecessary for a personal system), and Taxonomy (ML classification overhead unjustified for a single user). See [ADR-008](docs/architecture/decisions.md) and [ADR-012](docs/architecture/decisions.md) for rationale.

**Why 11 modules for a single-tenant system?** Strict domain isolation prevents monolith degradation over time. When you need to swap pgvector for Qdrant, or replace nomic-embed-text with a fine-tuned model, you change one module's service layer without touching the API contract or breaking downstream consumers. The Event Bus ensures modules remain independently deployable.

---

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL (production) or SQLite (development)
- Docker Desktop (for PostgreSQL + Redis backing services)
- 8GB RAM recommended (4GB minimum)
- NVIDIA GPU with CUDA (optional, for Edge Worker)

### Docker Development Setup (Recommended)

```bash
# Start backing services
cd backend/deployment
docker-compose -f docker-compose.dev.yml up -d

# Create virtual environment
cd ..
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r config/requirements.txt

# Configure environment
cp config/.env.example .env
# Edit .env with your settings

# Run migrations and start
alembic upgrade head -c config/alembic.ini
uvicorn app.main:app --reload
```

### SQLite Setup (Zero-Config)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r config/requirements.txt
cp config/.env.example .env
alembic upgrade head -c config/alembic.ini
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Interactive docs at `/docs` (Swagger) and `/redoc`.

---

## API Usage

### Authentication

Auth serves as **perimeter defense** for the single-tenant deployment. Public signup is disabled — only the pre-configured admin account can authenticate.

```bash
# Login (returns access + refresh tokens)
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "YourSecurePassword"}'
```

### Ingest a Repository

```bash
curl -X POST http://127.0.0.1:8000/resources/ingest-repository \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/user/repo.git", "title": "My Project"}'
```

### Search Across All Indexed Code

```bash
curl -X GET "http://127.0.0.1:8000/search?query=authentication+system&mode=hybrid&limit=10" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Context Retrieval (Ronin Integration)

```bash
curl -X POST http://127.0.0.1:8000/api/context/retrieve \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How does the authentication system work?",
    "codebase": "myapp-backend",
    "context_types": ["code", "graph", "patterns", "research"],
    "max_chunks": 10,
    "include_content": true
  }'
```

### Pattern Learning (Ronin Integration)

```bash
curl -X POST http://127.0.0.1:8000/api/patterns/learn \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task": "create auth microservice",
    "language": "Python",
    "framework": "FastAPI",
    "include": ["successful_patterns", "failed_patterns", "research_insights", "coding_style"]
  }'
```

---

## Development

### Running Tests

```bash
pytest tests/ -v                                    # All tests
pytest tests/ --cov=app --cov-report=html           # Coverage report
pytest tests/integration/ -v                        # Cross-module integration
pytest tests/performance/ -v                        # Performance benchmarks
```

### Code Quality

```bash
ruff check app/                                     # Lint
ruff format app/                                    # Format
python scripts/check_module_isolation.py            # Verify no cross-module imports
```

### Database Migrations

```bash
alembic revision --autogenerate -m "description" -c config/alembic.ini
alembic upgrade head -c config/alembic.ini
alembic downgrade -1 -c config/alembic.ini
```

---

## Configuration

Key environment variables (see `config/.env.example` for the full list):

| Variable | Purpose | Default |
|----------|---------|---------|
| `DATABASE_URL` | PostgreSQL or SQLite connection string | `sqlite:///backend.db` |
| `JWT_SECRET_KEY` | Token signing key (generate with `secrets.token_urlsafe(32)`) | — |
| `REDIS_HOST` / `REDIS_PORT` | Cache and rate limiting | `localhost:6379` |
| `EMBEDDING_MODEL_NAME` | Dense embedding model | `nomic-ai/nomic-embed-text-v1` |
| `DEFAULT_HYBRID_SEARCH_WEIGHT` | Keyword vs. semantic balance | `0.5` |
| `GOOGLE_CLIENT_ID` / `GITHUB_CLIENT_ID` | OAuth2 providers | — |

---

## Documentation

- [API Reference](docs/index.md) — Complete endpoint documentation
- [Architecture Overview](docs/architecture/overview.md) — System design and data flow
- [ADRs](docs/architecture/decisions.md) — Architectural Decision Records
- [Event System](docs/architecture/event-system.md) — Event Bus internals
- [Module Guide](docs/architecture/modules.md) — Vertical slice details
- [Setup Guide](docs/guides/setup.md) — Installation and environment
- [Deployment Guide](docs/guides/deployment.md) — Cloud + Edge deployment
- [Ronin Integration](docs/RONIN_INTEGRATION_GUIDE.md) — How Ronin queries Pharos
- [Docker Guide](docs/guides/DOCKER_SETUP_GUIDE.md) — Docker development setup

---

## License

MIT License — see [LICENSE](../LICENSE).

---

**Status**: Production (Phase 19+)
**API**: https://pharos.onrender.com
**Health**: https://pharos.onrender.com/health
