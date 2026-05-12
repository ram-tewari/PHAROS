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

import heapq
import logging
from typing import Any, Dict, List, Optional, Tuple

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
        self,
        query: str,
        top_k: int = 10,
        context_window: int = 2,
        filters: Optional[dict] = None,
    ) -> List[dict]:
        """
        Vector-rank resources, then load a representative chunk + neighbors
        for each, with the parent Resource eagerly joined.

        Returns dicts where `chunk`, `parent_resource`, and entries in
        `surrounding_chunks` are ORM objects (not dicts) so callers can
        read every field — including github_uri, start_line, end_line,
        symbol_name, etc. — without a second round-trip.
        """
        from sqlalchemy import select, text as _sql
        from sqlalchemy.orm import selectinload

        from ...database.models import DocumentChunk

        logger.info(
            "parent_child_search: query=%r, top_k=%d, context_window=%d",
            query, top_k, context_window,
        )

        query_embedding = self._embed_query(query)
        if not query_embedding:
            return []

        embedding_str = f"[{','.join(map(str, query_embedding))}]"
        params: Dict[str, Any] = {"embedding": embedding_str, "top_k": top_k}
        where = [
            "r.embedding IS NOT NULL",
            "EXISTS (SELECT 1 FROM document_chunks dc WHERE dc.resource_id = r.id)",
            "(r.is_stale IS NULL OR r.is_stale = FALSE)",
        ]
        if filters:
            if "resource_type" in filters:
                where.append("r.type = :resource_type")
                params["resource_type"] = filters["resource_type"]
            if "min_quality_score" in filters:
                where.append("r.quality_score >= :min_quality_score")
                params["min_quality_score"] = filters["min_quality_score"]

        # Stage 1: pgvector rank at resource level (HNSW on r.embedding).
        # tests/ penalty: see commit history — keeps test modules reachable
        # without crowding out the real implementations.
        rank_sql = (
            "SELECT r.id::text AS resource_id, "
            "(r.embedding <=> CAST(:embedding AS vector)) "
            "+ CASE WHEN r.title ~ '(/|\\\\)tests(/|\\\\)' THEN 0.10 ELSE 0 END "
            "AS distance "
            "FROM resources r "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY distance ASC LIMIT :top_k"
        )
        try:
            ranked = self.db.execute(_sql(rank_sql), params).fetchall()
        except Exception as exc:
            logger.error("pgvector search failed: %s", exc, exc_info=True)
            return []
        if not ranked:
            logger.info("parent_child_search returned 0 results")
            return []

        distance_by_rid: Dict[str, float] = {row[0]: float(row[1]) for row in ranked}
        resource_ids = list(distance_by_rid.keys())

        # Stage 2: SQLAlchemy 2.0 select with selectinload — chunks + parent
        # Resource in one logical fetch (selectinload runs a second IN-list
        # query, cheap, no row-explosion vs joinedload's LEFT OUTER JOIN).
        stmt = (
            select(DocumentChunk)
            .options(selectinload(DocumentChunk.resource))
            .where(DocumentChunk.resource_id.in_(resource_ids))
            .order_by(DocumentChunk.resource_id, DocumentChunk.chunk_index)
        )
        chunks_by_rid: Dict[str, list] = {}
        try:
            for chunk in self.db.execute(stmt).scalars().all():
                chunks_by_rid.setdefault(str(chunk.resource_id), []).append(chunk)
        except Exception as exc:
            logger.error("Chunk eager-load failed: %s", exc, exc_info=True)
            return []

        # Stage 3: pick a representative chunk per resource.
        # Without chunk-level embeddings, do a cheap text-overlap re-rank on
        # semantic_summary so we don't always return chunk_index=0 (imports).
        query_terms = {t.lower() for t in query.split() if len(t) > 2}

        def _score(chunk) -> tuple[int, int]:
            summary = (chunk.semantic_summary or "").lower()
            overlap = sum(1 for t in query_terms if t in summary)
            ast_bonus = 1 if (chunk.ast_node_type in {"function", "class", "method"}) else 0
            return (overlap, ast_bonus)

        results: List[dict] = []
        for rid in resource_ids:
            chunks = chunks_by_rid.get(rid)
            if not chunks:
                continue
            representative = max(chunks, key=_score) if query_terms else chunks[0]
            parent_resource = representative.resource
            if parent_resource is None:
                continue

            idx = representative.chunk_index
            surrounding = [
                c for c in chunks
                if c.id != representative.id
                and idx - context_window <= c.chunk_index <= idx + context_window
            ]

            # Cosine distance ∈ [0, 2] → similarity clamped to [0, 1].
            score = max(0.0, 1.0 - distance_by_rid[rid])

            results.append({
                "chunk": representative,
                "parent_resource": parent_resource,
                "surrounding_chunks": surrounding,
                "score": score,
            })

        logger.info("parent_child_search → %d results", len(results))
        return results

    def parent_child_search_json(
        self,
        query: str,
        top_k: int = 10,
        context_window: int = 2,
    ) -> str:
        """Memory-frugal parent-child retrieval. Postgres builds the response
        body via json_build_object / json_agg and returns ONE text column;
        Python only holds a single str. Bypasses ORM and Pydantic entirely.

        Returns:
            JSON-encoded string ready to splice into a fastapi.Response.
            Shape: '[{score, chunk, parent_resource, surrounding_chunks, graph_path}, ...]'
            On empty result returns the literal '[]'.
        """
        from sqlalchemy import text as _sql

        query_embedding = self._embed_query(query)
        if not query_embedding:
            return "[]"

        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
        params: Dict[str, Any] = {
            "embedding": embedding_str,
            "top_k": top_k,
            "ctx": context_window,
        }

        sql = """
        WITH ranked AS (
            SELECT r.id AS resource_id,
                   (r.embedding <=> CAST(:embedding AS vector))
                   + CASE WHEN r.title ~ '(/|\\\\)tests(/|\\\\)' THEN 0.10 ELSE 0 END
                     AS distance
            FROM resources r
            WHERE r.embedding IS NOT NULL
              AND (r.is_stale IS NULL OR r.is_stale = FALSE)
              AND EXISTS (
                  SELECT 1 FROM document_chunks dc
                  WHERE dc.resource_id = r.id
              )
            ORDER BY distance ASC
            LIMIT :top_k
        ),
        representative AS (
            SELECT DISTINCT ON (dc.resource_id)
                   dc.id            AS chunk_id,
                   dc.resource_id   AS resource_id,
                   dc.chunk_index   AS chunk_index
            FROM document_chunks dc
            JOIN ranked rk ON dc.resource_id = rk.resource_id
            ORDER BY dc.resource_id,
                     CASE WHEN dc.ast_node_type IN ('function','class','method')
                          THEN 0 ELSE 1 END,
                     dc.chunk_index
        ),
        surrounding AS (
            SELECT rep.chunk_id AS rep_id,
                   json_agg(
                       json_build_object(
                           'id',               dc.id::text,
                           'resource_id',      dc.resource_id::text,
                           'chunk_index',      dc.chunk_index,
                           'content',          dc.content,
                           'chunk_metadata',   dc.chunk_metadata,
                           'symbol_name',      dc.symbol_name,
                           'ast_node_type',    dc.ast_node_type,
                           'semantic_summary', dc.semantic_summary,
                           'file_name',        split_part(dc.github_uri, '/', -1),
                           'github_uri',       dc.github_uri,
                           'branch_reference', dc.branch_reference,
                           'start_line',       dc.start_line,
                           'end_line',         dc.end_line,
                           'code',             NULL,
                           'source',           NULL,
                           'cache_hit',        NULL
                       ) ORDER BY dc.chunk_index
                   ) AS surrounding_json
            FROM representative rep
            JOIN document_chunks dc
              ON dc.resource_id = rep.resource_id
             AND dc.id <> rep.chunk_id
             AND dc.chunk_index BETWEEN rep.chunk_index - :ctx
                                    AND rep.chunk_index + :ctx
            GROUP BY rep.chunk_id
        )
        SELECT COALESCE(
          json_agg(payload ORDER BY distance ASC)::text,
          '[]'
        ) AS body
        FROM (
            SELECT rk.distance,
                   json_build_object(
                       'score', GREATEST(0.0, 1.0 - rk.distance),
                       'chunk', json_build_object(
                           'id',               dc.id::text,
                           'resource_id',      dc.resource_id::text,
                           'chunk_index',      dc.chunk_index,
                           'content',          dc.content,
                           'chunk_metadata',   dc.chunk_metadata,
                           'symbol_name',      dc.symbol_name,
                           'ast_node_type',    dc.ast_node_type,
                           'semantic_summary', dc.semantic_summary,
                           'file_name',        split_part(dc.github_uri, '/', -1),
                           'github_uri',       dc.github_uri,
                           'branch_reference', dc.branch_reference,
                           'start_line',       dc.start_line,
                           'end_line',         dc.end_line,
                           'code',             NULL,
                           'source',           NULL,
                           'cache_hit',        NULL
                       ),
                       'parent_resource', json_build_object(
                           'id',                      r.id::text,
                           'title',                   r.title,
                           'description',             r.description,
                           'type',                    r.type,
                           'language',                r.language,
                           'source',                  r.source,
                           'url',                     r.source,
                           'subject',                 r.subject,
                           'relation',                r.relation,
                           'quality_score',           r.quality_score,
                           'read_status',             r.read_status,
                           'ingestion_status',        r.ingestion_status,
                           'ingestion_error',         r.ingestion_error,
                           'ingestion_started_at',    r.ingestion_started_at,
                           'ingestion_completed_at',  r.ingestion_completed_at,
                           'created_at',              r.created_at,
                           'updated_at',              r.updated_at
                       ),
                       'surrounding_chunks', COALESCE(s.surrounding_json, '[]'::json),
                       'graph_path',         '[]'::json
                   ) AS payload
            FROM ranked rk
            JOIN representative rep ON rep.resource_id = rk.resource_id
            JOIN document_chunks dc ON dc.id = rep.chunk_id
            JOIN resources r       ON r.id  = dc.resource_id
            LEFT JOIN surrounding s ON s.rep_id = rep.chunk_id
        ) inner_q
        """

        try:
            row = self.db.execute(_sql(sql), params).first()
        except Exception as exc:
            logger.error("parent_child_search_json failed: %s", exc, exc_info=True)
            return "[]"

        return row[0] if row and row[0] else "[]"

    def _embed_query(self, query: str) -> Optional[List[float]]:
        """Edge-or-local query embedding, factored out so other strategies
        can reuse it without duplicating the CLOUD-mode branching."""
        import os

        if os.getenv("MODE") == "CLOUD":
            import httpx
            edge_url = os.getenv("EDGE_EMBEDDING_URL", "").rstrip("/")
            if not edge_url:
                logger.error("EDGE_EMBEDDING_URL not configured in CLOUD mode")
                return None
            try:
                # 30s tolerates Render cold-starts and bursts where the edge
                # /embed endpoint is queued behind heavy ingestion.
                resp = httpx.post(
                    f"{edge_url}/embed", json={"text": query}, timeout=30.0
                )
                resp.raise_for_status()
                return resp.json().get("embedding")
            except Exception as exc:
                logger.error("Edge embedding service unreachable: %s", exc)
                return None

        try:
            from ...shared.embeddings import EmbeddingService
            return EmbeddingService(self.db).generate_embedding(query)
        except Exception as exc:
            logger.error("Local embedding failed: %s", exc)
            return None

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

        # Retrieve chunks; top-K via heap (O(N log K)).
        results = []
        for chunk_id, score in heapq.nlargest(
            top_k, chunk_scores.items(), key=lambda x: x[1]
        ):
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

        # Top-K via size-K min-heap: O(N log K) instead of O(N log N).
        top_questions = heapq.nlargest(top_k, question_scores, key=lambda x: x[1])

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
