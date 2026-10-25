# Configuration

| File | Purpose |
|---|---|
| `.env.example` | Every setting the API, CLI and worker read, with placeholders. Copy to `config/.env` (or `backend/.env`). |
| `.env.edge.template` | Edge (GPU) worker settings. Copy to `backend/.env`; `start_worker.ps1` and `worker.py` load it. |
| `alembic.ini` | Alembic configuration: `alembic -c config/alembic.ini upgrade head` from `backend/`. |
| `monitoring/` | Prometheus / Grafana examples. |

Settings load `backend/.env` and then `backend/config/.env` (the later file wins). Both are
git-ignored. Real environment variables override both files.

Dependencies are not configured here. They live in `backend/requirements-*.in` (direct
dependencies) and the hash-pinned locks `backend/requirements-*.txt`; regenerate the locks
with `make lock`.
