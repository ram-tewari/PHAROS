# Changelog

## Unreleased — retrieval phase 1 (branch `retrieval-phase1`)

Held-out nDCG@10 0.394 → 0.697 and 0.463 → 0.726 (two locked test sets, 101 questions);
see `docs/benchmarks/retrieval-phase1-2026-10-30.md`.

### Changed

- **Default embedding model** for the free deployment: granite-embedding-english-r2 (int8 ONNX).
  Switching models requires re-indexing. On 512 MB hosts it embeds queries only, and indexing runs
  on another machine (`backend/deployment/mac/`, `INGEST_WORKER_IN_PROCESS=false`).
- **`auto` is `dense`**, or `hybrid` when `hints` are passed (it was hybrid + graph for every query).
- **Tests, docs and examples** are down-ranked (× 0.7, was × 0.85 for tests only) unless the query
  asks for them.
- **Embedded summaries** include up to 25 body lines; line-fallback chunks embed their own lines.
- **Rust doc comments** survive `#[...]` attributes; **Rust `macro_rules!` and C/C++ function-like
  macros** are indexed as `macro` symbols; **TypeScript `./x.js` imports** resolve to `x.ts`.
- pgvector ≥ 0.8: filtered dense queries use iterative HNSW scans.

### Added

- `hints` on `POST /api/v1/search/code`, `POST /api/v1/context/retrieve` and the MCP
  `search_code` / `retrieve_context` tools: identifiers the caller guesses.
- `scripts/fetch_onnx_model.py --model …`: several pinned models, each with a `pharos_model.json`
  profile (pooling, prefixes, maximum length) that `OnnxEmbedder` reads.
- `pharos describe` and migration `0003_chunk_descriptions`: Codex-written function descriptions,
  grounded and cached per blob SHA, folded into embeddings (built, not yet measured).
- `app.learning.llm.CodexCLI`: a hardened `codex exec` adapter for jobs on the owner's machine.
- Benchmarks: `--local-checkouts` and `--hints` in `retrieval_eval`, `prod_eval.py`,
  `make_synthetic.py`, the locked `heldout_v2` set and the synthetic `dev_synth_v1` set.

## 0.5.0 — 2026-10 (unreleased; branch `claude/trusting-wozniak-8n9q2q`)

A hardening release: one working code-intelligence path, real tests, measured retrieval, and the
removal of exposed credentials and dead subsystems.

### Breaking

- **Authentication** is now two static bearer tokens: `PHAROS_ADMIN_TOKEN` (everything) and
  `PHAROS_READ_TOKEN` (search, context, `/mcp`). JWT/OAuth login, refresh tokens, CSRF middleware,
  rate-limit tiers and `PHAROS_API_KEY` were removed. MCP clients need the read token.
- **Migrations were squashed** into `0001_baseline` and `0002_codeintel`. Existing databases need
  the one-time procedure in `docs/operations/database-migrations.md`. Until then `upgrade head`
  fails safely with "Can't locate revision" and changes nothing.
- **Repository ingestion** goes through `POST /api/v1/repositories` and durable jobs.
  `POST /api/resources/ingest-repo` returns 410 with a pointer. The legacy
  `POST /api/v1/ingestion/ingest/{repo}` still works and queues the same durable job.
- The native MCP server exposes `retrieve_context`, `search_code`, `find_symbol` and
  `list_repositories`. Its previous four tools failed on every call. They remain, now fixed, on
  `POST /api/v1/mcp/invoke`.
- `DATABASE_URL` always wins over `POSTGRES_*`. It used to be silently rebuilt from the
  `POSTGRES_*` defaults.
- **Dependencies** are hash-pinned locks (`requirements-cloud.txt`, `requirements-dev.txt`,
  `requirements-onnx.txt`), generated from `.in` files. `requirements-base.txt`,
  `requirements.txt` and the duplicates in `config/` were removed.

### Added

- `app.codeintel`: AST chunking for Python, JavaScript, TypeScript/TSX, Go, Rust, C, C++ and Java,
  with observable line fallback. It also provides incremental indexing by blob SHA, a resolved
  call/import graph, and keyword, dense, hybrid and graph retrieval. Context assembly returns
  source verified against the git blob SHA. Ingestion jobs are durable, with retries,
  stalled-worker recovery, cancellation and a queue cap.
- REST API under `/api/v1` (repositories, jobs, search, symbol, context, status), a native MCP
  endpoint at `/mcp`, and the CLI `python -m app.cli` (`doctor`, `ingest`, `search`, `context`,
  `symbol`, `repos`, `jobs`, `worker`, `gen-token`).
- Embedding backends: `hash` (offline), `onnx` (CPU), `http` (edge server, with `/embed/batch` and
  token auth), `sentence-transformers`.
- Retrieval benchmark harness, a hand-labelled dataset and results
  (`docs/benchmarks/retrieval-2026-10.md`).
- `docker-compose.yml` (pgvector, Redis, API, worker), a `Makefile`, the `scripts/demo.py`
  end-to-end smoke test, and `.env.example` covering every setting.
- CI on Python 3.11 and 3.13 against PostgreSQL + pgvector and Redis. It covers migrations and
  drift, the demo, the secret scan, pip-audit and a Docker build.
- `SECURITY.md` (threat model), `CONTRIBUTING.md`, `docs/operations/database-migrations.md`.

### Fixed

These are real defects found while writing tests; each has a regression test.

- Hover (`/api/graph/code/hover`) on indexed code, which previously could never find a symbol.
  Community detection, which always returned empty because `python-louvain` was never installed.
  PageRank, whose `networkx`/`scipy` dependencies were undeclared.
- The REST MCP tool registry was empty after the first request. The patterns router crashed on
  every authenticated request. `POST /api/resources` turned its own 503 into a 500 and left rows
  pending forever. The auto-link route sat at a doubled prefix.
- Health reported "degraded: Celery workers unavailable" forever, because Celery had been removed.
  It now reports from the job table.
- Graph extraction reported success with no extractor available, and ignored
  `GRAPH_EXTRACTION_METHOD`.
- Python 3.11: `IndexStats.as_dict()` raised on `defaultdict` fields.
- URL validation raised a 500 for inputs like `javascript:alert(1)`. `RepositoryParser.clone_repository`
  now validates URLs (`ext::` / CVE-2022-24439).
- Alembic's `fileConfig` disabled the application's loggers when migrations ran in-process.
- Context assembly regained `profile_id` (coding-profile rules).

### Removed

- Production credentials from the working tree; see `docs/security/credential-exposure-2026-10.md`.
  **Rotation is still required.**
- Dead code and configuration: JWT/OAuth/CSRF, the previous ingestion pipelines, Celery tasks, the
  orphaned `deployment/worker.py`, broken Dockerfiles and compose files, and tests for removed
  features.

### Known limitations

See the README. In short: dense retrieval was measured with MiniLM, not the production model; the
GPU path is unvalidated; graph expansion does not improve ranking; storage savings are about 5%,
not 17×; and pgvector < 0.8 post-filtering will starve filtered queries at scale.
