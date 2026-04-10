"""
Recommendation strategy pattern implementation for Neo Alexandria.

This module implements the Strategy pattern to replace conditional logic
in recommendation generation with polymorphic strategies. Each strategy
represents a different approach to generating recommendations.

Based on Fowler's "Replace Conditional with Polymorphism" refactoring technique.
"""

import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import logging

from .domain import Recommendation, RecommendationScore

logger = logging.getLogger(__name__)


class RecommendationStrategy(ABC):
    """
    Abstract base class for recommendation strategies.

    Defines the interface that all concrete recommendation strategies
    must implement. Each strategy encapsulates a different algorithm
    for generating recommendations.

    Attributes:
        db: Database session for data access
    """

    def __init__(self, db: Session):
        """
        Initialize recommendation strategy.

        Args:
            db: Database session
        """
        self.db = db

    @abstractmethod
    def generate(self, user_id: str, limit: int = 10, **kwargs) -> List[Recommendation]:
        """
        Generate recommendations for a user.

        Args:
            user_id: Unique identifier of the user
            limit: Maximum number of recommendations to return
            **kwargs: Additional strategy-specific parameters

        Returns:
            List of Recommendation objects sorted by rank
        """
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """
        Get human-readable strategy name.

        Returns:
            Name of the strategy
        """
        pass

    def _create_recommendation(
        self,
        resource_id: str,
        user_id: str,
        score: float,
        confidence: float,
        rank: int,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Recommendation:
        """
        Helper method to create a Recommendation object.

        Args:
            resource_id: ID of recommended resource
            user_id: ID of user receiving recommendation
            score: Relevance score (0.0-1.0)
            confidence: Confidence in recommendation (0.0-1.0)
            rank: Ranking position (1-based)
            reason: Optional explanation
            metadata: Optional additional metadata

        Returns:
            Recommendation object
        """
        rec_score = RecommendationScore(score=score, confidence=confidence, rank=rank)

        return Recommendation(
            resource_id=resource_id,
            user_id=user_id,
            recommendation_score=rec_score,
            strategy=self.get_strategy_name(),
            reason=reason,
            metadata=metadata or {},
        )


class CollaborativeFilteringStrategy(RecommendationStrategy):
    """
    Collaborative filtering strategy using Neural Collaborative Filtering (NCF).

    Generates recommendations based on user-item interaction patterns
    learned by a neural network model. Uses implicit feedback from
    user interactions to predict items the user might like.
    """

    def generate(self, user_id: str, limit: int = 10, **kwargs) -> List[Recommendation]:
        """
        Generate recommendations using collaborative filtering.

        Uses NCF model to predict user preferences based on
        interaction history patterns.

        Args:
            user_id: Unique identifier of the user
            limit: Maximum number of recommendations
            **kwargs: Additional parameters (min_score, etc.)

        Returns:
            List of recommendations sorted by predicted score
        """
        logger.info(
            f"Generating collaborative filtering recommendations "
            f"for user {user_id}, limit={limit}"
        )

        try:
            # Import NCF service from module-local file
            from .ncf import NCFService

            ncf_service = NCFService(self.db)

            # Check if model is trained
            if not ncf_service.is_model_trained():
                logger.warning("NCF model not trained, returning empty recommendations")
                return []

            # Get recommendations from NCF model
            ncf_recommendations = ncf_service.get_top_recommendations(
                user_id=user_id, top_k=limit
            )

            # Convert to domain objects
            recommendations = []
            for rank, (resource_id, score) in enumerate(ncf_recommendations, start=1):
                # NCF provides score, estimate confidence based on score
                confidence = self._estimate_confidence(score)

                rec = self._create_recommendation(
                    resource_id=str(resource_id),
                    user_id=user_id,
                    score=score,
                    confidence=confidence,
                    rank=rank,
                    reason="Based on similar users' preferences",
                    metadata={"model": "ncf", "model_score": score},
                )
                recommendations.append(rec)

            logger.info(
                f"Generated {len(recommendations)} collaborative "
                f"filtering recommendations"
            )
            return recommendations

        except ImportError:
            logger.error("NCF service not available")
            return []
        except Exception as e:
            logger.error(f"Error in collaborative filtering: {e}")
            return []

    def get_strategy_name(self) -> str:
        """Get strategy name."""
        return "collaborative_filtering"

    def _estimate_confidence(self, score: float) -> float:
        """
        Estimate confidence based on prediction score.

        Higher scores indicate higher confidence in the prediction.

        Args:
            score: Prediction score (0.0-1.0)

        Returns:
            Confidence estimate (0.0-1.0)
        """
        # Simple heuristic: confidence correlates with score
        # Could be improved with model uncertainty estimates
        return min(score * 1.1, 1.0)


class ContentBasedStrategy(RecommendationStrategy):
    """
    Content-based filtering strategy using embedding similarity.

    Generates recommendations based on similarity between resource
    embeddings and user profile. Recommends items similar to those
    the user has interacted with previously.
    """

    def generate(self, user_id: str, limit: int = 10, **kwargs) -> List[Recommendation]:
        """
        Generate recommendations using content-based filtering.

        Computes user profile from interaction history and finds
        resources with similar embeddings.

        Args:
            user_id: Unique identifier of the user
            limit: Maximum number of recommendations
            **kwargs: Additional parameters (min_similarity, etc.)

        Returns:
            List of recommendations sorted by similarity
        """
        logger.info(
            f"Generating content-based recommendations "
            f"for user {user_id}, limit={limit}"
        )

        try:
            from app.database.models import Resource, UserInteraction

            # Get user's interaction history
            interactions = (
                self.db.query(UserInteraction)
                .filter(UserInteraction.user_id == user_id)
                .all()
            )

            if not interactions:
                logger.warning(f"No interactions found for user {user_id}")
                return []

            # Build user profile from interacted resources
            user_profile = self._build_user_profile(interactions)

            if user_profile is None:
                logger.warning("Could not build user profile")
                return []

            # Get candidate resources (exclude already interacted)
            interacted_ids = {str(i.resource_id) for i in interactions}
            candidates = (
                self.db.query(Resource)
                .filter(
                    Resource.embedding.isnot(None), ~Resource.id.in_(interacted_ids)
                )
                .all()
            )

            # Compute similarities
            similarities = []
            for resource in candidates:
                if resource.embedding:
                    try:
                        if isinstance(resource.embedding, str):
                            resource_emb = json.loads(resource.embedding)
                        else:
                            resource_emb = resource.embedding
                    except (json.JSONDecodeError, TypeError):
                        continue
                    similarity = self._cosine_similarity(user_profile, resource_emb)
                    similarities.append((str(resource.id), similarity))

            # Sort by similarity and take top-k
            similarities.sort(key=lambda x: x[1], reverse=True)
            top_similarities = similarities[:limit]

            # Convert to domain objects
            recommendations = []
            for rank, (resource_id, similarity) in enumerate(top_similarities, start=1):
                # Normalize similarity to 0-1 range (cosine is -1 to 1)
                score = (similarity + 1.0) / 2.0
                confidence = self._estimate_confidence_from_similarity(similarity)

                rec = self._create_recommendation(
                    resource_id=resource_id,
                    user_id=user_id,
                    score=score,
                    confidence=confidence,
                    rank=rank,
                    reason="Similar to resources you've interacted with",
                    metadata={"similarity": similarity, "normalized_score": score},
                )
                recommendations.append(rec)

            logger.info(
                f"Generated {len(recommendations)} content-based recommendations"
            )
            return recommendations

        except Exception as e:
            logger.error(f"Error in content-based filtering: {e}")
            return []

    def get_strategy_name(self) -> str:
        """Get strategy name."""
        return "content_based"

    def _build_user_profile(self, interactions: List[Any]) -> Optional[List[float]]:
        """
        Build user profile vector from interaction history.

        Averages embeddings of interacted resources, weighted by
        interaction strength.

        Args:
            interactions: List of user interactions

        Returns:
            User profile vector or None if no valid embeddings
        """
        import numpy as np
        from app.database.models import Resource

        embeddings = []
        weights = []

        for interaction in interactions:
            resource = (
                self.db.query(Resource)
                .filter(Resource.id == interaction.resource_id)
                .first()
            )

            if resource and resource.embedding:
                try:
                    if isinstance(resource.embedding, str):
                        resource_emb = json.loads(resource.embedding)
                    else:
                        resource_emb = resource.embedding
                except (json.JSONDecodeError, TypeError):
                    continue
                embeddings.append(resource_emb)
                # Weight by interaction type (could be improved)
                weight = self._get_interaction_weight(interaction.interaction_type)
                weights.append(weight)

        if not embeddings:
            return None

        # Weighted average of embeddings
        embeddings_array = np.array(embeddings)
        weights_array = np.array(weights).reshape(-1, 1)

        weighted_sum = np.sum(embeddings_array * weights_array, axis=0)
        total_weight = np.sum(weights_array)

        user_profile = weighted_sum / total_weight

        return user_profile.tolist()

    def _get_interaction_weight(self, interaction_type: str) -> float:
        """
        Get weight for interaction type.

        Args:
            interaction_type: Type of interaction

        Returns:
            Weight value (higher = more important)
        """
        weights = {"annotation": 1.0, "view": 0.5, "search": 0.3, "click": 0.4}
        return weights.get(interaction_type, 0.5)

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity (-1.0 to 1.0)
        """
        import numpy as np

        v1 = np.array(vec1)
        v2 = np.array(vec2)

        if v1.size == 0 or v2.size == 0 or v1.shape != v2.shape:
            return 0.0

        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0

        similarity = np.dot(v1, v2) / (norm1 * norm2)

        return float(np.clip(similarity, -1.0, 1.0))

    def _estimate_confidence_from_similarity(self, similarity: float) -> float:
        """
        Estimate confidence from similarity score.

        Args:
            similarity: Cosine similarity (-1.0 to 1.0)

        Returns:
            Confidence estimate (0.0-1.0)
        """
        # Normalize to 0-1 and apply sigmoid-like transformation
        normalized = (similarity + 1.0) / 2.0
        # Higher similarities get higher confidence
        return min(normalized * 1.2, 1.0)


class GraphBasedStrategy(RecommendationStrategy):
    """
    Graph-based recommendation strategy using citation network.

    Generates recommendations based on graph structure, finding
    resources connected through citations and co-citations.
    Leverages the knowledge graph topology.
    """

    def generate(self, user_id: str, limit: int = 10, **kwargs) -> List[Recommendation]:
        """
        Generate recommendations using graph traversal.

        Finds resources connected to user's interaction history
        through citation relationships.

        Args:
            user_id: Unique identifier of the user
            limit: Maximum number of recommendations
            **kwargs: Additional parameters (max_hops, etc.)

        Returns:
            List of recommendations sorted by graph score
        """
        logger.info(
            f"Generating graph-based recommendations for user {user_id}, limit={limit}"
        )

        try:
            from app.database.models import UserInteraction

            # Get user's interaction history
            interactions = (
                self.db.query(UserInteraction)
                .filter(UserInteraction.user_id == user_id)
                .all()
            )

            if not interactions:
                logger.warning(f"No interactions found for user {user_id}")
                return []

            # Get seed resources from interactions
            seed_resource_ids = [str(i.resource_id) for i in interactions]

            # Find neighbors through citations (1-hop and 2-hop)
            neighbors = self._find_graph_neighbors(seed_resource_ids, max_hops=2)

            # Exclude already interacted resources
            interacted_ids = set(seed_resource_ids)
            candidates = [
                (rid, score)
                for rid, score in neighbors.items()
                if rid not in interacted_ids
            ]

            # Sort by score and take top-k
            candidates.sort(key=lambda x: x[1], reverse=True)
            top_candidates = candidates[:limit]

            # Convert to domain objects
            recommendations = []
            for rank, (resource_id, graph_score) in enumerate(top_candidates, start=1):
                # Normalize graph score to 0-1 range
                score = min(graph_score, 1.0)
                confidence = self._estimate_confidence_from_graph(graph_score)

                rec = self._create_recommendation(
                    resource_id=resource_id,
                    user_id=user_id,
                    score=score,
                    confidence=confidence,
                    rank=rank,
                    reason="Connected to resources you've interacted with",
                    metadata={
                        "graph_score": graph_score,
                        "connection_type": "citation_network",
                    },
                )
                recommendations.append(rec)

            logger.info(f"Generated {len(recommendations)} graph-based recommendations")
            return recommendations

        except Exception as e:
            logger.error(f"Error in graph-based filtering: {e}")
            return []

    def get_strategy_name(self) -> str:
        """Get strategy name."""
        return "graph_based"

    def _find_graph_neighbors(
        self, seed_ids: List[str], max_hops: int = 2
    ) -> Dict[str, float]:
        """
        Find neighbors in citation graph.

        Args:
            seed_ids: Starting resource IDs
            max_hops: Maximum number of hops (default: 2)

        Returns:
            Dictionary mapping resource_id to graph score
        """
        from app.database.models import Citation

        neighbors = {}

        # 1-hop neighbors (direct citations)
        for seed_id in seed_ids:
            # Outgoing citations (resources this cites)
            outgoing = (
                self.db.query(Citation)
                .filter(Citation.source_resource_id == seed_id)
                .all()
            )

            for citation in outgoing:
                target_id = str(citation.target_resource_id)
                neighbors[target_id] = neighbors.get(target_id, 0.0) + 0.8

            # Incoming citations (resources that cite this)
            incoming = (
                self.db.query(Citation)
                .filter(Citation.target_resource_id == seed_id)
                .all()
            )

            for citation in incoming:
                source_id = str(citation.source_resource_id)
                neighbors[source_id] = neighbors.get(source_id, 0.0) + 0.7

        # 2-hop neighbors if requested
        if max_hops >= 2:
            one_hop_ids = list(neighbors.keys())

            for neighbor_id in one_hop_ids[:20]:  # Limit to avoid explosion
                # Find neighbors of neighbors
                citations = (
                    self.db.query(Citation)
                    .filter(
                        (Citation.source_resource_id == neighbor_id)
                        | (Citation.target_resource_id == neighbor_id)
                    )
                    .all()
                )

                for citation in citations:
                    target_id = str(citation.target_resource_id)
                    source_id = str(citation.source_resource_id)

                    # Add 2-hop neighbors with lower weight
                    if target_id not in seed_ids and target_id != neighbor_id:
                        neighbors[target_id] = neighbors.get(target_id, 0.0) + 0.3
                    if source_id not in seed_ids and source_id != neighbor_id:
                        neighbors[source_id] = neighbors.get(source_id, 0.0) + 0.3

        return neighbors

    def _estimate_confidence_from_graph(self, graph_score: float) -> float:
        """
        Estimate confidence from graph score.

        Args:
            graph_score: Graph-based score

        Returns:
            Confidence estimate (0.0-1.0)
        """
        # Higher graph scores indicate more connections
        # Normalize and cap at 1.0
        return min(graph_score / 2.0, 1.0)


class HybridStrategy(RecommendationStrategy):
    """
    Hybrid recommendation strategy combining multiple strategies.

    Generates recommendations by fusing results from multiple
    strategies using weighted combination. Provides more robust
    recommendations by leveraging strengths of different approaches.
    """

    def __init__(
        self,
        db: Session,
        strategies: Optional[List[RecommendationStrategy]] = None,
        weights: Optional[List[float]] = None,
    ):
        """
        Initialize hybrid strategy.

        Args:
            db: Database session
            strategies: List of strategies to combine (default: all strategies)
            weights: Weights for each strategy (default: equal weights)
        """
        super().__init__(db)

        # Initialize strategies if not provided
        if strategies is None:
            self.strategies = [
                CollaborativeFilteringStrategy(db),
                ContentBasedStrategy(db),
                GraphBasedStrategy(db),
            ]
        else:
            self.strategies = strategies

        # Initialize weights if not provided
        if weights is None:
            # Default weights: favor collaborative filtering
            self.weights = [0.4, 0.3, 0.3]
        else:
            if len(weights) != len(self.strategies):
                raise ValueError(
                    f"Number of weights ({len(weights)}) must match "
                    f"number of strategies ({len(self.strategies)})"
                )
            # Normalize weights to sum to 1.0
            total = sum(weights)
            self.weights = [w / total for w in weights]

    def generate(self, user_id: str, limit: int = 10, **kwargs) -> List[Recommendation]:
        """
        Generate recommendations using weighted fusion.

        Combines recommendations from multiple strategies using
        weighted score fusion.

        Args:
            user_id: Unique identifier of the user
            limit: Maximum number of recommendations
            **kwargs: Additional parameters passed to strategies

        Returns:
            List of fused recommendations sorted by combined score
        """
        logger.info(
            f"Generating hybrid recommendations for user {user_id}, limit={limit}"
        )

        # Get recommendations from each strategy
        all_recommendations = []
        for strategy, weight in zip(self.strategies, self.weights):
            try:
                # Request more recommendations from each strategy for better fusion
                strategy_recs = strategy.generate(
                    user_id=user_id, limit=limit * 2, **kwargs
                )
                all_recommendations.append((strategy_recs, weight))
                logger.info(
                    f"Got {len(strategy_recs)} recommendations from "
                    f"{strategy.get_strategy_name()}"
                )
            except Exception as e:
                logger.error(
                    f"Error getting recommendations from "
                    f"{strategy.get_strategy_name()}: {e}"
                )
                all_recommendations.append(([], weight))

        # Fuse recommendations
        fused = self._weighted_fusion(all_recommendations, limit)

        logger.info(f"Generated {len(fused)} hybrid recommendations")
        return fused

    def get_strategy_name(self) -> str:
        """Get strategy name."""
        return "hybrid"

    def _weighted_fusion(
        self, strategy_results: List[tuple], limit: int
    ) -> List[Recommendation]:
        """
        Fuse recommendations using weighted score combination.

        Args:
            strategy_results: List of (recommendations, weight) tuples
            limit: Maximum number of recommendations to return

        Returns:
            Fused and ranked recommendations
        """
        # Collect all unique resource IDs
        resource_scores = {}
        resource_metadata = {}

        for recommendations, weight in strategy_results:
            for rec in recommendations:
                resource_id = rec.resource_id

                if resource_id not in resource_scores:
                    resource_scores[resource_id] = {
                        "weighted_score": 0.0,
                        "confidence": 0.0,
                        "strategies": [],
                    }

                # Add weighted score
                resource_scores[resource_id]["weighted_score"] += (
                    rec.get_score() * weight
                )

                # Average confidence
                resource_scores[resource_id]["confidence"] += (
                    rec.get_confidence() * weight
                )

                # Track which strategies recommended this
                resource_scores[resource_id]["strategies"].append(rec.strategy)

                # Store metadata from first occurrence
                if resource_id not in resource_metadata:
                    resource_metadata[resource_id] = {
                        "reasons": [rec.reason] if rec.reason else [],
                        "metadata": rec.metadata,
                    }

        # Sort by weighted score
        sorted_resources = sorted(
            resource_scores.items(), key=lambda x: x[1]["weighted_score"], reverse=True
        )

        # Take top-k and create recommendations
        fused_recommendations = []
        for rank, (resource_id, scores) in enumerate(sorted_resources[:limit], start=1):
            metadata = resource_metadata.get(resource_id, {})

            # Combine reasons from different strategies
            reasons = metadata.get("reasons", [])
            combined_reason = (
                "; ".join(reasons) if reasons else "Recommended by multiple strategies"
            )

            # Create fused recommendation
            rec = self._create_recommendation(
                resource_id=resource_id,
                user_id=list(strategy_results[0][0])[0].user_id
                if strategy_results[0][0]
                else "",
                score=scores["weighted_score"],
                confidence=scores["confidence"],
                rank=rank,
                reason=combined_reason,
                metadata={
                    "fusion_method": "weighted",
                    "strategies_used": scores["strategies"],
                    "num_strategies": len(scores["strategies"]),
                    "original_metadata": metadata.get("metadata", {}),
                },
            )
            fused_recommendations.append(rec)

        return fused_recommendations


class RecommendationStrategyFactory:
    """
    Factory for creating recommendation strategies.

    Provides a centralized way to instantiate recommendation strategies
    based on strategy type. Supports dependency injection of database
    session and strategy-specific configuration.
    """

    @staticmethod
    def create(strategy_type: str, db: Session, **kwargs) -> RecommendationStrategy:
        """
        Create recommendation strategy by type.

        Args:
            strategy_type: Type of strategy to create
                ('collaborative', 'content', 'graph', 'hybrid')
            db: Database session
            **kwargs: Additional strategy-specific parameters

        Returns:
            Concrete strategy instance

        Raises:
            ValueError: If strategy_type is unknown
        """
        strategy_map = {
            "collaborative": CollaborativeFilteringStrategy,
            "collaborative_filtering": CollaborativeFilteringStrategy,
            "content": ContentBasedStrategy,
            "content_based": ContentBasedStrategy,
            "graph": GraphBasedStrategy,
            "graph_based": GraphBasedStrategy,
            "hybrid": HybridStrategy,
        }

        strategy_class = strategy_map.get(strategy_type.lower())

        if strategy_class is None:
            raise ValueError(
                f"Unknown strategy type: {strategy_type}. "
                f"Valid types: {list(strategy_map.keys())}"
            )

        # Create strategy instance
        if strategy_class == HybridStrategy:
            # Hybrid strategy may need special initialization
            strategies = kwargs.get("strategies")
            weights = kwargs.get("weights")
            return HybridStrategy(db, strategies, weights)
        else:
            return strategy_class(db)

    @staticmethod
    def get_available_strategies() -> List[str]:
        """
        Get list of available strategy types.

        Returns:
            List of strategy type names
        """
        return ["collaborative", "content", "graph", "hybrid"]

    @staticmethod
    def create_all_strategies(db: Session) -> Dict[str, RecommendationStrategy]:
        """
        Create instances of all available strategies.

        Args:
            db: Database session

        Returns:
            Dictionary mapping strategy names to instances
        """
        return {
            "collaborative": CollaborativeFilteringStrategy(db),
            "content": ContentBasedStrategy(db),
            "graph": GraphBasedStrategy(db),
            "hybrid": HybridStrategy(db),
        }
