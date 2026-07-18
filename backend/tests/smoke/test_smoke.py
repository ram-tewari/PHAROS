"""Smoke suite — the money paths that must never silently break.

Fast, dependency-light, no GPU, no network. This is the suite CI gates on.
Each test guards a specific failure this codebase has actually suffered:

  - auth bypass via a client header (security hole, fixed)
  - torch leaking into the CLOUD process (broke the 512 MB / $7-mo claim)
  - polyglot AST silently degrading to line-chunking (tree-sitter API drift)
  - protected endpoints served without a token

Run just this suite:  pytest tests/smoke -q
"""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Auth middleware — the security regressions
# ---------------------------------------------------------------------------

def _clear_settings_cache():
    import app.config.settings as settings_mod
    getter = settings_mod.get_settings
    if hasattr(getter, "cache_clear"):
        getter.cache_clear()


def _auth_client(monkeypatch, env: str, admin_token: str | None, bypass: str | None):
    """A TestClient whose auth middleware sees a controlled environment.

    The session-wide conftest sets TEST_AUTH_BYPASS=true so the big suite's
    fixtures work; these tests must override that to exercise the REAL auth
    path. monkeypatch restores everything at test end. The middleware reads the
    token/bypass from os.environ live per request and calls get_settings() per
    request, so clearing the settings lru_cache is enough to pick up a new ENV.
    """
    monkeypatch.setenv("ENV", env)
    monkeypatch.delenv("TESTING", raising=False)  # let middleware enforce, not skip
    if admin_token is not None:
        monkeypatch.setenv("PHAROS_ADMIN_TOKEN", admin_token)
    else:
        monkeypatch.delenv("PHAROS_ADMIN_TOKEN", raising=False)
    if bypass is not None:
        monkeypatch.setenv("TEST_AUTH_BYPASS", bypass)
    else:
        monkeypatch.delenv("TEST_AUTH_BYPASS", raising=False)
    _clear_settings_cache()

    from app import create_app
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _restore_settings_cache():
    """Ensure the settings lru_cache doesn't leak a test's ENV into others."""
    yield
    _clear_settings_cache()


def test_bypass_header_is_ignored(monkeypatch):
    """A client-supplied X-Test-Auth-Bypass header must NOT bypass auth.

    This was a real hole: any caller could add the header and skip auth
    entirely against the live service.
    """
    client = _auth_client(monkeypatch, env="dev", admin_token="secret-token", bypass=None)
    # A protected endpoint + the old magic header. Must still be rejected.
    resp = client.get(
        "/api/resources",
        headers={"X-Test-Auth-Bypass": "true"},
    )
    assert resp.status_code == 401, (
        f"bypass header was honored (status {resp.status_code}) — security regression"
    )


def test_protected_endpoint_requires_token(monkeypatch):
    client = _auth_client(monkeypatch, env="dev", admin_token="secret-token", bypass=None)
    resp = client.get("/api/resources")
    assert resp.status_code == 401


def test_valid_admin_token_is_accepted(monkeypatch):
    client = _auth_client(monkeypatch, env="dev", admin_token="secret-token", bypass=None)
    resp = client.get(
        "/api/resources",
        headers={"Authorization": "Bearer secret-token"},
    )
    # Anything but 401/403 means the token cleared the auth gate (endpoint may
    # 200, 404, 422, or 500 downstream — we only assert auth passed).
    assert resp.status_code not in (401, 403), (
        f"valid admin token was rejected (status {resp.status_code})"
    )


def test_health_is_public(monkeypatch):
    client = _auth_client(monkeypatch, env="dev", admin_token="secret-token", bypass=None)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "healthy"


def test_search_endpoint_is_not_public(monkeypatch):
    """The three-way hybrid search endpoint used to be in the excluded-paths
    allowlist, exposing the indexed corpus without a token. It must not be."""
    client = _auth_client(monkeypatch, env="dev", admin_token="secret-token", bypass=None)
    resp = client.post(
        "/api/search/search/three-way-hybrid",
        json={"query": "anything"},
    )
    assert resp.status_code == 401, (
        f"search endpoint answered without auth (status {resp.status_code})"
    )


# ---------------------------------------------------------------------------
# Cloud/edge split — torch must never load in CLOUD mode
# ---------------------------------------------------------------------------

def test_cloud_mode_does_not_import_torch():
    """MODE=CLOUD must build the app without importing torch/transformers.

    Loading them either OOMs Render's 512 MB container or (if not installed)
    silently drops modules. This runs in a subprocess so it observes a clean
    import graph regardless of what the parent test process already loaded.
    """
    import subprocess
    import textwrap

    code = textwrap.dedent(
        """
        import os, sys
        os.environ["MODE"] = "CLOUD"
        os.environ.pop("TESTING", None)
        from app import create_app
        app = create_app()
        heavy = [m for m in ("torch", "transformers", "sentence_transformers")
                 if m in sys.modules]
        print("HEAVY=" + ",".join(heavy))
        # The native MCP server (real MCP protocol, mcp>=1.9,<2) must be
        # mounted at exactly "/mcp" without dragging torch into the CLOUD
        # boot path — the SDK depends only on httpx/anyio/pydantic/starlette.
        mcp_mounted = any(
            getattr(route, "path", None) == "/mcp" for route in app.routes
        )
        print("MCP_MOUNTED=" + str(mcp_mounted))
        sys.exit(1 if (heavy or not mcp_mounted) else 0)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(Path(__file__).resolve().parents[2]),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "CLOUD mode imported the ML stack at load time, or /mcp was not "
        "mounted: "
        + [
            ln
            for ln in result.stdout.splitlines()
            if ln.startswith("HEAVY=") or ln.startswith("MCP_MOUNTED=")
        ].__repr__()
        + f"\nstderr tail: {result.stderr[-1000:]}"
    )


def test_prod_entrypoint_imports():
    """`app.main` must import with ENV=prod — the exact path Render boots.

    create_app()-based tests never execute main.py's module-level code, so a
    broken prod-only import (e.g. the JSON-logging branch pulling in a
    deleted module) boots fine in tests and crash-loops in production.
    This happened: ml_monitoring/__init__.py kept importing files deleted
    in Phase 2 and only ENV=prod hit it.
    """
    import subprocess
    import textwrap

    code = textwrap.dedent(
        """
        import os, secrets
        os.environ["ENV"] = "prod"
        os.environ["MODE"] = "CLOUD"
        # prod refuses to boot with the default secret; Render sets a real one
        os.environ["JWT_SECRET_KEY"] = secrets.token_hex(32)
        # neutralize dev-machine leakage (.env / shell) that prod forbids
        os.environ["TEST_MODE"] = "false"
        os.environ.pop("TEST_AUTH_BYPASS", None)
        os.environ.pop("TESTING", None)
        # prod requires HTTPS redirect URLs (Render sets real ones)
        os.environ["FRONTEND_URL"] = "https://example.invalid"
        os.environ["ALLOWED_REDIRECT_URLS"] = '["https://example.invalid"]'
        import app.main
        assert app.main.app is not None
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(Path(__file__).resolve().parents[2]),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"app.main failed to import with ENV=prod (Render's boot path):\n"
        f"{result.stderr[-2000:]}"
    )


# ---------------------------------------------------------------------------
# Polyglot AST — grammars present AND tree-sitter API compatible
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "filename,source",
    [
        ("x.go", "package m\nimport \"fmt\"\nfunc Hello() { fmt.Println(1) }\n"),
        ("x.rs", "fn hello() {}\nstruct P { x: i32 }\n"),
        ("x.ts", "export function hello(): void {}\nclass Foo {}\n"),
        ("x.js", "function hello() {}\n"),
    ],
)
def test_polyglot_ast_extracts_symbols(filename, source):
    """Non-Python languages must parse via tree-sitter, not fall back to
    line-chunking. Guards both missing grammar packages and tree-sitter API
    drift (Language.query() removed in 0.25+)."""
    from app.modules.ingestion.language_parser import LanguageParser

    parser = LanguageParser.for_path(Path(filename))
    assert parser is not None, f"no parser for {filename}"
    symbols = parser.extract(source, "probe")
    names = {s.name for s in symbols}
    assert "hello" in {n.lower() for n in names} or "Hello" in names, (
        f"{filename} produced no function symbol (line-chunk fallback?): {names}"
    )
