"""
Search Module Service

Unified search service consolidating all search functionality.

This service provides a single interface for:
- Full-text search (FTS5, PostgreSQL tsvector)
- Dense vector semantic search
- Sparse vector learned keyword search
- Hybrid search with RRF fusion
- ColBERT reranking
- Query-adaptive weighting

Architecture:
- Delegates to existing services for implementation
- Provides unified interface for module consumers
- Handles strategy selection and orchestration
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

# Import existing services (delayed import for AdvancedSearchService to avoid circular dependency)
from .hybrid_methods import pure_vector_search
from .rrf import ReciprocalRankFusionService
from .reranking import RerankingService
from .sparse_embeddings import SparseEmbeddingService

logger = logging.getLogger(__name__)


def _get_advanced_search_service():
    """Lazy import to avoid circular dependency."""
    from ...services.search_service import AdvancedSearchService

    return AdvancedSearchService


class SearchService:
    """
    Unified search service providing all search functionality.

    This service consolidates multiple search methods into a single interface:
    - Full-text search (FTS5, PostgreSQL)
    - Dense vector semantic search
    - Sparse vector learned keyword search
    - Hybrid search with RRF fusion
    - ColBERT reranking

    The service delegates to existing implementations while providing
    a clean, modular interface for the Search module.
    """

    def __init__(self, db: Session):
        """
        Initialize the search service.

        Args:
            db: Database session
        """
        self.db = db

    # ========================================================================
    # Main Search Methods
    # ========================================================================

    def search(self, query: Any) -> Tuple[List[Any], int, Any, Dict[str, str]]:
        """
        Execute search using the appropriate method based on query parameters.

        Args:
            query: SearchQuery object with search parameters

        Returns:
            Tuple of (resources, total, facets, snippets)
        """
        AdvancedSearchService = _get_advanced_search_service()
        return AdvancedSearchService.search(self.db, query)

    def hybrid_search(
        self, query: Any, hybrid_weight: float = 0.5
    ) -> Tuple[List[Any], int, Any, Dict[str, str]]:
        """
        Execute hybrid search combining FTS and vector similarity.

        Args:
            query: SearchQuery object
            hybrid_weight: Weight for fusion (0.0=keyword, 1.0=semantic)

        Returns:
            Tuple of (resources, total, facets, snippets)
        """
        AdvancedSearchService = _get_advanced_search_service()
        return AdvancedSearchService.hybrid_search(self.db, query, hybrid_weight)

    def three_way_hybrid_search(
        self, query: Any, enable_reranking: bool = True, adaptive_weighting: bool = True
    ) -> Tuple[List[Any], int, Any, Dict[str, str], Dict[str, Any]]:
        """
        Execute three-way hybrid search with RRF fusion and optional reranking.

        Combines FTS5, dense vectors, and sparse vectors using Reciprocal Rank
        Fusion with query-adaptive weighting and optional ColBERT reranking.

        Args:
            query: SearchQuery object
            enable_reranking: Whether to apply ColBERT reranking
            adaptive_weighting: Whether to use query-adaptive RRF weights

        Returns:
            Tuple of (resources, total, facets, snippets, metadata)
        """
        AdvancedSearchService = _get_advanced_search_service()
        return AdvancedSearchService.search_three_way_hybrid(
            self.db,
            query,
            enable_reranking=enable_reranking,
            adaptive_weighting=adaptive_weighting,
        )

    # ========================================================================
    # Component Services (for direct access if needed)
    # ========================================================================

    def get_rrf_service(self, k: int = 60) -> ReciprocalRankFusionService:
        """Get RRF service for result fusion."""
        return ReciprocalRankFusionService(k=k)

    def get_reranking_service(
        self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    ) -> RerankingService:
        """Get reranking service for ColBERT reranking."""
        return RerankingService(self.db, model_name=model_name)

    def get_sparse_embedding_service(
        self, model_name: str = "BAAI/bge-m3"
    ) -> SparseEmbeddingService:
        """Get sparse embedding service."""
        return SparseEmbeddingService(self.db, model_name=model_name)

    # ========================================================================
    # Parent-Child Retrieval
    # ========================================================================

    def parent_child_search(
        self, query: str, top_k: int = 10, context_window: int = 2, filters: dict = None
    ) -> List[dict]:
        """
        Execute parent-child retrieval strategy.

        Retrieves top-k chunks by embedding similarity, then expands to parent
        resources and surrounding chunks for context.

        Args:
            query: Search query text
            top_k: Number of chunks to retrieve
            context_window: Number of surrounding chunks to include (±N)
            filters: Optional filters for resources (type, quality_score, etc.)

        Returns:
            List of result dictionaries with:
            - chunk: Dict with chunk data
            - parent_resource: Dict with resource data
            - surrounding_chunks: List of dicts with chunk data
            - score: Similarity score
        """
        from ...database.models import DocumentChunk, Resource
        from ...shared.embeddings import EmbeddingService

        logger.info(
            f"Parent-child search: query='{query}', top_k={top_k}, context_window={context_window}"
        )

        # Generate query embedding
        try:
            embedding_service = EmbeddingService(self.db)
            query_embedding = embedding_service.generate_embedding(query)
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}")
            return []

        if not query_embedding:
            logger.error("Failed to generate query embedding")
            return []

        # Retrieve top-k chunks by embedding similarity
        # Note: This is a simplified implementation. In production, this would use:
        # - FAISS index for fast similarity search
        # - PostgreSQL pgvector extension
        # - Approximate nearest neighbor search

        # For now, we'll retrieve chunks and compute similarity in Python
        chunks_query = self.db.query(DocumentChunk).join(Resource)

        # Apply filters if provided
        if filters:
            if "resource_type" in filters:
                chunks_query = chunks_query.filter(
                    Resource.type == filters["resource_type"]
                )
            if "min_quality_score" in filters:
                chunks_query = chunks_query.filter(
                    Resource.quality_score >= filters["min_quality_score"]
                )

        all_chunks = chunks_query.all()

        # Compute similarity scores using actual embeddings
        chunk_scores = []
        for chunk in all_chunks:
            if chunk.embedding:
                # Use cosine similarity between query embedding and chunk embedding
                score = self._cosine_similarity(query_embedding, chunk.embedding)
                chunk_scores.append((chunk, score))
            else:
                # Fallback to keyword similarity if no embedding
                score = self._compute_similarity_score(query, chunk.content)
                chunk_scores.append((chunk, score))

        # Sort by score and take top-k
        chunk_scores.sort(key=lambda x: x[1], reverse=True)
        top_chunks = chunk_scores[:top_k]

        # Expand to parent resources and surrounding chunks
        results = []
        seen_resources = set()

        for chunk, score in top_chunks:
            # Get parent resource
            parent_resource = chunk.resource

            # Get surrounding chunks
            surrounding_chunks = self._get_surrounding_chunks(
                chunk.resource_id, chunk.chunk_index, context_window
            )

            # Deduplicate: if we've already included this resource, skip
            if parent_resource.id in seen_resources:
                continue

            seen_resources.add(parent_resource.id)

            # Convert ORM objects to dictionaries
            results.append(
                {
                    "chunk": {
                        "id": str(chunk.id),
                        "resource_id": str(chunk.resource_id),
                        "content": chunk.content,
                        "chunk_index": chunk.chunk_index,
                        "chunk_metadata": chunk.chunk_metadata,
                    },
                    "parent_resource": parent_resource,  # Will be converted by Pydantic
                    "surrounding_chunks": [
                        {
                            "id": str(sc.id),
                            "resource_id": str(sc.resource_id),
                            "content": sc.content,
                            "chunk_index": sc.chunk_index,
                            "chunk_metadata": sc.chunk_metadata,
                        }
                        for sc in surrounding_chunks
                    ],
                    "score": score,
                }
            )

        logger.info(f"Parent-child search returned {len(results)} results")
        return results

    def _get_surrounding_chunks(
        self, resource_id: str, chunk_index: int, context_window: int
    ) -> List:
        """
        Get surrounding chunks for context.

        Args:
            resource_id: Parent resource ID
            chunk_index: Index of the retrieved chunk
            context_window: Number of chunks to include before and after

        Returns:
            List of DocumentChunk objects
        """
        from ...database.models import DocumentChunk
        from sqlalchemy import and_

        # Calculate range
        start_index = max(0, chunk_index - context_window)
        end_index = chunk_index + context_window

        # Query surrounding chunks
        surrounding = (
            self.db.query(DocumentChunk)
            .filter(
                and_(
                    DocumentChunk.resource_id == resource_id,
                    DocumentChunk.chunk_index >= start_index,
                    DocumentChunk.chunk_index <= end_index,
                )
            )
            .order_by(DocumentChunk.chunk_index)
            .all()
        )

        return surrounding

    def _compute_similarity_score(self, query: str, text: str) -> float:
        """
        Compute similarity score between query and text.

        This is a simplified implementation for testing. In production, this would:
        - Use cosine similarity between embeddings
        - Leverage vector database (FAISS, pgvector)
        - Use approximate nearest neighbor search

        Args:
            query: Query text
            text: Document text

        Returns:
            Similarity score (0.0 to 1.0)
        """
        # Simple keyword overlap score
        query_words = set(query.lower().split())
        text_words = set(text.lower().split())

        if not query_words:
            return 0.0

        overlap = len(query_words & text_words)
        score = overlap / len(query_words)

        return min(score, 1.0)

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity score (-1.0 to 1.0, typically 0.0 to 1.0 for embeddings)
        """
        import numpy as np

        # Convert to numpy arrays
        v1 = np.array(vec1)
        v2 = np.array(vec2)

        # Compute cosine similarity
        dot_product = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = dot_product / (norm1 * norm2)

        # Clamp to [0, 1] range (embeddings are typically in this range)
        return max(0.0, min(1.0, float(similarity)))

    # ========================================================================
    # GraphRAG Retrieval
    # ========================================================================

    def graphrag_search(
        self,
        query: str,
        top_k: int = 10,
        max_hops: int = 2,
        relation_types: List[str] = None,
    ) -> List[dict]:
        """
        Execute GraphRAG retrieval strategy.

        Extracts entities from query, finds matching entities in knowledge graph,
        traverses relationships, and retrieves chunks associated with entities.

        Args:
            query: Search query text
            top_k: Number of results to return
            max_hops: Maximum graph traversal depth
            relation_types: Filter by specific relation types (e.g., ["SUPPORTS", "CONTRADICTS"])

        Returns:
            List of result dictionaries with:
            - chunk: Dict with chunk data
            - parent_resource: Dict with resource data
            - graph_path: List of dicts with graph path nodes
            - score: Combined embedding + graph weight score
        """
        from ...database.models import GraphEntity, GraphRelationship, DocumentChunk
        from sqlalchemy import or_

        logger.info(
            f"GraphRAG search: query='{query}', top_k={top_k}, max_hops={max_hops}"
        )

        # Extract entities from query (simplified - would use NER in production)
        query_entities = self._extract_entities_from_query(query)

        if not query_entities:
            logger.warning("No entities extracted from query")
            return []

        # Find matching entities in knowledge graph
        matching_entities = []
        for entity_name in query_entities:
            entities = (
                self.db.query(GraphEntity)
                .filter(GraphEntity.name.ilike(f"%{entity_name}%"))
                .all()
            )
            matching_entities.extend(entities)

        if not matching_entities:
            logger.warning("No matching entities found in knowledge graph")
            return []

        # Traverse relationships to find related entities
        related_entities = self._traverse_graph(
            matching_entities, max_hops=max_hops, relation_types=relation_types
        )

        # Retrieve chunks associated with entities via provenance
        chunk_scores = {}
        chunk_paths = {}
        chunk_entities = {}

        for entity, path in related_entities:
            # Find relationships that have this entity and provenance
            relationships = (
                self.db.query(GraphRelationship)
                .filter(
                    or_(
                        GraphRelationship.source_entity_id == entity.id,
                        GraphRelationship.target_entity_id == entity.id,
                    ),
                    GraphRelationship.provenance_chunk_id.isnot(None),
                )
                .all()
            )

            for rel in relationships:
                if rel.provenance_chunk_id:
                    chunk_id = rel.provenance_chunk_id

                    # Compute score combining graph weight and path length
                    path_length = len(path)
                    graph_score = rel.weight / (path_length + 1)  # Decay by path length

                    if (
                        chunk_id not in chunk_scores
                        or graph_score > chunk_scores[chunk_id]
                    ):
                        chunk_scores[chunk_id] = graph_score
                        chunk_paths[chunk_id] = path
                        chunk_entities[chunk_id] = entity

        # Retrieve chunks and sort by score
        results = []
        for chunk_id, score in sorted(
            chunk_scores.items(), key=lambda x: x[1], reverse=True
        )[:top_k]:
            chunk = (
                self.db.query(DocumentChunk)
                .filter(DocumentChunk.id == chunk_id)
                .first()
            )
            if chunk and chunk.resource:
                # Convert graph path to serializable format
                graph_path = []
                for rel in chunk_paths[chunk_id]:
                    source_entity = rel.source_entity
                    target_entity = rel.target_entity
                    graph_path.append(
                        {
                            "entity_id": str(source_entity.id),
                            "entity_name": source_entity.name,
                            "entity_type": source_entity.type,
                            "relation_type": rel.relation_type,
                            "weight": rel.weight,
                        }
                    )
                    # Add target entity as final node
                    if rel == chunk_paths[chunk_id][-1]:
                        graph_path.append(
                            {
                                "entity_id": str(target_entity.id),
                                "entity_name": target_entity.name,
                                "entity_type": target_entity.type,
                                "relation_type": None,
                                "weight": None,
                            }
                        )

                results.append(
                    {
                        "chunk": {
                            "id": str(chunk.id),
                            "resource_id": str(chunk.resource_id),
                            "content": chunk.content,
                            "chunk_index": chunk.chunk_index,
                            "chunk_metadata": chunk.chunk_metadata,
                        },
                        "parent_resource": chunk.resource,  # Will be converted by Pydantic
                        "surrounding_chunks": [],  # Not used in GraphRAG
                        "graph_path": graph_path,
                        "score": score,
                    }
                )

        logger.info(f"GraphRAG search returned {len(results)} results")
        return results

    def _extract_entities_from_query(self, query: str) -> List[str]:
        """
        Extract entity names from query.

        This is a simplified implementation. In production, this would use:
        - Named Entity Recognition (spaCy, BERT-NER)
        - Query parsing and entity linking
        - Coreference resolution

        Args:
            query: Query text

        Returns:
            List of entity names
        """
        # Simple heuristic: extract capitalized words and noun phrases
        words = query.split()
        entities = []

        for word in words:
            # Extract capitalized words (potential proper nouns)
            if word and word[0].isupper() and len(word) > 2:
                entities.append(word)

        # Also extract multi-word phrases (simplified)
        if len(words) >= 2:
            for i in range(len(words) - 1):
                if words[i][0].isupper() and words[i + 1][0].isupper():
                    entities.append(f"{words[i]} {words[i + 1]}")

        return entities if entities else [query]  # Fallback to full query

    def _traverse_graph(
        self, start_entities: List, max_hops: int = 2, relation_types: List[str] = None
    ) -> List[Tuple]:
        """
        Traverse knowledge graph from starting entities.

        Args:
            start_entities: List of GraphEntity objects to start from
            max_hops: Maximum traversal depth
            relation_types: Filter by specific relation types

        Returns:
            List of (entity, path) tuples where path is list of relationships
        """
        from ...database.models import GraphRelationship
        from sqlalchemy import or_

        visited = set()
        results = []
        queue = [(entity, []) for entity in start_entities]

        while queue:
            current_entity, path = queue.pop(0)

            if current_entity.id in visited:
                continue

            visited.add(current_entity.id)
            results.append((current_entity, path))

            # Stop if we've reached max hops
            if len(path) >= max_hops:
                continue

            # Find outgoing relationships
            query = self.db.query(GraphRelationship).filter(
                or_(
                    GraphRelationship.source_entity_id == current_entity.id,
                    GraphRelationship.target_entity_id == current_entity.id,
                )
            )

            # Filter by relation types if specified
            if relation_types:
                query = query.filter(
                    GraphRelationship.relation_type.in_(relation_types)
                )

            relationships = query.all()

            for rel in relationships:
                # Get the other entity
                if rel.source_entity_id == current_entity.id:
                    next_entity = rel.target_entity
                else:
                    next_entity = rel.source_entity

                if next_entity.id not in visited:
                    new_path = path + [rel]
                    queue.append((next_entity, new_path))

        return results

    # ========================================================================
    # Contradiction Discovery
    # ========================================================================

    def discover_contradictions(
        self, query: str = None, entity_id: str = None, top_k: int = 10
    ) -> List[dict]:
        """
        Discover contradictions in the knowledge graph.

        Filters relationships by CONTRADICTS relation_type and returns
        graph paths explaining contradictions.

        Args:
            query: Optional query to focus contradiction search
            entity_id: Optional entity ID to find contradictions for
            top_k: Number of contradictions to return

        Returns:
            List of contradiction dictionaries with:
            - source_entity: GraphEntity object
            - target_entity: GraphEntity object
            - relationship: GraphRelationship object
            - source_chunk: DocumentChunk object (if available)
            - target_chunk: DocumentChunk object (if available)
            - explanation: Text explaining the contradiction
        """
        from ...database.models import GraphEntity, GraphRelationship, DocumentChunk

        logger.info(
            f"Discovering contradictions: query='{query}', entity_id={entity_id}"
        )

        # Build query for CONTRADICTS relationships
        contradictions_query = self.db.query(GraphRelationship).filter(
            GraphRelationship.relation_type == "CONTRADICTS"
        )

        # If entity_id provided, filter by that entity
        if entity_id:
            from sqlalchemy import or_

            contradictions_query = contradictions_query.filter(
                or_(
                    GraphRelationship.source_entity_id == entity_id,
                    GraphRelationship.target_entity_id == entity_id,
                )
            )

        # If query provided, find relevant entities first
        if query:
            query_entities = self._extract_entities_from_query(query)
            entity_ids = []

            for entity_name in query_entities:
                entities = (
                    self.db.query(GraphEntity)
                    .filter(GraphEntity.name.ilike(f"%{entity_name}%"))
                    .all()
                )
                entity_ids.extend([e.id for e in entities])

            if entity_ids:
                from sqlalchemy import or_

                contradictions_query = contradictions_query.filter(
                    or_(
                        GraphRelationship.source_entity_id.in_(entity_ids),
                        GraphRelationship.target_entity_id.in_(entity_ids),
                    )
                )

        # Execute query and limit results
        contradictions = (
            contradictions_query.order_by(GraphRelationship.weight.desc())
            .limit(top_k)
            .all()
        )

        # Build result objects
        results = []
        for rel in contradictions:
            source_entity = rel.source_entity
            target_entity = rel.target_entity

            # Get source chunk if available
            source_chunk = None
            if rel.provenance_chunk_id:
                source_chunk = (
                    self.db.query(DocumentChunk)
                    .filter(DocumentChunk.id == rel.provenance_chunk_id)
                    .first()
                )

            # Build explanation
            explanation = f"{source_entity.name} contradicts {target_entity.name}"
            if source_chunk:
                explanation += f" (found in chunk {source_chunk.chunk_index})"

            results.append(
                {
                    "source_entity": source_entity,
                    "target_entity": target_entity,
                    "relationship": rel,
                    "source_chunk": source_chunk,
                    "explanation": explanation,
                }
            )

        logger.info(f"Found {len(results)} contradictions")
        return results

    # ========================================================================
    # Question-Based Retrieval (Reverse HyDE)
    # ========================================================================

    def question_search(
        self, query: str, top_k: int = 10, hybrid_mode: bool = False
    ) -> List[dict]:
        """
        Execute question-based retrieval using Reverse HyDE.

        Matches user query against synthetic question embeddings and retrieves
        chunks associated with matching questions.

        Args:
            query: User query text
            top_k: Number of results to return
            hybrid_mode: If True, combine with semantic search

        Returns:
            List of result dictionaries with:
            - chunk: DocumentChunk object
            - matching_question: SyntheticQuestion object
            - score: Question similarity score
        """
        from ...database.models import SyntheticQuestion
        from ...shared.embeddings import EmbeddingService

        logger.info(
            f"Question search: query='{query}', top_k={top_k}, hybrid={hybrid_mode}"
        )

        # Generate query embedding
        embedding_service = EmbeddingService(self.db)
        query_embedding = embedding_service.generate_embedding(query)

        if not query_embedding:
            logger.error("Failed to generate query embedding")
            return []

        # Retrieve all synthetic questions
        # In production, this would use vector similarity search
        all_questions = self.db.query(SyntheticQuestion).all()

        # Compute similarity scores
        question_scores = []
        for question in all_questions:
            # In production, question embeddings would be stored and indexed
            # For now, use text similarity
            score = self._compute_similarity_score(query, question.question_text)
            question_scores.append((question, score))

        # Sort by score and take top-k
        question_scores.sort(key=lambda x: x[1], reverse=True)
        top_questions = question_scores[:top_k]

        # Retrieve chunks associated with matching questions
        results = []
        seen_chunks = set()

        for question, score in top_questions:
            chunk = question.chunk

            # Deduplicate chunks
            if chunk.id in seen_chunks:
                continue

            seen_chunks.add(chunk.id)

            results.append(
                {"chunk": chunk, "matching_question": question, "score": score}
            )

        # If hybrid mode, combine with semantic search
        if hybrid_mode:
            semantic_results = self.parent_child_search(query, top_k=top_k)

            # Merge results (simple approach - would use RRF in production)
            for sem_result in semantic_results:
                chunk = sem_result["chunk"]
                if chunk.id not in seen_chunks:
                    results.append(
                        {
                            "chunk": chunk,
                            "matching_question": None,
                            "score": sem_result["score"] * 0.5,  # Weight semantic lower
                        }
                    )

            # Re-sort by score
            results.sort(key=lambda x: x["score"], reverse=True)
            results = results[:top_k]

        logger.info(f"Question search returned {len(results)} results")
        return results

    # ========================================================================
    # Utility Methods
    # ========================================================================

    @staticmethod
    def parse_search_query(text: str) -> str:
        """
        Parse input text into FTS5 MATCH syntax.

        Args:
            text: Raw search query text

        Returns:
            Parsed query string for FTS5
        """
        AdvancedSearchService = _get_advanced_search_service()
        return AdvancedSearchService.parse_search_query(text)

    @staticmethod
    def generate_snippets(text: str, query: str) -> str:
        """
        Generate highlighted snippet from text.

        Args:
            text: Source text
            query: Search query for highlighting

        Returns:
            Snippet with highlighted matches
        """
        AdvancedSearchService = _get_advanced_search_service()
        return AdvancedSearchService.generate_snippets(text, query)

    @staticmethod
    def analyze_query(query: str) -> Dict[str, Any]:
        """
        Analyze query characteristics for adaptive weighting.

        Args:
            query: Search query text

        Returns:
            Dictionary with query characteristics
        """
        AdvancedSearchService = _get_advanced_search_service()
        return AdvancedSearchService._analyze_query(query)


# ============================================================================
# Strategy Classes (for internal use)
# ============================================================================


class FTSSearchStrategy:
    """Strategy for FTS5 keyword search."""

    def __init__(self, db: Session):
        self.db = db

    def search(self, query: str, limit: int = 100) -> List[Tuple[str, float]]:
        """Execute FTS5 search and return (resource_id, score) tuples."""
        # Delegate to AdvancedSearchService
        AdvancedSearchService = _get_advanced_search_service()
        parsed_query = AdvancedSearchService.parse_search_query(query)
        items, _, scores, _ = AdvancedSearchService.fts_search(
            self.db, parsed_query, None, limit=limit, offset=0
        )
        return [(str(item.id), scores.get(str(item.id), 1.0)) for item in items]


class VectorSearchStrategy:
    """Strategy for dense vector semantic search."""

    def __init__(self, db: Session):
        self.db = db

    def search(self, query: str, limit: int = 100) -> List[Tuple[str, float]]:
        """Execute dense vector search and return (resource_id, score) tuples."""
        # Use pure_vector_search from hybrid_methods
        from .schema import SearchQuery

        AdvancedSearchService = _get_advanced_search_service()
        search_query = SearchQuery(text=query, limit=limit, offset=0)
        items, _, _, _ = pure_vector_search(
            self.db, search_query, AdvancedSearchService
        )
        # Return with similarity scores (would need to compute)
        return [(str(item.id), 1.0) for item in items]


class HybridSearchStrategy:
    """Strategy for hybrid search combining multiple methods."""

    def __init__(self, db: Session):
        self.db = db
        self.rrf_service = ReciprocalRankFusionService(k=60)

    def search(
        self,
        query: str,
        enable_reranking: bool = True,
        adaptive_weighting: bool = True,
        limit: int = 20,
    ) -> Tuple[List[Any], Dict[str, Any]]:
        """
        Execute hybrid search with RRF fusion.

        Returns:
            Tuple of (resources, metadata)
        """
        from ...schemas.search import SearchQuery

        search_query = SearchQuery(text=query, limit=limit, offset=0)

        AdvancedSearchService = _get_advanced_search_service()
        resources, total, facets, snippets, metadata = (
            AdvancedSearchService.search_three_way_hybrid(
                self.db,
                search_query,
                enable_reranking=enable_reranking,
                adaptive_weighting=adaptive_weighting,
            )
        )

        return resources, metadata


# Synthetic Question Service for Reverse HyDE
class SyntheticQuestionService:
    """
    Service for generating synthetic questions from document chunks.

    Implements Reverse HyDE (Hypothetical Document Embeddings) by generating
    questions that each chunk could answer. These questions are embedded and
    used for question-based retrieval.

    Configuration:
    - SYNTHETIC_QUESTIONS_ENABLED: Enable/disable question generation
    - QUESTIONS_PER_CHUNK: Number of questions to generate per chunk (1-3)
    - QUESTION_GENERATION_MODEL: LLM model to use (e.g., "gpt-3.5-turbo")
    """

    def __init__(self, db: Session, ai_service=None, embedding_service=None):
        """
        Initialize the synthetic question service.

        Args:
            db: Database session
            ai_service: AI service for LLM-based question generation
            embedding_service: Service for generating question embeddings
        """
        self.db = db
        self.ai_service = ai_service
        self.embedding_service = embedding_service

        # Configuration (would come from settings in production)
        self.enabled = True  # SYNTHETIC_QUESTIONS_ENABLED
        self.questions_per_chunk = 2  # QUESTIONS_PER_CHUNK
        self.model_name = "gpt-3.5-turbo"  # QUESTION_GENERATION_MODEL

        logger.info(f"SyntheticQuestionService initialized (enabled={self.enabled})")

    def generate_questions(self, chunk_content: str, chunk_id: str) -> List[dict]:
        """
        Generate synthetic questions for a chunk.

        Uses prompt engineering to generate specific, relevant questions
        that the chunk content could answer.

        Args:
            chunk_content: Text content of the chunk
            chunk_id: ID of the source chunk

        Returns:
            List of question dictionaries with 'question_text', 'chunk_id',
            and optionally 'embedding_id' keys
        """
        if not self.enabled:
            logger.debug("Synthetic question generation is disabled")
            return []

        if not chunk_content or not chunk_content.strip():
            return []

        # Generate questions using LLM or heuristics
        questions = self._generate_questions_heuristic(chunk_content)

        # Limit to configured number
        questions = questions[: self.questions_per_chunk]

        # Generate embeddings for questions
        questions_with_embeddings = []
        for question_text in questions:
            question_dict = {"question_text": question_text, "chunk_id": chunk_id}

            # Generate embedding if service available
            if self.embedding_service:
                try:
                    embedding = self.embedding_service.generate_embedding(question_text)
                    if embedding:
                        question_dict["embedding_id"] = self._store_embedding(embedding)
                except Exception as e:
                    logger.error(f"Error generating embedding for question: {e}")

            questions_with_embeddings.append(question_dict)

        return questions_with_embeddings

    def _generate_questions_heuristic(self, text: str) -> List[str]:
        """
        Generate questions using heuristic rules.

        This is a simplified implementation. In production, this would use:
        - LLM prompting (GPT-3.5/4) to generate natural questions
        - Template-based question generation
        - Question quality filtering

        Args:
            text: Chunk content

        Returns:
            List of question strings
        """
        questions = []

        # Simple heuristic: generate questions based on content patterns
        text_lower = text.lower()

        # Pattern 1: If text defines something, ask "What is X?"
        if "is a" in text_lower or "is an" in text_lower:
            # Extract the subject (simplified)
            sentences = text.split(".")
            for sentence in sentences[:2]:  # Check first 2 sentences
                if "is a" in sentence.lower() or "is an" in sentence.lower():
                    words = sentence.split()
                    if len(words) > 2:
                        subject = words[0]
                        questions.append(f"What is {subject}?")
                        break

        # Pattern 2: If text describes a process, ask "How does X work?"
        if any(
            word in text_lower
            for word in ["process", "method", "algorithm", "technique"]
        ):
            questions.append("How does this process work?")

        # Pattern 3: If text mentions benefits/advantages, ask "What are the benefits?"
        if any(word in text_lower for word in ["benefit", "advantage", "improve"]):
            questions.append("What are the benefits of this approach?")

        # Pattern 4: Generic question based on content
        if not questions:
            # Extract first few words as topic
            words = text.split()[:5]
            topic = " ".join(words)
            questions.append(f"What does this text discuss about {topic}?")

        return questions

    def _generate_questions_llm(self, text: str) -> List[str]:
        """
        Generate questions using LLM.

        This would use the AI service to prompt an LLM to generate
        high-quality questions.

        Args:
            text: Chunk content

        Returns:
            List of question strings
        """
        if not self.ai_service:
            return self._generate_questions_heuristic(text)

        # In production, this would use LLM prompting:
        # prompt = f"""Generate {self.questions_per_chunk} specific questions that the following text could answer:
        #
        # {text}
        #
        # Questions:"""
        #
        # response = self.ai_service.generate(prompt, model=self.model_name)
        # questions = parse_questions_from_response(response)

        # For now, fall back to heuristic
        return self._generate_questions_heuristic(text)

    def _store_embedding(self, embedding: List[float]) -> str:
        """
        Store an embedding in the database.

        Args:
            embedding: Vector embedding

        Returns:
            Embedding ID
        """
        # In production, this would store the embedding in the database
        # For now, return a placeholder ID
        import uuid

        return str(uuid.uuid4())
