# Credential exposure in the public repository (found 2026-10-24)

**Status:** values removed from the working tree on branch
`claude/trusting-wozniak-8n9q2q`. **Rotation and history clean-up are still
required and can only be done by the repository owner.**

`ram-tewari/PHAROS` is a **public** repository. The credentials below were
committed in plain text and remain readable in Git history, forks and any
clones or caches made before removal. Deleting them from the current tree
does **not** make them safe. Treat every one as compromised.

## What was exposed

The secret values are intentionally not reproduced here.

| Credential | Where it was committed (tree state before this branch) | Owner action |
|---|---|---|
| Production `PHAROS_ADMIN_TOKEN` (full API access to `pharos-cloud-api.onrender.com`) | `.claude/settings.local.json`, `.kiro/steering/admin-credentials.md`, `backend/start_worker.ps1`, `backend/scripts/backfill_chunk_embeddings.py`, ~15 docs under `docs/archive/` and `backend/docs/archive/` | Generate a new token (`python -c "import secrets; print(secrets.token_hex(32))"`), set it in Render, update Ronin / edge worker `.env` |
| Neon Postgres password, endpoint `ep-flat-meadow-…` | `backend/deployment/render.yaml`, `backend/start_worker.ps1`, ~10 archived docs | Reset the `neondb_owner` password in the Neon console, update `DATABASE_URL` in Render and the edge worker |
| Neon Postgres password, endpoint `ep-fancy-grass-…` | `backend/config/.env.staging` | Same as above (or delete the project if unused) |
| Upstash Redis REST token, database `lucky-pug-…` | `backend/config/.env.staging` | Rotate the token in the Upstash console |
| Upstash Redis REST token + `rediss://` password, database `living-sculpin-…` | `backend/start_worker.ps1`, several archived docs | Rotate the token / password in the Upstash console |
| Qdrant Cloud API key | `backend/config/.env.staging` | Revoke the key in the Qdrant console (Qdrant is no longer used by the code) |
| `JWT_SECRET_KEY` used in production | `backend/start_worker.ps1`, archived deployment docs | Replace in Render. JWT auth was removed from the request path, so this only matters if the old value is still configured anywhere |
| A sample JWT access token | `.kiro/specs/frontend/phase2.5-backend-api-integration/AUTH_SETUP.md` | Low risk (signed with a dev secret); covered by the rotation above |

Non-secret but sensitive operational details are also present: the Tailscale
Funnel hostname of the developer's machine. Consider whether the Funnel should
stay enabled; when it is, the embed server must not be reachable without
authentication (see `SECURITY.md`).

## What this branch does

- Deletes `backend/config/.env.staging` and `.kiro/steering/admin-credentials.md`.
- Stops tracking `.claude/`, `.idea/`, `.vscode/`, `.venv/` and other local
  state that can carry tokens in command history.
- Replaces every remaining occurrence of the values above with
  `<REDACTED-…-rotate>` markers (71 + 170 + 4 replacements across ~90 files).
- Rewrites `backend/start_worker.ps1` to read `backend/.env` instead of
  hard-coding credentials.
- Extends `.gitignore` so env files, local agent state and databases are not
  re-committed.
- Adds a secret scan (`detect-secrets` with a reviewed baseline) to CI.

## Proposed history remediation (requires owner approval — not done)

Rewriting history on a public repository is destructive: it changes every
commit SHA, breaks existing clones and open PRs, and does **not** remove copies
that others already have. It is only worthwhile **after** rotation, to stop
the old values from being trivially discoverable.

If the owner approves:

1. Rotate everything in the table above first.
2. Make a mirror backup: `git clone --mirror https://github.com/ram-tewari/PHAROS pharos-backup.git`.
3. Write the old values to a local, untracked `replacements.txt`, one per line
   (`<old-value>==>REDACTED`).
4. `git filter-repo --replace-text replacements.txt --invert-paths --path backend/config/.env.staging --path .kiro/steering/admin-credentials.md --path .claude/settings.local.json`.
5. Force-push all branches and tags. Ask GitHub Support to purge cached views
   of the old commits (Settings → contact support → "remove sensitive data").
6. Ask anyone with a clone to re-clone.
