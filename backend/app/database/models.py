"""
Neo Alexandria 2.0 - Database Models

This module is the SINGLE SOURCE OF TRUTH for all SQLAlchemy database models.
All models are defined here to avoid circular import dependencies.

Model Organization:
- Resources: Resource model with ResourceStatus enum
- Collections: Collection, CollectionResource models
- Annotations: Annotation model
- Graph: Citation, GraphEdge, GraphEmbedding, DiscoveryHypothesis models
- Recommendations: UserProfile, UserInteraction, RecommendationFeedback models
- Taxonomy: TaxonomyNode, ResourceTaxonomy models
- Authority: AuthoritySubject, AuthorityCreator, AuthorityPublisher models
- User: Core authentication model
- Classification: ClassificationCode lookup table
- ML Infrastructure: ModelVersion, ABTestExperiment, PredictionLog, RetrainingRun

IMPORTANT: Module model.py files should NOT define models, only re-export from here.
This prevents circular import dependencies.

Related files:
- app/shared/base_model.py: Base class and database configuration
- app/modules/*/model.py: Re-export models from this file
- alembic/versions/: Database migration scripts
"""

import enum
import uuid
from datetime import datetime
from typing import List

from sqlalchemy import (
    String,
    Text,
    DateTime,
    Float,
    func,
    JSON,
    Integer,
    ForeignKey,
    Index,
    ARRAY,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, backref
from sqlalchemy.dialects import postgresql

from ..shared.base_model import Base, GUID

# ============================================================================
# Enums
# ============================================================================


class ResourceStatus(str, enum.Enum):
    """Resource ingestion status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================================
# Resource Models
# ============================================================================

# ============================================================================
# Enums (continued)
# ============================================================================


# ============================================================================
# Resource Models
# ============================================================================


class Resource(Base):
    """Resource model implementing hybrid Dublin Core + custom metadata schema."""

    __tablename__ = "resources"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    # Dublin Core required fields
    title: Mapped[str] = mapped_column(String, nullable=False)

    # Dublin Core optional fields
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    creator: Mapped[str | None] = mapped_column(String, nullable=True)
    publisher: Mapped[str | None] = mapped_column(String, nullable=True)
    contributor: Mapped[str | None] = mapped_column(String, nullable=True)
    date_created: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    date_modified: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    type: Mapped[str | None] = mapped_column(String, nullable=True)
    format: Mapped[str | None] = mapped_column(String, nullable=True)
    identifier: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    coverage: Mapped[str | None] = mapped_column(String, nullable=True)
    rights: Mapped[str | None] = mapped_column(String, nullable=True)

    # JSON arrays for multi-valued fields
    subject: Mapped[List[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    relation: Mapped[List[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )

    # Custom fields
    classification_code: Mapped[str | None] = mapped_column(String, nullable=True)
    read_status: Mapped[str] = mapped_column(String, nullable=False, default="unread")
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Ingestion workflow fields
    ingestion_status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending"
    )
    ingestion_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingestion_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ingestion_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Curation workflow fields
    curation_status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default="pending"
    )
    assigned_curator: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    # Vector embedding for hybrid search
    # Use Text to avoid JSON casting issues with NULL in PostgreSQL
    embedding: Mapped[List[float] | None] = mapped_column(
        Text,
        nullable=True,
    )

    sparse_embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    sparse_embedding_model: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    sparse_embedding_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    search_vector: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Scholarly Metadata Fields
    authors: Mapped[str | None] = mapped_column(Text, nullable=True)
    affiliations: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    pmid: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    isbn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    journal: Mapped[str | None] = mapped_column(String, nullable=True)
    conference: Mapped[str | None] = mapped_column(String, nullable=True)
    volume: Mapped[str | None] = mapped_column(String(50), nullable=True)
    issue: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pages: Mapped[str | None] = mapped_column(String(50), nullable=True)
    publication_year: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    funding_sources: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledgments: Mapped[str | None] = mapped_column(Text, nullable=True)
    equation_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    table_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    figure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    reference_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    equations: Mapped[str | None] = mapped_column(Text, nullable=True)
    tables: Mapped[str | None] = mapped_column(Text, nullable=True)
    figures: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_completeness_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    requires_manual_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    quality_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_completeness: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_consistency: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_timeliness: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_relevance: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_overall: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_weights: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_last_computed: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    quality_computation_version: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    is_quality_outlier: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    outlier_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    outlier_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_quality_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    summary_coherence: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary_consistency: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary_fluency: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary_relevance: Mapped[float | None] = mapped_column(Float, nullable=True)

    # OCR Metadata
    is_ocr_processed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_corrections_applied: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Optimistic concurrency control
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    collections: Mapped[List["Collection"]] = relationship(
        "Collection", secondary="collection_resources", back_populates="resources"
    )
    annotations: Mapped[List["Annotation"]] = relationship(
        "Annotation", back_populates="resource", cascade="all, delete-orphan"
    )
    taxonomy_nodes: Mapped[List["TaxonomyNode"]] = relationship(
        "TaxonomyNode", secondary="resource_taxonomy", back_populates="resources"
    )
    centrality_cache: Mapped["GraphCentralityCache"] = relationship(
        "GraphCentralityCache", back_populates="resource", uselist=False
    )
    community_assignments: Mapped[List["CommunityAssignment"]] = relationship(
        "CommunityAssignment", back_populates="resource", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_resources_sparse_updated", "sparse_embedding_updated_at"),
    )

    def __repr__(self) -> str:
        scholarly_info = f", doi={self.doi!r}" if self.doi else ""
        return f"<Resource(id={self.id!r}, title={self.title!r}{scholarly_info})>"


# ============================================================================
# Advanced RAG Models
# ============================================================================


class DocumentChunk(Base):
    """
    Document chunk model for parent-child chunking in advanced RAG.

    Stores small, searchable text chunks with embeddings (retrieval units)
    while maintaining relationship to parent resource (generation unit).
    Supports both PDF pages and code line numbers via flexible metadata.
    """

    __tablename__ = "document_chunks"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    resource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        nullable=True,  # Embedding may be generated asynchronously
    )

    # Content and metadata
    # Nullable: code chunks omit raw content — content lives on GitHub.
    # Document (PDF) chunks still populate this field.
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Flexible metadata supporting both PDF and code
    # For PDFs: {"page": 1, "coordinates": [x, y]}
    # For Code: {"start_line": 10, "end_line": 25, "function_name": "calculate_loss", "file_path": "src/model.py"}
    chunk_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── Hybrid GitHub Storage (Phase 2) ───────────────────────────────────
    # When is_remote=True the raw source lives on GitHub; content is NULL.
    # Fetch on-demand via GitHubFetcher using these pointer fields.

    # Flag distinguishing remote (code) chunks from inline (PDF) chunks
    is_remote: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Full GitHub raw URL, e.g.
    # https://raw.githubusercontent.com/owner/repo/SHA/path/to/file.py
    github_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Pinned commit SHA or branch name for reproducible fetches
    branch_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Source line span within the file (1-based, inclusive)
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # AST symbol information
    ast_node_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # "function", "class", "method", "module"
    symbol_name: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )  # fully-qualified name, e.g. "auth.oauth.handle_oauth_callback"

    # Semantic summary used for embedding generation (signature + docstring).
    # Stored so the embedding can be re-generated without re-fetching GitHub.
    semantic_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    resource: Mapped["Resource"] = relationship(
        "Resource",
        backref=backref("chunks", cascade="all, delete-orphan", passive_deletes=True),
    )

    # Indexes
    __table_args__ = (
        Index("idx_chunk_resource", "resource_id"),
        Index("idx_chunk_resource_index", "resource_id", "chunk_index"),
    )

    def __repr__(self) -> str:
        return f"<DocumentChunk(id={self.id!r}, resource_id={self.resource_id!r}, chunk_index={self.chunk_index})>"


class ChunkLink(Base):
    """
    Bidirectional semantic link between document chunks.

    Stores similarity-based links between PDF chunks and code chunks
    for auto-linking functionality.
    """

    __tablename__ = "chunk_links"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    source_chunk_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_chunk_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Link metadata
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    link_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "pdf_to_code", "code_to_pdf", "bidirectional"

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    source_chunk: Mapped["DocumentChunk"] = relationship(
        "DocumentChunk",
        foreign_keys=[source_chunk_id],
    )
    target_chunk: Mapped["DocumentChunk"] = relationship(
        "DocumentChunk",
        foreign_keys=[target_chunk_id],
    )

    # Indexes
    __table_args__ = (
        Index("idx_chunk_links_source", "source_chunk_id"),
        Index("idx_chunk_links_target", "target_chunk_id"),
        Index("idx_chunk_links_similarity", "similarity_score"),
        Index("idx_chunk_links_source_target", "source_chunk_id", "target_chunk_id"),
    )

    def __repr__(self) -> str:
        return f"<ChunkLink(source={self.source_chunk_id!r}, target={self.target_chunk_id!r}, similarity={self.similarity_score:.3f})>"


class PlanningSession(Base):
    """
    Stores multi-hop planning sessions for iterative refinement.

    Part of the AI Planning infrastructure.
    """

    __tablename__ = "planning_sessions"

    # Primary key
    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID string

    # Planning data
    task_description: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict] = mapped_column(JSON, nullable=False)
    steps: Mapped[list] = mapped_column(
        JSON, nullable=False
    )  # List of PlanningStep dicts
    dependencies: Mapped[list] = mapped_column(JSON, nullable=False)  # List of tuples
    status: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "active", "completed", "failed"

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Indexes
    __table_args__ = (
        Index("idx_planning_status", "status"),
        Index("idx_planning_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<PlanningSession(id={self.id!r}, status={self.status!r}, steps={len(self.steps)})>"


# ============================================================================
# Collection Models
# ============================================================================


class CollectionResource(Base):
    """Many-to-many association table between collections and resources."""

    __tablename__ = "collection_resources"

    collection_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (
        Index("idx_collection_resources_collection", "collection_id"),
        Index("idx_collection_resources_resource", "resource_id"),
    )

    def __repr__(self) -> str:
        return f"<CollectionResource(collection_id={self.collection_id!r}, resource_id={self.resource_id!r})>"


class Collection(Base):
    """User-curated collection of resources with hierarchical organization."""

    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    visibility: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="private",
        server_default="private",
        index=True,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    embedding: Mapped[List[float] | None] = mapped_column(
        JSON, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    parent: Mapped["Collection"] = relationship(
        "Collection",
        remote_side=[id],
        back_populates="subcollections",
        foreign_keys=[parent_id],
    )
    subcollections: Mapped[List["Collection"]] = relationship(
        "Collection",
        back_populates="parent",
        cascade="all, delete-orphan",
        foreign_keys=[parent_id],
    )
    resources: Mapped[List["Resource"]] = relationship(
        "Resource", secondary="collection_resources", back_populates="collections"
    )

    def __repr__(self) -> str:
        return f"<Collection(id={self.id!r}, name={self.name!r}, owner_id={self.owner_id!r}, visibility={self.visibility!r})>"


# ============================================================================
# Annotation Models
# ============================================================================


class Annotation(Base):
    """Annotation model for user notes and highlights on resources."""

    __tablename__ = "annotations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    highlighted_text: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(
        String(7), nullable=False, server_default="#FFFF00"
    )
    embedding: Mapped[List[float] | None] = mapped_column(JSON, nullable=True)
    context_before: Mapped[str | None] = mapped_column(String(50), nullable=True)
    context_after: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_shared: Mapped[bool] = mapped_column(Integer, nullable=False, server_default="0")
    collection_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    resource: Mapped["Resource"] = relationship(
        "Resource", back_populates="annotations"
    )

    __table_args__ = (
        Index("idx_annotations_resource", "resource_id"),
        Index("idx_annotations_user", "user_id"),
        Index("idx_annotations_user_resource", "user_id", "resource_id"),
        Index("idx_annotations_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Annotation(id={self.id!r}, resource_id={self.resource_id!r})>"


# ============================================================================
# Graph Models
# ============================================================================


class GraphEntity(Base):
    """
    Named entity extracted from text for GraphRAG.

    Stores entities like concepts, people, organizations, and methods
    extracted from document chunks for knowledge graph construction.
    """

    __tablename__ = "graph_entities"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    # Entity data
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # Concept, Person, Organization, Method
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    outgoing_relationships: Mapped[List["GraphRelationship"]] = relationship(
        "GraphRelationship",
        foreign_keys="GraphRelationship.source_entity_id",
        back_populates="source_entity",
        cascade="all, delete-orphan",
    )
    incoming_relationships: Mapped[List["GraphRelationship"]] = relationship(
        "GraphRelationship",
        foreign_keys="GraphRelationship.target_entity_id",
        back_populates="target_entity",
        cascade="all, delete-orphan",
    )

    # Indexes
    __table_args__ = (Index("idx_entity_name_type", "name", "type"),)

    def __repr__(self) -> str:
        return f"<GraphEntity(id={self.id!r}, name={self.name!r}, type={self.type!r})>"


class GraphRelationship(Base):
    """
    Semantic triple (Subject -> Predicate -> Object) for GraphRAG.

    Stores relationships between entities with provenance linking back to source chunks.
    Supports both academic relationships (CONTRADICTS, SUPPORTS, EXTENDS, CITES) and
    code-specific relationships (CALLS, IMPORTS, DEFINES).
    """

    __tablename__ = "graph_relationships"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("graph_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("graph_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provenance_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True
    )

    # Relationship data
    # Academic: CONTRADICTS, SUPPORTS, EXTENDS, CITES
    # Code: CALLS, IMPORTS, DEFINES
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # Metadata for code relationships (source_file, target_symbol, line_number, confidence)
    relationship_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    source_entity: Mapped["GraphEntity"] = relationship(
        "GraphEntity",
        foreign_keys=[source_entity_id],
        back_populates="outgoing_relationships",
    )
    target_entity: Mapped["GraphEntity"] = relationship(
        "GraphEntity",
        foreign_keys=[target_entity_id],
        back_populates="incoming_relationships",
    )
    provenance_chunk: Mapped["DocumentChunk"] = relationship("DocumentChunk")

    # Indexes
    __table_args__ = (
        Index("idx_relationship_source", "source_entity_id"),
        Index("idx_relationship_target", "target_entity_id"),
        Index("idx_relationship_type", "relation_type"),
    )

    def __repr__(self) -> str:
        return f"<GraphRelationship(source={self.source_entity_id!r}, target={self.target_entity_id!r}, type={self.relation_type!r})>"


class Citation(Base):
    """Citation relationship between resources."""

    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    source_resource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_resource_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("resources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_url: Mapped[str] = mapped_column(String, nullable=False)
    citation_type: Mapped[str] = mapped_column(
        String, nullable=False, server_default="reference"
    )
    context_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    importance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (
        Index("idx_citations_source", "source_resource_id"),
        Index("idx_citations_target", "target_resource_id"),
        Index("idx_citations_url", "target_url"),
    )

    def __repr__(self) -> str:
        return f"<Citation(source_resource_id={self.source_resource_id!r}, target_resource_id={self.target_resource_id!r})>"


class GraphEdge(Base):
    """Semantic relationship edge in knowledge graph."""

    __tablename__ = "graph_edges"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    edge_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    edge_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    __table_args__ = (
        Index("idx_graph_edges_source", "source_id"),
        Index("idx_graph_edges_target", "target_id"),
        Index("idx_graph_edges_type", "edge_type"),
        Index(
            "idx_graph_edges_composite",
            "source_id",
            "target_id",
            "edge_type",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return f"<GraphEdge(source_id={self.source_id!r}, target_id={self.target_id!r}, type={self.edge_type!r})>"


class GraphEmbedding(Base):
    """Graph embedding for resources in knowledge graph."""

    __tablename__ = "graph_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    structural_embedding: Mapped[List[float] | None] = mapped_column(
        JSON, nullable=True
    )
    fusion_embedding: Mapped[List[float] | None] = mapped_column(JSON, nullable=True)
    embedding_method: Mapped[str] = mapped_column(String(50), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(20), nullable=False)
    hnsw_index_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    __table_args__ = (
        Index("idx_graph_embeddings_resource", "resource_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<GraphEmbedding(resource_id={self.resource_id!r}, method={self.embedding_method!r})>"


class GraphCentralityCache(Base):
    """Cache for graph centrality metrics with TTL."""

    __tablename__ = "graph_centrality_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    in_degree: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    out_degree: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    betweenness: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0.0"
    )
    pagerank: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationship
    resource: Mapped["Resource"] = relationship(
        "Resource", back_populates="centrality_cache"
    )

    __table_args__ = (
        Index("idx_centrality_resource", "resource_id"),
        Index("idx_centrality_computed", "computed_at"),
    )

    def __repr__(self) -> str:
        return f"<GraphCentralityCache(resource_id={self.resource_id!r}, pagerank={self.pagerank})>"


class CommunityAssignment(Base):
    """Cache for community detection results with TTL (15 minutes)."""

    __tablename__ = "community_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    community_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    modularity: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0.0"
    )
    resolution: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="1.0"
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationship
    resource: Mapped["Resource"] = relationship(
        "Resource", back_populates="community_assignments"
    )

    __table_args__ = (
        Index("idx_community_resource", "resource_id"),
        Index("idx_community_id", "community_id"),
        Index("idx_community_computed", "computed_at"),
    )

    def __repr__(self) -> str:
        return f"<CommunityAssignment(resource_id={self.resource_id!r}, community_id={self.community_id})>"


class DiscoveryHypothesis(Base):
    """AI-generated hypothesis for knowledge discovery."""

    __tablename__ = "discovery_hypotheses"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    a_resource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("resources.id", ondelete="CASCADE"), nullable=False
    )
    c_resource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("resources.id", ondelete="CASCADE"), nullable=False
    )
    b_resource_ids: Mapped[str] = mapped_column(Text, nullable=False)
    hypothesis_type: Mapped[str] = mapped_column(String(20), nullable=False)
    plausibility_score: Mapped[float] = mapped_column(Float, nullable=False)
    path_strength: Mapped[float] = mapped_column(Float, nullable=False)
    path_length: Mapped[int] = mapped_column(Integer, nullable=False)
    common_neighbors: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_validated: Mapped[bool | None] = mapped_column(Integer, nullable=True)
    validation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    __table_args__ = (
        Index("idx_discovery_a_c", "a_resource_id", "c_resource_id"),
        Index("idx_discovery_type", "hypothesis_type"),
        Index("idx_discovery_plausibility", "plausibility_score"),
    )

    def __repr__(self) -> str:
        return f"<DiscoveryHypothesis(id={self.id!r}, plausibility={self.plausibility_score})>"


class SyntheticQuestion(Base):
    """
    LLM-generated question for Reverse HyDE retrieval.

    Stores synthetic questions that a chunk could answer, enabling
    question-based retrieval by matching user queries to synthetic questions.
    """

    __tablename__ = "synthetic_questions"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        nullable=True,  # Embedding may be generated asynchronously
    )

    # Question data
    question_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    chunk: Mapped["DocumentChunk"] = relationship(
        "DocumentChunk", backref="synthetic_questions"
    )

    # Indexes
    __table_args__ = (Index("idx_synthetic_chunk", "chunk_id"),)

    def __repr__(self) -> str:
        return f"<SyntheticQuestion(id={self.id!r}, chunk_id={self.chunk_id!r})>"


# ============================================================================
# Recommendation Models
# ============================================================================


class UserProfile(Base):
    """
    User profile for personalized recommendations.

    Stores user preferences, learned patterns, and recommendation settings.
    Supports diversity, novelty, and recency preferences for hybrid recommendations.
    """

    __tablename__ = "user_profiles"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    # Foreign key (one-to-one with User)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Research context (JSON arrays stored as Text)
    research_domains: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON: ["AI", "ML", "NLP"]
    active_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Learned preferences (JSON arrays stored as Text)
    preferred_taxonomy_ids: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON: ["uuid1", "uuid2", ...]
    preferred_authors: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON: ["Author 1", "Author 2", ...]
    preferred_sources: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON: ["source1.com", "source2.com", ...]
    excluded_sources: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON: ["excluded1.com", "excluded2.com", ...]

    # Preference settings (0.0-1.0 range)
    diversity_preference: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5, server_default="0.5"
    )
    novelty_preference: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.3, server_default="0.3"
    )
    recency_bias: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5, server_default="0.5"
    )

    # Interaction metrics
    total_interactions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    avg_session_duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="profile")

    __table_args__ = (Index("idx_user_profiles_user", "user_id", unique=True),)

    def __repr__(self) -> str:
        return f"<UserProfile(user_id={self.user_id!r})>"


class UserInteraction(Base):
    """
    User-resource interaction tracking for recommendation engine.

    Tracks all user interactions with resources using implicit feedback signals.
    Supports multiple interaction types with computed interaction strength.
    """

    __tablename__ = "user_interactions"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Interaction metadata
    interaction_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'view', 'annotation', 'collection_add', 'export', 'rating'
    interaction_strength: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0.0"
    )  # 0.0-1.0 computed score

    # Implicit feedback signals
    dwell_time: Mapped[int | None] = mapped_column(Integer, nullable=True)  # seconds
    scroll_depth: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0.0-1.0
    annotation_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    return_visits: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Explicit feedback
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5 stars

    # Context
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    interaction_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        index=True,
    )

    # Derived fields
    is_positive: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )  # SQLite uses 0/1 for bool (strength > 0.4)
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0.0"
    )  # 0.0-1.0

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="interactions")
    resource: Mapped["Resource"] = relationship("Resource")

    __table_args__ = (
        Index("idx_user_interactions_user", "user_id"),
        Index("idx_user_interactions_resource", "resource_id"),
        Index("idx_user_interactions_user_resource", "user_id", "resource_id"),
        Index("idx_user_interactions_timestamp", "interaction_timestamp"),
    )

    def __repr__(self) -> str:
        return f"<UserInteraction(user_id={self.user_id!r}, resource_id={self.resource_id!r}, type={self.interaction_type!r})>"


class RecommendationFeedback(Base):
    """User feedback on recommendations for model improvement."""

    __tablename__ = "recommendation_feedback"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feedback_type: Mapped[str] = mapped_column(String(50), nullable=False)
    feedback_value: Mapped[float] = mapped_column(Float, nullable=False)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="feedback")

    __table_args__ = (
        Index("idx_recommendation_feedback_user", "user_id"),
        Index("idx_recommendation_feedback_resource", "resource_id"),
        Index("idx_recommendation_feedback_type", "feedback_type"),
    )

    def __repr__(self) -> str:
        return f"<RecommendationFeedback(user_id={self.user_id!r}, resource_id={self.resource_id!r})>"


# ============================================================================
# Taxonomy and Authority Models
# ============================================================================


class ClassificationCode(Base):
    """Lookup table for personal/UDC-inspired classification codes."""

    __tablename__ = "classification_codes"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    title: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # Changed from 'label' to 'title'
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_code: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("classification_codes.code", ondelete="SET NULL"),
        nullable=True,
    )
    keywords: Mapped[List[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )

    def __repr__(self) -> str:
        return f"<ClassificationCode(code={self.code!r}, title={self.title!r})>"


class AuthoritySubject(Base):
    """Authority table for subjects with canonical form, variants, and usage counts."""

    __tablename__ = "authority_subjects"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    canonical_form: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    variants: Mapped[List[str] | None] = mapped_column(JSON, nullable=True)
    usage_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    def __repr__(self) -> str:
        return f"<AuthoritySubject(canonical_form={self.canonical_form!r}, usage_count={self.usage_count})>"


class AuthorityCreator(Base):
    """Authority table for creators/authors with canonical form, variants, and usage counts."""

    __tablename__ = "authority_creators"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    canonical_form: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    variants: Mapped[List[str] | None] = mapped_column(JSON, nullable=True)
    usage_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    def __repr__(self) -> str:
        return f"<AuthorityCreator(canonical_form={self.canonical_form!r}, usage_count={self.usage_count})>"


class AuthorityPublisher(Base):
    """Authority table for publishers with canonical form, variants, and usage counts."""

    __tablename__ = "authority_publishers"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    canonical_form: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    variants: Mapped[List[str] | None] = mapped_column(JSON, nullable=True)
    usage_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    def __repr__(self) -> str:
        return f"<AuthorityPublisher(canonical_form={self.canonical_form!r}, usage_count={self.usage_count})>"


class TaxonomyNode(Base):
    """Hierarchical taxonomy tree node for ML-based classification."""

    __tablename__ = "taxonomy_nodes"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("taxonomy_nodes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[List[str] | None] = mapped_column(JSON, nullable=True)
    resource_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    descendant_resource_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_leaf: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    allow_resources: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    parent: Mapped["TaxonomyNode"] = relationship(
        "TaxonomyNode",
        remote_side=[id],
        back_populates="children",
        foreign_keys=[parent_id],
    )
    children: Mapped[List["TaxonomyNode"]] = relationship(
        "TaxonomyNode",
        back_populates="parent",
        cascade="all, delete-orphan",
        foreign_keys=[parent_id],
    )
    resources: Mapped[List["Resource"]] = relationship(
        "Resource", secondary="resource_taxonomy", back_populates="taxonomy_nodes"
    )

    __table_args__ = (
        Index("idx_taxonomy_parent_id", "parent_id"),
        Index("idx_taxonomy_path", "path"),
        Index("idx_taxonomy_slug", "slug", unique=True),
    )

    def __repr__(self) -> str:
        return f"<TaxonomyNode(slug={self.slug!r}, name={self.name!r})>"

    def validate(self):
        """Validate taxonomy node before insert/update."""
        if not self.name or not self.name.strip():
            raise ValueError("Category name cannot be empty or whitespace-only")


# Add validation event listeners for TaxonomyNode
from sqlalchemy import event


@event.listens_for(TaxonomyNode, "before_insert")
@event.listens_for(TaxonomyNode, "before_update")
def validate_taxonomy_node(mapper, connection, target):
    """Validate taxonomy node before database operations."""
    target.validate()


class ResourceTaxonomy(Base):
    """Association table for many-to-many Resource-Taxonomy relationship."""

    __tablename__ = "resource_taxonomy"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("resources.id", ondelete="CASCADE"), nullable=False
    )
    taxonomy_node_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("taxonomy_nodes.id", ondelete="CASCADE"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0.0"
    )
    is_predicted: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    predicted_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    needs_review: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    review_priority: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (
        Index("idx_resource_taxonomy_resource", "resource_id"),
        Index("idx_resource_taxonomy_taxonomy", "taxonomy_node_id"),
        Index("idx_resource_taxonomy_needs_review", "needs_review"),
    )

    def __repr__(self) -> str:
        return f"<ResourceTaxonomy(resource_id={self.resource_id!r}, taxonomy_node_id={self.taxonomy_node_id!r})>"


# ============================================================================
# Curation Models
# ============================================================================


class CurationReview(Base):
    """Curation review record for tracking content review actions."""

    __tablename__ = "curation_reviews"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    curator_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # approve, reject, flag
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (
        Index("idx_curation_reviews_resource", "resource_id"),
        Index("idx_curation_reviews_curator", "curator_id"),
        Index("idx_curation_reviews_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<CurationReview(resource_id={self.resource_id!r}, action={self.action!r})>"


class RAGEvaluation(Base):
    """
    RAG evaluation metrics storage for RAGAS framework.

    Stores ground-truth evaluation data and computed metrics for measuring
    and improving RAG system performance.
    """

    __tablename__ = "rag_evaluations"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    # Evaluation data
    query: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_chunk_ids: Mapped[List[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )

    # RAGAS metrics (0.0 to 1.0)
    faithfulness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_precision_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        index=True,
    )

    # Indexes
    __table_args__ = (Index("idx_evaluation_created", "created_at"),)

    def __repr__(self) -> str:
        return f"<RAGEvaluation(id={self.id!r}, query={self.query[:50]!r})>"


# ============================================================================
# User and Authentication Models
# ============================================================================


class User(Base):
    """User model for authentication and profile management."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user", server_default="user"
    )
    tier: Mapped[str] = mapped_column(
        String(20), nullable=False, default="free", server_default="free"
    )  # free, premium, admin
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    profile: Mapped["UserProfile"] = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    interactions: Mapped[List["UserInteraction"]] = relationship(
        "UserInteraction", back_populates="user", cascade="all, delete-orphan"
    )
    feedback: Mapped[List["RecommendationFeedback"]] = relationship(
        "RecommendationFeedback", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(username={self.username!r}, email={self.email!r})>"


# ============================================================================
# ML Infrastructure Models
# ============================================================================


class ModelVersion(Base):
    """Model version tracking for ML models."""

    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    model_path: Mapped[str] = mapped_column(String(512), nullable=False)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    deployed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("idx_model_version_name_version", "model_name", "version", unique=True),
        Index("idx_model_version_active", "is_active"),
    )

    def __repr__(self) -> str:
        return (
            f"<ModelVersion(model_name={self.model_name!r}, version={self.version!r})>"
        )


class ABTestExperiment(Base):
    """A/B test experiment configuration."""

    __tablename__ = "ab_test_experiments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_a_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("model_versions.id"), nullable=False
    )
    model_b_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("model_versions.id"), nullable=False
    )
    traffic_split: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    winner_model_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    model_a: Mapped["ModelVersion"] = relationship(
        "ModelVersion", foreign_keys=[model_a_id]
    )
    model_b: Mapped["ModelVersion"] = relationship(
        "ModelVersion", foreign_keys=[model_b_id]
    )

    def __repr__(self) -> str:
        return f"<ABTestExperiment(name={self.name!r}, status={self.status!r})>"


class PredictionLog(Base):
    """Prediction logging for A/B test analysis."""

    __tablename__ = "prediction_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("ab_test_experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("model_versions.id"), nullable=False, index=True
    )
    input_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    prediction: Mapped[dict] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    user_feedback: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    feedback_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        index=True,
    )

    experiment: Mapped["ABTestExperiment"] = relationship("ABTestExperiment")
    model_version: Mapped["ModelVersion"] = relationship("ModelVersion")

    def __repr__(self) -> str:
        return f"<PredictionLog(experiment_id={self.experiment_id!r})>"


class RetrainingRun(Base):
    """Retraining run tracking for automated model retraining pipeline."""

    __tablename__ = "retraining_runs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    trigger: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    resulting_model_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("model_versions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    resulting_model: Mapped["ModelVersion"] = relationship("ModelVersion")

    def __repr__(self) -> str:
        return (
            f"<RetrainingRun(model_name={self.model_name!r}, status={self.status!r})>"
        )


# ============================================================================
# Pattern Learning Engine Models
# ============================================================================


class DeveloperProfileRecord(Base):
    """
    Persisted developer coding profile generated by the Pattern Learning Engine.

    Stores the JSON profile produced by AST parsing and Git history analysis
    for a given repository and user.
    """

    __tablename__ = "developer_profiles"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    # Link to user who triggered the analysis
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Repository identification
    repository_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    repository_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # The full JSON profile (DeveloperProfile schema)
    profile_data: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Analysis metadata
    total_files_analyzed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_commits_analyzed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    languages_detected: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON array as text

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Indexes
    __table_args__ = (
        Index("ix_developer_profiles_user_repo", "user_id", "repository_url"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", backref="developer_profiles")

    def __repr__(self) -> str:
        return (
            f"<DeveloperProfileRecord(repo={self.repository_name!r}, "
            f"user_id={self.user_id!r})>"
        )


# ============================================================================
# Feedback Loop: Proposed Rules
# ============================================================================


class RuleStatus(str, enum.Enum):
    """Status lifecycle for auto-extracted coding rules."""

    PENDING_REVIEW = "PENDING_REVIEW"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"


class ProposedRule(Base):
    """
    A coding rule extracted by the local LLM from a surviving Git diff.

    Created by the local extraction worker and triaged via the CLI.
    Active rules feed into the context assembly pipeline.
    """

    __tablename__ = "proposed_rules"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    # Source provenance
    repository: Mapped[str] = mapped_column(String(1024), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    # The raw diff that triggered extraction
    diff_payload: Mapped[str] = mapped_column(Text, nullable=False)

    # LLM-extracted rule (JSON schema)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_description: Mapped[str] = mapped_column(Text, nullable=False)
    rule_schema: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Confidence score from the local LLM (0.0–1.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Review lifecycle
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RuleStatus.PENDING_REVIEW.value
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    __table_args__ = (
        Index("ix_proposed_rules_status", "status"),
        Index("ix_proposed_rules_repo_sha", "repository", "commit_sha"),
    )

    def __repr__(self) -> str:
        return f"<ProposedRule(name={self.rule_name!r}, status={self.status!r})>"


# Export all models for easy importing
__all__ = [
    # Enums
    "ResourceStatus",
    # Resource models
    "Resource",
    # Advanced RAG models
    "DocumentChunk",
    "GraphEntity",
    "GraphRelationship",
    "SyntheticQuestion",
    "RAGEvaluation",
    # Collection models
    "Collection",
    "CollectionResource",
    # Annotation models
    "Annotation",
    # Curation models
    "CurationReview",
    # Graph models
    "Citation",
    "GraphEdge",
    "GraphEmbedding",
    "DiscoveryHypothesis",
    # Recommendation models
    "UserProfile",
    "UserInteraction",
    "RecommendationFeedback",
    # Taxonomy and authority models
    "ClassificationCode",
    "AuthoritySubject",
    "AuthorityCreator",
    "AuthorityPublisher",
    "TaxonomyNode",
    "ResourceTaxonomy",
    # User models
    "User",
    # ML infrastructure models
    "ModelVersion",
    "ABTestExperiment",
    "PredictionLog",
    "RetrainingRun",
    # Pattern learning engine models
    "DeveloperProfileRecord",
    # Feedback loop models
    "RuleStatus",
    "ProposedRule",
]
