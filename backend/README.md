# PHAROS backend

The FastAPI service, ingestion workers, CLI and benchmarks. The project overview, quick start, API
reference and limitations are in the [top-level README](../README.md).

All commands below run from this directory.

```bash
pip install --require-hashes -r requirements-dev.txt      # or `make install` from the repo root
python scripts/demo.py                                     # end-to-end smoke test (temp SQLite DB)
python -m app.cli doctor                                   # checks configuration, schema, grammars, embeddings
alembic -c config/alembic.ini upgrade head                 # migrations
uvicorn app.main:app --reload                              # API on :8000 (OpenAPI at /docs)
python -m app.workers.ingest_worker                        # CPU ingestion worker
python -m pytest tests -q                                  # tests (set PHAROS_TEST_DATABASE_URL for PostgreSQL)
```

| Path | |
|---|---|
| `app/codeintel/` | The core: `git_source` (safe cloning), `parsers/` (ast and tree-sitter), `indexer`, `embeddings`, `graph`, `retrieval`, `context`, `source` (verified code fetch), `jobs` (durable queue), `symbols` |
| `app/modules/code/` | `/api/v1` repositories, jobs, search, symbol, context and status |
| `app/modules/mcp/` | Native MCP server (`/mcp`) and the legacy REST tool router (`/api/v1/mcp`) |
| `app/shared/auth.py` | Bearer-token auth (admin and read scopes) |
| `app/workers/` | `ingest_worker` (CPU) and `main_worker` (edge/GPU: embedding server and job runner) |
| `app/modules/…` | Legacy modules (resources, search, graph, planning, patterns, PDF, monitoring) |
| `alembic/` | Migrations (`versions/`) and the archived pre-2026-10 chain (`archive/`) |
| `benchmarks/` | Retrieval benchmark harness, dataset and results |
| `config/` | `.env.example`, `.env.edge.template`, `alembic.ini` |
| `deployment/` | Render blueprint, the cloud Dockerfile, edge-worker setup |
| `requirements-*.in` / `.txt` | Direct dependencies / hash-pinned locks (`make lock`) |

Configuration is read from the environment, `backend/.env` and `backend/config/.env`; every
setting is listed in [`config/.env.example`](config/.env.example).
