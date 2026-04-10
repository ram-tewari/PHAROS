"""
PDF Ingestion Module

Handles PDF upload, extraction, and annotation for research papers.
Integrates with GraphRAG for conceptual linking between PDFs and codebase.
"""

from .router import router
from .service import PDFIngestionService
from .schema import (
    PDFUploadRequest,
    PDFUploadResponse,
    PDFAnnotationRequest,
    PDFAnnotationResponse,
    PDFChunkResponse,
)

__all__ = [
    "router",
    "PDFIngestionService",
    "PDFUploadRequest",
    "PDFUploadResponse",
    "PDFAnnotationRequest",
    "PDFAnnotationResponse",
    "PDFChunkResponse",
]
