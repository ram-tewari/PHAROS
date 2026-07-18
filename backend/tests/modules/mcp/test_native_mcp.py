"""
Native MCP transport tests

Boots the real FastAPI app (uvicorn, background thread) and drives it with
the official `mcp` SDK's streamable-HTTP client — a real MCP client talking
real MCP protocol, not TestClient hitting REST endpoints. Mounted sub-apps
don't get FastAPI's TestClient lifespan wiring reliably exercised the same
way a real server does, so this uses an actual running server on a free
local port, matching how a client like Claude Code would connect.
"""

import contextlib
import os
import socket
import threading
import time

import pytest

os.environ.setdefault("TESTING", "true")
os.environ.setdefault("TEST_AUTH_BYPASS", "true")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def native_mcp_server():
    """Start the real app under uvicorn on a background thread."""
    import uvicorn

    from app import create_app

    app = create_app()
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for the server socket to accept connections.
    deadline = time.time() + 15
    while time.time() < deadline:
        with contextlib.suppress(OSError):
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        time.sleep(0.1)
    else:
        raise RuntimeError("native MCP test server did not start in time")

    yield f"http://127.0.0.1:{port}/mcp"

    server.should_exit = True
    thread.join(timeout=10)


@pytest.mark.asyncio
async def test_handshake_reports_server_name(native_mcp_server):
    """A real MCP client can initialize() against /mcp and see server 'pharos'."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(native_mcp_server) as (read, write, _):
        async with ClientSession(read, write) as session:
            result = await session.initialize()
            assert result.serverInfo.name == "pharos"


@pytest.mark.asyncio
async def test_tools_list_contains_expected_tools(native_mcp_server):
    """tools/list must surface retrieve_context plus the four delegated tools."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(native_mcp_server) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            names = {tool.name for tool in result.tools}

    expected = {
        "retrieve_context",
        "search_resources",
        "get_hover_info",
        "compute_graph_metrics",
        "detect_communities",
    }
    assert expected <= names, f"missing tools: {expected - names}"


@pytest.mark.asyncio
async def test_retrieve_context_tool_call_returns_mcp_result(native_mcp_server):
    """A tool call for retrieve_context must return an MCP result, not a
    transport failure — even if the underlying service errors out because
    the test environment lacks a running embedding backend.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(native_mcp_server) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "retrieve_context",
                {"query": "how does auth work", "codebase": "pharos"},
            )

    # Whether the call succeeds or the handler surfaces an error, it must
    # come back as a well-formed MCP CallToolResult (isError True/False),
    # never a transport-level failure.
    assert result is not None
    assert hasattr(result, "isError")
