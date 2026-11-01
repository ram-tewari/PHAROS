# Changelog

## Unreleased — learning phase 2: test homes and a leaner memory block

### Added

- **`testhome` miner** (L1): the existing test files a source file's changes add tests to, from
  git history ("Tests for src/flask/ctx.py go in the existing tests/test_reqctx.py (12 of 30
  commits)"). Test helpers, fixtures and `conftest.py` are excluded.

### Changed

- **`retrieve_context` memory block:** the brief is cut to its Conventions section (retrieval
  already shows the layout and main modules; `get_repo_brief` still returns all of it), and test
  homes for the retrieved files come first.
- On the dev repositories (flask, ky; 16 tasks), against no memory: all-file recall 0.419 → 0.512
  (8 tasks better, 1 worse), and the commits' test files found went from 3 to 9 of 31. Source-file
  recall did not change (0.643 → 0.611, one task worse).

### Evaluated

- The locked Phase 2 evaluation ran once: [results](docs/benchmarks/phase2-memory-2026-11-01.md). It
  fails the protocol: source-file recall B − A is −0.004 [−0.035, +0.031], and audited precision is 55% (target
  90%). Repo QA 5 → 14 of 30 correct (p = 0.012), all-file recall +0.089 and file precision +0.140, both
  significant. Grounding 100%.

### Fixed

- `phase2_eval.py` arm C (every L2 proposal) now includes proposals the review rejected. It activated
  nothing in the locked run, so C equalled B.
- Learning a single new miner family no longer fails with a `KeyError` when its items are retired.

## Unreleased — learning phase 2, stage 1: deterministic repository memory

Evaluation protocol locked first: `docs/benchmarks/phase2-eval-protocol.md`. Not evaluated yet.

### Added

- **Repository memory** (`app/learning/`, migration `0004_learning`):
  - `memory_items`: facts and conventions with evidence (lines with a hash, a file blob, or a commit),
    support counts, scope (path globs, languages), and status `proposed → active → stale → archived`.
  - `memory_skills`: playbooks.
  - `repo_briefs`: a brief of at most 2,200 characters, frozen per indexed commit.
  - `memory_ledger`: append-only, so a run can be rolled back.
  - `learning_jobs`: the ingestion job state machine, shared through `app/codeintel/jobs.py`.
- **L1 miners**, all deterministic. They use source files only (`path_role`), the index for every
  language, and the full git history with renames followed:
  - naming and C prefixes; docs and Sphinx directives; Python typing; exception hierarchies;
  - deprecation pattern; test layout; changelog habit; commit style; tooling;
  - co-change per file; dropped dependencies and runtime versions; directory moves; file origins;
  - "add a new X" playbooks.
  - High-support items activate automatically; everything else is proposed.
- **`retrieve_context` leads with memory:** the brief, the items scoped to the retrieved files, and
  matching playbooks, in at most a third of the budget. `include_memory=false` turns it off. Ranking
  is unchanged.
- **MCP tools:** `get_repo_brief`, `search_memory`, `list_skills` and `get_skill`.
- **REST:** `/api/v1/memory/{brief,search,items,skills}` with the read token. With the admin token,
  `PATCH /api/v1/memory/items/{id}?action=accept|reject|archive|restore` and
  `POST /api/v1/repositories/{id}/learn`.
- **Mac:**
  - CLI: `pharos learn <repo>` and `pharos memory <repo>`.
  - `app.workers.learning_worker --once`.
  - `deployment/mac/run-learner.sh` with `com.pharos.learner.plist`, to run nightly; not installed.

- **L2 extraction** (`app/learning/extract.py`, `app/learning/reviews.py`, `pharos learn --codex`):
  - **Input:** Codex reads the repository's contributing, style and internals documents, plus public
    pull-request review comments that maintainers left before the learned commit.
  - **Output:** it proposes add, patch or retire operations on memory.
  - **Grounding:** it may cite only evidence ids PHAROS issued. Any identifier it mentions must
    appear in that evidence. It never rewrites a deterministic item. One-off advice about a single
    PR is dropped.
  - **Gate:** results start `proposed`, so a human accepts them. A model rewrite of an accepted item
    needs accepting again. An item whose cited lines change goes stale.
  - **Budget:** evidence already read is cached by hash. The worker's budget is
    `LEARNING_MAX_CODEX_CALLS` (default 40 a night) and `LEARNING_CODEX_CALLS_PER_REPO` (default 10).
- `benchmarks/phase2_eval.py`: runs the locked Phase 2 protocol. It resumes from a checkpoint, so no
  Codex call is spent twice.

### Changed

- `POST /api/patterns/learn` (Python-only profiles) is marked deprecated and experimental.

## Unreleased — edge query embedding

- `EMBEDDING_BACKEND=edge-onnx`: query embeddings come from `app.codeintel.edge_server` on the
  owner's machine (same ONNX model, bearer token, bounded and rate-limited), with the local model
  loaded only while the edge is unreachable. Frees ~200 MB on the 512 MB instance.
  `backend/deployment/mac/` has the launchd agent and the Tailscale Funnel command.
  Measured: production peak memory 441 → 137 MB, heldout_v1 0.690 → 0.697 (the same as local),
  server time p50 205 → 660 ms. The client keeps one connection open to the Mac and retries a
  dropped one once before falling back.

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
  grounded and cached per blob SHA, folded into embeddings (dev pilot: no measurable gain on
  codeqa_v1, Δ +0.001; not run on the deployment).
- Indexing a full commit SHA (`--branch <sha>`) fetches exactly that commit.
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
