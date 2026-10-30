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
``get_repo_brief``    a repository's brief            (= GET  /api/v1/memory/brief)
``search_memory``     learned facts and conventions   (= POST /api/v1/memory/search)
``list_skills``       a repository's playbooks        (= GET  /api/v1/memory/skills)
``get_skill``         one playbook, levels 1-2        (= GET  /api/v1/memory/skills/{name})

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
from ...learning import recall

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
            "ranked functions/classes with verified source, their callers/callees, what PHAROS learned "
            "about the repository (brief, conventions for these files, playbooks) and its coding rules, "
            "plus a Markdown rendering with path:line citations. "
            "Ask in plain words; optionally pass hints: identifiers or keywords you guess the code uses "
            "(e.g. ['parse_url', 'redirect'])."
        )
    )
    def retrieve_context(
        query: str,
        repository: str | None = None,
        max_chunks: int = 8,
        include_code: bool = True,
        max_chars: int = 24000,
        profile_id: str | None = None,
        hints: list[str] | None = None,
        include_memory: bool = True,
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
                        hints=(hints or [])[:20] or None,
                        include_memory=include_memory,
                    ),
                    fetch_token=secret(get_settings().GIT_CLONE_TOKEN),
                )
            except (ModeUnavailable, RepositoryNotFound) as exc:
                return _error(exc)

    @server.tool(
        description=(
            "Search indexed code. mode: auto (default), keyword, dense, hybrid or graph. "
            "Returns chunk pointers (path, lines, symbol) with retrieval evidence, no code. "
            "Optionally pass hints: identifiers or keywords you guess the code uses."
        )
    )
    def search_code(
        query: str,
        repository: str | None = None,
        mode: str = "auto",
        k: int = 10,
        languages: list[str] | None = None,
        path_prefix: str | None = None,
        hints: list[str] | None = None,
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
                    hints=(hints or [])[:20] or None,
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

    @server.tool(
        description=(
            "The repository brief: what the repository is, its layout, main modules and strongest "
            "conventions, learned from its code and history (at most 2,200 characters). Read it first."
        )
    )
    def get_repo_brief(repository: str) -> dict[str, Any]:
        with session_scope() as db:
            try:
                repos = resolve_repositories(db, repository)
            except RepositoryNotFound as exc:
                return _error(exc)
            out = []
            for repo in repos:
                brief = recall.get_brief(db, repo)
                out.append({"repository": repo.name, "commit_sha": brief.commit_sha if brief else None,
                            "text": brief.text if brief else None})
            return {"briefs": out}

    @server.tool(
        description=(
            "Search what PHAROS learned about a repository: conventions (naming, docs, errors, "
            "deprecation, tests, changelog, commit style), which files change together, and history "
            "(when files were added, dependencies dropped, directories moved). Each result cites evidence. "
            "kinds: convention, co_change, history, fact."
        )
    )
    def search_memory(query: str, repository: str | None = None, k: int = 8,
                      kinds: list[str] | None = None) -> dict[str, Any]:
        with session_scope() as db:
            try:
                ids = [r.id for r in resolve_repositories(db, repository)] or None
            except RepositoryNotFound as exc:
                return _error(exc)
            return {"results": recall.search_memory(db, get_embedder(), query, ids, k=max(1, min(k, 50)),
                                                    kinds=kinds)}

    @server.tool(description="List a repository's playbooks: how recurring changes are made there (one line each).")
    def list_skills(repository: str | None = None) -> dict[str, Any]:
        with session_scope() as db:
            try:
                ids = [r.id for r in resolve_repositories(db, repository)] or None
            except RepositoryNotFound as exc:
                return _error(exc)
            return {"skills": recall.list_skills(db, ids)}

    @server.tool(
        description="One playbook. level 1: steps and example commits; level 2: also every file with its rate."
    )
    def get_skill(name: str, repository: str | None = None, level: int = 1) -> dict[str, Any]:
        with session_scope() as db:
            try:
                ids = [r.id for r in resolve_repositories(db, repository)] or None
            except RepositoryNotFound as exc:
                return _error(exc)
            skill = recall.get_skill(db, ids, name, level)
            return skill if skill else {"error": "skill_not_found", "detail": name}

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
