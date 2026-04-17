"""
Search Module Schemas

Pydantic schemas for search functionality including:
- SearchQuery: Search query parameters
- SearchResults: Search results with facets and snippets
- ThreeWayHybridResults: Results from three-way hybrid search
- SearchFilters: Structured filtering options
- Facets: Faceted search results
- Evaluation schemas: For search quality evaluation
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Literal

from pydantic import BaseModel, Field, field_validator, ConfigDict

from ..resources.schema import ResourceRead


class FacetBucket(BaseModel):
    key: str
    count: int


class Facets(BaseModel):
    classification_code: List[FacetBucket] = Field(default_factory=list)
    type: List[FacetBucket] = Field(default_factory=list)
    language: List[FacetBucket] = Field(default_factory=list)
    read_status: List[FacetBucket] = Field(default_factory=list)
    subject: List[FacetBucket] = Field(default_factory=list)


class SearchFilters(BaseModel):
    classification_code: Optional[List[str]] = None
    type: Optional[List[str]] = None
    language: Optional[List[str]] = None
    read_status: Optional[
        List[Literal["unread", "in_progress", "completed", "archived"]]
    ] = None
    created_from: Optional[datetime] = None
    created_to: Optional[datetime] = None
    updated_from: Optional[datetime] = None
    updated_to: Optional[datetime] = None
    subject_any: Optional[List[str]] = None
    subject_all: Optional[List[str]] = None
    min_quality: Optional[float] = None


class SearchQuery(BaseModel):
    text: Optional[str] = None
    filters: Optional[SearchFilters] = None
    limit: int = 25
    offset: int = 0
    sort_by: Literal[
        "relevance", "updated_at", "created_at", "quality_score", "title"
    ] = "relevance"
    sort_dir: Literal["asc", "desc"] = "desc"
    hybrid_weight: Optional[float] = (
        None  # 0.0=keyword only, 1.0=semantic only, None=use default
    )

    @field_validator("limit")
    @classmethod
    def _validate_limit(cls, v: int) -> int:
        if not (1 <= v <= 100):
            raise ValueError("limit must be between 1 and 100")
        return v

    @field_validator("offset")
    @classmethod
    def _validate_offset(cls, v: int) -> int:
        if v < 0:
            raise ValueError("offset must be >= 0")
        return v

    @field_validator("hybrid_weight")
    @classmethod
    def _validate_hybrid_weight(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError("hybrid_weight must be between 0.0 and 1.0")
        return v


class SearchResults(BaseModel):
    total: int
    items: List[ResourceRead]
    facets: Facets = Field(default_factory=Facets)
    snippets: dict[str, str] = Field(default_factory=dict)


class MethodContributions(BaseModel):
    """Contribution counts from each retrieval method"""

    fts5: int = 0
    dense: int = 0
    sparse: int = 0


class ThreeWayHybridResults(BaseModel):
    """Results from three-way hybrid search with metadata"""

    total: int
    items: List[ResourceRead]
    facets: Facets = Field(default_factory=Facets)
    snippets: dict[str, str] = Field(default_factory=dict)
    latency_ms: float
    method_contributions: MethodContributions
    weights_used: List[float]


class ComparisonMethodResults(BaseModel):
    """Results from a single search method for comparison"""

    results: List[ResourceRead]
    latency_ms: float
    total: int = 0


class ComparisonResults(BaseModel):
    """Side-by-side comparison of different search methods"""

    query: str
    methods: dict[str, ComparisonMethodResults]


class RelevanceJudgments(BaseModel):
    """Relevance judgments for evaluation (0-3 scale)"""

    judgments: dict[str, int] = Field(
        description="Map of resource_id to relevance score (0=not relevant, 1=marginally, 2=relevant, 3=highly relevant)"
    )


class EvaluationMetrics(BaseModel):
    """Information retrieval metrics"""

    ndcg_at_20: float
    recall_at_20: float
    precision_at_20: float
    mrr: float


class EvaluationRequest(BaseModel):
    """Request for search quality evaluation"""

    query: str
    relevance_judgments: dict[str, int] = Field(
        description="Map of resource_id to relevance score (0-3)"
    )


class EvaluationResults(BaseModel):
    """Evaluation results with metrics and baseline comparison"""

    query: str
    metrics: EvaluationMetrics
    baseline_comparison: Optional[dict[str, float]] = None


class BatchSparseEmbeddingRequest(BaseModel):
    """Request for batch sparse embedding generation"""

    resource_ids: Optional[List[str]] = Field(
        None,
        description="Optional list of specific resource IDs to process. If None, processes all resources without sparse embeddings.",
    )
    batch_size: Optional[int] = Field(
        32, description="Batch size for processing (32 for GPU, 8 for CPU)"
    )


class BatchSparseEmbeddingResponse(BaseModel):
    """Response for batch sparse embedding generation"""

    status: str
    job_id: str
    estimated_duration_minutes: int
    resources_to_process: int


# ============================================================================
# SYNTHETIC QUESTION SCHEMAS (Advanced RAG)
# ============================================================================


class SyntheticQuestionCreate(BaseModel):
    """Schema for creating a synthetic question.

    Synthetic questions are LLM-generated questions that a chunk could answer,
    used for Reverse HyDE retrieval to improve question-based search.
    """

    chunk_id: str = Field(..., description="Associated document chunk UUID")
    question_text: str = Field(..., min_length=1, description="Generated question text")

    @field_validator("question_text")
    @classmethod
    def validate_question_text(cls, v: str) -> str:
        """Validate question text is non-empty."""
        if not v or not v.strip():
            raise ValueError("Question text must be non-empty")
        return v.strip()


class SyntheticQuestionResponse(BaseModel):
    """Schema for synthetic question API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Question UUID")
    chunk_id: str = Field(..., description="Associated document chunk UUID")
    question_text: str = Field(..., description="Generated question text")
    embedding_id: Optional[str] = Field(None, description="Question embedding UUID")
    created_at: datetime = Field(..., description="Creation timestamp")


# ============================================================================
# ADVANCED SEARCH SCHEMAS (Advanced RAG)
# ============================================================================


class AdvancedSearchRequest(BaseModel):
    """Request schema for advanced search with multiple strategies.

    Supports:
    - parent-child: Retrieve chunks, expand to parent resources
    - graphrag: Graph-enhanced retrieval with entity relationships
    - hybrid: Combine parent-child with GraphRAG
    """

    query: str = Field(..., min_length=1, description="Search query text")
    strategy: Literal["parent-child", "graphrag", "hybrid"] = Field(
        default="parent-child", description="Retrieval strategy to use"
    )
    top_k: int = Field(
        default=10, ge=1, le=100, description="Number of results to return"
    )
    context_window: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Number of surrounding chunks to include (parent-child only)",
    )
    relation_types: Optional[List[str]] = Field(
        default=None,
        description="Filter by relationship types (GraphRAG only): CONTRADICTS, SUPPORTS, EXTENDS, CITES",
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate query is non-empty."""
        if not v or not v.strip():
            raise ValueError("Query must be non-empty")
        return v.strip()


class DocumentChunkResult(BaseModel):
    """Document chunk in search results."""

    id: str = Field(..., description="Chunk UUID")
    resource_id: str = Field(..., description="Parent resource UUID")
    content: str = Field(..., description="Chunk content")
    chunk_index: int = Field(..., description="Position within parent resource")
    chunk_metadata: Optional[dict] = Field(
        None, description="Chunk metadata (page, line numbers, etc.)"
    )


class GraphPathNode(BaseModel):
    """Node in a graph path."""

    entity_id: str = Field(..., description="Entity UUID")
    entity_name: str = Field(..., description="Entity name")
    entity_type: str = Field(..., description="Entity type (Concept, Person, etc.)")
    relation_type: Optional[str] = Field(
        None, description="Relationship type to next node"
    )
    weight: Optional[float] = Field(None, description="Relationship weight")


class AdvancedSearchResult(BaseModel):
    """Single result from advanced search."""

    chunk: DocumentChunkResult = Field(..., description="Retrieved chunk")
    parent_resource: ResourceRead = Field(..., description="Parent resource context")
    surrounding_chunks: List[DocumentChunkResult] = Field(
        default_factory=list,
        description="Surrounding chunks for context (parent-child only)",
    )
    graph_path: List[GraphPathNode] = Field(
        default_factory=list,
        description="Graph path explaining retrieval (GraphRAG only)",
    )
    score: float = Field(..., description="Relevance score")


class AdvancedSearchResponse(BaseModel):
    """Response schema for advanced search."""

    query: str = Field(..., description="Original query")
    strategy: str = Field(..., description="Strategy used")
    results: List[AdvancedSearchResult] = Field(..., description="Search results")
    total: int = Field(..., description="Total number of results")
    latency_ms: float = Field(..., description="Search latency in milliseconds")
