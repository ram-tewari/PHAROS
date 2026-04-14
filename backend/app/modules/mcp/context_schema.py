"""
Context Assembly Schemas

Pydantic models for Ronin context retrieval and assembly.
Phase 5: Ronin Integration & Context Assembly
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Request Models
# ============================================================================


class ContextRetrievalRequest(BaseModel):
    """Request for context assembly from all intelligence layers"""

    query: str = Field(
        ...,
        description="Natural language query from Ronin (e.g., 'Refactor my login route')",
        min_length=1,
        max_length=1000,
    )
    codebase: str = Field(
        ...,
        description="Codebase identifier (repository name or ID)",
        min_length=1,
    )
    user_id: Optional[str] = Field(
        None,
        description="User ID for personalized pattern retrieval",
    )
    max_code_chunks: int = Field(
        default=10,
        description="Maximum number of code chunks to retrieve",
        ge=1,
        le=50,
    )
    max_graph_hops: int = Field(
        default=2,
        description="Maximum graph traversal depth for dependencies",
        ge=1,
        le=3,
    )
    max_pdf_chunks: int = Field(
        default=5,
        description="Maximum number of PDF annotation chunks to retrieve",
        ge=0,
        le=20,
    )
    include_patterns: bool = Field(
        default=True,
        description="Include developer pattern profile",
    )
    profile_id: Optional[str] = Field(
        None,
        description="CodingProfile ID to swap in. If set, fetches rules linked to this "
        "profile instead of the user's personal baseline. If omitted, uses "
        "the personal baseline (profile_id IS NULL).",
    )
    timeout_ms: int = Field(
        default=1000,
        description="Maximum time to wait for context assembly (milliseconds)",
        ge=100,
        le=5000,
    )


# ============================================================================
# Response Models - Intelligence Layer Results
# ============================================================================


class CodeChunk(BaseModel):
    """Single code chunk from semantic search"""

    chunk_id: str = Field(..., description="Unique chunk identifier")
    content: str = Field(..., description="Code content")
    file_path: str = Field(..., description="File path in repository")
    language: str = Field(..., description="Programming language")
    start_line: int = Field(..., description="Starting line number")
    end_line: int = Field(..., description="Ending line number")
    similarity_score: float = Field(
        ..., description="Semantic similarity score (0-1)", ge=0, le=1
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class GraphDependency(BaseModel):
    """Architectural dependency from GraphRAG"""

    source_chunk_id: str = Field(..., description="Source chunk ID")
    target_chunk_id: str = Field(..., description="Target chunk ID")
    relationship_type: str = Field(
        ..., description="Type of relationship (imports, calls, extends, etc.)"
    )
    weight: float = Field(..., description="Relationship strength (0-1)", ge=0, le=1)
    hops: int = Field(..., description="Number of hops from query entities", ge=1)


class DeveloperPattern(BaseModel):
    """Developer coding style and architectural preferences"""

    pattern_type: str = Field(
        ..., description="Type of pattern (style, architecture, error_handling, etc.)"
    )
    description: str = Field(..., description="Human-readable pattern description")
    examples: List[str] = Field(
        default_factory=list, description="Code examples demonstrating pattern"
    )
    frequency: float = Field(
        ..., description="How often this pattern appears (0-1)", ge=0, le=1
    )
    success_rate: Optional[float] = Field(
        None, description="Success rate if tracked (0-1)", ge=0, le=1
    )


class PDFAnnotation(BaseModel):
    """Research paper annotation linked to query concepts"""

    annotation_id: str = Field(..., description="Annotation identifier")
    pdf_title: str = Field(..., description="PDF document title")
    chunk_content: str = Field(..., description="Annotated text content")
    concept_tags: List[str] = Field(
        default_factory=list, description="Concept tags (OAuth, ML, Security, etc.)"
    )
    note: Optional[str] = Field(None, description="User annotation note")
    page_number: int = Field(..., description="Page number in PDF")
    relevance_score: float = Field(
        ..., description="Relevance to query (0-1)", ge=0, le=1
    )


# ============================================================================
# Assembled Context Response
# ============================================================================


class ContextAssemblyMetrics(BaseModel):
    """Performance metrics for context assembly"""

    total_time_ms: int = Field(..., description="Total assembly time (milliseconds)")
    semantic_search_ms: int = Field(
        ..., description="Semantic search time (milliseconds)"
    )
    graphrag_ms: int = Field(..., description="GraphRAG traversal time (milliseconds)")
    pattern_learning_ms: int = Field(
        ..., description="Pattern retrieval time (milliseconds)"
    )
    pdf_memory_ms: int = Field(
        ..., description="PDF annotation retrieval time (milliseconds)"
    )
    timeout_occurred: bool = Field(
        default=False, description="Whether any service timed out"
    )
    partial_results: bool = Field(
        default=False, description="Whether results are partial due to timeout"
    )


class AssembledContext(BaseModel):
    """Complete context assembled from all intelligence layers"""

    # Core query info
    query: str = Field(..., description="Original query")
    codebase: str = Field(..., description="Codebase identifier")

    # Intelligence layer results
    code_chunks: List[CodeChunk] = Field(
        default_factory=list, description="Relevant code chunks from semantic search"
    )
    graph_dependencies: List[GraphDependency] = Field(
        default_factory=list,
        description="Architectural dependencies from GraphRAG traversal",
    )
    developer_patterns: List[DeveloperPattern] = Field(
        default_factory=list,
        description="Developer coding style and architectural preferences",
    )
    pdf_annotations: List[PDFAnnotation] = Field(
        default_factory=list,
        description="Relevant research paper annotations",
    )

    # Metadata
    metrics: ContextAssemblyMetrics = Field(
        ..., description="Performance metrics for assembly"
    )
    warnings: List[str] = Field(
        default_factory=list, description="Warnings during assembly"
    )


class ContextRetrievalResponse(BaseModel):
    """Response for context retrieval request"""

    success: bool = Field(..., description="Whether context assembly succeeded")
    context: Optional[AssembledContext] = Field(
        None, description="Assembled context (null if failed)"
    )
    error: Optional[str] = Field(None, description="Error message if failed")

    # Formatted context for LLM consumption
    formatted_context: Optional[str] = Field(
        None,
        description="XML-formatted context ready for LLM consumption",
    )


# ============================================================================
# Context Formatting Templates
# ============================================================================


def format_context_for_llm(context: AssembledContext) -> str:
    """
    Format assembled context into XML structure for LLM parsing.

    Uses XML tags to create clear sections that Ronin can parse with zero ambiguity.
    """
    sections = []

    # Header
    sections.append(f"<context_assembly>")
    sections.append(f"<query>{context.query}</query>")
    sections.append(f"<codebase>{context.codebase}</codebase>")

    # Code chunks section
    if context.code_chunks:
        sections.append("<relevant_code>")
        for i, chunk in enumerate(context.code_chunks, 1):
            sections.append(f"  <chunk id='{chunk.chunk_id}' rank='{i}'>")
            sections.append(f"    <file>{chunk.file_path}</file>")
            sections.append(f"    <language>{chunk.language}</language>")
            sections.append(
                f"    <lines>{chunk.start_line}-{chunk.end_line}</lines>"
            )
            sections.append(
                f"    <similarity>{chunk.similarity_score:.3f}</similarity>"
            )
            sections.append(f"    <content><![CDATA[")
            sections.append(chunk.content)
            sections.append(f"    ]]></content>")
            sections.append(f"  </chunk>")
        sections.append("</relevant_code>")

    # Graph dependencies section
    if context.graph_dependencies:
        sections.append("<architectural_dependencies>")
        for dep in context.graph_dependencies:
            sections.append(
                f"  <dependency type='{dep.relationship_type}' "
                f"weight='{dep.weight:.3f}' hops='{dep.hops}'>"
            )
            sections.append(f"    <source>{dep.source_chunk_id}</source>")
            sections.append(f"    <target>{dep.target_chunk_id}</target>")
            sections.append(f"  </dependency>")
        sections.append("</architectural_dependencies>")

    # Developer patterns section
    if context.developer_patterns:
        sections.append("<developer_style>")
        for pattern in context.developer_patterns:
            sections.append(f"  <pattern type='{pattern.pattern_type}'>")
            sections.append(f"    <description>{pattern.description}</description>")
            sections.append(f"    <frequency>{pattern.frequency:.2f}</frequency>")
            if pattern.success_rate is not None:
                sections.append(
                    f"    <success_rate>{pattern.success_rate:.2f}</success_rate>"
                )
            if pattern.examples:
                sections.append(f"    <examples>")
                for example in pattern.examples[:3]:  # Limit to 3 examples
                    sections.append(f"      <example><![CDATA[{example}]]></example>")
                sections.append(f"    </examples>")
            sections.append(f"  </pattern>")
        sections.append("</developer_style>")

    # PDF annotations section
    if context.pdf_annotations:
        sections.append("<research_papers>")
        for annotation in context.pdf_annotations:
            sections.append(
                f"  <annotation id='{annotation.annotation_id}' "
                f"relevance='{annotation.relevance_score:.3f}'>"
            )
            sections.append(f"    <paper>{annotation.pdf_title}</paper>")
            sections.append(f"    <page>{annotation.page_number}</page>")
            sections.append(
                f"    <concepts>{', '.join(annotation.concept_tags)}</concepts>"
            )
            if annotation.note:
                sections.append(f"    <note>{annotation.note}</note>")
            sections.append(f"    <content><![CDATA[")
            sections.append(annotation.chunk_content)
            sections.append(f"    ]]></content>")
            sections.append(f"  </annotation>")
        sections.append("</research_papers>")

    # Metrics section
    sections.append("<assembly_metrics>")
    sections.append(f"  <total_time_ms>{context.metrics.total_time_ms}</total_time_ms>")
    sections.append(
        f"  <code_chunks_count>{len(context.code_chunks)}</code_chunks_count>"
    )
    sections.append(
        f"  <dependencies_count>{len(context.graph_dependencies)}</dependencies_count>"
    )
    sections.append(
        f"  <patterns_count>{len(context.developer_patterns)}</patterns_count>"
    )
    sections.append(
        f"  <annotations_count>{len(context.pdf_annotations)}</annotations_count>"
    )
    if context.metrics.partial_results:
        sections.append(
            f"  <warning>Partial results due to timeout</warning>"
        )
    sections.append("</assembly_metrics>")

    # Warnings
    if context.warnings:
        sections.append("<warnings>")
        for warning in context.warnings:
            sections.append(f"  <warning>{warning}</warning>")
        sections.append("</warnings>")

    sections.append("</context_assembly>")

    return "\n".join(sections)
