"""
MCP Module Router

FastAPI endpoints for MCP server operations.
Phase 5: Added context assembly endpoint for Ronin integration.
Phase 5.1: Added M2M API Key Authentication for secure access.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .context_schema import ContextRetrievalRequest
from .schema import (
    CreateSessionRequest,
    ListToolsResponse,
    SessionResponse,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from .service import MCPServer
from .tools import register_all_tools
from ...shared.database import get_sync_db

logger = logging.getLogger(__name__)


def get_mcp_server(db: Session = Depends(get_sync_db)) -> MCPServer:
    """Get an MCP server (with its tools) bound to this request's DB session.

    Each MCPServer has its own ToolRegistry, so tools are registered on every
    instance. (Registering only "once per process" left every request after
    the first with an empty registry: "Tool not found".)
    """
    server = MCPServer(db)
    register_all_tools(server)
    return server


def get_current_user_optional(request: Request):
    """Get current user from request state if available"""
    return getattr(request.state, "user", None)


# ============================================================================
# MCP Router (Phase 20 - MCP Integration)
# ============================================================================
# Separate router for MCP endpoints with prefix /api/v1/mcp
# This router is registered in app/__init__.py to fix 404 errors

mcp_router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])
# Old name kept for importers; the /mcp-prefixed duplicate router was never
# registered (the native MCP transport owns /mcp).
router = mcp_router


@mcp_router.post("/context/retrieve", deprecated=True)
def retrieve_context(request: ContextRetrievalRequest, db: Session = Depends(get_sync_db)):
    """Deprecated alias of ``POST /api/v1/context/retrieve``.

    Accepts the old request shape (``codebase`` names the repository,
    ``max_code_chunks`` the result count) and returns the new
    ``ContextResponse``. The previous implementation called search methods
    with arguments they do not accept, so it always returned zero code
    chunks, and it required a second, separately configured API key.
    """
    from ...codeintel.context import ContextRequest as CodeContextRequest
    from ...codeintel.context import RepositoryNotFound, assemble_context
    from ...codeintel.embeddings import get_embedder
    from ...codeintel.retrieval import ModeUnavailable

    try:
        return assemble_context(
            db,
            get_embedder(),
            CodeContextRequest(
                query=request.query,
                repository=request.codebase or None,
                max_chunks=request.max_code_chunks,
                include_rules=request.include_patterns,
                profile_id=request.profile_id,
            ),
        )
    except RepositoryNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "repository_not_found", "detail": str(exc)})
    except ModeUnavailable as exc:
        raise HTTPException(status_code=503, detail={"error": "mode_unavailable", "detail": exc.reason})


@mcp_router.get("/tools", response_model=ListToolsResponse)
async def list_tools_di(
    mcp_server: MCPServer = Depends(get_mcp_server),
):
    """
    List all available MCP tools.

    Returns:
        ListToolsResponse: List of available tools with their schemas
    """
    tools = mcp_server.list_tools()
    return ListToolsResponse(tools=tools, total=len(tools))


@mcp_router.post("/invoke", response_model=ToolInvocationResult)
async def invoke_tool_di(
    request: ToolInvocationRequest,
    mcp_server: MCPServer = Depends(get_mcp_server),
    current_user=Depends(get_current_user_optional),
):
    """
    Invoke an MCP tool.

    Args:
        request: Tool invocation request with tool name and arguments

    Returns:
        ToolInvocationResult: Result of tool invocation

    Raises:
        HTTPException: If tool requires auth and user not authenticated
    """
    # Check authentication if tool requires it
    tool = mcp_server.tool_registry.get_tool(request.tool_name)
    if tool and tool["definition"].requires_auth and not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for this tool",
        )

    result = await mcp_server.invoke_tool(
        session_id=request.session_id,
        tool_name=request.tool_name,
        arguments=request.arguments,
    )

    return result


@mcp_router.post(
    "/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED
)
async def create_session_di(
    request: CreateSessionRequest,
    mcp_server: MCPServer = Depends(get_mcp_server),
    current_user=Depends(get_current_user_optional),
):
    """
    Create a new MCP session for multi-turn interactions.

    Args:
        request: Session creation request with initial context

    Returns:
        SessionResponse: Created session information
    """
    # mcp_sessions.user_id is a legacy integer column; M2M principals have no
    # integer id, so sessions are not attributed to a user.
    session = mcp_server.create_session(user_id=None, context=request.context)
    return session


@mcp_router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session_di(
    session_id: str,
    mcp_server: MCPServer = Depends(get_mcp_server),
):
    """
    Get MCP session by ID.

    Args:
        session_id: Session ID

    Returns:
        SessionResponse: Session information

    Raises:
        HTTPException: If session not found
    """
    session = mcp_server.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
    return session


@mcp_router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def close_session_di(
    session_id: str,
    mcp_server: MCPServer = Depends(get_mcp_server),
):
    """
    Close an MCP session.

    Args:
        session_id: Session ID

    Raises:
        HTTPException: If session not found
    """
    success = mcp_server.close_session(session_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {session_id}",
        )
