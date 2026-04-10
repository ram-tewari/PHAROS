"""
Search Module

This module provides comprehensive search functionality for Neo Alexandria 2.0,
including full-text search, semantic search, and hybrid search capabilities.

Public Interface:
- search_router: FastAPI router for search endpoints
- SearchService: Unified search service
- Search schemas: SearchQuery, SearchResults, etc.

Domain: Search and Information Retrieval
Version: 1.0.0
"""

__version__ = "1.0.0"
__domain__ = "search"

# Import public interface
from ...modules.search.router import router as search_router
from ...modules.search.router import advanced_search_router
from ...modules.search.service import SearchService
from ...modules.search.schema import (
    SearchQuery,
    SearchResults,
    SearchFilters,
    Facets,
    FacetBucket,
    ThreeWayHybridResults,
    MethodContributions,
    ComparisonResults,
    ComparisonMethodResults,
    EvaluationRequest,
    EvaluationResults,
    EvaluationMetrics,
    BatchSparseEmbeddingRequest,
    BatchSparseEmbeddingResponse,
)
from ...modules.search.handlers import register_handlers

# Public exports
__all__ = [
    # Router
    "search_router",
    "advanced_search_router",
    # Service
    "SearchService",
    # Schemas
    "SearchQuery",
    "SearchResults",
    "SearchFilters",
    "Facets",
    "FacetBucket",
    "ThreeWayHybridResults",
    "MethodContributions",
    "ComparisonResults",
    "ComparisonMethodResults",
    "EvaluationRequest",
    "EvaluationResults",
    "EvaluationMetrics",
    "BatchSparseEmbeddingRequest",
    "BatchSparseEmbeddingResponse",
    # Event handlers
    "register_handlers",
    # Metadata
    "__version__",
    "__domain__",
]
