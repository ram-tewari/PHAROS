"""
MCP Module Router

FastAPI endpoints for MCP server operations.
Phase 5: Added context assembly endpoint for Ronin integration.
Phase 5.1: Added M2M API Key Authentication for secure access.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from .context_schema import ContextRetrievalRequest, ContextRetrievalResponse
from .context_service import ContextAssemblyService
from .schema import (
    CreateSessionRequest,
    ListToolsResponse,
    SessionResponse,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from .service import MCPServer
from .tools import register_all_tools
from ...shared.database import get_db, get_sync_db
from ...shared.embeddings import EmbeddingService
from ...shared.security import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])

# Tool registration only needs to happen once
_tools_registered = False


def get_context_assembly_service(
    db: Session = Depends(get_sync_db),
) -> ContextAssemblyService:
    """Get context assembly service instance"""
    # Note: We'll need to handle async_db differently since get_db is async
    # For now, we'll create a workaround
    embedding_service = EmbeddingService()
    # Pass None for async_db - service will handle it
    return ContextAssemblyService(db, None, embedding_service)


def get_mcp_server(db: Session = Depends(get_sync_db)) -> MCPServer:
    """Get MCP server instance with fresh DB session per request."""
    global _tools_registered
    server = MCPServer(db)

    # Register tools on first access
    if not _tools_registered:
        register_all_tools(server)
        _tools_registered = True
        logger.info("MCP tools registered successfully")

    return server


def get_current_user_optional(request: Request):
    """Get current user from request state if available"""
    return getattr(request.state, "user", None)


# ============================================================================
# Phase 5: Context Assembly Endpoint for Ronin Integration
# ============================================================================


@router.post("/context/retrieve", response_model=ContextRetrievalResponse)
async def retrieve_context(
    request: ContextRetrievalRequest,
    context_service: ContextAssemblyService = Depends(get_context_assembly_service),
    current_user=Depends(get_current_user_optional),
    api_key: str = Depends(verify_api_key),  # M2M Authentication
):
    """
    Assemble context from all intelligence layers for Ronin LLM consumption.

    **Security**: Requires valid API key in Authorization header.

    This endpoint orchestrates parallel fetching from:
    - Semantic Search: Top-K code chunks from vector database
    - GraphRAG: 2-hop architectural dependencies
    - Pattern Engine: Developer coding style and preferences
    - External Memory: Relevant PDF annotations

    Performance target: <1000ms for complete context assembly

    Args:
        request: Context retrieval request with query and parameters
        api_key: Validated API key (injected by security dependency)

    Returns:
        ContextRetrievalResponse: Assembled context with XML formatting

    Security:
        - M2M authentication via API key
        - Authorization header required: "Authorization: Bearer <key>"
        - Returns 403 Forbidden if key is missing or invalid

    Example:
        ```bash
        curl -X POST http://localhost:8000/api/mcp/context/retrieve \
          -H "Authorization: Bearer your-api-key-here" \
          -H "Content-Type: application/json" \
          -d '{
            "query": "Refactor my login route",
            "codebase": "app-backend",
            "max_code_chunks": 10,
            "max_graph_hops": 2
          }'
        ```
    """
    # Add user_id if authenticated
    if current_user and not request.user_id:
        request.user_id = str(current_user.id)

    # Assemble context
    response = await context_service.assemble_context(request)

    # Log metrics (including API key usage for audit)
    if response.success and response.context:
        metrics = response.context.metrics
        logger.info(
            f"Context retrieval: query='{request.query[:50]}...', "
            f"codebase={request.codebase}, "
            f"total_time={metrics.total_time_ms}ms, "
            f"code_chunks={len(response.context.code_chunks)}, "
            f"dependencies={len(response.context.graph_dependencies)}, "
            f"patterns={len(response.context.developer_patterns)}, "
            f"annotations={len(response.context.pdf_annotations)}, "
            f"timeout={metrics.timeout_occurred}, "
            f"api_key_length={len(api_key)}"  # Audit log
        )

    return response


@router.get("/tools", response_model=ListToolsResponse)
async def list_tools(
    mcp_server: MCPServer = Depends(get_mcp_server),
):
    """
    List all available MCP tools.

    Returns:
        ListToolsResponse: List of available tools with their schemas
    """
    tools = mcp_server.list_tools()
    return ListToolsResponse(tools=tools, total=len(tools))


@router.post("/invoke", response_model=ToolInvocationResult)
async def invoke_tool(
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


@router.post(
    "/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED
)
async def create_session(
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
    user_id = current_user.id if current_user else None
    session = mcp_server.create_session(user_id=user_id, context=request.context)
    return session


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
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


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def close_session(
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


# ============================================================================
# MCP Router (Phase 20 - MCP Integration)
# ============================================================================
# Separate router for MCP endpoints with prefix /api/v1/mcp
# This router is registered in app/__init__.py to fix 404 errors

mcp_router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


@mcp_router.post("/context/retrieve", response_model=ContextRetrievalResponse)
async def retrieve_context_di(
    request: ContextRetrievalRequest,
    context_service: ContextAssemblyService = Depends(get_context_assembly_service),
    current_user=Depends(get_current_user_optional),
    api_key: str = Depends(verify_api_key),  # M2M Authentication
):
    """
    Assemble context from all intelligence layers for Ronin LLM consumption.

    **Security**: Requires valid API key in Authorization header.

    This endpoint orchestrates parallel fetching from:
    - Semantic Search: Top-K code chunks from vector database
    - GraphRAG: 2-hop architectural dependencies
    - Pattern Engine: Developer coding style and preferences
    - External Memory: Relevant PDF annotations

    Performance target: <1000ms for complete context assembly
    """
    # Add user_id if authenticated
    if current_user and not request.user_id:
        request.user_id = str(current_user.id)

    # Assemble context
    response = await context_service.assemble_context(request)

    # Log metrics (including API key usage for audit)
    if response.success and response.context:
        metrics = response.context.metrics
        logger.info(
            f"Context retrieval: query='{request.query[:50]}...', "
            f"codebase={request.codebase}, "
            f"total_time={metrics.total_time_ms}ms, "
            f"code_chunks={len(response.context.code_chunks)}, "
            f"dependencies={len(response.context.graph_dependencies)}, "
            f"patterns={len(response.context.developer_patterns)}, "
            f"annotations={len(response.context.pdf_annotations)}, "
            f"timeout={metrics.timeout_occurred}, "
            f"api_key_length={len(api_key)}"  # Audit log
        )

    return response


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
    user_id = current_user.id if current_user else None
    session = mcp_server.create_session(user_id=user_id, context=request.context)
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
