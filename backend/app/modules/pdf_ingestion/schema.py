"""
PDF Ingestion Module - Pydantic Schemas

Request/response models for PDF ingestion and annotation API.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid


class PDFUploadRequest(BaseModel):
    """Request schema for PDF upload (multipart/form-data)."""

    title: str = Field(..., description="Title of the PDF document")
    description: Optional[str] = Field(None, description="Optional description")
    authors: Optional[str] = Field(None, description="Comma-separated authors")
    publication_year: Optional[int] = Field(None, description="Year of publication")
    doi: Optional[str] = Field(None, description="Digital Object Identifier")
    tags: Optional[List[str]] = Field(
        default_factory=list, description="Initial tags for the document"
    )


class PDFChunkResponse(BaseModel):
    """Response schema for a single PDF chunk."""

    chunk_id: uuid.UUID
    chunk_index: int
    content: str
    page_number: Optional[int] = None
    coordinates: Optional[Dict[str, Any]] = None
    chunk_type: str = Field(
        default="text", description="Type: text, equation, table, figure"
    )

    class Config:
        from_attributes = True


class PDFUploadResponse(BaseModel):
    """Response schema for PDF upload."""

    resource_id: uuid.UUID
    title: str
    status: str = Field(default="processing", description="Ingestion status")
    total_pages: Optional[int] = None
    total_chunks: int
    chunks: List[PDFChunkResponse]
    message: str

    class Config:
        from_attributes = True


class PDFAnnotationRequest(BaseModel):
    """Request schema for annotating a PDF chunk."""

    chunk_id: uuid.UUID = Field(..., description="ID of the chunk to annotate")
    concept_tags: List[str] = Field(
        ..., description="Conceptual tags (e.g., 'OAuth', 'Security')"
    )
    note: Optional[str] = Field(None, description="Optional annotation note")
    color: str = Field(default="#FFFF00", description="Highlight color (hex)")

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        """Validate hex color format."""
        if not v.startswith("#") or len(v) != 7:
            raise ValueError("Color must be in hex format (#RRGGBB)")
        return v


class PDFAnnotationResponse(BaseModel):
    """Response schema for PDF annotation."""

    annotation_id: uuid.UUID
    chunk_id: uuid.UUID
    concept_tags: List[str]
    note: Optional[str]
    color: str
    created_at: datetime
    graph_links_created: int = Field(
        default=0, description="Number of graph edges created"
    )
    linked_code_chunks: List[uuid.UUID] = Field(
        default_factory=list, description="IDs of linked code chunks"
    )

    class Config:
        from_attributes = True


class GraphTraversalRequest(BaseModel):
    """Request schema for GraphRAG traversal search."""

    query: str = Field(..., description="Search query (e.g., 'auth implementation')")
    max_hops: int = Field(default=2, description="Maximum graph traversal depth")
    include_pdf: bool = Field(default=True, description="Include PDF chunks in results")
    include_code: bool = Field(
        default=True, description="Include code chunks in results"
    )
    limit: int = Field(default=10, description="Maximum results to return")


class GraphTraversalResult(BaseModel):
    """Single result from graph traversal."""

    chunk_id: uuid.UUID
    resource_id: uuid.UUID
    chunk_type: str = Field(description="'pdf' or 'code'")
    content: Optional[str] = None
    semantic_summary: Optional[str] = None
    relevance_score: float
    graph_distance: int = Field(description="Hops from query node")
    concept_tags: List[str] = Field(default_factory=list)
    file_path: Optional[str] = None  # For code chunks
    page_number: Optional[int] = None  # For PDF chunks
    annotations: List[Dict[str, Any]] = Field(default_factory=list)

    class Config:
        from_attributes = True


class GraphTraversalResponse(BaseModel):
    """Response schema for GraphRAG traversal search."""

    query: str
    total_results: int
    pdf_results: int
    code_results: int
    results: List[GraphTraversalResult]
    execution_time_ms: float

    class Config:
        from_attributes = True
