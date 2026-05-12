"""
Neo Alexandria 2.0 - Resource Data Models and Validation

This module defines Pydantic schemas for resource data validation and serialization.
It provides comprehensive models for resource creation, updates, and responses with
proper validation rules and field constraints.

Related files:
- model.py: SQLAlchemy models that these schemas represent
- router.py: API endpoints that use these schemas
- service.py: Business logic that validates with these schemas

Schemas:
- ResourceBase: Common fields for all resource operations
- ResourceCreate: Schema for creating new resources
- ResourceUpdate: Schema for updating existing resources
- ResourceResponse: Schema for API responses
- ResourceListResponse: Schema for paginated resource lists
"""

import uuid
from datetime import datetime
from typing import List, Optional, Literal, Union, Any
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict, field_serializer, field_validator


# Query parameter schemas
class PageParams(BaseModel):
    """Pagination parameters."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    per_page: int = Field(default=25, ge=1, le=100, description="Items per page")
    limit: int = Field(
        default=25, ge=1, le=100, description="Items per page (alias for per_page)"
    )
    offset: int = Field(default=0, ge=0, description="Offset for pagination")


class SortOrder(str, Enum):
    """Sort order enum."""

    ASC = "asc"
    DESC = "desc"


class SortParams(BaseModel):
    """Sorting parameters."""

    sort_by: Optional[str] = Field(default=None, description="Field to sort by")
    sort_order: SortOrder = Field(default=SortOrder.DESC, description="Sort order")
    sort_dir: Optional[str] = Field(
        default="desc", description="Sort direction (alias for sort_order)"
    )


class ResourceFilters(BaseModel):
    """Resource filtering parameters."""

    q: Optional[str] = Field(default=None, description="Search query")
    classification_code: Optional[str] = Field(
        default=None, description="Filter by classification code"
    )
    type: Optional[str] = Field(default=None, description="Filter by resource type")
    format: Optional[str] = Field(default=None, description="Filter by format")
    language: Optional[str] = Field(default=None, description="Filter by language")
    read_status: Optional[Literal["unread", "in_progress", "completed", "archived"]] = (
        Field(default=None, description="Filter by read status")
    )
    min_quality: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Minimum quality score"
    )
    created_from: Optional[str] = Field(
        default=None, description="Filter by created date from"
    )
    created_to: Optional[str] = Field(
        default=None, description="Filter by created date to"
    )
    updated_from: Optional[str] = Field(
        default=None, description="Filter by updated date from"
    )
    updated_to: Optional[str] = Field(
        default=None, description="Filter by updated date to"
    )
    subject: Optional[str] = Field(default=None, description="Filter by subject")
    subject_any: Optional[list[str]] = Field(
        default=None, description="Filter by any of these subjects"
    )
    subject_all: Optional[list[str]] = Field(
        default=None, description="Filter by all of these subjects"
    )
    creator: Optional[str] = Field(default=None, description="Filter by creator")


class ResourceBase(BaseModel):
    """Base resource schema with common fields."""

    title: Optional[str] = None
    description: Optional[str] = None
    creator: Optional[str] = None
    publisher: Optional[str] = None
    contributor: Optional[str] = None
    date_created: Optional[datetime] = None
    date_modified: Optional[datetime] = None
    type: Optional[str] = None
    format: Optional[str] = None
    identifier: Optional[str] = None
    source: Optional[str] = None
    language: Optional[str] = None
    coverage: Optional[str] = None
    rights: Optional[str] = None
    subject: List[str] = Field(default_factory=list)
    relation: List[str] = Field(default_factory=list)
    classification_code: Optional[str] = None
    read_status: Optional[Literal["unread", "in_progress", "completed", "archived"]] = (
        None
    )
    quality_score: Optional[Union[float, Any]] = None


class ResourceCreate(ResourceBase):
    """Schema for creating a new resource."""

    title: str  # Required for creation


class ResourceUpdate(ResourceBase):
    """Schema for updating an existing resource.

    All fields are optional for partial updates.
    """

    pass


class ResourceRead(ResourceBase):
    """Schema for reading a resource (includes all fields)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str  # Always present in read
    subject: List[str]  # Always present (default to empty list)
    relation: List[str]  # Always present (default to empty list)
    read_status: Literal[
        "unread", "in_progress", "completed", "archived"
    ]  # Always present
    quality_score: Union[float, Any]  # Can be float or QualityScore domain object
    # Expose computed URL; map from source when present
    url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Ingestion workflow fields
    ingestion_status: Literal["pending", "processing", "completed", "failed"]
    ingestion_error: Optional[str] = None
    ingestion_started_at: Optional[datetime] = None
    ingestion_completed_at: Optional[datetime] = None

    @field_serializer("quality_score")
    def serialize_quality_score(self, quality_score: Union[float, Any], _info) -> float:
        """Serialize quality_score to float for API responses.

        Handles both float values (from database) and QualityScore domain objects.
        """
        # If it's already a float, return it
        if isinstance(quality_score, (int, float)):
            return float(quality_score)

        # If it's a QualityScore domain object, get overall_score
        if hasattr(quality_score, "overall_score"):
            return quality_score.overall_score()

        # If it has a to_dict method, extract overall_score from dict
        if hasattr(quality_score, "to_dict"):
            return quality_score.to_dict().get("overall_score", 0.0)

        # Fallback to 0.0 if we can't determine the score
        return 0.0


class ResourceInDB(ResourceRead):
    """Schema representing resource as stored in database.

    Identical to ResourceRead but makes the distinction clear.
    """

    pass


class ResourceStatus(BaseModel):
    """Lightweight status payload for ingestion polling."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ingestion_status: Literal["pending", "processing", "completed", "failed"]
    ingestion_error: Optional[str] = None
    ingestion_started_at: Optional[datetime] = None
    ingestion_completed_at: Optional[datetime] = None


# ============================================================================
# DOCUMENT CHUNK SCHEMAS (Advanced RAG)
# ============================================================================


class DocumentChunkCreate(BaseModel):
    """Schema for creating a new document chunk.

    Supports both PDF metadata (page, coordinates) and code metadata
    (start_line, end_line, function_name, file_path) through flexible
    chunk_metadata field.
    """

    resource_id: str = Field(..., description="Parent resource UUID")
    content: str = Field(..., description="Chunk text content")
    chunk_index: int = Field(
        ..., ge=0, description="Sequential position within parent resource (0-indexed)"
    )
    chunk_metadata: Optional[dict] = Field(
        None,
        description="Flexible metadata: PDF {page, coordinates} or Code {start_line, end_line, function_name, file_path}",
    )

    @field_validator("chunk_index")
    @classmethod
    def validate_chunk_index(cls, v: int) -> int:
        """Validate that chunk_index is non-negative."""
        if v < 0:
            raise ValueError("chunk_index must be non-negative")
        return v


class DocumentChunkResponse(BaseModel):
    """Schema for document chunk API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Chunk UUID")
    resource_id: str = Field(..., description="Parent resource UUID")
    # content is None for remote (GitHub-backed) code chunks where the
    # source lives at github_uri rather than inline in the database.
    content: Optional[str] = Field(None, description="Inline chunk text; NULL for remote code chunks")
    chunk_index: int = Field(
        ..., description="Sequential position within parent resource"
    )
    chunk_metadata: Optional[dict] = Field(
        None,
        description="Flexible metadata: PDF {page, coordinates} or Code {start_line, end_line, function_name, file_path}",
    )
    embedding_id: Optional[str] = Field(None, description="Associated embedding UUID")
    is_remote: bool = Field(False, description="True if source content lives on GitHub")
    github_uri: Optional[str] = Field(None, description="Full GitHub raw URL when is_remote")
    start_line: Optional[int] = Field(None, description="1-based inclusive start line within github_uri")
    end_line: Optional[int] = Field(None, description="1-based inclusive end line within github_uri")
    ast_node_type: Optional[str] = Field(None, description="function|class|method|module|block")
    symbol_name: Optional[str] = Field(None, description="Fully-qualified symbol name")
    created_at: datetime = Field(..., description="Creation timestamp")


# ============================================================================
# REPOSITORY INGESTION SCHEMAS (Code Intelligence)
# ============================================================================


class RepoIngestionRequest(BaseModel):
    """Schema for repository ingestion request.

    Either path or git_url must be provided, but not both.
    """

    path: Optional[str] = Field(None, description="Local directory path to ingest")
    git_url: Optional[str] = Field(
        None, description="Git repository URL to clone and ingest"
    )

    @field_validator("path", "git_url", mode="after")
    @classmethod
    def validate_path_or_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate individual fields."""
        return v

    @classmethod
    def __init_subclass__(cls, **kwargs):
        """Ensure validation is applied."""
        super().__init_subclass__(**kwargs)

    def model_post_init(self, __context: Any) -> None:
        """Validate that exactly one of path or git_url is provided."""
        # Check that exactly one is provided
        if self.path is None and self.git_url is None:
            raise ValueError("Either 'path' or 'git_url' must be provided")

        if self.path is not None and self.git_url is not None:
            raise ValueError(
                "Only one of 'path' or 'git_url' can be provided, not both"
            )


class IngestionTaskResponse(BaseModel):
    """Schema for repository ingestion task response."""

    task_id: str = Field(..., description="Celery task ID for tracking progress")
    status: str = Field(..., description="Initial task status (typically 'PENDING')")
    message: str = Field(
        default="Repository ingestion started", description="Status message"
    )


class IngestionStatusResponse(BaseModel):
    """Schema for repository ingestion status response."""

    task_id: str = Field(..., description="Celery task ID")
    status: str = Field(
        ..., description="Task status: PENDING, PROCESSING, COMPLETED, FAILED"
    )
    files_processed: Optional[int] = Field(
        None, description="Number of files processed so far"
    )
    total_files: Optional[int] = Field(
        None, description="Total number of files to process"
    )
    current_file: Optional[str] = Field(
        None, description="Currently processing file path"
    )
    error: Optional[str] = Field(None, description="Error message if status is FAILED")
    started_at: Optional[datetime] = Field(None, description="When ingestion started")
    completed_at: Optional[datetime] = Field(
        None, description="When ingestion completed"
    )
