"""
MCP Tool Registrations

This module registers existing backend capabilities as MCP tools.
"""

import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Tool schemas
TOOL_SCHEMAS = {
    "search_resources": {
        "description": "Search for resources using hybrid search (keyword + semantic)",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 10, "description": "Maximum results"},
                "offset": {"type": "integer", "default": 0, "description": "Result offset"},
            },
            "required": ["query"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "results": {"type": "array"},
                "total": {"type": "integer"},
            },
        },
        "requires_auth": True,
        "rate_limit": 60,
    },
    "get_hover_info": {
        "description": "Get hover information for code at specific position",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "File path"},
                "line": {"type": "integer", "description": "Line number"},
                "column": {"type": "integer", "description": "Column number"},
                "resource_id": {"type": "integer", "description": "Resource ID"},
            },
            "required": ["file_path", "line", "column", "resource_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string"},
                "symbol_type": {"type": "string"},
                "documentation": {"type": "string"},
                "related_chunks": {"type": "array"},
            },
        },
        "requires_auth": True,
        "rate_limit": 120,
    },
    "compute_graph_metrics": {
        "description": "Compute centrality metrics for graph nodes",
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Resource IDs to compute metrics for",
                },
            },
            "required": ["resource_ids"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "metrics": {"type": "object"},
            },
        },
        "requires_auth": True,
        "rate_limit": 30,
    },
    "detect_communities": {
        "description": "Detect communities in knowledge graph using Louvain algorithm",
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Resource IDs to analyze",
                },
                "resolution": {
                    "type": "number",
                    "default": 1.0,
                    "description": "Resolution parameter for community granularity",
                },
            },
            "required": ["resource_ids"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "communities": {"type": "object"},
                "modularity": {"type": "number"},
                "num_communities": {"type": "integer"},
            },
        },
        "requires_auth": True,
        "rate_limit": 20,
    },
    "generate_plan": {
        "description": "Generate multi-step implementation plan for a task",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_description": {"type": "string", "description": "Task to plan"},
                "context": {
                    "type": "object",
                    "default": {},
                    "description": "Additional context",
                },
            },
            "required": ["task_description"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "steps": {"type": "array"},
                "dependencies": {"type": "array"},
            },
        },
        "requires_auth": True,
        "rate_limit": 10,
    },
    "parse_architecture": {
        "description": "Parse architecture document to extract components and patterns",
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_id": {"type": "integer", "description": "Architecture document resource ID"},
            },
            "required": ["resource_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "components": {"type": "array"},
                "relationships": {"type": "array"},
                "patterns": {"type": "array"},
                "gaps": {"type": "array"},
            },
        },
        "requires_auth": True,
        "rate_limit": 20,
    },
    "link_pdf_to_code": {
        "description": "Auto-link PDF chunks to code chunks based on semantic similarity",
        "input_schema": {
            "type": "object",
            "properties": {
                "pdf_resource_id": {"type": "integer", "description": "PDF resource ID"},
                "similarity_threshold": {
                    "type": "number",
                    "default": 0.7,
                    "description": "Similarity threshold for linking",
                },
            },
            "required": ["pdf_resource_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "links_created": {"type": "integer"},
                "links": {"type": "array"},
            },
        },
        "requires_auth": True,
        "rate_limit": 10,
    },
}


# Tool handlers
async def search_resources_handler(arguments: Dict[str, Any], context: Dict[str, Any]) -> Any:
    """Handler for search_resources tool"""
    from ..search.service import SearchService
    from ...shared.database import get_sync_db

    db = next(get_db())
    try:
        service = SearchService(db)
        results = await service.hybrid_search(
            query=arguments["query"],
            limit=arguments.get("limit", 10),
            offset=arguments.get("offset", 0),
        )
        return {"results": results, "total": len(results)}
    finally:
        db.close()


async def get_hover_info_handler(arguments: Dict[str, Any], context: Dict[str, Any]) -> Any:
    """Handler for get_hover_info tool"""
    from ..graph.router import get_hover_information
    from ...shared.database import get_sync_db

    db = next(get_db())
    try:
        result = await get_hover_information(
            file_path=arguments["file_path"],
            line=arguments["line"],
            column=arguments["column"],
            resource_id=arguments["resource_id"],
            db=db,
        )
        return result.dict()
    finally:
        db.close()


async def compute_graph_metrics_handler(arguments: Dict[str, Any], context: Dict[str, Any]) -> Any:
    """Handler for compute_graph_metrics tool"""
    from ..graph.service import GraphService
    from ...shared.database import get_sync_db

    db = next(get_db())
    try:
        service = GraphService(db)
        metrics = await service.compute_degree_centrality(arguments["resource_ids"])
        return {"metrics": {str(k): v.dict() for k, v in metrics.items()}}
    finally:
        db.close()


async def detect_communities_handler(arguments: Dict[str, Any], context: Dict[str, Any]) -> Any:
    """Handler for detect_communities tool"""
    from ..graph.service import CommunityDetectionService
    from ...shared.database import get_sync_db

    db = next(get_db())
    try:
        service = CommunityDetectionService(db)
        result = await service.detect_communities(
            resource_ids=arguments["resource_ids"],
            resolution=arguments.get("resolution", 1.0),
        )
        return result.dict()
    finally:
        db.close()


async def generate_plan_handler(arguments: Dict[str, Any], context: Dict[str, Any]) -> Any:
    """Handler for generate_plan tool"""
    from ..planning.service import MultiHopAgent
    from ...shared.database import get_sync_db

    db = next(get_db())
    try:
        # Note: LLM client would need to be initialized
        agent = MultiHopAgent(db, llm_client=None)
        result = await agent.generate_plan(
            task_description=arguments["task_description"],
            context=arguments.get("context", {}),
        )
        return result.dict()
    finally:
        db.close()


async def parse_architecture_handler(arguments: Dict[str, Any], context: Dict[str, Any]) -> Any:
    """Handler for parse_architecture tool"""
    from ..planning.service import ArchitectureParser
    from ...shared.database import get_sync_db

    db = next(get_db())
    try:
        # Note: LLM client would need to be initialized
        parser = ArchitectureParser(db, llm_client=None)
        result = await parser.parse_architecture_doc(resource_id=arguments["resource_id"])
        return result.dict()
    finally:
        db.close()


async def link_pdf_to_code_handler(arguments: Dict[str, Any], context: Dict[str, Any]) -> Any:
    """Handler for link_pdf_to_code tool"""
    from ..resources.service import AutoLinkingService
    from ...shared.database import get_sync_db
    from ...shared.embeddings import EmbeddingGenerator

    db = next(get_db())
    try:
        embedding_generator = EmbeddingGenerator()
        service = AutoLinkingService(db, embedding_generator)
        links = await service.link_pdf_to_code(
            pdf_resource_id=arguments["pdf_resource_id"],
            similarity_threshold=arguments.get("similarity_threshold", 0.7),
        )
        return {"links_created": len(links), "links": [link.dict() for link in links]}
    finally:
        db.close()


# Tool handler mapping
TOOL_HANDLERS = {
    "search_resources": search_resources_handler,
    "get_hover_info": get_hover_info_handler,
    "compute_graph_metrics": compute_graph_metrics_handler,
    "detect_communities": detect_communities_handler,
    "generate_plan": generate_plan_handler,
    "parse_architecture": parse_architecture_handler,
    "link_pdf_to_code": link_pdf_to_code_handler,
}


def register_all_tools(mcp_server) -> None:
    """Register all MCP tools with the server"""
    for tool_name, schema in TOOL_SCHEMAS.items():
        handler = TOOL_HANDLERS.get(tool_name)
        if handler:
            mcp_server.register_tool(tool_name, schema, handler)
            logger.info(f"Registered MCP tool: {tool_name}")
        else:
            logger.warning(f"No handler found for tool: {tool_name}")

    logger.info(f"Registered {len(TOOL_SCHEMAS)} MCP tools")
