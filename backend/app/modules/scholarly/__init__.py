"""
Neo Alexandria 2.0 - Scholarly Module

This module handles academic metadata extraction including authors, DOIs,
equations, tables, and publication details.

Public Interface:
- scholarly_router: FastAPI router with 5 endpoints
- MetadataExtractor: Service for extracting scholarly metadata
- Schema classes: ScholarlyMetadataResponse, Equation, TableData, etc.

Events Emitted:
- metadata.extracted: When metadata is successfully extracted
- equations.parsed: When equations are found and parsed
- tables.extracted: When tables are extracted

Events Subscribed:
- resource.created: Triggers metadata extraction for new resources
"""

from .router import router as scholarly_router
from .router import document_intelligence_router
from .extractor import MetadataExtractor
from .schema import (
    Author,
    Equation,
    TableData,
    Figure,
    ScholarlyMetadataResponse,
    MetadataExtractionRequest,
    MetadataExtractionResponse,
    MetadataCompletenessStats,
)
from .handlers import register_handlers

__version__ = "1.0.0"
__domain__ = "scholarly"

__all__ = [
    "scholarly_router",
    "document_intelligence_router",
    "MetadataExtractor",
    "Author",
    "Equation",
    "TableData",
    "Figure",
    "ScholarlyMetadataResponse",
    "MetadataExtractionRequest",
    "MetadataExtractionResponse",
    "MetadataCompletenessStats",
    "register_handlers",
]
