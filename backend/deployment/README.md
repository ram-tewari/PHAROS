# Deployment files

| File | Used for | Status |
|---|---|---|
| `render.yaml` | Render blueprint for the Docker service `pharos-cloud-api` | Secrets are `sync: false` (managed in the Render dashboard) |
| `../render.yaml` | Alternative Render blueprint (`pharos-api`, Python runtime, gunicorn) | Same convention |
| `Dockerfile.cloud` | Image built by `render.yaml` (context `backend/`) | Installs from the hash-pinned lock |
| `../Dockerfile` | Recommended API/worker image (non-root user, gunicorn, `RUN_MIGRATIONS` switch) | Used by `docker-compose.yml` and CI |
| `Dockerfile.edge`, `docker-compose.edge.yml`, `build-and-test-edge.*` | GPU edge worker in a container | **Not validated** |
| `setup_edge.sh`, `setup_edge.ps1`, `pharos-edge-worker.service`, `NSSM_WINDOWS_SETUP.md` | Edge worker on a host (systemd / Windows service) running `backend/worker.py` | Not validated in CI |
| `../render.free.yaml` | The live free deployment: one Render free web service (API only) + Neon free | Deployed from `master` |
| `mac/run-worker.sh`, `mac/com.pharos.mac-worker.plist` | Indexing for the free deployment, on the owner's Mac (launchd, hourly) | Used with `render.free.yaml` |
| `mac/run-embed-server.sh`, `mac/com.pharos.edge-embed.plist` | Query embedding for the free deployment, on the owner's Mac (launchd, always on; Tailscale Funnel) | Used with `EMBEDDING_BACKEND=edge-onnx` |
| `mac/run-learner.sh`, `mac/com.pharos.learner.plist` | Repository memory for the free deployment, on the owner's Mac (launchd, nightly) | Not installed yet |

Both blueprints point their auto-deploy at a `main` branch. This repository's default branch is
`master`, so check which branch the live services actually deploy from before relying on either
file.

**Before the first deploy of 0.5.0** to an existing database, follow
[docs/operations/database-migrations.md](../../docs/operations/database-migrations.md). Then set
`PHAROS_ADMIN_TOKEN` and `PHAROS_READ_TOKEN`; `PHAROS_API_KEY` is no longer read. Also set
`MCP_ALLOWED_HOSTS` to the service hostname. Rotate the credentials listed in
[docs/security/credential-exposure-2026-10.md](../../docs/security/credential-exposure-2026-10.md).

## Free deployment: the API on Render, indexing on a Mac

`../render.free.yaml` runs only the API on a 512 MB Render instance. It embeds
queries with granite-embedding-english-r2 (int8 ONNX, about +200 MB), but it
cannot index: embedding documents with that model peaks near 700 MB and needs
far more CPU than 0.1 vCPU. So `INGEST_WORKER_IN_PROCESS=false`, and a
submitted repository stays `queued` until a machine with the same model drains
the queue straight into the production database:

```sh
cd backend
python scripts/fetch_onnx_model.py --model granite-embedding-english-r2-int8
deployment/mac/run-worker.sh          # drains the queue once (reads DATABASE_URL from ~/.pharos-deploy.env)
# hourly, while the Mac is awake:
sed "s#__BACKEND__#$PWD#g" deployment/mac/com.pharos.mac-worker.plist > ~/Library/LaunchAgents/com.pharos.mac-worker.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.pharos.mac-worker.plist
```

The worker only connects out (to Neon and the git host); nothing listens on the
Mac. Hourly rather than continuous, because every run wakes the Neon database
and a 24/7 poller would use up the free tier's compute.

Changing the embedding model on a live deployment: deploy the new
`EMBEDDING_MODEL_ID` (search falls back to keyword with a warning, because the
stored vectors belong to the old model), then re-index every repository on the
Mac with `python -m app.cli ingest <url> --force`. Vectors of different models
are never compared. `--branch <full commit SHA>` re-indexes exactly the commit
the deployment already holds (no content change, so benchmark results stay
comparable); without it the repository moves to its default branch's head.

### Query embedding on the Mac too (`EMBEDDING_BACKEND=edge-onnx`)

Loading Granite costs the 512 MB instance about 200 MB; production peaked at
441 MB with it. With `edge-onnx`, production asks the Mac's
`app.codeintel.edge_server` first and loads its own copy only while the Mac is
unreachable. It waits `EDGE_EMBED_TIMEOUT` (2.5 s), then skips the Mac for
`EDGE_EMBED_RETRY_SECONDS` (60 s). Answers from a different model are refused.
Queries also get embedded on the same CPU architecture as the documents.

```sh
cd backend
printf "EDGE_EMBED_TOKEN='%s'\n" "$(python -c 'import secrets; print(secrets.token_hex(32))')" >> ~/.pharos-deploy.env
sed "s#__BACKEND__#$PWD#g" deployment/mac/com.pharos.edge-embed.plist > ~/Library/LaunchAgents/com.pharos.edge-embed.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.pharos.edge-embed.plist
tailscale funnel --bg --https=8443 http://127.0.0.1:8790     # publishes only this port
# Render: EMBEDDING_BACKEND=edge-onnx, EDGE_EMBEDDING_URL=https://<mac>.<tailnet>.ts.net:8443, EDGE_EMBED_TOKEN=<same token>
```

The server listens on loopback only. Funnel gives it a public HTTPS address,
and every request needs the bearer token. Requests are capped at 16 texts of
4,000 characters, rate-limited to 10 per second, and processed one at a time.
Queries are not logged. Undo with `tailscale funnel --https=8443 off`.

Measured on production, 30 October, with heldout_v1 (51 queries):

| | Production embeds | Mac embeds (`edge-onnx`) |
|---|---|---|
| Peak memory | 441 MB | 137 MB |
| nDCG@10 | 0.690 | 0.697 (the same as local) |
| Server time p50 / p95 | 205 / 305 ms | 660 / 837 ms |

Quality now matches local exactly because queries are embedded on the same ARM CPU as the documents.
The latency is the route from Render through Tailscale's Funnel relay to the Mac. The edge client
reuses one keep-alive connection, which avoids a new TLS handshake for every query.

### Learning on the Mac too (repository memory)

Memory is learned where the history is: on the Mac, never in production.
- **What a run does:** a run reads the index from Neon. For each repository whose indexed commit has
  no brief yet, it does the following:
  - Fetches a full mirror into `LEARNING_MIRROR_DIR` (default `~/.cache/pharos/git/<owner>_<repo>`).
  - Checks out the indexed commit in a temporary worktree and runs the miners.
  - Writes memory items, playbooks and a brief back to Neon.
- **Production's part:** production only reads them, through `retrieve_context`, the MCP memory
  tools and `/api/v1/memory/*`.

```sh
cd backend
deployment/mac/run-learner.sh            # learn every repository that needs it, once
python -m app.cli learn pallets/click    # one repository, now (reads DATABASE_URL)
python -m app.cli memory pallets/click   # brief, items and playbooks
# nightly at 03:30 (or at the next wake):
sed "s#__BACKEND__#$PWD#g" deployment/mac/com.pharos.learner.plist > ~/Library/LaunchAgents/com.pharos.learner.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.pharos.learner.plist
```

- **Deterministic miners (L1):** they need no Codex. A run takes seconds per repository.
- **L2 (Codex):** it runs when the Codex CLI on the Mac is signed in with ChatGPT.
  - **Inputs:** the repository's contributing, style and internals docs, plus maintainers' public
    pull-request review comments. The comments are fetched from the GitHub API, optionally with
    `GIT_CLONE_TOKEN`, and cached under `~/.cache/pharos/learn/`.
  - **Budget:** at most `LEARNING_MAX_CODEX_CALLS` calls a run (default 40) and
    `LEARNING_CODEX_CALLS_PER_REPO` per repository (default 10).
  - **Output:** its items are always `proposed` until accepted.
  - `--no-codex` skips L2.
- **Storage:** memory is small; expect a few hundred rows of under 1 KB per repository.
- **Activation and review:**
  - High-support items activate automatically.
  - Everything else waits as `proposed` until a human accepts it with
    `PATCH /api/v1/memory/items/{id}?action=accept`.
  - Every change is in `memory_ledger`, with the run id.
