"""
Reciprocal Rank Fusion Service

Implements Reciprocal Rank Fusion (RRF) for combining multiple ranked lists.
"""

import heapq
from typing import List, Optional, Tuple, Dict
from collections import defaultdict


class ReciprocalRankFusionService:
    """
    Reciprocal Rank Fusion service for combining ranked lists.

    RRF formula: score(d) = sum(1 / (k + rank(d)))
    where k is a constant (typically 60) and rank(d) is the rank of document d.
    """

    def __init__(self, k: int = 60):
        """
        Initialize RRF service.

        Args:
            k: RRF constant (default 60)
        """
        self.k = k

    def fuse(
        self,
        ranked_lists: List[List[Tuple[str, float]]],
        weights: List[float] = None,
        top_k: Optional[int] = None,
    ) -> List[Tuple[str, float]]:
        """
        Fuse multiple ranked lists using RRF.

        Args:
            ranked_lists: List of ranked lists, each containing (id, score) tuples
            weights: Optional weights for each list (default: equal weights)
            top_k: If set, return only the K highest-scoring fused results using
                a size-K min-heap (O(N log K) instead of O(N log N)).

        Returns:
            Fused ranked list of (id, score) tuples
        """
        if not ranked_lists:
            return []

        if weights is None:
            weights = [1.0] * len(ranked_lists)

        rrf_scores: Dict[str, float] = defaultdict(float)

        for ranked_list, weight in zip(ranked_lists, weights):
            for rank, (doc_id, _) in enumerate(ranked_list, start=1):
                rrf_scores[doc_id] += weight * (1.0 / (self.k + rank))

        if top_k is not None and top_k < len(rrf_scores):
            return heapq.nlargest(top_k, rrf_scores.items(), key=lambda x: x[1])

        return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
