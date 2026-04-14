"""
Context Assembly Service

Orchestrates parallel fetching from all intelligence layers and assembles
context for Ronin LLM consumption.

Phase 5: Ronin Integration & Context Assembly
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from .context_schema import (
    AssembledContext,
    CodeChunk,
    ContextAssemblyMetrics,
    ContextRetrievalRequest,
    ContextRetrievalResponse,
    DeveloperPattern,
    format_context_for_llm,
    GraphDependency,
    PDFAnnotation,
)
from ..graph.service import GraphService
from ..patterns.model import DeveloperProfileRecord
from ..patterns.schema import DeveloperProfile
from ..pdf_ingestion.service import PDFIngestionService
from ..search.service import SearchService
from ...shared.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


# ============================================================================
# Context Assembly Service
# ============================================================================


class ContextAssemblyService:
    """
    Orchestrates parallel context retrieval from all intelligence layers.

    Implements graceful degradation: if one service times out, returns
    partial results from other services rather than failing entirely.
    """

    def __init__(
        self,
        db: Session,
        async_db: Optional[AsyncSession],
        embedding_service: EmbeddingService,
    ):
        self.db = db
        self.async_db = async_db
        self.embedding_service = embedding_service

        # Initialize service instances
        self.search_service = SearchService(db)
        self.graph_service = GraphService(db)
        # PDF service requires async_db - will be None if not available
        self.pdf_service = (
            PDFIngestionService(async_db, embedding_service) if async_db else None
        )

    async def assemble_context(
        self, request: ContextRetrievalRequest
    ) -> ContextRetrievalResponse:
        """
        Main entry point: assemble context from all intelligence layers.

        Uses asyncio.gather with timeout to fetch data in parallel.
        Implements graceful degradation if services timeout.
        """
        start_time = time.time()
        warnings: List[str] = []
        timeout_occurred = False

        try:
            # Convert timeout from ms to seconds
            timeout_seconds = request.timeout_ms / 1000.0

            # Launch all fetching tasks in parallel
            tasks = [
                self._fetch_semantic_search(request),
                self._fetch_graphrag(request),
                self._fetch_patterns(request),
                self._fetch_pdf_annotations(request),
            ]

            # Wait for all tasks with timeout
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Context assembly timeout after {timeout_seconds}s, "
                    "returning partial results"
                )
                timeout_occurred = True
                warnings.append(
                    f"Context assembly timed out after {timeout_seconds}s"
                )
                # Cancel pending tasks
                for task in tasks:
                    if not task.done():
                        task.cancel()
                # Get whatever results we have
                results = [None, None, None, None]

            # Unpack results (handle exceptions)
            code_result, graph_result, pattern_result, pdf_result = results

            # Extract data from results (handle None and exceptions)
            code_chunks, search_time = self._extract_result(
                code_result, "semantic_search", warnings
            )
            graph_deps, graph_time = self._extract_result(
                graph_result, "graphrag", warnings
            )
            patterns, pattern_time = self._extract_result(
                pattern_result, "pattern_learning", warnings
            )
            pdf_annotations, pdf_time = self._extract_result(
                pdf_result, "pdf_memory", warnings
            )

            # Calculate total time
            total_time_ms = int((time.time() - start_time) * 1000)

            # Build metrics
            metrics = ContextAssemblyMetrics(
                total_time_ms=total_time_ms,
                semantic_search_ms=search_time,
                graphrag_ms=graph_time,
                pattern_learning_ms=pattern_time,
                pdf_memory_ms=pdf_time,
                timeout_occurred=timeout_occurred,
                partial_results=timeout_occurred or len(warnings) > 0,
            )

            # Assemble context
            context = AssembledContext(
                query=request.query,
                codebase=request.codebase,
                code_chunks=code_chunks or [],
                graph_dependencies=graph_deps or [],
                developer_patterns=patterns or [],
                pdf_annotations=pdf_annotations or [],
                metrics=metrics,
                warnings=warnings,
            )

            # Format for LLM
            formatted = format_context_for_llm(context)

            logger.info(
                f"Context assembled: {len(code_chunks or [])} code chunks, "
                f"{len(graph_deps or [])} dependencies, "
                f"{len(patterns or [])} patterns, "
                f"{len(pdf_annotations or [])} annotations "
                f"in {total_time_ms}ms"
            )

            return ContextRetrievalResponse(
                success=True,
                context=context,
                error=None,
                formatted_context=formatted,
            )

        except Exception as e:
            logger.error(f"Context assembly failed: {e}", exc_info=True)
            return ContextRetrievalResponse(
                success=False,
                context=None,
                error=str(e),
                formatted_context=None,
            )

    # ========================================================================
    # Parallel Fetching Methods
    # ========================================================================

    async def _fetch_semantic_search(
        self, request: ContextRetrievalRequest
    ) -> Tuple[List[CodeChunk], int]:
        """Fetch relevant code chunks via semantic search"""
        start = time.time()

        try:
            # Use hybrid search for best results
            results = self.search_service.hybrid_search(
                query=request.query,
                limit=request.max_code_chunks,
                weight=0.6,  # Favor semantic over keyword
            )

            chunks = []
            for result in results:
                # Extract chunk data
                chunk = CodeChunk(
                    chunk_id=str(result.get("id", "")),
                    content=result.get("content", ""),
                    file_path=result.get("file_path", "unknown"),
                    language=result.get("language", "unknown"),
                    start_line=result.get("start_line", 0),
                    end_line=result.get("end_line", 0),
                    similarity_score=result.get("score", 0.0),
                    metadata=result.get("metadata", {}),
                )
                chunks.append(chunk)

            elapsed_ms = int((time.time() - start) * 1000)
            logger.info(f"Semantic search: {len(chunks)} chunks in {elapsed_ms}ms")

            return chunks, elapsed_ms

        except Exception as e:
            logger.error(f"Semantic search failed: {e}", exc_info=True)
            raise

    async def _fetch_graphrag(
        self, request: ContextRetrievalRequest
    ) -> Tuple[List[GraphDependency], int]:
        """Fetch architectural dependencies via GraphRAG traversal"""
        start = time.time()

        try:
            # Use GraphRAG search to find related chunks
            results = self.search_service.graphrag_search(
                query=request.query,
                max_hops=request.max_graph_hops,
                limit=request.max_code_chunks,
            )

            dependencies = []

            # Extract relationships from graph results
            for result in results:
                relationships = result.get("relationships", [])
                for rel in relationships:
                    dep = GraphDependency(
                        source_chunk_id=str(rel.get("source_id", "")),
                        target_chunk_id=str(rel.get("target_id", "")),
                        relationship_type=rel.get("type", "related"),
                        weight=rel.get("weight", 0.5),
                        hops=rel.get("hops", 1),
                    )
                    dependencies.append(dep)

            # Deduplicate by (source, target, type)
            seen = set()
            unique_deps = []
            for dep in dependencies:
                key = (dep.source_chunk_id, dep.target_chunk_id, dep.relationship_type)
                if key not in seen:
                    seen.add(key)
                    unique_deps.append(dep)

            elapsed_ms = int((time.time() - start) * 1000)
            logger.info(
                f"GraphRAG traversal: {len(unique_deps)} dependencies in {elapsed_ms}ms"
            )

            return unique_deps, elapsed_ms

        except Exception as e:
            logger.error(f"GraphRAG traversal failed: {e}", exc_info=True)
            raise

    async def _fetch_patterns(
        self, request: ContextRetrievalRequest
    ) -> Tuple[List[DeveloperPattern], int]:
        """
        Fetch coding patterns — either from a CodingProfile or from the
        user's personal baseline.

        Context Swapping Logic:
        - If request.profile_id is set, query ProposedRule WHERE
          profile_id = requested_id AND status = 'ACTIVE'.
        - If profile_id is omitted, fall back to the user's
          DeveloperProfileRecord (personal baseline).
        """
        start = time.time()

        try:
            if not request.include_patterns:
                return [], 0

            # ── Profile-based context swap ──────────────────────────
            if request.profile_id:
                return self._fetch_profile_rules(request.profile_id, start)

            # ── Personal baseline (original behavior) ───────────────
            if not request.user_id:
                return [], 0

            user_uuid = UUID(request.user_id)
            profile_record = (
                self.db.query(DeveloperProfileRecord)
                .filter(
                    DeveloperProfileRecord.user_id == user_uuid,
                    DeveloperProfileRecord.repository_url.contains(request.codebase),
                )
                .first()
            )

            if not profile_record:
                logger.info(f"No developer profile found for user {request.user_id}")
                return [], int((time.time() - start) * 1000)

            profile = DeveloperProfile(**profile_record.profile_data)
            patterns = self._extract_patterns_from_profile(profile)

            elapsed_ms = int((time.time() - start) * 1000)
            logger.info(f"Pattern learning: {len(patterns)} patterns in {elapsed_ms}ms")
            return patterns, elapsed_ms

        except Exception as e:
            logger.error(f"Pattern learning failed: {e}", exc_info=True)
            raise

    def _fetch_profile_rules(
        self, profile_id: str, start: float
    ) -> Tuple[List[DeveloperPattern], int]:
        """
        Query active ProposedRules linked to a specific CodingProfile and
        convert them to DeveloperPattern objects for context injection.
        """
        from app.database.models import ProposedRule, RuleStatus

        rules = (
            self.db.query(ProposedRule)
            .filter(
                ProposedRule.profile_id == profile_id,
                ProposedRule.status == RuleStatus.ACTIVE.value,
            )
            .order_by(ProposedRule.confidence.desc())
            .limit(20)
            .all()
        )

        patterns = []
        for rule in rules:
            example_code = rule.rule_schema.get("example_code", "") if rule.rule_schema else ""
            patterns.append(
                DeveloperPattern(
                    pattern_type=rule.rule_schema.get("pattern_type", "architectural_pattern") if rule.rule_schema else "architectural_pattern",
                    description=rule.rule_description,
                    examples=[example_code] if example_code else [],
                    frequency=rule.confidence,
                    success_rate=1.0,
                )
            )

        elapsed_ms = int((time.time() - start) * 1000)
        logger.info(
            f"Profile rules ({profile_id}): {len(patterns)} patterns in {elapsed_ms}ms"
        )
        return patterns, elapsed_ms

    @staticmethod
    def _extract_patterns_from_profile(profile: DeveloperProfile) -> List[DeveloperPattern]:
        """Extract DeveloperPattern list from a personal DeveloperProfile."""
        patterns: List[DeveloperPattern] = []

        if profile.style:
            if profile.style.async_patterns.async_density > 0.1:
                patterns.append(
                    DeveloperPattern(
                        pattern_type="async_style",
                        description=f"Prefers async/await style "
                        f"({profile.style.async_patterns.async_density:.0%} of functions)",
                        examples=[],
                        frequency=profile.style.async_patterns.async_density,
                    )
                )

            if profile.style.error_handling.exception_logging_style:
                patterns.append(
                    DeveloperPattern(
                        pattern_type="error_handling",
                        description=f"Error logging style: "
                        f"{profile.style.error_handling.exception_logging_style}",
                        examples=[],
                        frequency=1.0,
                    )
                )

        if profile.architecture:
            if profile.architecture.framework.framework:
                patterns.append(
                    DeveloperPattern(
                        pattern_type="framework",
                        description=f"Uses {profile.architecture.framework.framework} framework",
                        examples=[],
                        frequency=1.0,
                    )
                )

            if profile.architecture.detected_patterns:
                for arch_pattern in profile.architecture.detected_patterns[:5]:
                    patterns.append(
                        DeveloperPattern(
                            pattern_type="architectural_pattern",
                            description=arch_pattern,
                            examples=[],
                            frequency=0.8,
                        )
                    )

        if profile.git_analysis:
            for kept in profile.git_analysis.kept_patterns[:3]:
                patterns.append(
                    DeveloperPattern(
                        pattern_type="successful_pattern",
                        description=kept.get("description", ""),
                        examples=kept.get("examples", [])[:2],
                        frequency=kept.get("frequency", 0.5),
                        success_rate=1.0,
                    )
                )

            for abandoned in profile.git_analysis.abandoned_patterns[:2]:
                patterns.append(
                    DeveloperPattern(
                        pattern_type="avoided_pattern",
                        description=f"AVOID: {abandoned.get('description', '')}",
                        examples=abandoned.get("examples", [])[:1],
                        frequency=abandoned.get("frequency", 0.3),
                        success_rate=0.0,
                    )
                )

        return patterns

    async def _fetch_pdf_annotations(
        self, request: ContextRetrievalRequest
    ) -> Tuple[List[PDFAnnotation], int]:
        """Fetch relevant PDF annotations via concept matching"""
        start = time.time()

        try:
            if request.max_pdf_chunks == 0 or self.pdf_service is None:
                return [], 0

            # Use PDF service's graph traversal search
            results = await self.pdf_service.graph_traversal_search(
                query=request.query,
                max_hops=2,
                limit=request.max_pdf_chunks,
            )

            annotations = []
            for result in results:
                # Extract annotation data
                annotation = PDFAnnotation(
                    annotation_id=str(result.get("annotation_id", "")),
                    pdf_title=result.get("pdf_title", "Unknown"),
                    chunk_content=result.get("content", ""),
                    concept_tags=result.get("concept_tags", []),
                    note=result.get("note"),
                    page_number=result.get("page_number", 0),
                    relevance_score=result.get("score", 0.0),
                )
                annotations.append(annotation)

            elapsed_ms = int((time.time() - start) * 1000)
            logger.info(
                f"PDF memory: {len(annotations)} annotations in {elapsed_ms}ms"
            )

            return annotations, elapsed_ms

        except Exception as e:
            logger.error(f"PDF annotation retrieval failed: {e}", exc_info=True)
            raise

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _extract_result(
        self,
        result: Any,
        service_name: str,
        warnings: List[str],
    ) -> Tuple[Optional[Any], int]:
        """
        Extract data from service result, handling exceptions and None.

        Returns (data, elapsed_ms)
        """
        # Handle exception
        if isinstance(result, Exception):
            logger.warning(f"{service_name} failed: {result}")
            warnings.append(f"{service_name} failed: {str(result)}")
            return None, 0

        # Handle None (timeout)
        if result is None:
            logger.warning(f"{service_name} timed out")
            warnings.append(f"{service_name} timed out")
            return None, 0

        # Handle tuple result (data, elapsed_ms)
        if isinstance(result, tuple) and len(result) == 2:
            return result

        # Unexpected result format
        logger.warning(f"{service_name} returned unexpected format: {type(result)}")
        warnings.append(f"{service_name} returned unexpected format")
        return None, 0
