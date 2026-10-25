"""HTTP API contract: auth, validation, error shapes, end-to-end flow, MCP."""

import json

import pytest

from tests.codeintel.conftest import ADMIN_TOKEN, READ_TOKEN, auth


@pytest.fixture
def indexed_api(api, indexed):
    return api


# ── authentication ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/health", "/openapi.json", "/api/v1/ingestion/health"])
def test_public_paths(api, path):
    assert api.get(path).status_code == 200


@pytest.mark.parametrize("path", ["/healthz", "/health/../api/v1/repositories", "/docsx", "/api/v1/repositories"])
def test_protected_paths_need_a_token(api, path):
    assert api.get(path).status_code in (401, 404)
    assert api.get("/api/v1/repositories").status_code == 401


@pytest.mark.parametrize(
    "header",
    [{"Authorization": "Bearer wrong"}, {"Authorization": f"Basic {ADMIN_TOKEN}"}, {"Authorization": ADMIN_TOKEN},
     {"Authorization": "Bearer "}, {"X-API-Key": ADMIN_TOKEN}],
)
def test_bad_credentials_are_rejected(api, header):
    resp = api.get("/api/v1/repositories", headers=header)
    assert resp.status_code == 401
    assert ADMIN_TOKEN not in resp.text


def test_read_token_scope(indexed_api):
    api = indexed_api
    assert api.get("/api/v1/repositories", headers=auth(READ_TOKEN)).status_code == 200
    assert api.post("/api/v1/search/code", json={"query": "cart"}, headers=auth(READ_TOKEN)).status_code == 200
    assert api.post("/api/v1/context/retrieve", json={"query": "cart"}, headers=auth(READ_TOKEN)).status_code == 200
    denied = [
        api.post("/api/v1/repositories", json={"repository": "github.com/a/b"}, headers=auth(READ_TOKEN)),
        api.post("/api/search/admin/sparse-embeddings/generate", json={}, headers=auth(READ_TOKEN)),
        api.post("/api/v1/ingestion/ingest/github.com/a/b", headers=auth(READ_TOKEN)),
    ]
    assert [r.status_code for r in denied] == [403, 403, 403]
    repo_id = api.get("/api/v1/repositories", headers=auth(READ_TOKEN)).json()[0]["id"]
    assert api.delete(f"/api/v1/repositories/{repo_id}", headers=auth(READ_TOKEN)).status_code == 403


def test_auth_fails_closed_without_configured_token(api, monkeypatch):
    monkeypatch.delenv("PHAROS_ADMIN_TOKEN")
    monkeypatch.delenv("PHAROS_READ_TOKEN")
    assert api.get("/api/v1/repositories", headers=auth()).status_code == 401


# ── repository submission ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "repository",
    ["/etc", "file:///etc/passwd", "http://github.com/a/b", "https://169.254.169.254/x/y",
     "https://gitlab.com/a/b", "github.com/a/b; rm -rf /", "x" * 3000,
     "javascript:alert(1)", "github.com:junk/a/b"],
)
def test_repository_validation(api, repository):
    resp = api.post("/api/v1/repositories", json={"repository": repository}, headers=auth())
    assert resp.status_code in (400, 422)


def test_submission_dedupes_and_job_is_readable(api):
    body = {"repository": "github.com/Example/Repo"}
    first = api.post("/api/v1/repositories", json=body, headers=auth())
    second = api.post("/api/v1/repositories", json={"repository": "https://github.com/example/repo.git"}, headers=auth())
    assert first.status_code == second.status_code == 202
    assert first.json()["created"] is True and second.json()["created"] is False
    job_id = first.json()["job"]["id"]
    assert second.json()["job"]["id"] == job_id
    job = api.get(f"/api/v1/ingestion/jobs/{job_id}", headers=auth(READ_TOKEN)).json()
    assert job["status"] == "queued" and job["repo_url"] == "https://github.com/example/repo"
    assert api.get("/api/v1/ingestion/jobs/history", headers=auth()).json()["jobs"][0]["job_id"] == job_id
    cancelled = api.post(f"/api/v1/ingestion/jobs/{job_id}/cancel", headers=auth())
    assert cancelled.json()["status"] == "cancelled"
    assert api.post(f"/api/v1/ingestion/jobs/{job_id}/cancel", headers=auth()).status_code == 409



def test_queue_cap_returns_429_but_resubmission_still_dedupes(api, codeintel_settings, monkeypatch):
    monkeypatch.setattr(codeintel_settings, "QUEUE_SIZE", 2)
    for name in ("a/one", "a/two"):
        assert api.post("/api/v1/repositories", json={"repository": name}, headers=auth()).status_code == 202
    full = api.post("/api/v1/repositories", json={"repository": "a/three"}, headers=auth())
    assert full.status_code == 429 and full.headers["retry-after"] == "60"
    assert full.json()["detail"]["error"] == "queue_full" and full.json()["detail"]["limit"] == 2
    again = api.post("/api/v1/repositories", json={"repository": "a/one"}, headers=auth())
    assert again.status_code == 202 and again.json()["created"] is False
    legacy = api.post("/api/v1/ingestion/ingest/github.com/a/four", headers=auth())
    assert legacy.status_code == 429

def test_unknown_ids_are_404(api):
    import uuid

    assert api.get(f"/api/v1/ingestion/jobs/{uuid.uuid4()}", headers=auth()).status_code == 404
    assert api.get(f"/api/v1/repositories/{uuid.uuid4()}", headers=auth()).status_code == 404
    assert api.get("/api/v1/repositories/not-a-uuid", headers=auth()).status_code == 422


def test_legacy_ingest_endpoint_queues_a_durable_job(api):
    resp = api.post("/api/v1/ingestion/ingest/github.com/fatih/color", headers=auth())
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    assert api.post("/api/v1/ingestion/ingest/github.com/fatih/color", headers=auth()).json()["status"] == "already_active"


# ── retrieval endpoints ────────────────────────────────────────────────────


def test_search_code_contract(indexed_api, fixture_repo):
    resp = indexed_api.post(
        "/api/v1/search/code",
        json={"query": "check a password against the stored hash", "repository": "tinyshop", "k": 3},
        headers=auth(READ_TOKEN),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode_requested"] == "auto" and data["mode_used"] == "graph"
    top = data["results"][0]
    assert top["repository"]["name"] == "tinyshop"
    assert top["commit_sha"] == fixture_repo.head
    assert set(top["evidence"]) == {"keyword_rank", "keyword_score", "dense_rank", "dense_similarity", "graph", "boosts"}
    assert "shop.auth.verify_password" in [r["symbol"] for r in data["results"]]


def test_search_unavailable_mode_is_503(indexed_api, codeintel_settings, monkeypatch):
    from app.codeintel import embeddings

    monkeypatch.setattr(codeintel_settings, "EMBEDDING_BACKEND", "none")
    monkeypatch.setenv("EMBEDDING_BACKEND", "none")
    embeddings.reset_embedder_cache()
    resp = indexed_api.post("/api/v1/search/code", json={"query": "cart", "mode": "dense"}, headers=auth())
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "mode_unavailable"
    auto = indexed_api.post("/api/v1/search/code", json={"query": "cart"}, headers=auth()).json()
    assert auto["mode_used"] == "keyword" and auto["warnings"]


@pytest.mark.parametrize(
    "body",
    [{"query": ""}, {"query": "x" * 2001}, {"query": "x", "k": 0}, {"query": "x", "k": 1000},
     {"query": "x", "mode": "magic"}, {"query": "x", "languages": ["py"] * 50}],
)
def test_search_validation(api, body):
    assert api.post("/api/v1/search/code", json=body, headers=auth()).status_code == 422


def test_unknown_repository_is_404(indexed_api):
    resp = indexed_api.post("/api/v1/search/code", json={"query": "x", "repository": "nope/nope"}, headers=auth())
    assert resp.status_code == 404 and resp.json()["detail"]["error"] == "repository_not_found"


def test_context_contract(indexed_api):
    resp = indexed_api.post(
        "/api/v1/context/retrieve",
        json={"query": "how does checkout charge the cart", "repository": "tinyshop", "max_chunks": 3},
        headers=auth(READ_TOKEN),
    )
    assert resp.status_code == 200
    ctx = resp.json()
    assert len(ctx["chunks"]) == 3
    assert all(c["code_status"] == "resolved" and c["verified"] for c in ctx["chunks"])
    assert ctx["context_text"].startswith("# Code context for:")
    # Deprecated alias returns the same shape.
    alias = indexed_api.post(
        "/api/v1/mcp/context/retrieve", json={"query": "checkout", "codebase": "tinyshop"}, headers=auth(READ_TOKEN)
    )
    assert alias.status_code == 200 and "chunks" in alias.json()


def test_symbol_lookup(indexed_api):
    resp = indexed_api.post("/api/v1/search/symbol", json={"name": "TokenSigner.verify"}, headers=auth())
    match = resp.json()["matches"][0]
    assert match["symbol"] == "shop.auth.TokenSigner.verify"
    assert match["verified"] is True and "def verify" in match["code"]
    callers = {c["symbol"] for c in match["graph"]["called_by"]}
    assert callers == {"shop.api.add_to_cart_handler", "shop.api.checkout_handler"}


def test_repositories_and_status(indexed_api):
    repos = indexed_api.get("/api/v1/repositories", headers=auth()).json()
    assert repos[0]["index_status"] == "ready" and repos[0]["languages"]["go"]["ast_files"] == 1
    status = indexed_api.get("/api/v1/system/status", headers=auth()).json()
    assert status["database"]["status"] == "ok"
    assert status["embedding"]["model_id"] == "hash-v1" and status["embedding"]["semantic"] is False
    assert set(status["grammars"].values()) == {"ok"}
    assert status["index"]["chunks"] > 50
    assert ADMIN_TOKEN not in json.dumps(status) and READ_TOKEN not in json.dumps(status)


def test_delete_repository(indexed_api):
    repo_id = indexed_api.get("/api/v1/repositories", headers=auth()).json()[0]["id"]
    assert indexed_api.delete(f"/api/v1/repositories/{repo_id}", headers=auth()).status_code == 204
    assert indexed_api.get("/api/v1/repositories", headers=auth()).json() == []
    out = indexed_api.post("/api/v1/search/code", json={"query": "cart", "mode": "keyword"}, headers=auth()).json()
    assert out["results"] == []


# ── native MCP (JSON-RPC over streamable HTTP) ─────────────────────────────


def _mcp(api, method, params=None, token=READ_TOKEN):
    headers = {**auth(token), "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return api.post("/mcp/", json=body, headers=headers)


def test_mcp_tools_and_calls(indexed_api):
    init = _mcp(indexed_api, "initialize", {
        "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "pytest", "version": "1"},
    })
    assert init.status_code == 200 and init.json()["result"]["serverInfo"]["name"] == "pharos"
    tools = {t["name"] for t in _mcp(indexed_api, "tools/list").json()["result"]["tools"]}
    assert tools == {"retrieve_context", "search_code", "find_symbol", "list_repositories"}
    call = _mcp(indexed_api, "tools/call", {"name": "search_code", "arguments": {"query": "token bucket", "k": 2}})
    payload = json.loads(call.json()["result"]["content"][0]["text"])
    assert payload["results"][0]["symbol"] == "tools.ratelimit.limiter.Bucket"


def test_mcp_requires_token(indexed_api):
    assert _mcp(indexed_api, "tools/list", token="wrong").status_code == 401


# ── code-aware legacy endpoints ────────────────────────────────────────────


def _resource_id(session, path):
    from sqlalchemy import select

    from app.database.models import Resource

    return str(session.execute(select(Resource.id).where(Resource.identifier == path)).scalar_one())


def test_hover_on_indexed_code(indexed_api, session):
    """GET /api/graph/code/hover resolves the innermost symbol from the code index."""
    rid = _resource_id(session, "shop/auth.py")
    resp = indexed_api.get(
        "/api/graph/code/hover",
        params={"file_path": "shop/auth.py", "line": 22, "column": 8, "resource_id": rid},
        headers=auth(READ_TOKEN),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["symbol_name"] == "shop.auth.verify_password" and body["symbol_type"] == "function"
    assert body["definition_location"]["line"] == 20
    assert "constant time" in body["documentation"]
    previews = " ".join(r["content_preview"] for r in body["related_chunks"])
    assert "calls: shop.auth.hash_password" in previews and "called_by: shop.auth.authenticate" in previews
    assert any("def verify_password" in line for line in body["context_lines"])  # verified source from git


@pytest.mark.parametrize("tool", ["search_resources", "get_hover_info", "compute_graph_metrics", "detect_communities"])
def test_legacy_mcp_invoke_tools_run(indexed_api, session, tool):
    """The REST tool-invocation endpoint's read tools execute (they used to raise TypeError/AttributeError)."""
    rid = _resource_id(session, "shop/auth.py")
    arguments = {
        "search_resources": {"query": "password", "limit": 3},
        "get_hover_info": {"file_path": "shop/auth.py", "line": 22, "column": 8, "resource_id": rid},
        "compute_graph_metrics": {"resource_ids": [rid]},
        "detect_communities": {"resource_ids": [rid]},
    }[tool]
    resp = indexed_api.post("/api/v1/mcp/invoke", json={"tool_name": tool, "arguments": arguments}, headers=auth())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True and body["error"] is None, body
    if tool == "get_hover_info":
        assert body["result"]["symbol_name"] == "shop.auth.verify_password"


def test_principals_have_stable_distinct_uuids():
    from app.shared.auth import ADMIN, READER

    assert ADMIN.as_state()["user_id"] == str(ADMIN.user_uuid)
    assert ADMIN.user_uuid != READER.user_uuid
    assert ADMIN.user_uuid.version == 5  # deterministic across processes and restarts
