"""
Real Vector Search Implementation using pgvector

This module implements true PostgreSQL vector search using pgvector extension.
Replaces Python-based cosine similarity with database-native vector operations.

Key Features:
- Dense vector search using pgvector operators (<->, <=>)
- Sparse vector search using JSONB containment
- Hybrid search with Reciprocal Rank Fusion (RRF)
- Optimized with HNSW and IVFFlat indexes
"""

from typing import List, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import json

logger = logging.getLogger(__name__)


class RealVectorSearchService:
    """
    Real vector search service using pgvector extension.
    
    Provides:
    - Dense vector similarity search (cosine, L2, inner product)
    - Sparse vector search (SPLADE-based)
    - Hybrid search combining multiple strategies
    """
    
    def __init__(self, db: Session):
        """
        Initialize vector search service.
        
        Args:
            db: Database session
        """
        self.db = db
    
    def dense_vector_search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        distance_metric: str = "cosine",
        filters: Dict[str, Any] = None
    ) -> List[Tuple[str, float]]:
        """
        Execute dense vector similarity search using pgvector.
        
        Args:
            query_embedding: Query embedding vector (768 dimensions)
            top_k: Number of results to return
            distance_metric: Distance metric ("cosine", "l2", "inner_product")
            filters: Optional filters (type, quality_score, etc.)
            
        Returns:
            List of (resource_id, distance) tuples sorted by similarity
        """
        # Select distance operator based on metric
        if distance_metric == "cosine":
            # Cosine distance: <=> operator
            # Lower is better (0 = identical, 2 = opposite)
            distance_op = "<=>"
        elif distance_metric == "l2":
            # L2 (Euclidean) distance: <-> operator
            distance_op = "<->"
        elif distance_metric == "inner_product":
            # Negative inner product: <#> operator
            # pgvector uses negative for consistency (lower = better)
            distance_op = "<#>"
        else:
            raise ValueError(f"Unknown distance metric: {distance_metric}")
        
        embedding_str = f"[{','.join(map(str, query_embedding))}]"

        where_conditions = ["embedding IS NOT NULL"]
        params: Dict[str, Any] = {"embedding": embedding_str, "top_k": top_k}

        if filters:
            if "resource_type" in filters:
                where_conditions.append("type = :resource_type")
                params["resource_type"] = filters["resource_type"]
            if "min_quality_score" in filters:
                where_conditions.append("quality_score >= :min_quality_score")
                params["min_quality_score"] = filters["min_quality_score"]
            if "language" in filters:
                where_conditions.append("language = :language")
                params["language"] = filters["language"]

        query = f"""
            SELECT 
                id::text as resource_id,
                embedding {distance_op} :embedding::vector as distance
            FROM resources
            WHERE {' AND '.join(where_conditions)}
            ORDER BY distance ASC
            LIMIT :top_k;
        """

        result = self.db.execute(text(query), params)
        rows = result.fetchall()
        
        logger.info(
            f"Dense vector search returned {len(rows)} results "
            f"(metric={distance_metric}, top_k={top_k})"
        )
        
        return [(row[0], float(row[1])) for row in rows]
    
    def sparse_vector_search(
        self,
        query_sparse_embedding: Dict[int, float],
        top_k: int = 10,
        filters: Dict[str, Any] = None
    ) -> List[Tuple[str, float]]:
        """
        Execute sparse vector search using SPLADE embeddings.
        
        Uses JSONB containment and overlap scoring for sparse vectors.
        
        Args:
            query_sparse_embedding: Query sparse embedding {token_id: weight}
            top_k: Number of results to return
            filters: Optional filters
            
        Returns:
            List of (resource_id, score) tuples sorted by relevance
        """
        if not query_sparse_embedding:
            logger.warning("Empty query sparse embedding")
            return []

        query_sparse_json = json.dumps(query_sparse_embedding)

        params: Dict[str, Any] = {
            "query_sparse_json": query_sparse_json,
            "top_k": top_k,
        }
        filter_conditions = []
        if filters:
            if "resource_type" in filters:
                filter_conditions.append("r.type = :resource_type")
                params["resource_type"] = filters["resource_type"]
            if "min_quality_score" in filters:
                filter_conditions.append("r.quality_score >= :min_quality_score")
                params["min_quality_score"] = filters["min_quality_score"]

        query = f"""
            WITH query_tokens AS (
                SELECT 
                    key::int as token_id,
                    value::float as query_weight
                FROM jsonb_each_text(:query_sparse_json::jsonb)
            ),
            scored_resources AS (
                SELECT 
                    r.id::text as resource_id,
                    SUM(
                        LEAST(
                            qt.query_weight,
                            (r.sparse_embedding->>(qt.token_id::text))::float
                        )
                    ) as score
                FROM resources r
                CROSS JOIN query_tokens qt
                WHERE r.sparse_embedding IS NOT NULL
                  AND r.sparse_embedding ? (qt.token_id::text)
                  {'AND ' + ' AND '.join(filter_conditions) if filter_conditions else ''}
        """

        query += """
                GROUP BY r.id
            )
            SELECT resource_id, score
            FROM scored_resources
            WHERE score > 0
            ORDER BY score DESC
            LIMIT :top_k;
        """

        result = self.db.execute(text(query), params)
        rows = result.fetchall()
        
        logger.info(f"Sparse vector search returned {len(rows)} results")
        
        return [(row[0], float(row[1])) for row in rows]
    
    def chunk_dense_vector_search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        distance_metric: str = "l2",
        filters: Dict[str, Any] = None
    ) -> List[Tuple[str, float]]:
        """
        Execute dense vector search on document chunks.
        
        Args:
            query_embedding: Query embedding vector
            top_k: Number of chunks to return
            distance_metric: Distance metric
            filters: Optional filters
            
        Returns:
            List of (chunk_id, distance) tuples
        """
        # Select distance operator
        if distance_metric == "cosine":
            distance_op = "<=>"
        elif distance_metric == "l2":
            distance_op = "<->"
        elif distance_metric == "inner_product":
            distance_op = "<#>"
        else:
            raise ValueError(f"Unknown distance metric: {distance_metric}")
        
        embedding_str = f"[{','.join(map(str, query_embedding))}]"

        params: Dict[str, Any] = {"embedding": embedding_str, "top_k": top_k}
        where_conditions = ["dc.embedding IS NOT NULL"]
        join_clause = ""

        if filters:
            join_clause = "JOIN resources r ON dc.resource_id = r.id"
            if "resource_type" in filters:
                where_conditions.append("r.type = :resource_type")
                params["resource_type"] = filters["resource_type"]
            if "min_quality_score" in filters:
                where_conditions.append("r.quality_score >= :min_quality_score")
                params["min_quality_score"] = filters["min_quality_score"]

        query = f"""
            SELECT 
                dc.id::text as chunk_id,
                dc.embedding {distance_op} :embedding::vector as distance
            FROM document_chunks dc
            {join_clause}
            WHERE {' AND '.join(where_conditions)}
            ORDER BY distance ASC
            LIMIT :top_k;
        """

        result = self.db.execute(text(query), params)
        rows = result.fetchall()
        
        logger.info(
            f"Chunk dense vector search returned {len(rows)} results"
        )
        
        return [(row[0], float(row[1])) for row in rows]
    
    def hybrid_vector_search(
        self,
        query_dense_embedding: List[float],
        query_sparse_embedding: Dict[int, float],
        top_k: int = 10,
        dense_weight: float = 0.5,
        sparse_weight: float = 0.5,
        filters: Dict[str, Any] = None
    ) -> List[Tuple[str, float]]:
        """
        Execute hybrid search combining dense and sparse vectors.
        
        Uses weighted score fusion:
        final_score = dense_weight * (1 - dense_distance) + sparse_weight * sparse_score
        
        Args:
            query_dense_embedding: Dense query embedding
            query_sparse_embedding: Sparse query embedding
            top_k: Number of results
            dense_weight: Weight for dense vector (0-1)
            sparse_weight: Weight for sparse vector (0-1)
            filters: Optional filters
            
        Returns:
            List of (resource_id, combined_score) tuples
        """
        # Get dense results
        dense_results = self.dense_vector_search(
            query_dense_embedding,
            top_k=top_k * 2,  # Get more for fusion
            distance_metric="cosine",
            filters=filters
        )
        
        # Get sparse results
        sparse_results = self.sparse_vector_search(
            query_sparse_embedding,
            top_k=top_k * 2,
            filters=filters
        )
        
        # Normalize and combine scores
        # Dense: convert distance to similarity (1 - distance)
        # Sparse: already a similarity score
        
        combined_scores = {}
        
        # Add dense scores
        for resource_id, distance in dense_results:
            similarity = 1.0 - min(distance, 1.0)  # Clamp to [0, 1]
            combined_scores[resource_id] = dense_weight * similarity
        
        # Add sparse scores
        # Normalize sparse scores to [0, 1]
        if sparse_results:
            max_sparse_score = max(score for _, score in sparse_results)
            for resource_id, score in sparse_results:
                normalized_score = score / max_sparse_score if max_sparse_score > 0 else 0
                if resource_id in combined_scores:
                    combined_scores[resource_id] += sparse_weight * normalized_score
                else:
                    combined_scores[resource_id] = sparse_weight * normalized_score
        
        # Sort by combined score and return top-k
        sorted_results = sorted(
            combined_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]
        
        logger.info(
            f"Hybrid vector search returned {len(sorted_results)} results "
            f"(dense_weight={dense_weight}, sparse_weight={sparse_weight})"
        )
        
        return sorted_results
    
    def reciprocal_rank_fusion(
        self,
        result_lists: List[List[Tuple[str, float]]],
        k: int = 60,
        top_k: int = 10
    ) -> List[Tuple[str, float]]:
        """
        Combine multiple ranked lists using Reciprocal Rank Fusion (RRF).
        
        RRF formula: score(d) = sum over all lists of 1 / (k + rank(d))
        
        Args:
            result_lists: List of ranked result lists [(id, score), ...]
            k: RRF constant (default: 60, from original paper)
            top_k: Number of final results
            
        Returns:
            List of (resource_id, rrf_score) tuples
        """
        rrf_scores = {}
        
        for result_list in result_lists:
            for rank, (resource_id, _) in enumerate(result_list, start=1):
                rrf_score = 1.0 / (k + rank)
                if resource_id in rrf_scores:
                    rrf_scores[resource_id] += rrf_score
                else:
                    rrf_scores[resource_id] = rrf_score
        
        # Sort by RRF score descending
        sorted_results = sorted(
            rrf_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]
        
        logger.info(
            f"RRF fusion combined {len(result_lists)} lists into {len(sorted_results)} results"
        )
        
        return sorted_results
