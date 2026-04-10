"""
Unit Tests for MCP Server

Tests specific examples and edge cases for MCP server functionality.
"""

import pytest

from backend.app.modules.mcp.model import MCPSession
from backend.app.modules.mcp.service import MCPServer, ToolRegistry
from backend.app.shared.base_model import Base


@pytest.fixture
def mcp_server(db_session):
    """Create MCP server instance with test database"""
    # Create table if it doesn't exist
    Base.metadata.create_all(bind=db_session.get_bind(), tables=[MCPSession.__table__])
    return MCPServer(db_session)


class TestToolRegistry:
    """Tests for ToolRegistry class"""

    def test_register_tool(self):
        """Test registering a tool"""
        registry = ToolRegistry()

        registry.register(
            name="test_tool",
            description="Test tool",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=lambda args, ctx: {"success": True},
        )

        tool = registry.get_tool("test_tool")
        assert tool is not None
        assert tool["definition"].name == "test_tool"
        assert tool["definition"].description == "Test tool"

    def test_list_tools(self):
        """Test listing all tools"""
        registry = ToolRegistry()

        registry.register(
            name="tool1",
            description="Tool 1",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=lambda args, ctx: {},
        )

        registry.register(
            name="tool2",
            description="Tool 2",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=lambda args, ctx: {},
        )

        tools = registry.list_tools()
        assert len(tools) == 2
        assert tools[0].name == "tool1"
        assert tools[1].name == "tool2"

    def test_validate_valid_arguments(self):
        """Test validating valid arguments"""
        registry = ToolRegistry()

        registry.register(
            name="test_tool",
            description="Test tool",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "number"},
                },
                "required": ["name"],
            },
            output_schema={"type": "object"},
            handler=lambda args, ctx: {},
        )

        # Should not raise
        registry.validate_arguments("test_tool", {"name": "John", "age": 30})

    def test_validate_invalid_arguments(self):
        """Test validating invalid arguments"""
        registry = ToolRegistry()

        registry.register(
            name="test_tool",
            description="Test tool",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                },
                "required": ["name"],
            },
            output_schema={"type": "object"},
            handler=lambda args, ctx: {},
        )

        # Should raise ValueError
        with pytest.raises(ValueError):
            registry.validate_arguments("test_tool", {"age": 30})

    def test_get_nonexistent_tool(self):
        """Test getting a tool that doesn't exist"""
        registry = ToolRegistry()
        tool = registry.get_tool("nonexistent")
        assert tool is None


class TestMCPServer:
    """Tests for MCPServer class"""

    @pytest.mark.asyncio
    async def test_invoke_valid_tool(self, mcp_server):
        """Test invoking a valid tool"""

        # Register a test tool
        async def test_handler(args, ctx):
            return {"result": "success"}

        mcp_server.tool_registry.register(
            name="test_tool",
            description="Test tool",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=test_handler,
        )

        # Invoke the tool
        result = await mcp_server.invoke_tool(
            session_id=None,
            tool_name="test_tool",
            arguments={},
        )

        assert result.success is True
        assert result.result == {"result": "success"}
        assert result.error is None

    @pytest.mark.asyncio
    async def test_invoke_invalid_tool_name(self, mcp_server):
        """Test invoking a tool that doesn't exist"""
        result = await mcp_server.invoke_tool(
            session_id=None,
            tool_name="nonexistent_tool",
            arguments={},
        )

        assert result.success is False
        assert result.error is not None
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_invoke_with_schema_validation_failure(self, mcp_server):
        """Test invoking a tool with invalid arguments"""
        # Register a tool with strict schema
        mcp_server.tool_registry.register(
            name="test_tool",
            description="Test tool",
            input_schema={
                "type": "object",
                "properties": {
                    "required_field": {"type": "string"},
                },
                "required": ["required_field"],
            },
            output_schema={"type": "object"},
            handler=lambda args, ctx: {},
        )

        # Invoke with invalid arguments
        result = await mcp_server.invoke_tool(
            session_id=None,
            tool_name="test_tool",
            arguments={},  # Missing required_field
        )

        assert result.success is False
        assert result.error is not None

    def test_create_session(self, mcp_server):
        """Test creating a session"""
        session = mcp_server.create_session(
            user_id=None,
            context={"key": "value"},
        )

        assert session.session_id is not None
        assert session.context == {"key": "value"}
        assert session.status == "active"

    def test_get_session(self, mcp_server):
        """Test getting a session"""
        # Create a session
        created_session = mcp_server.create_session(
            user_id=None,
            context={"key": "value"},
        )

        # Retrieve the session
        retrieved_session = mcp_server.get_session(created_session.session_id)

        assert retrieved_session is not None
        assert retrieved_session.session_id == created_session.session_id
        assert retrieved_session.context == {"key": "value"}

    def test_get_nonexistent_session(self, mcp_server):
        """Test getting a session that doesn't exist"""
        session = mcp_server.get_session("nonexistent-session-id")
        assert session is None

    def test_close_session(self, mcp_server):
        """Test closing a session"""
        # Create a session
        created_session = mcp_server.create_session(
            user_id=None,
            context={},
        )

        # Close the session
        success = mcp_server.close_session(created_session.session_id)
        assert success is True

        # Verify session is closed
        retrieved_session = mcp_server.get_session(created_session.session_id)
        assert retrieved_session.status == "closed"

    def test_close_nonexistent_session(self, mcp_server):
        """Test closing a session that doesn't exist"""
        success = mcp_server.close_session("nonexistent-session-id")
        assert success is False

    def test_list_tools(self, mcp_server):
        """Test listing all tools"""
        # Register some tools
        mcp_server.tool_registry.register(
            name="tool1",
            description="Tool 1",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=lambda args, ctx: {},
        )

        mcp_server.tool_registry.register(
            name="tool2",
            description="Tool 2",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            handler=lambda args, ctx: {},
        )

        tools = mcp_server.list_tools()
        assert len(tools) == 2
