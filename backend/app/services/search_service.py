"""
Advanced Search Service

Legacy service for backward compatibility.
Provides basic search functionality.
"""

from typing import Any, Dict, List, Tuple
import time
import json
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import text, or_

from ..database.models import Resource
from ..modules.search.rrf import ReciprocalRankFusionService
from ..modules.search.reranking import RerankingService
from ..modules.search.sparse_embeddings import SparseEmbeddingService
from ..shared.embeddings import EmbeddingService


class AdvancedSearchService:
    """
    Advanced search service providing search functionality.

    This is a minimal implementation for backward compatibility.
    """

    @staticmethod
    def search(db: Session, query: Any) -> Tuple[List[Any], int, Any, Dict[str, str]]:
        """
        Execute search.

        Args:
            db: Database session
            query: Search query object

        Returns:
            Tuple of (resources, total, facets, snippets)
        """
        # Minimal implementation - returns empty results
        return [], 0, None, {}

    @staticmethod
    def hybrid_search(
        db: Session, query: Any, hybrid_weight: float = 0.5
    ) -> Tuple[List[Any], int, Any, Dict[str, str]]:
        """
        Execute hybrid search.

        Args:
            db: Database session
            query: Search query object
            hybrid_weight: Weight for fusion

        Returns:
            Tuple of (resources, total, facets, snippets)
        """
        return [], 0, None, {}

    @staticmethod
    def search_three_way_hybrid(
        db: Session,
        query: Any,
        enable_reranking: bool = True,
        adaptive_weighting: bool = True,
    ) -> Tuple[List[Any], int, Any, Dict[str, str], Dict[str, Any]]:
        """
        Execute three-way hybrid search combining FTS5, dense vectors, and sparse vectors.

        This method implements state-of-the-art search by:
        1. Executing three retrieval methods in parallel (FTS5, dense, sparse)
        2. Merging results using Reciprocal Rank Fusion (RRF)
        3. Applying query-adaptive weighting based on query characteristics
        4. Optionally reranking top results using ColBERT cross-encoder

        Args:
            db: Database session
            query: Search query object with text, limit, offset
            enable_reranking: Whether to apply ColBERT reranking
            adaptive_weighting: Whether to use query-adaptive RRF weights

        Returns:
            Tuple of (resources, total, facets, snippets, metadata)
            - resources: List of Resource objects ranked by relevance
            - total: Total number of results
            - facets: Facet aggregations (None for now)
            - snippets: Dict mapping resource_id to highlighted snippet
            - metadata: Dict with latency_ms, method_contributions, weights_used
        """
        start_time = time.time()

        query_text = query.text if hasattr(query, "text") else str(query)
        limit = query.limit if hasattr(query, "limit") else 20
        offset = query.offset if hasattr(query, "offset") else 0

        # Step 1: Execute FTS5 search (100 candidates)
        fts_start = time.time()
        fts_results = AdvancedSearchService._execute_fts_search(
            db, query_text, limit=100
        )
        fts_time = (time.time() - fts_start) * 1000

        # Step 2: Execute dense vector search (100 candidates)
        dense_start = time.time()
        dense_results = AdvancedSearchService._execute_dense_search(
            db, query_text, limit=100
        )
        dense_time = (time.time() - dense_start) * 1000

        # Step 3: Execute sparse vector search (100 candidates)
        sparse_start = time.time()
        sparse_results = AdvancedSearchService._execute_sparse_search(
            db, query_text, limit=100
        )
        sparse_time = (time.time() - sparse_start) * 1000

        # Step 4: Apply query-adaptive weighting
        if adaptive_weighting:
            weights = AdvancedSearchService._compute_adaptive_weights(query_text)
        else:
            weights = [1.0 / 3, 1.0 / 3, 1.0 / 3]  # Equal weights

        # Step 5: Merge with RRF
        rrf_start = time.time()
        rrf_service = ReciprocalRankFusionService(k=60)
        merged_results = rrf_service.fuse(
            [fts_results, dense_results, sparse_results], weights=weights
        )
        rrf_time = (time.time() - rrf_start) * 1000

        # Step 6: Optionally rerank top candidates
        if enable_reranking and len(merged_results) > 0:
            rerank_start = time.time()
            reranking_service = RerankingService(db)
            merged_results = reranking_service.rerank(query_text, merged_results[:100])
            rerank_time = (time.time() - rerank_start) * 1000
        else:
            rerank_time = 0.0

        # Recover from any aborted transaction before issuing ORM queries
        try:
            db.rollback()
        except Exception:
            pass

        # Step 7: Fetch resources and apply pagination
        resource_ids = [rid for rid, _ in merged_results[offset : offset + limit]]

        if not resource_ids:
            total_latency = (time.time() - start_time) * 1000
            metadata = {
                "latency_ms": total_latency,
                "method_contributions": {
                    "fts5": len(fts_results),
                    "dense": len(dense_results),
                    "sparse": len(sparse_results),
                },
                "weights_used": weights,
                "timing": {
                    "fts5_ms": fts_time,
                    "dense_ms": dense_time,
                    "sparse_ms": sparse_time,
                    "rrf_ms": rrf_time,
                    "rerank_ms": rerank_time,
                },
            }
            return [], 0, None, {}, metadata

        # Fetch resources maintaining order
        resources = db.query(Resource).filter(Resource.id.in_(resource_ids)).all()
        id_to_resource = {str(r.id): r for r in resources}
        ordered_resources = [
            id_to_resource[rid] for rid in resource_ids if rid in id_to_resource
        ]

        # Generate snippets
        snippets = {}
        for resource in ordered_resources:
            snippets[str(resource.id)] = AdvancedSearchService.generate_snippets(
                resource.description or resource.title, query_text
            )

        # Calculate total and metadata
        total = len(merged_results)
        total_latency = (time.time() - start_time) * 1000

        # Count method contributions (how many unique results from each method)
        fts_ids = {rid for rid, _ in fts_results}
        dense_ids = {rid for rid, _ in dense_results}
        sparse_ids = {rid for rid, _ in sparse_results}

        metadata = {
            "latency_ms": total_latency,
            "method_contributions": {
                "fts5": len(fts_ids),
                "dense": len(dense_ids),
                "sparse": len(sparse_ids),
            },
            "weights_used": weights,
            "timing": {
                "fts5_ms": fts_time,
                "dense_ms": dense_time,
                "sparse_ms": sparse_time,
                "rrf_ms": rrf_time,
                "rerank_ms": rerank_time,
            },
        }

        return ordered_resources, total, None, snippets, metadata

    @staticmethod
    def fts_search(
        db: Session, query: str, filters: Any, limit: int = 100, offset: int = 0
    ) -> Tuple[List[Any], int, Dict[str, float], Dict[str, str]]:
        """
        Execute FTS search.

        Args:
            db: Database session
            query: Search query string
            filters: Search filters
            limit: Result limit
            offset: Result offset

        Returns:
            Tuple of (resources, total, scores, snippets)
        """
        return [], 0, {}, {}

    @staticmethod
    def parse_search_query(text: str) -> str:
        """
        Parse search query text.

        Args:
            text: Raw query text

        Returns:
            Parsed query string
        """
        return text

    @staticmethod
    def generate_snippets(text: str, query: str) -> str:
        """
        Generate highlighted snippet.

        Args:
            text: Source text
            query: Search query

        Returns:
            Highlighted snippet
        """
        return text[:200] + "..." if len(text) > 200 else text

    @staticmethod
    def _analyze_query(query: str) -> Dict[str, Any]:
        """
        Analyze query characteristics for adaptive weighting.

        Args:
            query: Search query

        Returns:
            Query characteristics including:
            - length: Character count
            - word_count: Number of words
            - has_operators: Boolean for AND/OR/NOT operators
            - is_short: Boolean for short queries (≤3 words)
            - is_long: Boolean for long queries (>10 words)
            - is_technical: Boolean for technical queries (has code symbols)
            - is_question: Boolean for question queries
        """
        word_count = len(query.split())

        return {
            "length": len(query),
            "word_count": word_count,
            "has_operators": any(op in query for op in ["AND", "OR", "NOT"]),
            "is_short": word_count <= 3,
            "is_long": word_count > 10,
            "is_technical": any(
                c in query
                for c in ["(", ")", "{", "}", "=", "+", "-", "/", "*", ";", ":"]
            ),
            "is_question": query.lower()
            .strip()
            .startswith(("who", "what", "when", "where", "why", "how")),
        }

    @staticmethod
    def _compute_adaptive_weights(query: str) -> List[float]:
        """
        Compute query-adaptive weights for RRF fusion.

        Adjusts weights based on query characteristics:
        - Short queries (≤3 words): Boost FTS5 (keyword matching)
        - Long queries (>10 words): Boost dense (semantic understanding)
        - Technical queries: Boost sparse (learned keyword importance)
        - Question queries: Boost dense (semantic understanding)

        Args:
            query: Search query text

        Returns:
            List of three weights [fts5_weight, dense_weight, sparse_weight]
            normalized to sum to 1.0
        """
        # Start with equal weights
        weights = [1.0, 1.0, 1.0]  # [FTS5, dense, sparse]

        analysis = AdvancedSearchService._analyze_query(query)

        # Short queries: boost FTS5 (exact keyword matching works well)
        if analysis["is_short"]:
            weights[0] *= 1.5

        # Long queries: boost dense (semantic understanding needed)
        if analysis["is_long"]:
            weights[1] *= 1.5

        # Technical queries: boost sparse (learned keyword importance)
        if analysis["is_technical"]:
            weights[2] *= 1.5

        # Question queries: boost dense (semantic understanding)
        if analysis["is_question"]:
            weights[1] *= 1.3

        # Normalize to sum to 1.0
        total = sum(weights)
        return [w / total for w in weights]

    @staticmethod
    def _execute_fts_search(
        db: Session, query: str, limit: int = 100
    ) -> List[Tuple[str, float]]:
        """
        Execute FTS5 full-text search.

        Args:
            db: Database session
            query: Search query text
            limit: Maximum number of results

        Returns:
            List of (resource_id, score) tuples
        """
        try:
            # Detect database type without Session.bind (removed in SQLAlchemy 2.x)
            try:
                from ..shared.database import get_database_type
                dialect_name = get_database_type()
            except Exception:
                dialect_name = "postgresql"  # default for production

            if dialect_name == "sqlite":
                # SQLite FTS5 search
                # Note: This assumes FTS5 virtual table exists
                # For now, fall back to LIKE search
                results = (
                    db.query(Resource)
                    .filter(
                        or_(
                            Resource.title.ilike(f"%{query}%"),
                            Resource.description.ilike(f"%{query}%"),
                        )
                    )
                    .limit(limit)
                    .all()
                )

                # Return with simple relevance scores
                return [(str(r.id), 1.0) for r in results]

            elif dialect_name == "postgresql":
                # PostgreSQL tsvector search
                # Use ts_rank for scoring
                sql = text("""
                    SELECT id, ts_rank(
                        to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(description, '')),
                        plainto_tsquery('english', :query)
                    ) as rank
                    FROM resources
                    WHERE to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(description, ''))
                        @@ plainto_tsquery('english', :query)
                    ORDER BY rank DESC
                    LIMIT :limit
                """)

                result = db.execute(sql, {"query": query, "limit": limit})
                return [(str(row[0]), float(row[1])) for row in result]

            else:
                # Fallback for other databases
                results = (
                    db.query(Resource)
                    .filter(
                        or_(
                            Resource.title.ilike(f"%{query}%"),
                            Resource.description.ilike(f"%{query}%"),
                        )
                    )
                    .limit(limit)
                    .all()
                )

                return [(str(r.id), 1.0) for r in results]

        except Exception:
            # If FTS search fails, return empty results
            return []

    @staticmethod
    def _execute_dense_search(
        db: Session, query: str, limit: int = 100
    ) -> List[Tuple[str, float]]:
        """
        Execute dense vector semantic search.

        Args:
            db: Database session
            query: Search query text
            limit: Maximum number of results

        Returns:
            List of (resource_id, similarity_score) tuples
        """
        try:
            # Generate query embedding
            embedding_service = EmbeddingService(db)
            query_embedding = embedding_service.generate_embedding(query)

            if not query_embedding:
                return []

            # Fetch all resources with embeddings
            resources = db.query(Resource).filter(Resource.embedding.isnot(None)).all()

            if not resources:
                return []

            # Compute cosine similarity
            query_vec = np.array(query_embedding)
            query_norm = np.linalg.norm(query_vec)

            if query_norm == 0:
                return []

            similarities = []
            for resource in resources:
                try:
                    resource_embedding = resource.embedding
                    if isinstance(resource_embedding, str):
                        resource_embedding = json.loads(resource_embedding)

                    if not resource_embedding:
                        continue

                    resource_vec = np.array(resource_embedding)
                    resource_norm = np.linalg.norm(resource_vec)

                    if resource_norm == 0:
                        continue

                    # Cosine similarity
                    similarity = np.dot(query_vec, resource_vec) / (
                        query_norm * resource_norm
                    )
                    similarities.append((str(resource.id), float(similarity)))

                except Exception:
                    continue

            # Sort by similarity descending and return top N
            similarities.sort(key=lambda x: x[1], reverse=True)
            return similarities[:limit]

        except Exception:
            # If dense search fails, return empty results
            return []

    @staticmethod
    def _execute_sparse_search(
        db: Session, query: str, limit: int = 100
    ) -> List[Tuple[str, float]]:
        """
        Execute sparse vector search using learned keyword importance.

        Args:
            db: Database session
            query: Search query text
            limit: Maximum number of results

        Returns:
            List of (resource_id, score) tuples
        """
        try:
            # Use sparse embedding service
            sparse_service = SparseEmbeddingService(db)
            query_sparse = sparse_service.generate_embedding(query)

            if not query_sparse:
                return []

            # Fetch all resources with sparse embeddings
            # Note: sparse_embedding may be JSONB (not TEXT), so avoid != "" comparison
            resources = (
                db.query(Resource)
                .filter(Resource.sparse_embedding.isnot(None))
                .all()
            )

            if not resources:
                return []

            # Compute sparse similarity scores
            scores = []
            for resource in resources:
                try:
                    resource_sparse = json.loads(resource.sparse_embedding)

                    # Compute dot product (sparse vectors are already normalized)
                    score = 0.0
                    for token_id, weight in query_sparse.items():
                        if str(token_id) in resource_sparse:
                            score += weight * resource_sparse[str(token_id)]

                    if score > 0:
                        scores.append((str(resource.id), float(score)))

                except Exception:
                    continue

            # Sort by score descending and return top N
            scores.sort(key=lambda x: x[1], reverse=True)
            return scores[:limit]

        except Exception:
            # If sparse search fails, return empty results
            return []
