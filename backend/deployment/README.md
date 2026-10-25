# Deployment files

| File | Used for | Status |
|---|---|---|
| `render.yaml` | Render blueprint for the Docker service `pharos-cloud-api` | Secrets are `sync: false` (managed in the Render dashboard) |
| `../render.yaml` | Alternative Render blueprint (`pharos-api`, Python runtime, gunicorn) | Same convention |
| `Dockerfile.cloud` | Image built by `render.yaml` (context `backend/`) | Installs from the hash-pinned lock |
| `../Dockerfile` | Recommended API/worker image (non-root user, gunicorn, `RUN_MIGRATIONS` switch) | Used by `docker-compose.yml` and CI |
| `Dockerfile.edge`, `docker-compose.edge.yml`, `build-and-test-edge.*` | GPU edge worker in a container | **Not validated** |
| `setup_edge.sh`, `setup_edge.ps1`, `pharos-edge-worker.service`, `NSSM_WINDOWS_SETUP.md` | Edge worker on a host (systemd / Windows service) running `backend/worker.py` | Not validated in CI |

Both blueprints point their auto-deploy at a `main` branch. This repository's default branch is
`master`, so check which branch the live services actually deploy from before relying on either
file.

**Before the first deploy of 0.5.0** to an existing database, follow
[docs/operations/database-migrations.md](../../docs/operations/database-migrations.md). Then set
`PHAROS_ADMIN_TOKEN` and `PHAROS_READ_TOKEN`; `PHAROS_API_KEY` is no longer read. Also set
`MCP_ALLOWED_HOSTS` to the service hostname. Rotate the credentials listed in
[docs/security/credential-exposure-2026-10.md](../../docs/security/credential-exposure-2026-10.md).
