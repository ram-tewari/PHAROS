"""
MCP (Model Context Protocol) Module

This module provides MCP server infrastructure for tool registration and invocation.
It exposes backend capabilities as MCP-compatible tools for frontend integration.
"""

from .router import router, mcp_router

__all__ = ["router", "mcp_router"]
