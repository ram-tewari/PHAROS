# Security

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's
[private vulnerability reporting](https://github.com/ram-tewari/PHAROS/security/advisories/new), not in a
public issue. If that form is not available, open an issue that asks for a private contact and contains no
details. Include affected versions or commits, a reproduction and the impact you expect. You should get
an acknowledgement within a week.

## Known incident: credentials in Git history

Production credentials (API token, database and Redis passwords, a Qdrant key) were committed to this
public repository before 2026-10. They have been removed from the working tree, but they remain in
history and in existing clones. They **must be rotated** by the owner; deleting the files is not enough.
The list, the per-credential actions and an optional, approval-gated history rewrite are in
[docs/security/credential-exposure-2026-10.md](docs/security/credential-exposure-2026-10.md).

## Threat model

PHAROS clones and parses repositories that it does not control, and answers questions for AI agents
that relay untrusted text. The design assumes that **repository content, repository URLs and query
text are hostile**.

| Threat | Mitigation | Where |
|---|---|---|
| Executing repository code (build scripts, `conftest.py`, hooks) | Code is only read: Python `ast` and tree-sitter parse bytes, nothing is imported or run. Clones use `core.hooksPath=/dev/null` and `protocol.allow=never` with https only, and are bare, so no checkout and no hooks. | `app/codeintel/git_source.py`, `parsers/`; test `test_indexing_never_executes_repository_code` |
| SSRF and protocol smuggling through repository URLs (`ext::`, `file://`, `169.254.169.254`, IP literals, `user@host`, ports, `--upload-pack`) | One validator, `parse_repo_spec`: https only, host allowlist (`CODEINTEL_ALLOWED_GIT_HOSTS`), no credentials, ports, queries, IP literals or `..`, a strict segment pattern. Git runs with `http.followRedirects=false`. Local paths are accepted only from the CLI. | `git_source.py`; `tests/codeintel/test_url_security.py` (83 cases) |
| Source fetches redirected to other hosts, oversized bodies | Code is fetched only from the repository's own raw host, without redirects, with a 2 MB cap and a 5 s timeout, and is **verified against the indexed git blob SHA**. A mismatch is reported as `unavailable:content_mismatch`, never returned. | `app/codeintel/source.py` |
| Resource exhaustion through huge repositories or files | `CODEINTEL_MAX_FILES`, `CODEINTEL_MAX_FILE_BYTES`, clone timeout, minified/binary detection, a per-file symbol cap, and a queue cap (`MAX_QUEUE_SIZE`, HTTP 429) | `indexer.py`, `jobs.py` |
| Clone tokens leaking | `GIT_CLONE_TOKEN` is passed as an `http.<host>.extraHeader` scoped to the repository's host, never in the URL, argv or error messages | `git_source._auth_config`; test `test_clone_token_is_not_in_argv_or_error` |
| Unauthenticated access | Every route except an exact list of public paths needs a bearer token. Tokens are compared in constant time. With no tokens configured, the API returns 401 (fails closed). | `app/shared/auth.py` |
| Privilege escalation by a read-only client (e.g. an MCP agent) | Two scopes. The read token can call GET routes and an explicit list of read-only POST routes (search, context, `/mcp`). Indexing, deletion, job control and the REST tool-invocation endpoint need the admin token. | `auth.py`; `tests/codeintel/test_api.py::test_read_token_scope` |
| Test switches reaching production | `TEST_AUTH_BYPASS`, `TESTING` and `TEST_MODE` make settings validation fail when `ENV=prod` | `app/config/settings.py` |
| DNS rebinding against a local MCP server | MCP transport security allows only localhost plus `MCP_ALLOWED_HOSTS` | `app/modules/mcp/native_server.py` |
| SQL injection through queries | All SQL is parameterised. Full-text queries are built from `[a-z0-9]+` terms only. | `retrieval.py`, `text.tsquery_from_terms` |
| Secrets committed again | `.gitignore` covers env files and local agent/IDE state. CI runs `detect-secrets` against a reviewed baseline. | `.secrets.baseline`, `.github/workflows/ci.yml` |
| Vulnerable dependencies | Hash-pinned locks (`pip install --require-hashes`). CI runs `pip-audit` on the cloud lock. | `backend/requirements-*.txt` |

### Edge embedding server

The edge worker serves `/embed` and `/embed/batch` for the cloud API. Set `EDGE_EMBED_TOKEN` on both
sides: the server then requires it as a bearer token. Bind it to `127.0.0.1` (`EDGE_EMBED_HOST`) unless
it sits behind an authenticated tunnel. If it is exposed through a public tunnel such as Tailscale Funnel
without a token, anyone can use the GPU.

### Out of scope / known gaps

- No per-client rate limiting beyond the ingestion queue cap; put the API behind a proxy that rate-limits.
- Tokens are static and shared per scope: there is no per-user identity or audit log of who queried what.
- Legacy modules (papers/PDF ingestion, resource graph, planning) predate this review. They are
  admin-only for writes but have not been audited to the same depth as `app/codeintel`.
