"""
MCP Module Schemas

Pydantic models for MCP server requests and responses.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    """Definition of an MCP tool"""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    input_schema: Dict[str, Any] = Field(..., description="JSON schema for tool inputs")
    output_schema: Dict[str, Any] = Field(
        ..., description="JSON schema for tool outputs"
    )
    requires_auth: bool = Field(
        default=True, description="Whether tool requires authentication"
    )
    rate_limit: Optional[int] = Field(None, description="Rate limit per minute")


class ToolInvocationRequest(BaseModel):
    """Request to invoke an MCP tool"""

    tool_name: str = Field(..., description="Name of tool to invoke")
    arguments: Dict[str, Any] = Field(
        default_factory=dict, description="Tool arguments"
    )
    session_id: Optional[str] = Field(
        None, description="Session ID for context preservation"
    )


class ToolInvocationResult(BaseModel):
    """Result of tool invocation"""

    success: bool = Field(..., description="Whether invocation succeeded")
    result: Any = Field(None, description="Tool result data")
    error: Optional[str] = Field(None, description="Error message if failed")
    execution_time_ms: int = Field(..., description="Execution time in milliseconds")


class CreateSessionRequest(BaseModel):
    """Request to create MCP session"""

    context: Dict[str, Any] = Field(
        default_factory=dict, description="Initial session context"
    )


class SessionResponse(BaseModel):
    """MCP session information"""

    session_id: str = Field(..., description="Session ID")
    user_id: Optional[int] = Field(None, description="User ID if authenticated")
    context: Dict[str, Any] = Field(..., description="Session context")
    status: str = Field(..., description="Session status")
    created_at: datetime = Field(..., description="Session creation time")
    last_activity: datetime = Field(..., description="Last activity time")


class ListToolsResponse(BaseModel):
    """Response listing available tools"""

    tools: List[ToolDefinition] = Field(..., description="Available tools")
    total: int = Field(..., description="Total number of tools")
