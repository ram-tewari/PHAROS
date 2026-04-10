# Ronin Integration Guide

Pharos is designed to act as a "second brain" for local LLM assistants like Ronin. This guide explains how to connect Ronin to the Pharos backend.

## 1. Authentication
All endpoints used by Ronin (except health checks) require a Bearer token. 
Ronin must send requests with the header:
`Authorization: Bearer <JWT>`

## 2. Primary Search Endpoint
The primary endpoint designed for Ronin is the Three-Way Hybrid Search. It combines:
1. **FTS5 / tsvector**: Keyword matching
2. **Dense Vector**: Semantic similarity
3. **Sparse Vector**: Learned keyword importance
4. **RRF Fusion**: Reciprocal Rank Fusion of the three ranked lists

**Endpoint**: `GET /api/search/search/three-way-hybrid`

**Query Parameters:**
- `query` (string, required): The search text.
- `limit` (int, default 20): Number of results.
- `enable_reranking` (bool, default true): Apply ColBERT reranking.
- `adaptive_weighting` (bool, default true): Query-adaptive RRF weights.

## 3. Model Context Protocol (MCP)
Ronin can invoke Pharos tools programmatically via MCP.

**Endpoint**: `GET /api/v1/mcp/tools`
Lists all available MCP tools (e.g., `search_knowledge_base`) that Ronin can call to dynamically augment its context.
