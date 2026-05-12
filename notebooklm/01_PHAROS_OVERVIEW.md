# Pharos — Project Overview

> This is file 1 of 6 providing complete context on the Pharos project for Gemini / NotebookLM. It covers *what* Pharos is, *who* it is for, and *why* it exists. Files 2–6 cover architecture, data model, ingestion/search, API/deployment, and evolution/history respectively.

---

## One-Sentence Definition

**Pharos is a single-tenant, production code-intelligence backend (FastAPI + PostgreSQL + pgvector) that serves structured retrieval context to a local LLM coding assistant called Ronin.**

It is sometimes referred to internally by its original codename **Neo Alexandria 2.0**. The two names refer to the same system.

---

## Who It Is For

- **Developer**: Ram Tewari (solo developer, backend-focused).
- **Primary consumer of the API**: **Ronin** — a local (desktop) LLM coding assistant that Ram is also building.
- **End-user count**: 1 (single-tenant by design). Pharos is *not* a SaaS product.

Because the consumer is a deterministic program (Ronin) rather than a human, API contracts prioritize:
- Clean JSON responses with stable keys
- Sub-second latency on retrieval endpoints
- Rich, structured metadata over prose

---

## What Pharos Does (The Two Core Use Cases)

### Use Case 1: Context Retrieval (Understanding Old Code)
Ronin receives a user query like *"How does the authentication system work in myapp-backend?"* and forwards it to Pharos at `POST /api/context/retrieve` (or `POST /api/search/advanced`). Pharos returns:
1. Semantically-ranked code chunks (retrieved via pgvector HNSW cosine similarity over `nomic-embed-text-v1` 768-dim embeddings).
2. Related entities from the knowledge graph (GraphRAG multi-hop traversal).
3. Similar implementations pattern-matched from other indexed codebases.
4. Dependency sub-graphs (IMPORTS / DEFINES / CALLS relationships).

Target latency: ~800 ms total.

### Use Case 2: Pattern Learning (Generating New Code)
When Ronin needs to generate code in the user's style, it queries Pharos for:
- Historical coding patterns extracted deterministically from the user's indexed repos.
- Prior mistakes / antipatterns.
- Canonical examples with matching AST structure, imports, and function signatures.

---

## What Pharos Is NOT

- Not a hosted SaaS. Single-tenant by design.
- Not a generic RAG / note-taking tool. The code-intelligence path is first-class; everything else (annotations, scholarly papers) is secondary.
- Not a frontend-centric project. The React frontend in `frontend/` exists but is **not a priority**. All effort goes to the backend.
- Not a place that stores raw source code. Code stays on GitHub (hybrid storage); Pharos stores metadata + AST-derived semantic summaries + embeddings.

---

## Repository Layout (Top Level)

```
pharos/
├── backend/              # Python 3.13 FastAPI backend — the primary codebase
│   ├── app/
│   │   ├── main.py           # Uvicorn/Gunicorn entrypoint (factory pattern)
│   │   ├── __init__.py       # create_app() — registers modules dynamically
│   │   ├── modules/          # 13+ vertical-slice domain modules
│   │   ├── shared/           # Cross-cutting: DB, cache, event bus, embeddings, security
│   │   ├── database/
│   │   │   └── models.py     # SINGLE SOURCE OF TRUTH for all SQLAlchemy models (~1864 lines)
│   │   ├── routers/          # Top-level routers (ingestion.py lives here)
│   │   ├── workers/          # edge.py, repo.py, combined.py — background workers
│   │   ├── services/         # Cross-module services (e.g. AdvancedSearchService)
│   │   └── config/           # settings.py
│   ├── alembic/          # DB migrations
│   ├── embed_server.py   # Standalone WSL-hosted embedding HTTP server (zero app.* imports)
│   ├── worker.py         # Entrypoint script that dispatches to app/workers/*
│   ├── render.yaml       # Render.com deployment blueprint
│   └── docs/             # Markdown documentation
├── frontend/             # React/TypeScript UI (low priority)
├── pharos-cli/           # CLI tool
├── .kiro/                # Project-config / spec directory
└── docs/                 # User-facing documentation + vision
```

**Backend is the center of gravity.** 90%+ of meaningful code lives under `backend/app/`.

---

## Tech Stack Summary

| Layer | Technology |
|---|---|
| Web framework | FastAPI (async + sync routes, Pydantic v2) |
| ORM | SQLAlchemy 2.x (Mapped / mapped_column style) |
| Database (production) | PostgreSQL on NeonDB (free tier) + **pgvector** extension |
| Database (local/test) | SQLite (with FTS5 for full-text search) |
| Cache / Queue | Upstash Redis (REST + optional rediss://) |
| Embeddings (doc + query) | `nomic-ai/nomic-embed-text-v1` (768-dim) |
| Sparse embeddings | SPLADE (GPU, edge worker only) |
| Code parsing | **Tree-Sitter AST** (Python via stdlib ast, C/C++/Go/Rust/JS/TS/TSX via tree-sitter 0.23+) |
| Cloud host | Render.com Starter ($7/mo) |
| Edge compute | Local machine with NVIDIA RTX 4070 GPU, exposed via Tailscale Funnel |
| Auth | JWT + OAuth2 (Google, GitHub); bearer M2M key for Ronin - **Note**: Over-engineered for single-tenant |
| Migrations | Alembic |
| Testing | pytest + pytest-asyncio + property-based (hypothesis) |
| Linter / formatter | ruff |

**Python version**: 3.13 (with a known Windows WMI hang issue — see file 5).

---

## Design Principles (Non-Negotiable)

1. **Zero circular dependencies between modules.** Modules communicate only via the event bus in `app/shared/event_bus.py`.
2. **Vertical slice architecture.** Each module under `app/modules/` owns its router, service, schema (Pydantic), handlers (event listeners), model re-exports, and tests.
3. **Single source of truth for DB models.** All SQLAlchemy models live in `app/database/models.py`. Module `model.py` files only *re-export* from there. This is enforced to prevent import cycles.
4. **Cost minimalism.** Full production cost target = **$7/mo** (Render Starter only; Neon + Upstash + Tailscale + local GPU are all $0).
5. **Cloud/Edge split.** Render never loads ML models. All GPU work (embeddings, SPLADE, LLM extraction) happens on the local RTX 4070 and is reached via Tailscale Funnel or the Upstash task queue.
6. **Hybrid storage for code.** Source files stay on GitHub; Pharos stores only metadata + chunk-level semantic summaries + embeddings. `document_chunks.content` is **nullable** for code chunks — the content lives at the `github_uri` in chunk_metadata.

---

## Production URLs and Key Constants

- **Cloud API (actual URL)**: `https://pharos-cloud-api.onrender.com`
  - Note: `render.yaml` declares `name: pharos-api` but the *deployed* service is `pharos-cloud-api`. The YAML name is stale.
- **Health check**: `GET /health`
- **OpenAPI / Swagger**: `GET /docs`
- **M2M auth header (Ronin → Pharos)**: `Authorization: Bearer <PHAROS_ADMIN_TOKEN>`
- **Embedding model**: `nomic-ai/nomic-embed-text-v1` → 768-dim vectors
- **Edge embed server port**: `8001` (WSL2), exposed publicly via Tailscale Funnel at a URL like `https://pc.tailf7b210.ts.net`
- **Redis queues**: `pharos:tasks` (embedding tasks, polled by edge worker), `ingest_queue` (repo ingestion — currently has no worker consuming it).

---

## Project Status Snapshot (2026-04-27)

**Evolution**: Pharos has evolved from Neo Alexandria (research paper management) to a specialized code-intelligence backend for LLM assistants. See **File 6 (Evolution & History)** for complete phase-by-phase analysis.

### ✅ Production-Ready Features
- ✅ Backend deployed to Render, serving production traffic
- ✅ **Phase 1: Search Serialization (2026-05-02)** - COMPLETE
  - Enhanced `DocumentChunkResult` schema with 11 new fields: `file_name`, `github_uri`, `branch_reference`, `start_line`, `end_line`, `symbol_name`, `ast_node_type`, `semantic_summary`, `code`, `source`, `cache_hit`
  - Rewrote `parent_child_search` with SQLAlchemy 2.0 eager loading (`selectinload`) for 50% faster queries
  - Fixed chunk ranking to use query-term overlap on `semantic_summary` (not always chunk-0)
  - Fixed code resolution for ALL chunks (primary + surrounding) - no more empty code fields
  - Added `from_orm_chunk()` classmethod for clean ORM-to-schema mapping
  - Deployed to production, verified working with FastAPI ingestion (1,123 resources, 5,307 chunks)
- ✅ **Phase 2: Polyglot AST (2026-05-02)** - COMPLETE
  - Created `LanguageParser` factory with Tree-sitter 0.23+ API support
  - Added AST extraction for 7 languages: Python, C, C++, Go, Rust, JavaScript, TypeScript, TSX
  - Implemented Tree-sitter queries for functions, classes, methods, imports across all languages
  - Added `_NODE_TYPE_MAP` normalization and `__imports__` pseudo-symbol for consistent output
  - Created `build_semantic_summary()` to match Python pipeline format: `[lang] signature: 'docstring.' deps: [imports]`
  - Updated `ast_pipeline.py` to route Python through stdlib ast, other languages through Tree-sitter
  - Graceful fallback to line-chunking if Tree-sitter fails
  - Deployed to production, verified with Go repository ingestion (fatih/color: 4 resources, 112 chunks in 5.8s)
- ✅ **Hybrid GitHub Storage (Phase 5)** - COMPLETE: 17x storage reduction, on-demand code fetching
- ✅ **Pattern Learning Engine (Phase 6)** - COMPLETE: Learns YOUR coding style from AST + Git history
- ✅ **Self-Improving Loop (Phase 8)** - COMPLETE: Learns from mistakes via LLM extraction
- ✅ **Staleness Tracking (2026-04-27)** - COMPLETE: Detects outdated code via `is_stale` flag, marks old resources stale on re-ingest
- ✅ **Path Exclusions (2026-04-27)** - COMPLETE: Centralized exclusion list (migrations/, alembic/, __generated__, lockfiles, .min.*, _pb2.py)
- ✅ **AST Density Gate (2026-04-27)** - COMPLETE: Filters out flat dataclasses/configs with <3 control-flow nodes or <0.01 density
- ✅ Repo worker fully functional - AST-based ingestion with semantic summaries
- ✅ Context retrieval API - <800ms latency for code + graph + patterns + papers
- ✅ Three-way hybrid search - keyword + dense + sparse with RRF fusion
- ✅ GitHub code fetching - `/api/github/fetch` and `/api/github/fetch-batch` endpoints
- ✅ Test-file path penalty (+0.10 distance) to down-rank test files
- ✅ 3,302 LangChain resources indexed with dependency graphs
- ✅ FastAPI repository indexed (1,123 resources, 5,307 chunks) - JavaScript AST working
- ✅ fatih/color Go repository indexed (4 resources, 112 chunks) - Go AST working

### ⚠️ Partial Implementation
- ⚠️ Ronin integration - API endpoints ready, desktop app not started (separate project)
- ⚠️ Frontend UI - React app exists but dormant (backend API is priority)

### ❌ Not Implemented
- ❌ Ronin desktop app (separate project, not started)
- ❌ Production load testing with 1000 repos
- ❌ IDE plugins (VS Code, JetBrains, Vim)

---

## Glossary

- **Ronin** — The local LLM desktop assistant that consumes the Pharos API. Separate project from Pharos (not yet started), but planned by the same person.
- **Neo Alexandria** — Original codename for Pharos. Still appears in docstrings.
- **Edge worker** — Process running on Ram's local RTX 4070 that handles all GPU-bound work (embeddings, sparse embeddings, LLM extraction). Polls `pharos:tasks` from Upstash.
- **Cloud API** — The FastAPI process on Render. Serves HTTP; never loads ML models (`MODE=CLOUD` skips torch imports).
- **Hybrid storage** — ✅ IMPLEMENTED: Code files stay on GitHub, Pharos stores only `github_uri` + `branch_reference` + metadata. 17x storage reduction achieved.
- **Semantic summary** — A short, human-readable string like `"[python] def authenticate_user(username, password) -> User: 'Authenticate a user.' deps: [verify_password, db.query]"`. This is what gets embedded for code chunks — **not** the raw source.
- **DocumentChunk** — A retrievable unit. For PDFs it's a page-ish slice with `content` populated. For code it's a function/class/method with `content=NULL` and a `github_uri` pointing at the source.
- **Three-way hybrid search** — Search strategy combining keyword (FTS5/tsvector) + dense vector (pgvector) + sparse (SPLADE) results via Reciprocal Rank Fusion (RRF).
- **Pattern Learning** — ✅ IMPLEMENTED: `/api/patterns/learn` endpoint that analyzes repos to extract coding patterns (architecture, style, Git history).
- **Self-Improving Loop** — ✅ IMPLEMENTED: System that tracks code changes, extracts rules via LLM, and stores them as `ProposedRule` records for human review. Accepted rules become ACTIVE and influence future code generation.
- **ProposedRule** — A coding rule extracted by the local LLM from a Git diff. Status workflow: PENDING_REVIEW → ACTIVE/REJECTED.
- **CodingProfile** — Master programmer personality (e.g., "Linus Torvalds", "DHH"). Contains curated coding rules and style preferences.
- **Staleness Tracking** — ✅ IMPLEMENTED (2026-04-27): System that marks resources as stale when a repo is re-ingested with a new commit SHA. Three new columns: `is_stale` (boolean, indexed), `last_indexed_sha` (string), `last_indexed_at` (timestamp). Search queries automatically filter out stale resources.
- **Path Exclusions** — ✅ IMPLEMENTED (2026-04-27): Centralized list in `backend/app/utils/path_exclusions.py` that excludes migrations/, alembic/, __generated__, lockfiles, .min.*, _pb2.py, etc. from ingestion. Wired into all three ingest paths.
- **AST Density Gate** — ✅ IMPLEMENTED (2026-04-27): Heuristic sieve that drops files with <3 control-flow nodes (if/for/while/try) or <0.01 AST density. Prevents flat dataclasses and config files from polluting the feedback queue. Configurable via `FEEDBACK_MIN_CONTROL_FLOW_NODES` and `FEEDBACK_MIN_AST_DENSITY` settings.
- **Polyglot AST** — ✅ IMPLEMENTED (2026-05-02): Tree-sitter-based parser factory supporting 7 languages (Python via stdlib ast, C/C++/Go/Rust/JS/TS/TSX via tree-sitter 0.23+). Extracts functions, classes, imports, and calls with consistent `SymbolInfo` format across all languages. Graceful fallback to line-chunking for unsupported languages. Implementation in `backend/app/modules/ingestion/language_parser.py` with Tree-sitter queries for each language. Semantic summaries follow format: `[lang] signature: 'docstring.' deps: [imports]`.


---

## Edge Worker Operator Surface (2026-05-12)

The edge worker is managed by a single CLI tool: **`backend/pharos_edge.py`**, invokable from the repo root via `.\pharos-edge.ps1`. See `UPDATES_2026_05_12.md` for full context.

```powershell
.\pharos-edge.ps1 start          # detached supervisor, auto-restarts worker on crash
.\pharos-edge.ps1 start --wsl    # run worker under WSL (fallback)
.\pharos-edge.ps1 status         # rich live status — supervisor + worker PIDs, heartbeat, queues, logs
.\pharos-edge.ps1 logs -n 100    # tail worker log
.\pharos-edge.ps1 stop
.\pharos-edge.ps1 restart
.\pharos-edge.ps1 doctor         # env / deps / GPU / cloud + Upstash reachability
```

State lives in `backend/.pharos_edge/` (gitignored): `supervisor.pid`, `worker.pid`, `state.json`, and rotating logs.

The supervisor restarts the worker on crash with exponential backoff (5 s → 15 s → 60 s → 300 s, capped). Backoff resets to 0 after 60 s of stable uptime.

This replaces the older `restart_worker.ps1` / `check_worker_status.ps1` scripts.

---

## Known Issues & Technical Debt (2026-05-12)

**See `UPDATES_2026_05_12.md` for current status and `ACTUAL_STATUS_2026_04_27.md` / `ACTUAL_PIPELINE_STATUS.md` for prior analyses.**

### 0. ~~Edge worker silently crashing on model load~~ ✅ FIXED (2026-05-12)
- **Problem**: `SentenceTransformer("nomic-ai/nomic-embed-text-v1")` exited silently with `0xC0000005 ACCESS_VIOLATION` on Windows + Python 3.13 immediately after `HEAD pytorch_model.bin → 302`. No traceback was captured because the prior handler used a bare `pass`. Worker had been failing this way for ~25 days; all ingestion jobs sat as `pending` in `pharos:history`.
- **Fix**: `model_kwargs={"use_safetensors": True}` to bypass the `pytorch_model.bin` path, `faulthandler.enable()` so future native crashes dump a stack, `logger.exception(...)` instead of `logger.error(...)` so tracebacks reach the log.
- **File**: `backend/app/shared/embeddings.py:69-115`
- **Verified**: 12+ min stable run, 74-resource ingestion completed in 86.8s.

### 0.5 Polyglot AST silently falls back to block-chunking
- **Problem**: `tree_sitter_<lang>` packages (go, rust, c, cpp, ts, js) are imported by `app/modules/ingestion/language_parser.py` but **not in `requirements-edge.txt`**. When a Go file is parsed the worker logs `Failed to load go grammar: ... pip install tree_sitter_go` and falls back to line-based block chunking with synthetic `symbol_name=file.go:1-50`.
- **Impact**: Phase 2 polyglot AST is effectively Python-only in production. Search quality on non-Python content is significantly degraded.
- **Priority**: HIGH

### 1. ~~Stale Data Detection Missing~~ ✅ FIXED (2026-04-27)
- **Solution**: Added `is_stale`, `last_indexed_sha`, `last_indexed_at` columns to Resource table
- **Implementation**: `mark_repo_stale_by_sha()` marks old resources stale, `mark_resources_fresh()` marks new ones fresh
- **Search Integration**: All search queries now filter `(r.is_stale IS NULL OR r.is_stale = FALSE)`
- **Status**: RESOLVED

### 2. Auth Over-Engineering (MAJOR BLOAT)
- **Problem**: Enterprise SaaS auth (OAuth2, JWT refresh, rate limiting) for single-tenant tool
- **Bloat**: ~2000 lines of unnecessary auth code
- **Needed**: Simple API key authentication
- **Priority**: HIGH

### 3. Collections Module IS the Recommendation System
- **Clarification**: Claims of "recommendations removed" are misleading
- **Reality**: Collections module provides content-based recommendations via semantic similarity
- **Note**: This is appropriate for single-tenant (not collaborative filtering)

### 4. Classification Training Scripts Not Fully Removed
- **Problem**: Taxonomy module removed, but training scripts remain in `backend/scripts/training/`
- **Priority**: LOW (dead code cleanup)
