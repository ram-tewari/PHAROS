"""
Neo Alexandria 2.0 - Graph Module Schemas

Pydantic models for graph, citation, and discovery operations.
Merged from app/schemas/graph.py, app/schemas/discovery.py, and app/schemas/citation.py

Related files:
- app/modules/graph/service.py: Core graph operations
- app/modules/graph/citations.py: Citation service
- app/modules/graph/discovery.py: LBD service
- app/modules/graph/router.py: Graph API endpoints
- app/modules/graph/citations_router.py: Citation API endpoints
- app/modules/graph/discovery_router.py: Discovery API endpoints
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator


# ============================================================================
# SHARED SCHEMAS
# ============================================================================


class ResourceSummary(BaseModel):
    """
    Summary information about a resource in discovery and citation results.

    Attributes:
        id: Unique resource identifier
        title: Human-readable title
        type: Resource type (e.g., "article", "book")
        publication_year: Year of publication if available
    """

    id: str = Field(..., description="Unique resource identifier")
    title: str = Field(..., description="Human-readable title")
    type: Optional[str] = Field(
        None, description="Resource type (e.g., 'article', 'book')"
    )
    publication_year: Optional[int] = Field(None, description="Year of publication")


# ============================================================================
# GRAPH SCHEMAS (from app/schemas/graph.py)
# ============================================================================


class GraphNode(BaseModel):
    """
    A node in the knowledge graph representing a resource.

    Attributes:
        id: Unique resource identifier
        title: Human-readable title of the resource
        type: Resource type (e.g., "article", "book", "webpage")
        classification_code: UDC-inspired classification code if assigned
    """

    id: UUID = Field(..., description="Unique resource identifier")
    title: str = Field(..., description="Human-readable title of the resource")
    type: Optional[str] = Field(
        None, description="Resource type (e.g., 'article', 'book', 'webpage')"
    )
    classification_code: Optional[str] = Field(
        None, description="UDC-inspired classification code if assigned"
    )


class GraphEdgeDetails(BaseModel):
    """
    Detailed information about why two nodes are connected.

    Provides transparency for the UI to explain connection reasoning,
    showing the specific factors that contributed to the edge weight.

    Attributes:
        connection_type: Type of connection (e.g., "semantic", "topical", "classification")
        vector_similarity: Cosine similarity score between embeddings (if applicable)
        shared_subjects: List of canonical subjects shared between the resources
    """

    connection_type: str = Field(
        ...,
        description="Type of connection (e.g., 'semantic', 'topical', 'classification')",
    )
    vector_similarity: Optional[float] = Field(
        None, description="Cosine similarity score between embeddings (0.0-1.0)"
    )
    shared_subjects: List[str] = Field(
        default_factory=list,
        description="List of canonical subjects shared between resources",
    )


class GraphEdge(BaseModel):
    """
    A weighted edge between two nodes in the knowledge graph.

    Represents the hybrid-scored relationship between two resources,
    combining vector similarity, subject overlap, and classification matching.

    Attributes:
        source: Source node UUID
        target: Target node UUID
        weight: Combined hybrid weight score (0.0-1.0)
        details: Detailed information about the connection
    """

    source: UUID = Field(..., description="Source node UUID")
    target: UUID = Field(..., description="Target node UUID")
    weight: float = Field(
        ..., ge=0.0, le=1.0, description="Combined hybrid weight score (0.0-1.0)"
    )
    details: GraphEdgeDetails = Field(
        ..., description="Detailed information about the connection"
    )


class KnowledgeGraph(BaseModel):
    """
    A complete knowledge graph containing nodes and their relationships.

    Used for both the mind-map view (neighbors of a specific resource)
    and the global overview (strongest connections across the library).

    Attributes:
        nodes: List of graph nodes (resources)
        edges: List of weighted edges between nodes
    """

    nodes: List[GraphNode] = Field(
        default_factory=list, description="List of graph nodes (resources)"
    )
    edges: List[GraphEdge] = Field(
        default_factory=list, description="List of weighted edges between nodes"
    )

    class Config:
        """Pydantic configuration for proper JSON serialization"""

        json_encoders = {UUID: str}


# ============================================================================
# DISCOVERY SCHEMAS (from app/schemas/discovery.py)
# ============================================================================


class PathInfo(BaseModel):
    """
    Information about a specific path in the graph.

    Attributes:
        b_id: Intermediate resource UUID
        weight_ab: Edge weight from A to B
        weight_bc: Edge weight from B to C
        path_strength: Product of edge weights
        path: List of resource UUIDs in path
    """

    b_id: str = Field(..., description="Intermediate resource UUID")
    weight_ab: float = Field(..., description="Edge weight from A to B")
    weight_bc: float = Field(..., description="Edge weight from B to C")
    path_strength: float = Field(..., description="Product of edge weights")
    path: List[str] = Field(..., description="List of resource UUIDs in path")


class OpenDiscoveryHypothesis(BaseModel):
    """
    A hypothesis discovered through open discovery (A→B→C pattern).

    Represents a potential connection between the starting resource A
    and a discovered resource C through intermediate resources B.

    Attributes:
        c_resource: Target resource discovered
        b_resources: List of intermediate resources connecting A to C
        plausibility_score: Combined plausibility score (0.0-1.0)
        path_strength: Product of edge weights along best path
        common_neighbors: Count of shared neighbors between A and C
        semantic_similarity: Cosine similarity of embeddings (0.0-1.0)
        path_length: Number of hops in path
        paths: Detailed information about all paths to C
    """

    c_resource: ResourceSummary = Field(..., description="Target resource discovered")
    b_resources: List[ResourceSummary] = Field(
        ..., description="Intermediate resources connecting A to C"
    )
    plausibility_score: float = Field(
        ..., ge=0.0, le=1.0, description="Combined plausibility score"
    )
    path_strength: float = Field(
        ..., description="Product of edge weights along best path"
    )
    common_neighbors: int = Field(
        ..., description="Count of shared neighbors between A and C"
    )
    semantic_similarity: float = Field(
        ..., ge=0.0, le=1.0, description="Cosine similarity of embeddings"
    )
    path_length: int = Field(..., description="Number of hops in path")
    paths: Optional[List[PathInfo]] = Field(
        None, description="Detailed information about all paths"
    )


class OpenDiscoveryResponse(BaseModel):
    """
    Response for open discovery endpoint.

    Attributes:
        hypotheses: List of discovered hypotheses ranked by plausibility
        total_count: Total number of hypotheses found
    """

    hypotheses: List[OpenDiscoveryHypothesis] = Field(
        ..., description="List of discovered hypotheses"
    )
    total_count: int = Field(..., description="Total number of hypotheses found")


class ClosedDiscoveryRequest(BaseModel):
    """
    Request body for closed discovery endpoint.

    Attributes:
        a_resource_id: Starting resource UUID
        c_resource_id: Target resource UUID
        max_hops: Maximum number of hops to search (default 3)
    """

    a_resource_id: str = Field(..., description="Starting resource UUID")
    c_resource_id: str = Field(..., description="Target resource UUID")
    max_hops: int = Field(3, ge=2, le=4, description="Maximum number of hops to search")


class ClosedDiscoveryPath(BaseModel):
    """
    A path connecting two resources in closed discovery.

    Attributes:
        b_resources: List of intermediate resources in path
        path: List of resource UUIDs in path
        path_length: Number of hops in path
        plausibility_score: Combined plausibility score with hop penalty
        path_strength: Product of edge weights
        common_neighbors: Count of shared neighbors between A and C
        semantic_similarity: Cosine similarity of embeddings
        is_direct: True if direct A→C edge exists
        weights: List of edge weights in path
    """

    b_resources: List[ResourceSummary] = Field(
        ..., description="Intermediate resources in path"
    )
    path: List[str] = Field(..., description="List of resource UUIDs in path")
    path_length: int = Field(..., description="Number of hops in path")
    plausibility_score: float = Field(
        ..., ge=0.0, le=1.0, description="Combined plausibility score"
    )
    path_strength: float = Field(..., description="Product of edge weights")
    common_neighbors: int = Field(..., description="Count of shared neighbors")
    semantic_similarity: float = Field(
        ..., ge=0.0, le=1.0, description="Cosine similarity"
    )
    is_direct: bool = Field(..., description="True if direct A→C edge exists")
    weights: Optional[List[float]] = Field(
        None, description="List of edge weights in path"
    )


class ClosedDiscoveryResponse(BaseModel):
    """
    Response for closed discovery endpoint.

    Attributes:
        paths: List of paths connecting A and C, ranked by plausibility
        total_count: Total number of paths found
    """

    paths: List[ClosedDiscoveryPath] = Field(
        ..., description="List of paths connecting A and C"
    )
    total_count: int = Field(..., description="Total number of paths found")


class NeighborResponse(BaseModel):
    """
    A multi-hop neighbor with path information.

    Attributes:
        resource_id: Target resource UUID
        title: Resource title
        type: Resource type
        distance: Number of hops (1 or 2)
        path: List of resource UUIDs in path
        path_strength: Product of edge weights along path
        edge_types: List of edge types used in path
        score: Combined ranking score
        intermediate: Intermediate resource UUID (for 2-hop paths)
        quality: Resource quality score
        novelty: Novelty score based on node degree
    """

    resource_id: str = Field(..., description="Target resource UUID")
    title: str = Field(..., description="Resource title")
    type: Optional[str] = Field(None, description="Resource type")
    distance: int = Field(..., description="Number of hops")
    path: List[str] = Field(..., description="List of resource UUIDs in path")
    path_strength: float = Field(..., description="Product of edge weights")
    edge_types: List[str] = Field(..., description="List of edge types used")
    score: float = Field(..., description="Combined ranking score")
    intermediate: Optional[str] = Field(
        None, description="Intermediate resource UUID for 2-hop"
    )
    quality: float = Field(..., description="Resource quality score")
    novelty: float = Field(..., description="Novelty score")


class NeighborsResponse(BaseModel):
    """
    Response for multi-hop neighbors endpoint.

    Attributes:
        neighbors: List of neighbors with path information
        total_count: Total number of neighbors found
    """

    neighbors: List[NeighborResponse] = Field(..., description="List of neighbors")
    total_count: int = Field(..., description="Total number of neighbors found")


class HypothesisValidation(BaseModel):
    """
    Request body for hypothesis validation endpoint.

    Attributes:
        is_valid: Whether the hypothesis is valid
        notes: Optional validation notes
    """

    is_valid: bool = Field(..., description="Whether the hypothesis is valid")
    notes: Optional[str] = Field(None, description="Optional validation notes")


class HypothesisResponse(BaseModel):
    """
    A stored discovery hypothesis.

    Attributes:
        id: Hypothesis UUID
        a_resource: Starting resource
        c_resource: Target resource
        b_resources: Intermediate resources
        hypothesis_type: Type of hypothesis ("open" or "closed")
        plausibility_score: Combined plausibility score
        path_strength: Product of edge weights
        path_length: Number of hops
        common_neighbors: Count of shared neighbors
        discovered_at: Timestamp of discovery
        is_validated: Validation status (None if not validated)
        validation_notes: Optional validation notes
    """

    id: str = Field(..., description="Hypothesis UUID")
    a_resource: ResourceSummary = Field(..., description="Starting resource")
    c_resource: ResourceSummary = Field(..., description="Target resource")
    b_resources: List[ResourceSummary] = Field(
        ..., description="Intermediate resources"
    )
    hypothesis_type: str = Field(..., description="Type of hypothesis")
    plausibility_score: float = Field(..., description="Combined plausibility score")
    path_strength: float = Field(..., description="Product of edge weights")
    path_length: int = Field(..., description="Number of hops")
    common_neighbors: int = Field(..., description="Count of shared neighbors")
    discovered_at: str = Field(..., description="Timestamp of discovery")
    is_validated: Optional[bool] = Field(None, description="Validation status")
    validation_notes: Optional[str] = Field(None, description="Validation notes")


class HypothesesListResponse(BaseModel):
    """
    Response for hypotheses list endpoint.

    Attributes:
        hypotheses: List of stored hypotheses
        total_count: Total number of hypotheses matching filters
        skip: Number of items skipped (pagination)
        limit: Maximum items per page
    """

    hypotheses: List[HypothesisResponse] = Field(..., description="List of hypotheses")
    total_count: int = Field(..., description="Total count matching filters")
    skip: int = Field(..., description="Number of items skipped")
    limit: int = Field(..., description="Maximum items per page")


# ============================================================================
# CITATION SCHEMAS (from app/schemas/citation.py)
# ============================================================================


class CitationBase(BaseModel):
    """Base schema for citation data."""

    source_resource_id: str = Field(..., description="UUID of the citing resource")
    target_url: str = Field(..., description="URL being cited")
    citation_type: str = Field(
        default="reference",
        description="Type of citation: reference, dataset, code, general",
    )
    context_snippet: Optional[str] = Field(
        None, description="Text context around the citation"
    )
    position: Optional[int] = Field(None, description="Position in the document")


class CitationCreate(CitationBase):
    """Schema for creating a new citation."""

    target_resource_id: Optional[str] = Field(
        None, description="UUID of the cited resource if internal"
    )


class CitationResponse(CitationBase):
    """Schema for citation API responses."""

    id: str = Field(..., description="Citation UUID")
    target_resource_id: Optional[str] = Field(
        None, description="UUID of the cited resource if resolved"
    )
    importance_score: Optional[float] = Field(
        None, description="PageRank importance score"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


class CitationWithResource(CitationResponse):
    """Citation response with embedded resource information."""

    target_resource: Optional[ResourceSummary] = None


class ResourceCitationsResponse(BaseModel):
    """Response for resource citations endpoint."""

    resource_id: str
    outbound: List[CitationWithResource] = Field(
        default_factory=list, description="Citations from this resource"
    )
    inbound: List[CitationWithResource] = Field(
        default_factory=list, description="Citations to this resource"
    )
    counts: dict = Field(default_factory=dict, description="Citation counts")


class CitationGraphResponse(BaseModel):
    """Response for citation graph endpoint."""

    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)


class CitationExtractionRequest(BaseModel):
    """Request to trigger citation extraction."""

    resource_id: str = Field(
        ..., description="UUID of resource to extract citations from"
    )


class CitationExtractionResponse(BaseModel):
    """Response for citation extraction trigger."""

    status: str = Field(
        ..., description="Task status: queued, processing, completed, failed"
    )
    resource_id: str = Field(..., description="Resource UUID")
    message: Optional[str] = None


class CitationResolutionResponse(BaseModel):
    """Response for citation resolution."""

    status: str = Field(..., description="Task status")
    resolved_count: Optional[int] = Field(
        None, description="Number of citations resolved"
    )


class ImportanceComputationResponse(BaseModel):
    """Response for importance score computation."""

    status: str = Field(..., description="Task status")
    computed_count: Optional[int] = Field(None, description="Number of scores computed")


# ============================================================================
# ADVANCED RAG SCHEMAS
# ============================================================================


class GraphEntityCreate(BaseModel):
    """Schema for creating a new graph entity.

    Entities represent named concepts, people, organizations, or methods
    extracted from document content.
    """

    name: str = Field(
        ..., description="Entity name (e.g., 'Neural Networks', 'Geoffrey Hinton')"
    )
    type: Literal["Concept", "Person", "Organization", "Method"] = Field(
        ..., description="Entity type classification"
    )
    description: Optional[str] = Field(None, description="Optional entity description")

    @field_validator("type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        """Validate entity type is one of the allowed values."""
        allowed_types = {"Concept", "Person", "Organization", "Method"}
        if v not in allowed_types:
            raise ValueError(f"Entity type must be one of: {allowed_types}")
        return v


class GraphEntityResponse(BaseModel):
    """Schema for graph entity API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Entity UUID")
    name: str = Field(..., description="Entity name")
    type: str = Field(
        ..., description="Entity type (Concept, Person, Organization, Method)"
    )
    description: Optional[str] = Field(None, description="Entity description")
    created_at: datetime = Field(..., description="Creation timestamp")


class GraphRelationshipCreate(BaseModel):
    """Schema for creating a new graph relationship.

    Relationships represent semantic triples (Subject -> Predicate -> Object)
    connecting entities. Supports both academic relationships (CONTRADICTS,
    SUPPORTS, EXTENDS, CITES) and code-specific relationships (CALLS, IMPORTS,
    DEFINES) for structural dependency tracking.
    """

    source_entity_id: str = Field(..., description="Source entity UUID")
    target_entity_id: str = Field(..., description="Target entity UUID")
    relation_type: Literal[
        "CONTRADICTS",
        "SUPPORTS",
        "EXTENDS",
        "CITES",  # Academic
        "CALLS",
        "IMPORTS",
        "DEFINES",  # Code-specific
    ] = Field(..., description="Relationship type")
    weight: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Relationship strength/confidence (0.0 to 1.0)",
    )
    provenance_chunk_id: Optional[str] = Field(
        None, description="Source chunk UUID for provenance tracking"
    )

    @field_validator("weight")
    @classmethod
    def validate_weight(cls, v: float) -> float:
        """Validate weight is between 0.0 and 1.0."""
        if not (0.0 <= v <= 1.0):
            raise ValueError("Weight must be between 0.0 and 1.0")
        return v

    @field_validator("relation_type")
    @classmethod
    def validate_relation_type(cls, v: str) -> str:
        """Validate relation type is one of the allowed values."""
        allowed_types = {
            "CONTRADICTS",
            "SUPPORTS",
            "EXTENDS",
            "CITES",  # Academic
            "CALLS",
            "IMPORTS",
            "DEFINES",  # Code-specific
        }
        if v not in allowed_types:
            raise ValueError(f"Relation type must be one of: {allowed_types}")
        return v


class GraphRelationshipResponse(BaseModel):
    """Schema for graph relationship API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Relationship UUID")
    source_entity_id: str = Field(..., description="Source entity UUID")
    target_entity_id: str = Field(..., description="Target entity UUID")
    relation_type: str = Field(..., description="Relationship type")
    weight: float = Field(..., description="Relationship strength (0.0 to 1.0)")
    provenance_chunk_id: Optional[str] = Field(None, description="Source chunk UUID")
    created_at: datetime = Field(..., description="Creation timestamp")


# ============================================================================
# HOVER INFORMATION SCHEMAS
# ============================================================================


class LocationInfo(BaseModel):
    """Location information for a symbol definition."""

    file_path: str = Field(..., description="File path of the definition")
    line: int = Field(..., description="Line number of the definition")
    column: Optional[int] = Field(None, description="Column number of the definition")


class ChunkReference(BaseModel):
    """Reference to a related document chunk."""

    chunk_id: str = Field(..., description="Document chunk UUID")
    content_preview: str = Field(
        ..., description="Preview of chunk content (first 200 chars)"
    )
    similarity_score: Optional[float] = Field(
        None, description="Similarity score if available"
    )


class HoverInformationResponse(BaseModel):
    """Response schema for hover information API.

    Provides contextual information about code at a specific position,
    including symbol information, documentation, and related chunks.
    """

    symbol_name: Optional[str] = Field(
        None, description="Name of the symbol at position"
    )
    symbol_type: Optional[str] = Field(
        None,
        description="Type of symbol (function, class, variable, method, etc.)",
    )
    definition_location: Optional[LocationInfo] = Field(
        None, description="Location where symbol is defined"
    )
    documentation: Optional[str] = Field(
        None, description="Documentation string for the symbol"
    )
    related_chunks: List[ChunkReference] = Field(
        default_factory=list,
        description="Related document chunks with similar content",
    )
    context_lines: List[str] = Field(
        default_factory=list, description="Surrounding code lines for context"
    )


class CentralityMetrics(BaseModel):
    """Centrality metrics for a graph node.

    Provides multiple centrality measures to identify important nodes:
    - Degree centrality: Number of direct connections
    - Betweenness centrality: How often node appears on shortest paths
    - PageRank: Importance based on incoming link structure
    """

    resource_id: UUID = Field(..., description="Resource UUID")
    in_degree: int = Field(..., description="Number of incoming edges")
    out_degree: int = Field(..., description="Number of outgoing edges")
    total_degree: int = Field(..., description="Total number of edges (in + out)")
    betweenness: float = Field(..., description="Betweenness centrality score (0-1)")
    pagerank: float = Field(..., description="PageRank score")
    computed_at: Optional[str] = Field(
        None, description="Timestamp when metrics were computed"
    )


class CentralityResponse(BaseModel):
    """Response schema for centrality metrics API.

    Returns centrality metrics for requested resources.
    """

    metrics: dict[UUID, CentralityMetrics] = Field(
        ..., description="Centrality metrics by resource ID"
    )
    computation_time_ms: float = Field(
        ..., description="Time taken to compute metrics (milliseconds)"
    )
    cached: bool = Field(..., description="Whether results were retrieved from cache")


class CommunityDetectionResult(BaseModel):
    """Result of community detection algorithm.

    Contains community assignments, modularity score, and community statistics.
    """

    communities: dict[int, int] = Field(
        ..., description="Mapping of resource_id to community_id"
    )
    modularity: float = Field(
        ..., description="Modularity score of the partition (-1 to 1)"
    )
    num_communities: int = Field(..., description="Number of communities detected")
    community_sizes: dict[int, int] = Field(
        ..., description="Mapping of community_id to number of members"
    )


class CommunityDetectionResponse(BaseModel):
    """Response schema for community detection API.

    Returns community assignments and statistics for the graph.
    """

    result: CommunityDetectionResult = Field(
        ..., description="Community detection results"
    )
    computation_time_ms: float = Field(
        ..., description="Time taken to detect communities (milliseconds)"
    )
    cached: bool = Field(..., description="Whether results were retrieved from cache")
    resolution: float = Field(
        ..., description="Resolution parameter used for detection"
    )


# ============================================================================
# GRAPH VISUALIZATION SCHEMAS
# ============================================================================


class NodePosition(BaseModel):
    """2D position of a node in graph layout."""

    x: float = Field(..., description="X coordinate (0-1000)")
    y: float = Field(..., description="Y coordinate (0-1000)")


class EdgeRouting(BaseModel):
    """Edge routing information for visualization."""

    source: UUID = Field(..., description="Source node UUID")
    target: UUID = Field(..., description="Target node UUID")
    weight: float = Field(..., description="Edge weight")


class BoundingBox(BaseModel):
    """Bounding box for graph layout."""

    min_x: float = Field(..., description="Minimum X coordinate")
    max_x: float = Field(..., description="Maximum X coordinate")
    min_y: float = Field(..., description="Minimum Y coordinate")
    max_y: float = Field(..., description="Maximum Y coordinate")


class GraphLayoutResult(BaseModel):
    """Result of graph layout computation.

    Contains node positions, edge routing, and bounding box.
    """

    nodes: dict[UUID, NodePosition] = Field(
        ..., description="Node positions by resource UUID"
    )
    edges: List[EdgeRouting] = Field(..., description="Edge routing information")
    bounds: BoundingBox = Field(..., description="Bounding box of the layout")
    layout_type: str = Field(
        ..., description="Layout algorithm used (force, hierarchical, circular)"
    )


class GraphLayoutResponse(BaseModel):
    """Response schema for graph layout API.

    Returns layout information for visualization.
    """

    layout: GraphLayoutResult = Field(..., description="Graph layout result")
    computation_time_ms: float = Field(
        ..., description="Time taken to compute layout (milliseconds)"
    )
    cached: bool = Field(..., description="Whether results were retrieved from cache")
    node_count: int = Field(..., description="Number of nodes in the layout")
    edge_count: int = Field(..., description="Number of edges in the layout")
