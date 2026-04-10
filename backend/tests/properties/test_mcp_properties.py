"""
Property-Based Tests for MCP Server

Tests universal properties of the MCP server implementation.
"""

import pytest
from hypothesis import given, settings, strategies as st, HealthCheck

from backend.app.modules.mcp.service import MCPServer, ToolRegistry


# Feature: phase20-frontend-backend-infrastructure
# Property 26: Schema validation


@given(
    tool_name=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
    ),
    invalid_args=st.dictionaries(
        keys=st.text(
            min_size=1,
            max_size=10,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
        ),
        values=st.one_of(st.integers(), st.text(max_size=20), st.booleans()),
        min_size=1,
        max_size=3,
    ),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_schema_validation_rejects_invalid_arguments(tool_name, invalid_args):
    """
    Feature: phase20-frontend-backend-infrastructure
    Property 26: Schema validation

    For any tool invocation request, invalid requests (not matching tool schema)
    should be rejected with validation error.

    Validates: Requirements 10.2
    """
    registry = ToolRegistry()

    # Register a tool with strict schema
    registry.register(
        name=tool_name,
        description="Test tool",
        input_schema={
            "type": "object",
            "properties": {
                "required_field": {"type": "string"},
                "number_field": {"type": "number"},
            },
            "required": ["required_field"],
        },
        output_schema={"type": "object"},
        handler=lambda args, ctx: args,
    )

    # Try to validate with invalid arguments
    # Should raise ValueError for invalid schema
    with pytest.raises(ValueError):
        registry.validate_arguments(tool_name, invalid_args)


# Feature: phase20-frontend-backend-infrastructure
# Property 28: Authentication enforcement


@pytest.mark.asyncio
@given(
    tool_name=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
    ),
    arguments=st.dictionaries(
        keys=st.text(
            min_size=1,
            max_size=10,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
        ),
        values=st.text(min_size=1, max_size=20),
        min_size=0,
        max_size=3,
    ),
)
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
async def test_authentication_enforcement_for_protected_tools(
    tool_name, arguments, db_session
):
    """
    Feature: phase20-frontend-backend-infrastructure
    Property 28: Authentication enforcement

    For any tool requiring authentication, requests without valid JWT tokens
    should be rejected with 401 status.

    Validates: Requirements 10.4

    Note: This property test verifies the tool registry marks tools as requiring auth.
    The actual JWT validation is tested in integration tests.
    """
    server = MCPServer(db_session)

    # Register a tool that requires authentication
    server.tool_registry.register(
        name=tool_name,
        description="Protected tool",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        handler=lambda args, ctx: {"success": True},
        requires_auth=True,
    )

    # Verify tool is marked as requiring auth
    tool = server.tool_registry.get_tool(tool_name)
    assert tool is not None
    assert tool["definition"].requires_auth is True


# Feature: phase20-frontend-backend-infrastructure
# Property 29: Rate limiting


@given(
    tool_name=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
    ),
    rate_limit=st.integers(min_value=1, max_value=1000),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_rate_limiting_configuration(tool_name, rate_limit):
    """
    Feature: phase20-frontend-backend-infrastructure
    Property 29: Rate limiting

    For any user exceeding rate limits, subsequent requests should return 429 status
    with retry-after header.

    Validates: Requirements 10.5

    Note: This property test verifies rate limit configuration.
    The actual rate limiting enforcement is tested in integration tests.
    """
    registry = ToolRegistry()

    # Register a tool with rate limit
    registry.register(
        name=tool_name,
        description="Rate limited tool",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        handler=lambda args, ctx: {"success": True},
        rate_limit=rate_limit,
    )

    # Verify rate limit is configured
    tool = registry.get_tool(tool_name)
    assert tool is not None
    assert tool["definition"].rate_limit == rate_limit


# Feature: phase20-frontend-backend-infrastructure
# Property 30: Session context preservation


@pytest.mark.asyncio
@given(
    context_data=st.dictionaries(
        keys=st.text(
            min_size=1,
            max_size=10,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
        ),
        values=st.one_of(
            st.integers(), st.text(min_size=1, max_size=20), st.booleans()
        ),
        min_size=1,
        max_size=5,
    ),
)
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
async def test_session_context_preservation(context_data, db_session):
    """
    Feature: phase20-frontend-backend-infrastructure
    Property 30: Session context preservation

    For any multi-turn MCP session, context from previous tool invocations
    should be available in subsequent invocations.

    Validates: Requirements 10.6
    """
    from backend.app.modules.mcp.model import MCPSession
    from backend.app.shared.base_model import Base

    # Create table if it doesn't exist
    Base.metadata.create_all(bind=db_session.get_bind(), tables=[MCPSession.__table__])

    server = MCPServer(db_session)

    # Create session with context
    session = server.create_session(user_id=None, context=context_data)

    # Verify context is preserved
    assert session.context == context_data

    # Retrieve session and verify context
    retrieved_session = server.get_session(session.session_id)
    assert retrieved_session is not None
    assert retrieved_session.context == context_data
