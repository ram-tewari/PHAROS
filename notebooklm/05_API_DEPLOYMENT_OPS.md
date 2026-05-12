# Pharos — API Reference, Deployment, and Operations

> File 5 of 6. Covers the full HTTP API surface (endpoint catalog), authentication, deployment (Render + NeonDB + Upstash + local edge), env vars, and a runbook of common operational tasks / known pitfalls. See File 6 for evolution history.

---

## Base URLs

- **Production (cloud API)**: `https://pharos-cloud-api.onrender.com`
- **Local dev (default)**: `http://127.0.0.1:8000`
- **OpenAPI / Swagger UI**: `{base}/docs`
- **ReDoc**: `{base}/redoc`
- **Health**: `{base}/health` → `{"status": "healthy", "database": "connected", "cache": "connected"}`

> Note: `backend/render.yaml` declares the service as `pharos-api`, but the actually-deployed service is named `pharos-cloud-api`. Use the `pharos-cloud-api.onrender.com` URL.

---

## Authentication

**Note (2026-04-27)**: The current auth system is over-engineered for a single-tenant tool. OAuth2 flows, JWT refresh, and rate limiting tiers are enterprise SaaS features unnecessary for Pharos. Simple API key authentication would suffice. See `ACTUAL_STATUS_2026_04_27.md` for details.

Two authentication modes:

### 1. Machine-to-machine (Ronin → Pharos) — **preferred for agents**
Bearer token, static, set in Render env var `PHAROS_ADMIN_TOKEN`.

```
Authorization: Bearer <PHAROS_ADMIN_TOKEN>
```

All endpoints under `/api/*` accept this header. No user context — all operations run as the single tenant.

**How to generate/rotate API keys**:
```python
import secrets
api_key = secrets.token_hex(32)  # 64-character hex string
```

Then set in Render dashboard:
1. Go to pharos-cloud-api service → Environment
2. Add/update `PHAROS_ADMIN_TOKEN` with the new value
3. Redeploy (or wait for auto-deploy on next commit)
4. Update Ronin's config with the new key

**Security notes**:
- API key is **not hashed** in the database (it's an env var, not a DB record)
- API key grants **full access** to all endpoints (no scoping)
- Rotate if compromised (no revocation list — just change the env var)
- For multi-user scenarios, switch to JWT (see below)

### 2. Interactive user auth — JWT
For future multi-user or frontend scenarios.
- `POST /api/auth/register { email, password }`
- `POST /api/auth/login { email, password }` → `{ access_token, refresh_token, token_type: "bearer" }`
- `POST /api/auth/refresh { refresh_token }`
- `POST /api/auth/logout`
- `GET  /api/auth/me`
- OAuth2: `GET /api/auth/oauth/google/login`, `/callback`; same for github.

Tiered rate limiting (by user role):
- Free: 100 req/hr
- Premium: 1 000 req/hr
- Admin: 10 000 req/hr
- M2M (API key): effectively unlimited (bypasses tier check)

---

## Endpoint Catalog (grouped by module)

This is a conceptual catalog — exact paths live in each `module/router.py`. ~100 endpoints total.

### Resources (`/api/resources`)
- `POST /api/resources` — Create (triggers ingestion)
- `GET /api/resources` — List with filters, pagination, facets
- `GET /api/resources/{id}` — Fetch single
- `PATCH /api/resources/{id}` — Partial update (optimistic lock via `version`)
- `DELETE /api/resources/{id}` — Delete (cascades to chunks, annotations)
- `POST /api/resources/upload` — Multipart upload (PDF, zip, etc.)
- `GET /api/resources/{id}/chunks` — List all DocumentChunks for a resource
- `POST /api/resources/{id}/reingest` — Re-queue to pharos:tasks

### Search (`/api/search`)
- `POST /api/search/search` — Standard FTS5 + filters
- `POST /api/search/advanced` — Three-way hybrid (primary Ronin endpoint)
- `POST /api/search/compare` — Run all methods, return separately
- `POST /api/search/evaluate` — Evaluate against ground-truth
- `POST /api/search/sparse/batch` — Batch sparse-embedding generation

### Context (`/api/context`)
- `POST /api/context/retrieve` — Ronin-facing retrieval (wraps advanced search)

### Graph (`/api/graph`)
- `GET /api/graph/entities` — List entities
- `GET /api/graph/entities/{id}` — Entity detail
- `GET /api/graph/traverse` — Multi-hop traversal
- `GET /api/graph/communities` — Louvain communities
- `GET /api/graph/centrality` — PageRank values

### Citations (`/api/citations`)
- `GET /api/citations/{resource_id}` — Outgoing citations
- `GET /api/citations/{resource_id}/incoming` — Backlinks
- `GET /api/citations/network/{resource_id}?depth=2` — Citation network

### Discovery (`/api/discovery`)
- `GET /api/discovery/hypotheses` — Discovery hypotheses
- `POST /api/discovery/generate` — Generate new hypotheses

### Annotations (`/api/annotations`)
- `POST /api/annotations` — Create highlight + note
- `GET /api/annotations?resource_id=...` — List
- `PATCH /api/annotations/{id}` — Update
- `DELETE /api/annotations/{id}`
- `GET /api/annotations/search?q=...` — Semantic search across annotations
- `GET /api/annotations/export?format=markdown|json`

### Collections (`/api/collections`)
- `POST /api/collections` — Create
- `GET /api/collections/{id}` — Fetch
- `POST /api/collections/{id}/resources` — Batch add (≤100)
- `DELETE /api/collections/{id}/resources` — Batch remove

### Quality (`/api/quality`, `/api/rag-evaluation`)
- `GET /api/quality/{resource_id}` — Quality breakdown
- `POST /api/quality/{resource_id}/recompute`
- `GET /api/quality/outliers`
- `POST /api/rag-evaluation` — Evaluate a RAG run

### Scholarly (`/api/scholarly`, `/api/document-intelligence`)
- `GET /api/scholarly/{resource_id}/citations`
- `GET /api/scholarly/{resource_id}/equations`
- `POST /api/document-intelligence/qa` — QA over a document

### Authority (`/api/authority`)
- `GET /api/authority/subjects`
- `POST /api/authority/subjects`
- Similar for creators, publishers

### Ingestion (`/api/v1/ingestion`, cloud-only)
- `POST /api/v1/ingestion/ingest/{repo_path:path}` — GitHub repo ingestion (queues to `ingest_queue`; see file 4 for current status)

### MCP (`/api/mcp`)
- Exposes Pharos as a Model Context Protocol server.

### Planning (`/api/planning`)
- Multi-step AI planning sessions.

### Patterns (`/api/patterns`) - ✅ COMPLETE (Phase 6 + Phase 8)
- `POST /api/patterns/learn` — Analyze repo and extract patterns (AST + Git analysis)
- `GET /api/patterns/profiles` — List all developer profiles
- `GET /api/patterns/profiles/{id}` — Get specific profile
- `GET /api/patterns/profiles/coding` — List all coding profiles (master programmer personalities)
- `POST /api/patterns/profiles/coding` — Create/update coding profile
- `POST /api/patterns/propose` — Receive rule proposals from local extraction worker
- `GET /api/patterns/rules` — List proposed rules (with status filter: PENDING_REVIEW, ACTIVE, REJECTED)
- `PATCH /api/patterns/rules/{rule_id}` — Accept or reject a proposed rule

### GitHub (`/api/github`) - ✅ COMPLETE (Phase 5)
- `POST /api/github/fetch` — On-demand fetch of single code chunk from GitHub (with Redis cache)
- `POST /api/github/fetch-batch` — Fetch up to 50 chunks in parallel
- `GET /api/github/health` — Module health check (cache availability, token status, concurrency)

### PDF Ingestion (`/api/pdf`)
- `POST /api/pdf/ingest` — PDF-specific flow (OCR, layout parsing).

### Monitoring (`/api/monitoring`)
- `GET /api/monitoring/pool-status` — DB pool stats
- `GET /api/monitoring/cache-stats` — Redis stats
- `GET /api/monitoring/queue-status` — Queue sizes

### Meta
- `GET /health`
- `GET /docs` (Swagger)
- `GET /redoc`

---

## Deployment Architecture

```
  NeonDB (free)  ────── pgvector, 500 MB
      ▲
      │ SQL (SSL)
      │
  ┌───────────────────────────────────────┐
  │  RENDER — web service (starter $7/mo) │
  │  Gunicorn → Uvicorn workers            │
  │  WEB_CONCURRENCY=1 (to stay <512 MB)    │
  │  MODE=CLOUD → no torch                  │
  │  ✅ Hybrid storage: metadata only       │
  │  ✅ Pattern learning: /api/patterns/*   │
  │  ✅ Self-improving: rule proposals      │
  └───┬───────────────────────────┬──────┘
      │                           │
      │ Redis REST                │ HTTPS (Tailscale Funnel)
      ▼                           ▼
 Upstash Redis (free)      Local RTX 4070 (WSL2 + Windows)
  pharos:tasks               - embed_server.py (FastAPI, port 8001)
  ingest_queue               - edge worker (polls pharos:tasks)
  pharos_extraction_jobs     - local extraction worker (self-improving loop)
  10k req/day                - cost: $0
```

Total recurring cost: **$7/mo** (Render Starter only).

**Key Features Deployed**:
- ✅ Hybrid GitHub storage (17x storage reduction)
- ✅ Pattern learning engine (AST + Git analysis)
- ✅ Self-improving loop (rule proposals + review)
- ✅ Context retrieval (<800ms)
- ✅ On-demand code fetching (Redis cached)

---

## Environment Variables (production, Render dashboard)

Set in `render.yaml` with `sync: false` → configured manually in Render dashboard.

### Required
| Var | Purpose |
|---|---|
| `DATABASE_URL` | NeonDB pooled connection string (must include `?sslmode=require`) |
| `REDIS_URL` | Upstash `rediss://` URL (TLS mandatory) |
| `UPSTASH_REDIS_REST_URL` | Upstash REST API URL |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash REST API token |
| `PHAROS_ADMIN_TOKEN` | M2M bearer for Ronin |
| `SECRET_KEY` | JWT signing secret (auto-generated by Render) |
| `EDGE_EMBEDDING_URL` | Tailscale Funnel URL, e.g. `https://pc.tailf7b210.ts.net` |
| `MODE` | `CLOUD` on Render; `EDGE` on local |

### Optional
| Var | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `production` | |
| `LOG_LEVEL` | `info` | |
| `WEB_CONCURRENCY` | `1` | **Keep at 1 on Starter** to avoid OOM |
| `DB_POOL_SIZE` | `3` | Per worker |
| `DB_MAX_OVERFLOW` | `7` | |
| `DB_POOL_RECYCLE` | `300` | Seconds |
| `DB_POOL_TIMEOUT` | `30` | Seconds |
| `DB_STATEMENT_TIMEOUT` | `30000` | Milliseconds |
| `EMBEDDING_MODEL_NAME` | `nomic-ai/nomic-embed-text-v1` | |
| `GITHUB_TOKEN` | — | Optional PAT for higher rate limit (5000 req/hr) |
| `GITHUB_CACHE_TTL` | `3600` | Seconds (1 hour cache for fetched code) |
| `GITHUB_FETCH_CONCURRENCY` | `10` | Parallel GitHub fetch requests |
| `CONTEXT_RETRIEVAL_TIMEOUT` | `1000` | ms |
| `PATTERN_LEARNING_TIMEOUT` | `2000` | ms |
| `MAX_CODEBASES` | `1000` | |
| `JSON_LOGGING` | `""` | Set to `true` for structured JSON logs |
| `FEEDBACK_GITHUB_OWNER` | `""` | GitHub repo owner for self-improving loop |
| `FEEDBACK_GITHUB_REPO` | `""` | GitHub repo name for self-improving loop |
| `FEEDBACK_REDIS_QUEUE` | `pharos_extraction_jobs` | Redis queue for rule extraction jobs |
| `FEEDBACK_LOCAL_LLM_URL` | `http://localhost:11434` | Ollama/vLLM endpoint for local extraction worker |
| `FEEDBACK_LOCAL_LLM_MODEL` | `codellama:13b` | Model name for rule extraction |

### Edge worker / embed server
Same vars plus:
- `WORKER_POLL_INTERVAL` (default `1`) — seconds to sleep between queue polls when queue is empty
- `WORKER_BLPOP_TIMEOUT` (default `9`) — seconds to block waiting for a task before returning empty
- `EDGE_EMBED_PORT` (default `8001`)

**BLPOP timeout tuning**:
- **Why 9 seconds specifically?** To stay under Upstash's 10 000 req/day free-tier limit.
- **The math**: 
  - One poll cycle = BLPOP (9s) + POLL_INTERVAL (1s) = 10s
  - Requests per day = 86 400 seconds / 10 seconds = 8 640 req/day
  - Margin: 10 000 - 8 640 = 1 360 req/day for other operations
- **Prior configuration**: BLPOP=5s, POLL_INTERVAL=0.1s → 86 400 / 5.1 = ~16 941 req/day (exceeded limit)
- **How to calculate for different values**:
  ```
  req_per_day = 86400 / (BLPOP_TIMEOUT + POLL_INTERVAL)
  ```
  Examples:
  - BLPOP=10s, POLL=0s → 8 640 req/day
  - BLPOP=8s, POLL=1s → 9 600 req/day
  - BLPOP=5s, POLL=5s → 8 640 req/day
- **Trade-off**: Longer BLPOP = lower req/day but higher latency when queue is empty. For Pharos, 9s latency is acceptable (embedding tasks are async anyway).

---

## Startup Sequence (cloud)

1. Render runs `buildCommand`: `pip install -r requirements-cloud.txt && alembic upgrade heads`.
2. Render runs `startCommand`: `gunicorn -c gunicorn_conf.py app.main:app`.
3. `app/main.py` applies Windows-WMI patch (no-op on Linux), configures logging, calls `create_app()`.
4. `create_app()` (in `app/__init__.py`) reads `MODE`, registers modules, mounts routers, sets up CORS, wires event-bus handlers.
5. `healthCheckPath: /health` confirms container is healthy; traffic routed in.

Cold start: ~10 s. First query after NeonDB suspend: ~500 ms extra due to DB wake-up.

---

## Multiple Requirements Files

`backend/` contains distinct requirements for distinct deploy targets:

- `requirements-base.txt` — shared core (FastAPI, SQLAlchemy, pydantic, asyncpg, httpx).
- `requirements-cloud.txt` — cloud-only (no torch / transformers / sentence-transformers / tree-sitter).
- `requirements-edge.txt` — adds torch, transformers, sentence-transformers, tree-sitter, spacy, etc.
- `requirements-embed.txt` — minimal set for the standalone `embed_server.py`.
- `requirements.txt` — convenience, usually an alias or superset.

This split is the single biggest tool for keeping the Render image under 512 MB.

---

## Docker Support

- `backend/Dockerfile` — single-image build.
- `backend/deployment/docker-compose.dev.yml` — local Postgres + Redis for development.
- `backend/deployment/docker-compose.yml` — full production-like stack.
- `backend/entrypoint.sh` — runs migrations then starts Gunicorn.

---

## Gunicorn Configuration

`backend/gunicorn_conf.py`:
- Workers: `WEB_CONCURRENCY` env var (default 1 on Starter).
- Worker class: `uvicorn.workers.UvicornWorker`.
- Keep-alive: 5 s.
- Timeout: 30 s.
- Logs to stdout (Render collects).

---

## Logging

- Non-production: plain text, `%(asctime)s [%(levelname)s] %(name)s: %(message)s`.
- Production / when `JSON_LOGGING=true`: JSON via `app/ml_monitoring/json_logging.py`. Each log line is a structured object — parseable by Render's log view and suitable for piping to a SIEM later.

---

## CI / Git Hooks

- `.pre-commit-config.yaml` — ruff lint / format, basic yaml/json checks, no `--no-verify` bypass.
- `.github/` — GitHub Actions (varies, may include test runs + lint).
- Pre-commit must pass locally; investigate failures rather than skipping.

---

## Testing

- Test suite: `backend/tests/`.
- Configuration: `backend/pytest.ini`.
- Modes:
  - Unit / integration: `pytest backend/tests -v`.
  - With coverage: `pytest backend/tests --cov=app --cov-report=html`.
  - Property-based: `pytest backend/tests/properties -v`.
  - Specific module: `pytest backend/tests/modules/test_resources_endpoints.py -v`.
- `TESTING=true` environment flag skips certain heavy imports in `app/__init__.py`.
- Coverage goal: 85 %+.

---

## Operational Runbook

### "Search returns nothing for a query I know should match"

1. Check resource `ingestion_status`:
   ```bash
   curl "https://pharos-cloud-api.onrender.com/api/resources/{id}" | jq '.ingestion_status'
   ```
   If `pending` → run `python backend/scripts/queue_pending_resources.py` locally with prod env.
2. Verify chunks have embeddings: `python backend/scripts/corpus_audit.py`.
3. If chunks lack embeddings, re-queue via `backfill_chunk_embeddings.py`.
4. Confirm edge worker / embed server are up: `curl {EDGE_EMBEDDING_URL}/health`.
5. Confirm test-path penalty isn't eating your hit (if the doc is in `/tests/`, add +0.10 tolerance or disable filter for diagnostic).

### "Render service is at high memory / OOM crashing"

1. Check `WEB_CONCURRENCY` is 1 (Starter plan).
2. Confirm `MODE=CLOUD` (should not be loading torch).
3. Look for leaked DB sessions — `GET /api/monitoring/pool-status`.
4. Upgrade to Standard ($25/mo, 2 GB) as last resort.

### "Embeddings aren't being generated" / "Worker is offline"

**Preferred path (2026-05-12+)**: use the `pharos-edge` CLI. It owns supervision, restart, and live status — no more curl-and-format scripts.

```powershell
# From repo root
.\pharos-edge.ps1 status         # supervisor + worker PIDs, cloud heartbeat, queue lengths, recent logs
.\pharos-edge.ps1 doctor         # validates env, deps, GPU, Upstash + cloud reachability, WSL presence
.\pharos-edge.ps1 logs -n 200    # last 200 lines of worker.log
.\pharos-edge.ps1 restart        # stop + start, supervisor auto-restarts worker on crash with backoff
.\pharos-edge.ps1 restart --wsl  # fallback: run worker under WSL
```

Things to check, in order:

1. `pharos-edge status` — is supervisor `running`? Is worker `running`? Is `Cloud heartbeat: online`?
2. `pharos-edge logs -n 200` — any `Traceback` / `Failed to load embedding model` / `exited code=` lines?
3. If the worker crash-loops on model load, the silent-crash bug may have regressed. Required: `model_kwargs={"use_safetensors": True}` in `backend/app/shared/embeddings.py` and `faulthandler.enable()` at the top of `backend/worker.py`. See `UPDATES_2026_05_12.md`.
4. Is Upstash quota exceeded? Check Upstash dashboard.
5. Is `EDGE_EMBEDDING_URL` reachable from Render (if testing the embed server, not just the worker)? `curl {URL}/health`.
6. Is Tailscale Funnel up (only needed for embed server)? `tailscale funnel status`.

**Legacy path (deprecated)**: `backend/edge_worker.log` was the old location. New logs are at `backend/.pharos_edge/logs/worker.log` (10 MB rotation, keep last 5).

### "NeonDB is suspended / slow"

- Free tier auto-suspends after idle. First query wakes it (~500 ms). Not a bug; accepted trade-off.

### "Redis WRONGTYPE error"

A queue key was set as a string instead of a list. Clear it:
```bash
curl -X POST "$UPSTASH_REDIS_REST_URL" \
  -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '["DEL","pharos:tasks"]'
```

### "`asyncpg` writes zero rows but no error"

Known trap: using `:p::vector` or `:p::uuid` postfix casts through SQLAlchemy `text()` with asyncpg silently writes zero rows. Always use `CAST(:p AS vector)` / `CAST(:p AS uuid)` and log `result.rowcount` after every embedding write.

**The bug in detail**:
```python
# WRONG (writes zero rows with asyncpg)
stmt = text("UPDATE document_chunks SET embedding = :emb::vector WHERE id = :id::uuid")
result = await session.execute(stmt, {"emb": json.dumps(embedding), "id": str(chunk_id)})
# result.rowcount == 0, but no exception raised

# CORRECT (writes 1 row)
stmt = text("UPDATE document_chunks SET embedding = CAST(:emb AS vector) WHERE id = CAST(:id AS uuid)")
result = await session.execute(stmt, {"emb": json.dumps(embedding), "id": str(chunk_id)})
# result.rowcount == 1
```

**Why this happens**: asyncpg's parameter binding doesn't recognize `::type` postfix casts in the SQL string. It treats `:p::vector` as a parameter named `p::vector` (invalid), so the bind fails silently and the WHERE clause matches zero rows.

**How to detect**: Always log `result.rowcount` after UPDATE/INSERT:
```python
result = await session.execute(stmt, params)
if result.rowcount == 0:
    logger.error(f"Expected to update 1 row, but updated {result.rowcount}")
```

**Where this was fixed**: `embed_server.py` (standalone embedding server) had this bug. Fixed in commit that added explicit CAST() calls and rowcount logging.

### "Python 3.13 on Windows hangs on startup"

`platform.uname()` calls into WMI and can deadlock with antivirus. Patch is applied before the app imports anything. For the embed server, run in WSL2 (`backend/start_embed_wsl.sh`) to avoid the issue entirely.

---

## Deployment Checklist (First-Time Render Setup)

Pre-deployment:
- [ ] Create NeonDB project → enable pgvector: `CREATE EXTENSION vector;`
- [ ] Copy NeonDB **pooled** connection string
- [ ] Create Upstash Redis database → copy `rediss://` URL + REST URL/token
- [ ] Generate `PHAROS_ADMIN_TOKEN` (used by Ronin)
- [ ] Set up Tailscale Funnel on the local GPU machine → copy public URL
- [ ] (Optional) Create GitHub PAT for hybrid-storage cache

Render dashboard:
- [ ] Connect GitHub repo
- [ ] Apply `render.yaml` blueprint
- [ ] Set `DATABASE_URL`, `REDIS_URL`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `PHAROS_ADMIN_TOKEN`, `EDGE_EMBEDDING_URL`
- [ ] Confirm `MODE=CLOUD`, `WEB_CONCURRENCY=1`
- [ ] Deploy (push to `master`/`main`)

Post-deployment:
- [ ] `GET /health` returns 200 with connected statuses
- [ ] `GET /docs` loads Swagger
- [ ] First ingestion attempt (`POST /api/resources` with a URL) reaches `ingestion_status=completed` within ~30 s (requires local edge worker up)
- [ ] `POST /api/search/advanced` returns results
- [ ] Render dashboard memory < 400 MB at idle

---

## Backup and Recovery

- **NeonDB**: Daily auto-backup, 7-day retention on free tier. Manual: `pg_dump` via pooled connection string.
- **Upstash**: Daily snapshots on free tier. Manual export via Redis CLI.
- **Application state**: All in Git. Env vars in Render dashboard (export via `render env pull`).

Recovery sequence:
1. Restore NeonDB from snapshot.
2. Restore Upstash from snapshot (or just clear the queues — they're transient).
3. Redeploy app from Git.
4. Verify `/health`.
5. Run `scripts/corpus_audit.py` to confirm data consistency.
6. Re-queue any `pending` resources.

---

## Cost Summary

| Item | Cost/mo |
|---|---|
| Render Web Service (Starter) | $7 |
| NeonDB Postgres (Free, 500 MB) | $0 |
| Upstash Redis (Free, 10k req/day) | $0 |
| Tailscale Funnel (Free, 1 node) | $0 |
| Local RTX 4070 compute | $0 |
| **Total** | **$7** |

For comparison, the "naïve" Render-native stack (Render Postgres $7 + Render Redis $10) would cost $24/mo — a 71 % saving.

---

## Scaling Up (when needed)

- Traffic > 100 req/min: upgrade Render to Standard ($25/mo, 2 GB, 1 CPU, `WEB_CONCURRENCY=3`).
- NeonDB > 500 MB: NeonDB Pro $19/mo (3 GB).
- Upstash > 10 000 req/day: Upstash Pro $10/mo (1 M req/mo).
- Multi-user: revisit single-tenant assumptions — row-level security on Postgres, per-user JWT scopes, rate-limit-by-user.

Until then: single-tenant, $7/mo, local GPU does all the heavy lifting.
