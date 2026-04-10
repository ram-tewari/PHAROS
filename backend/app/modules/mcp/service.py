"""
MCP Module Service Layer

Business logic for MCP server operations including tool registry,
tool invocation, and session management.
"""

import logging
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from jsonschema import ValidationError, validate
from sqlalchemy.orm import Session

from .model import MCPSession
from .schema import (
    SessionResponse,
    ToolDefinition,
    ToolInvocationResult,
)

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for MCP tools with schema validation"""

    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        output_schema: Dict[str, Any],
        handler: Callable,
        requires_auth: bool = True,
        rate_limit: Optional[int] = None,
    ) -> None:
        """Register a tool with the registry"""
        self._tools[name] = {
            "definition": ToolDefinition(
                name=name,
                description=description,
                input_schema=input_schema,
                output_schema=output_schema,
                requires_auth=requires_auth,
                rate_limit=rate_limit,
            ),
            "handler": handler,
        }
        logger.info(f"Registered MCP tool: {name}")

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        """Get tool by name"""
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        """List all registered tools"""
        return [tool["definition"] for tool in self._tools.values()]

    def validate_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        """Validate arguments against tool schema"""
        tool = self.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")

        try:
            validate(instance=arguments, schema=tool["definition"].input_schema)
        except ValidationError as e:
            raise ValueError(f"Invalid arguments for tool {tool_name}: {e.message}")


class MCPServer:
    """MCP server for tool registration and invocation"""

    def __init__(self, db: Session):
        self.db = db
        self.tool_registry = ToolRegistry()
        logger.info("MCPServer initialized")

    def register_tool(
        self,
        tool_name: str,
        tool_schema: Dict[str, Any],
        handler: Callable,
    ) -> None:
        """Register a tool with the MCP server"""
        self.tool_registry.register(
            name=tool_name,
            description=tool_schema.get("description", ""),
            input_schema=tool_schema.get("input_schema", {}),
            output_schema=tool_schema.get("output_schema", {}),
            handler=handler,
            requires_auth=tool_schema.get("requires_auth", True),
            rate_limit=tool_schema.get("rate_limit"),
        )

    async def invoke_tool(
        self,
        session_id: Optional[str],
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> ToolInvocationResult:
        """Invoke a tool with validation"""
        start_time = time.time()

        try:
            # Get tool
            tool = self.tool_registry.get_tool(tool_name)
            if not tool:
                return ToolInvocationResult(
                    success=False,
                    result=None,
                    error=f"Tool not found: {tool_name}",
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )

            # Validate arguments
            try:
                self.tool_registry.validate_arguments(tool_name, arguments)
            except ValueError as e:
                return ToolInvocationResult(
                    success=False,
                    result=None,
                    error=str(e),
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )

            # Get session context if session_id provided
            context = {}
            if session_id:
                session = (
                    self.db.query(MCPSession)
                    .filter(MCPSession.id == session_id)
                    .first()
                )
                if session:
                    context = session.context
                else:
                    logger.warning(f"Session not found: {session_id}")

            # Invoke handler
            handler = tool["handler"]
            result = await handler(arguments, context)

            # Update session if session_id provided
            if session_id:
                self._update_session(session_id, tool_name, arguments, result)

            execution_time_ms = int((time.time() - start_time) * 1000)

            # Log invocation
            logger.info(
                f"Tool invoked: {tool_name}, "
                f"session: {session_id}, "
                f"time: {execution_time_ms}ms"
            )

            return ToolInvocationResult(
                success=True,
                result=result,
                error=None,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            logger.error(
                f"Tool invocation failed: {tool_name}, error: {str(e)}", exc_info=True
            )
            return ToolInvocationResult(
                success=False,
                result=None,
                error=str(e),
                execution_time_ms=int((time.time() - start_time) * 1000),
            )

    def list_tools(self) -> List[ToolDefinition]:
        """List all available tools"""
        return self.tool_registry.list_tools()

    def create_session(
        self, user_id: Optional[int], context: Dict[str, Any]
    ) -> SessionResponse:
        """Create a new MCP session"""
        session_id = str(uuid.uuid4())
        session = MCPSession(
            id=session_id,
            user_id=user_id,
            context=context,
            tool_invocations=[],
            status="active",
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        logger.info(f"Created MCP session: {session_id}, user: {user_id}")

        return SessionResponse(
            session_id=session.id,
            user_id=session.user_id,
            context=session.context,
            status=session.status,
            created_at=session.created_at,
            last_activity=session.last_activity,
        )

    def get_session(self, session_id: str) -> Optional[SessionResponse]:
        """Get session by ID"""
        session = self.db.query(MCPSession).filter(MCPSession.id == session_id).first()
        if not session:
            return None

        return SessionResponse(
            session_id=session.id,
            user_id=session.user_id,
            context=session.context,
            status=session.status,
            created_at=session.created_at,
            last_activity=session.last_activity,
        )

    def close_session(self, session_id: str) -> bool:
        """Close an MCP session"""
        session = self.db.query(MCPSession).filter(MCPSession.id == session_id).first()
        if not session:
            return False

        session.status = "closed"
        session.last_activity = datetime.utcnow()
        self.db.commit()

        logger.info(f"Closed MCP session: {session_id}")
        return True

    def _update_session(
        self,
        session_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Any,
    ) -> None:
        """Update session with tool invocation"""
        session = self.db.query(MCPSession).filter(MCPSession.id == session_id).first()
        if not session:
            return

        # Add invocation to history
        invocation = {
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
            "timestamp": datetime.utcnow().isoformat(),
        }
        session.tool_invocations.append(invocation)
        session.last_activity = datetime.utcnow()

        # Mark as modified for JSON column
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(session, "tool_invocations")

        self.db.commit()
