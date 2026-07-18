"""
Native MCP Server — streamable-HTTP transport

Serves a real Model Context Protocol server (official `mcp` SDK) so MCP
clients (Claude Code, Cursor, ...) can connect to Pharos directly via
`claude mcp add --transport http`, instead of only through the REST-shaped
`/api/v1/mcp/...` endpoints in `router.py`.

Two SDK traps this module works around (see plans/001-native-mcp-transport.md):

1. Double-path trap: `FastMCP.streamable_http_app()` serves at its internal
   `streamable_http_path` (default "/mcp"). If that app is then mounted at
   "/mcp" in the parent app, the effective endpoint becomes "/mcp/mcp". We
   construct FastMCP with `streamable_http_path="/"` so mounting at "/mcp"
   in `app/__init__.py` serves at exactly "/mcp".
2. Lifespan trap: mounted sub-apps do not receive FastAPI's own lifespan.
   The streamable-HTTP transport requires `mcp_native.session_manager.run()`
   to be active for the whole app lifetime or every request 500s. That is
   wired into the parent app's lifespan in `app/__init__.py`, not here.

Tool handlers are NOT reimplemented here. `retrieve_context` mirrors the
construction used by the REST endpoint in `router.py`
(`get_context_assembly_service` / `retrieve_context_di`). The remaining
tools delegate to the existing async handlers in `TOOL_HANDLERS` (`.tools`)
so there is exactly one implementation of each tool's logic.
"""

import logging
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from .context_schema import ContextRetrievalRequest
from .context_service import ContextAssemblyService
from .tools import TOOL_HANDLERS, TOOL_SCHEMAS
from ...shared.database import get_sync_db
from ...shared.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


# Construct with streamable_http_path="/" (see double-path trap above) —
# the parent app mounts this at "/mcp", so the effective path is "/mcp".
mcp_native = FastMCP(
    "pharos",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


@mcp_native.tool(
    description=(
        "Assemble context from all intelligence layers (semantic search, "
        "GraphRAG, developer patterns, PDF annotations) for an LLM coding "
        "assistant. Mirrors the /api/v1/mcp/context/retrieve REST endpoint."
    )
)
async def retrieve_context(
    query: str,
    codebase: str,
    user_id: Optional[str] = None,
    max_code_chunks: int = 10,
    max_graph_hops: int = 2,
    max_pdf_chunks: int = 5,
    include_patterns: bool = True,
    profile_id: Optional[str] = None,
    timeout_ms: int = 1000,
) -> Dict[str, Any]:
    """Assemble context for Ronin/Claude Code from all intelligence layers."""
    db = next(get_sync_db())
    try:
        service = ContextAssemblyService(db, None, EmbeddingService())
        request = ContextRetrievalRequest(
            query=query,
            codebase=codebase,
            user_id=user_id,
            max_code_chunks=max_code_chunks,
            max_graph_hops=max_graph_hops,
            max_pdf_chunks=max_pdf_chunks,
            include_patterns=include_patterns,
            profile_id=profile_id,
            timeout_ms=timeout_ms,
        )
        response = await service.assemble_context(request)
        return response.model_dump()
    finally:
        db.close()


# Thin wrapper tools below delegate to the existing sanctioned handlers in
# .tools — do not reimplement their logic here (module isolation gate lives
# in tools.py's existing imports). Parameters mirror each tool's
# TOOL_SCHEMAS["...]["input_schema"] so MCP clients see a real, typed schema
# instead of an opaque arguments blob.


@mcp_native.tool(description=TOOL_SCHEMAS["search_resources"]["description"])
async def search_resources(query: str, limit: int = 10, offset: int = 0) -> Any:
    return await TOOL_HANDLERS["search_resources"](
        {"query": query, "limit": limit, "offset": offset}, context={}
    )


@mcp_native.tool(description=TOOL_SCHEMAS["get_hover_info"]["description"])
async def get_hover_info(
    file_path: str, line: int, column: int, resource_id: int
) -> Any:
    return await TOOL_HANDLERS["get_hover_info"](
        {
            "file_path": file_path,
            "line": line,
            "column": column,
            "resource_id": resource_id,
        },
        context={},
    )


@mcp_native.tool(description=TOOL_SCHEMAS["compute_graph_metrics"]["description"])
async def compute_graph_metrics(resource_ids: List[int]) -> Any:
    return await TOOL_HANDLERS["compute_graph_metrics"](
        {"resource_ids": resource_ids}, context={}
    )


@mcp_native.tool(description=TOOL_SCHEMAS["detect_communities"]["description"])
async def detect_communities(
    resource_ids: List[int], resolution: float = 1.0
) -> Any:
    return await TOOL_HANDLERS["detect_communities"](
        {"resource_ids": resource_ids, "resolution": resolution}, context={}
    )


def get_streamable_http_app():
    """Return the ASGI app to mount at "/mcp" in the parent FastAPI app."""
    return mcp_native.streamable_http_app()
