"""
Native MCP server — streamable-HTTP transport at ``/mcp``.

MCP clients (Claude Code, Cursor, ...) connect directly::

    claude mcp add --transport http pharos http://localhost:8000/mcp \\
        --header "Authorization: Bearer $PHAROS_READ_TOKEN"

Every tool is read-only and backed by :mod:`app.codeintel`, so it returns
exactly what the REST API returns:

``retrieve_context``  assembled context for a question (= POST /api/v1/context/retrieve)
``search_code``       chunk-level code search        (= POST /api/v1/search/code)
``find_symbol``       definition lookup + call graph (= POST /api/v1/search/symbol)
``list_repositories`` indexed repositories           (= GET  /api/v1/repositories)

Two SDK traps handled here and in ``app/__init__.py``:

1. Double path: ``FastMCP.streamable_http_app()`` serves at its
   ``streamable_http_path`` (default "/mcp"); mounting that at "/mcp" would
   serve "/mcp/mcp". We use ``streamable_http_path="/"``.
2. Lifespan: mounted sub-apps do not get the parent's lifespan, and the
   session manager must be running or every request 500s. A
   ``StreamableHTTPSessionManager`` can only be ``run()`` once, so the server
   is built **per application** by :func:`build_mcp_server` (a module-level
   singleton broke every second app instance, e.g. in tests).
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from ...codeintel.context import ContextRequest, RepositoryNotFound, assemble_context, resolve_repositories
from ...codeintel.embeddings import get_embedder
from ...codeintel.retrieval import Filters, ModeUnavailable, Retriever
from ...codeintel.runtime import secret, session_scope
from ...codeintel.symbols import chunk_ref, find_symbol, repository_summary, symbol_graph
from ...config.settings import get_settings
from ...database.models import Repository

logger = logging.getLogger(__name__)


def _error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ModeUnavailable):
        return {"error": "mode_unavailable", "detail": exc.reason}
    if isinstance(exc, RepositoryNotFound):
        return {"error": "repository_not_found", "detail": str(exc)}
    raise exc


_LOCAL_HOSTS = ["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "[::1]", "[::1]:*"]


def _transport_security() -> TransportSecuritySettings:
    """DNS-rebinding protection on, with the deployment's own hostnames allowed.

    The SDK default allows only localhost, which makes every request to a
    deployed server (Host: pharos.example.com) fail with HTTP 421.
    """
    settings = get_settings()
    hosts = _LOCAL_HOSTS + list(settings.MCP_ALLOWED_HOSTS)
    origins = [f"http://{h}" for h in _LOCAL_HOSTS] + list(settings.ALLOWED_ORIGINS)
    origins += [f"https://{h}" for h in settings.MCP_ALLOWED_HOSTS]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins
    )


def build_mcp_server() -> FastMCP:
    server = FastMCP(
        "pharos",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=_transport_security(),
    )

    @server.tool(
        description=(
            "Retrieve the code most relevant to a question about an indexed repository: "
            "ranked functions/classes with verified source, their callers/callees, and the "
            "repository's coding rules, plus a Markdown rendering with path:line citations."
        )
    )
    def retrieve_context(
        query: str,
        repository: str | None = None,
        max_chunks: int = 8,
        include_code: bool = True,
        max_chars: int = 24000,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        with session_scope() as db:
            try:
                return assemble_context(
                    db,
                    get_embedder(),
                    ContextRequest(
                        query=query,
                        repository=repository,
                        max_chunks=max(1, min(max_chunks, 50)),
                        include_code=include_code,
                        max_chars=max(1000, min(max_chars, 400_000)),
                        profile_id=profile_id,
                    ),
                    fetch_token=secret(get_settings().GIT_CLONE_TOKEN),
                )
            except (ModeUnavailable, RepositoryNotFound) as exc:
                return _error(exc)

    @server.tool(
        description=(
            "Search indexed code. mode: auto (default), keyword, dense, hybrid or graph. "
            "Returns chunk pointers (path, lines, symbol) with retrieval evidence, no code."
        )
    )
    def search_code(
        query: str,
        repository: str | None = None,
        mode: str = "auto",
        k: int = 10,
        languages: list[str] | None = None,
        path_prefix: str | None = None,
    ) -> dict[str, Any]:
        from ...codeintel.context import hit_to_dict

        with session_scope() as db:
            try:
                repos = resolve_repositories(db, repository)
                outcome = Retriever(db, get_embedder()).search(
                    query,
                    mode=mode,
                    k=max(1, min(k, 100)),
                    filters=Filters(
                        repository_ids=[r.id for r in repos] or None,
                        languages=languages,
                        path_prefix=path_prefix,
                    ),
                )
            except (ModeUnavailable, RepositoryNotFound) as exc:
                return _error(exc)
            except ValueError as exc:
                return {"error": "invalid_request", "detail": str(exc)}
            return {
                "mode_used": outcome.mode_used,
                "warnings": outcome.warnings,
                "results": [hit_to_dict(h, i) for i, h in enumerate(outcome.hits, start=1)],
            }

    @server.tool(
        name="find_symbol",
        description="Find where a symbol (e.g. 'TokenSigner.verify') is defined, with its callers and callees.",
    )
    def find_symbol_tool(name: str, repository: str | None = None, limit: int = 5) -> dict[str, Any]:
        with session_scope() as db:
            try:
                repos = resolve_repositories(db, repository)
            except RepositoryNotFound as exc:
                return _error(exc)
            matches = find_symbol(db, name, repository_ids=[r.id for r in repos] or None, limit=limit)
            return {
                "name": name,
                "matches": [
                    chunk_ref(c) | {"summary": c.semantic_summary, "graph": symbol_graph(db, c.id)}
                    for c in matches
                ],
            }

    @server.tool(description="List indexed repositories with their commit, language coverage and status.")
    def list_repositories() -> dict[str, Any]:
        from sqlalchemy import select

        with session_scope() as db:
            repos = db.execute(select(Repository).order_by(Repository.name)).scalars().all()
            return {"repositories": [repository_summary(db, r) for r in repos]}

    return server


# Kept for callers that import the old names.
def get_streamable_http_app(server: FastMCP | None = None):
    return (server or build_mcp_server()).streamable_http_app()
