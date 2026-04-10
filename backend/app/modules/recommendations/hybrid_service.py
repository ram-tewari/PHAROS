"""
Hybrid Recommendation Service.

This service implements a two-stage recommendation pipeline:
1. Candidate Generation: Multi-strategy candidate generation (collaborative, content, graph)
2. Ranking & Reranking: Hybrid scoring, MMR diversity optimization, novelty boosting

Architecture:
- Combines Neural Collaborative Filtering (NCF), content-based, and graph-based strategies
- Applies hybrid scoring with configurable weights
- Optimizes for diversity using Maximal Marginal Relevance (MMR)
- Promotes novelty to prevent filter bubbles
- Handles cold start users gracefully

Related files:
- app/services/user_profile_service.py: User profiles and embeddings
- app/services/collaborative_filtering_service.py: NCF predictions
- app/services/graph_service.py: Graph-based recommendations
- app/database/models.py: Resource, UserProfile, UserInteraction models
"""

import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Set
from uuid import UUID

import numpy as np
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.database.models import Resource, UserProfile, UserInteraction
from .collaborative import CollaborativeFilteringService
from .user_profile import UserProfileService
from app.utils.performance_monitoring import timing_decorator, metrics
from app.utils.recommendation_metrics import compute_gini_coefficient

logger = logging.getLogger(__name__)


class HybridRecommendationService:
    """
    Service for hybrid recommendation generation.

    Provides methods for:
    - Multi-strategy candidate generation
    - Hybrid scoring and ranking
    - Diversity optimization (MMR)
    - Novelty promotion
    - Cold start handling

    Note: Graph-based recommendations are currently disabled to maintain
    module isolation. This functionality should be re-enabled through
    event-driven communication in a future update.
    """

    def __init__(self, db: Session):
        """
        Initialize the HybridRecommendationService.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.user_profile_service = UserProfileService(db)
        self.collaborative_filtering_service = CollaborativeFilteringService(db)
        # Graph service disabled for module isolation
        # TODO: Re-enable through event-driven communication
        self.graph_service = None

        # Default hybrid weights
        self.default_weights = {
            "collaborative": 0.35,
            "content": 0.30,
            "graph": 0.20,
            "quality": 0.10,
            "recency": 0.05,
        }

        # Cold start threshold
        self.cold_start_threshold = 5

        logger.info("HybridRecommendationService initialized")

    def _generate_candidates(
        self, user_id: UUID, strategy: str = "hybrid"
    ) -> List[Dict]:
        """
        Generate candidates from multiple strategies.

        Strategies:
        - collaborative: Use NCF to score resources, select top 100
        - content: Compute user embedding, find similar resources (cosine > 0.3), select top 100
        - graph: Use GraphService.get_neighbors_multihop(hops=2), select top 100
        - hybrid: Combine all strategies

        Args:
            user_id: User UUID
            strategy: Strategy to use ('collaborative', 'content', 'graph', 'hybrid')

        Returns:
            List of candidate dictionaries with resource_id and source strategy metadata
        """
        try:
            candidates = []
            candidate_ids_seen: Set[UUID] = set()

            # Check if user has enough interactions for collaborative filtering
            interaction_count = (
                self.db.query(func.count(UserInteraction.id))
                .filter(UserInteraction.user_id == user_id)
                .scalar()
            )

            use_collaborative = interaction_count >= self.cold_start_threshold

            # 1. Collaborative Filtering Candidates
            if strategy in ["collaborative", "hybrid"] and use_collaborative:
                try:
                    # Get all resources
                    all_resources = self.db.query(Resource).limit(1000).all()
                    resource_ids = [str(r.id) for r in all_resources]

                    # Get NCF predictions
                    ncf_recommendations = (
                        self.collaborative_filtering_service.get_top_recommendations(
                            user_id=str(user_id), candidate_ids=resource_ids, limit=100
                        )
                    )

                    for rec in ncf_recommendations:
                        resource_id = UUID(rec["resource_id"])
                        if resource_id not in candidate_ids_seen:
                            candidates.append(
                                {
                                    "resource_id": resource_id,
                                    "source_strategy": "collaborative",
                                    "collaborative_score": rec["score"],
                                }
                            )
                            candidate_ids_seen.add(resource_id)

                    logger.info(
                        f"Generated {len(ncf_recommendations)} collaborative candidates for user {user_id}"
                    )

                except Exception as e:
                    logger.warning(
                        f"Error generating collaborative candidates: {str(e)}"
                    )

            # 2. Content-Based Candidates
            if strategy in ["content", "hybrid"]:
                try:
                    # Get user embedding
                    user_embedding = self.user_profile_service.get_user_embedding(
                        user_id
                    )

                    # Find similar resources (cosine similarity > 0.3)
                    resources = (
                        self.db.query(Resource)
                        .filter(Resource.embedding.isnot(None))
                        .limit(500)
                        .all()
                    )

                    content_candidates = []
                    for resource in resources:
                        if resource.id in candidate_ids_seen:
                            continue

                        if not resource.embedding:
                            continue

                        try:
                            # Parse embedding
                            if isinstance(resource.embedding, str):
                                resource_emb = json.loads(resource.embedding)
                            else:
                                resource_emb = resource.embedding

                            # Compute cosine similarity
                            similarity = self._cosine_similarity(
                                user_embedding, np.array(resource_emb)
                            )

                            if similarity > 0.3:
                                content_candidates.append(
                                    {
                                        "resource_id": resource.id,
                                        "source_strategy": "content",
                                        "content_score": float(similarity),
                                    }
                                )

                        except Exception as e:
                            logger.debug(
                                f"Error computing similarity for resource {resource.id}: {str(e)}"
                            )
                            continue

                    # Sort by content score and take top 100
                    content_candidates.sort(
                        key=lambda x: x["content_score"], reverse=True
                    )
                    content_candidates = content_candidates[:100]

                    for candidate in content_candidates:
                        if candidate["resource_id"] not in candidate_ids_seen:
                            candidates.append(candidate)
                            candidate_ids_seen.add(candidate["resource_id"])

                    logger.info(
                        f"Generated {len(content_candidates)} content candidates for user {user_id}"
                    )

                except Exception as e:
                    logger.warning(f"Error generating content candidates: {str(e)}")

            # 3. Graph-Based Candidates (disabled for module isolation)
            # TODO: Re-enable through event-driven communication
            if strategy in ["graph", "hybrid"] and self.graph_service is not None:
                try:
                    # Get user's recently interacted resources
                    recent_interactions = (
                        self.db.query(UserInteraction)
                        .filter(
                            UserInteraction.user_id == user_id,
                            UserInteraction.is_positive == 1,
                        )
                        .order_by(desc(UserInteraction.interaction_timestamp))
                        .limit(10)
                        .all()
                    )

                    graph_candidate_ids: Set[UUID] = set()

                    for interaction in recent_interactions:
                        # Get 2-hop neighbors
                        neighbors = self.graph_service.get_neighbors_multihop(
                            resource_id=str(interaction.resource_id), hops=2, limit=20
                        )

                        for neighbor in neighbors:
                            try:
                                neighbor_id = UUID(neighbor["resource_id"])
                                if (
                                    neighbor_id not in candidate_ids_seen
                                    and neighbor_id not in graph_candidate_ids
                                ):
                                    graph_candidate_ids.add(neighbor_id)
                                    candidates.append(
                                        {
                                            "resource_id": neighbor_id,
                                            "source_strategy": "graph",
                                            "graph_score": neighbor.get("score", 0.5),
                                        }
                                    )
                            except Exception as e:
                                logger.debug(
                                    f"Error processing graph neighbor: {str(e)}"
                                )
                                continue

                    # Limit to top 100 graph candidates
                    graph_candidates = [
                        c for c in candidates if c["source_strategy"] == "graph"
                    ]
                    graph_candidates.sort(
                        key=lambda x: x.get("graph_score", 0), reverse=True
                    )
                    graph_candidates = graph_candidates[:100]

                    # Update candidates list
                    candidates = [
                        c for c in candidates if c["source_strategy"] != "graph"
                    ] + graph_candidates

                    # Update seen IDs
                    for candidate in graph_candidates:
                        candidate_ids_seen.add(candidate["resource_id"])

                    logger.info(
                        f"Generated {len(graph_candidates)} graph candidates for user {user_id}"
                    )

                except Exception as e:
                    logger.warning(f"Error generating graph candidates: {str(e)}")
            elif strategy in ["graph", "hybrid"]:
                logger.debug(
                    "Graph-based recommendations currently disabled for module isolation"
                )

            logger.info(
                f"Total candidates generated: {len(candidates)} for user {user_id}"
            )
            return candidates

        except Exception as e:
            logger.error(
                f"Error in _generate_candidates for user {user_id}: {str(e)}",
                exc_info=True,
            )
            return []

    def _cosine_similarity(self, vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            vec_a: First vector
            vec_b: Second vector

        Returns:
            Cosine similarity score (0.0-1.0)
        """
        try:
            # Handle zero vectors
            norm_a = np.linalg.norm(vec_a)
            norm_b = np.linalg.norm(vec_b)

            if norm_a == 0.0 or norm_b == 0.0:
                return 0.0

            # Compute cosine similarity
            similarity = np.dot(vec_a, vec_b) / (norm_a * norm_b)

            # Clamp to [0, 1] range (negative similarities are not useful for recommendations)
            return float(max(0.0, min(1.0, similarity)))

        except Exception as e:
            logger.warning(f"Error computing cosine similarity: {str(e)}")
            return 0.0

    @timing_decorator(target_ms=50.0)
    def _rank_candidates(self, user_id: UUID, candidates: List[Dict]) -> List[Dict]:
        """
        Rank candidates using hybrid scoring.

        Hybrid score formula:
        score = w_collab*collab + w_content*content + w_graph*graph + w_quality*quality + w_recency*recency

        Default weights:
        - collaborative: 0.35
        - content: 0.30
        - graph: 0.20
        - quality: 0.10
        - recency: 0.05

        User-specific weights can override defaults from UserProfile.

        Args:
            user_id: User UUID
            candidates: List of candidate dictionaries

        Returns:
            List of ranked candidates with hybrid scores, sorted descending
        """
        try:
            # Get user profile for custom weights
            self.user_profile_service.get_or_create_profile(user_id)

            # Use default weights (user-specific weight overrides could be added to UserProfile in future)
            weights = self.default_weights.copy()

            # Get current timestamp for recency calculation
            current_time = datetime.utcnow()

            # Score each candidate
            scored_candidates = []

            # Batch query resources to avoid N+1 problem
            resource_ids = [candidate["resource_id"] for candidate in candidates]
            resources = (
                self.db.query(Resource)
                .filter(Resource.id.in_(resource_ids))
                .limit(1000)
                .all()
            )

            # Create resource lookup dict
            resource_dict = {resource.id: resource for resource in resources}

            for candidate in candidates:
                resource_id = candidate["resource_id"]

                # Get resource from dict
                resource = resource_dict.get(resource_id)
                if not resource:
                    continue

                # Extract individual scores (default to 0.0 if missing)
                collaborative_score = candidate.get("collaborative_score", 0.0)
                content_score = candidate.get("content_score", 0.0)
                graph_score = candidate.get("graph_score", 0.0)

                # Quality score
                quality_score = (
                    resource.quality_overall if resource.quality_overall else 0.5
                )

                # Recency score (based on publication year or date_created)
                recency_score = 0.5  # Default
                if resource.publication_year:
                    # Normalize publication year to [0, 1] range
                    # Assume years range from 1900 to current year
                    current_year = current_time.year
                    year_range = current_year - 1900
                    if year_range > 0:
                        recency_score = max(
                            0.0,
                            min(1.0, (resource.publication_year - 1900) / year_range),
                        )
                elif resource.date_created:
                    # Use date_created for recency
                    days_old = (current_time - resource.date_created).days
                    # Exponential decay: score = exp(-days_old / 365)
                    recency_score = max(0.0, min(1.0, np.exp(-days_old / 365.0)))

                # Compute hybrid score
                hybrid_score = (
                    weights["collaborative"] * collaborative_score
                    + weights["content"] * content_score
                    + weights["graph"] * graph_score
                    + weights["quality"] * quality_score
                    + weights["recency"] * recency_score
                )

                # Add to scored candidates
                scored_candidates.append(
                    {
                        "resource_id": resource_id,
                        "hybrid_score": hybrid_score,
                        "scores": {
                            "collaborative": collaborative_score,
                            "content": content_score,
                            "graph": graph_score,
                            "quality": quality_score,
                            "recency": recency_score,
                        },
                        "source_strategy": candidate.get("source_strategy", "unknown"),
                        "resource": resource,
                    }
                )

            # Sort by hybrid score descending
            scored_candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)

            logger.info(
                f"Ranked {len(scored_candidates)} candidates for user {user_id}"
            )
            return scored_candidates

        except Exception as e:
            logger.error(
                f"Error in _rank_candidates for user {user_id}: {str(e)}", exc_info=True
            )
            return []

    @timing_decorator(target_ms=30.0)
    def _apply_mmr(
        self, candidates: List[Dict], user_profile: UserProfile, limit: int
    ) -> List[Dict]:
        """
        Apply Maximal Marginal Relevance (MMR) for diversity optimization.

        MMR formula: MMR = λ*relevance - (1-λ)*max_similarity

        Where:
        - λ = user.diversity_preference (default 0.5)
        - relevance = hybrid_score
        - max_similarity = maximum cosine similarity to already-selected items

        Iteratively selects candidates that maximize MMR score.

        Args:
            candidates: List of scored candidate dictionaries
            user_profile: UserProfile instance
            limit: Number of recommendations to return

        Returns:
            List of diversified candidates
        """
        try:
            # Handle empty candidate list
            if not candidates:
                logger.warning("Empty candidate list for MMR")
                return []

            # Get lambda parameter from user profile preferences
            lambda_param = 0.5  # Default
            if user_profile and hasattr(user_profile, "diversity_preference"):
                lambda_param = user_profile.diversity_preference

            # Extract embeddings for all candidates
            candidate_embeddings = []
            valid_candidates = []

            for candidate in candidates:
                resource = candidate.get("resource")
                if not resource or not resource.embedding:
                    continue

                try:
                    # Parse embedding
                    if isinstance(resource.embedding, str):
                        embedding = json.loads(resource.embedding)
                    else:
                        embedding = resource.embedding

                    # Validate embedding
                    if len(embedding) != 768:
                        continue

                    candidate_embeddings.append(np.array(embedding))
                    valid_candidates.append(candidate)

                except Exception as e:
                    logger.debug(
                        f"Error parsing embedding for resource {resource.id}: {str(e)}"
                    )
                    continue

            # Handle case where no valid embeddings
            if not valid_candidates:
                logger.warning(
                    "No valid embeddings for MMR, returning top candidates by score"
                )
                return candidates[:limit]

            # MMR algorithm
            selected = []
            selected_embeddings = []
            remaining_indices = list(range(len(valid_candidates)))

            # Select first candidate (highest relevance)
            first_idx = 0
            selected.append(valid_candidates[first_idx])
            selected_embeddings.append(candidate_embeddings[first_idx])
            remaining_indices.remove(first_idx)

            # Iteratively select candidates maximizing MMR
            while len(selected) < limit and remaining_indices:
                best_mmr_score = -float("inf")
                best_idx = None

                for idx in remaining_indices:
                    candidate = valid_candidates[idx]
                    candidate_emb = candidate_embeddings[idx]

                    # Relevance score (hybrid score)
                    relevance = candidate["hybrid_score"]

                    # Compute max similarity to already-selected items
                    max_similarity = 0.0
                    for selected_emb in selected_embeddings:
                        similarity = self._cosine_similarity(
                            candidate_emb, selected_emb
                        )

                        # Validate similarity is finite
                        if not np.isfinite(similarity):
                            similarity = 0.0

                        max_similarity = max(max_similarity, similarity)

                    # Compute MMR score
                    mmr_score = (
                        lambda_param * relevance - (1 - lambda_param) * max_similarity
                    )

                    # Track best candidate
                    if mmr_score > best_mmr_score:
                        best_mmr_score = mmr_score
                        best_idx = idx

                # Add best candidate to selected
                if best_idx is not None:
                    selected.append(valid_candidates[best_idx])
                    selected_embeddings.append(candidate_embeddings[best_idx])
                    remaining_indices.remove(best_idx)
                else:
                    # No valid candidate found, break
                    break

            logger.info(
                f"MMR selected {len(selected)} diverse candidates (lambda={lambda_param})"
            )
            return selected

        except Exception as e:
            logger.error(f"Error in _apply_mmr: {str(e)}", exc_info=True)
            # Fallback: return top candidates by score
            return candidates[:limit]

    @timing_decorator(target_ms=20.0)
    def _apply_novelty_boost(
        self, candidates: List[Dict], user_profile: UserProfile
    ) -> List[Dict]:
        """
        Apply novelty boosting to promote lesser-known resources.

        Novelty score formula:
        novelty_score = 1.0 - (view_count / median_view_count)

        Boost formula (for resources with novelty_score > user.novelty_preference):
        hybrid_score *= (1.0 + 0.2 * novelty_score)

        Ensures at least 20% of recommendations are from outside top-viewed resources.

        Args:
            candidates: List of scored candidate dictionaries
            user_profile: UserProfile instance

        Returns:
            List of candidates with novelty boosting applied
        """
        try:
            if not candidates:
                return []

            # Get novelty preference from user profile preferences
            novelty_preference = 0.3  # Default
            if user_profile and hasattr(user_profile, "novelty_preference"):
                novelty_preference = user_profile.novelty_preference

            # Compute view counts for all candidates
            # Note: We don't have a view_count field in Resource model, so we'll use interaction counts as proxy
            resource_ids = [c["resource_id"] for c in candidates]

            # Batch query interaction counts for all resources to avoid N+1 problem
            view_count_results = (
                self.db.query(
                    UserInteraction.resource_id,
                    func.count(UserInteraction.id).label("count"),
                )
                .filter(
                    UserInteraction.resource_id.in_(resource_ids),
                    UserInteraction.interaction_type == "view",
                )
                .group_by(UserInteraction.resource_id)
                .all()
            )

            # Create view counts dict
            view_counts = {
                resource_id: count for resource_id, count in view_count_results
            }

            # Fill in zeros for resources with no views
            for resource_id in resource_ids:
                if resource_id not in view_counts:
                    view_counts[resource_id] = 0

            # Compute median view count
            view_count_values = list(view_counts.values())
            if view_count_values:
                median_view_count = float(np.median(view_count_values))
            else:
                median_view_count = 1.0

            # Avoid division by zero
            if median_view_count == 0:
                median_view_count = 1.0

            # Apply novelty boosting
            boosted_candidates = []
            novel_count = 0

            for candidate in candidates:
                resource_id = candidate["resource_id"]
                view_count = view_counts.get(resource_id, 0)

                # Compute novelty score
                novelty_score = 1.0 - (view_count / median_view_count)
                novelty_score = max(0.0, min(1.0, novelty_score))  # Clamp to [0, 1]

                # Apply boost if novelty score exceeds preference
                hybrid_score = candidate["hybrid_score"]
                if novelty_score > novelty_preference:
                    hybrid_score *= 1.0 + 0.2 * novelty_score
                    novel_count += 1

                # Update candidate
                boosted_candidate = candidate.copy()
                boosted_candidate["hybrid_score"] = hybrid_score
                boosted_candidate["novelty_score"] = novelty_score
                boosted_candidate["view_count"] = view_count

                boosted_candidates.append(boosted_candidate)

            # Re-sort by boosted hybrid score
            boosted_candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)

            # Ensure at least 20% are novel (from outside top-viewed)
            total_candidates = len(boosted_candidates)
            min_novel = int(total_candidates * 0.2)

            if novel_count < min_novel:
                # Find additional novel candidates and promote them
                novel_candidates = [
                    c for c in boosted_candidates if c["novelty_score"] > 0.5
                ]
                novel_candidates.sort(key=lambda x: x["novelty_score"], reverse=True)

                # Take top novel candidates to meet 20% threshold
                additional_novel = novel_candidates[: min_novel - novel_count]

                # Boost their scores to ensure they appear in results
                for candidate in additional_novel:
                    candidate["hybrid_score"] *= 1.5

                # Re-sort
                boosted_candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)

            logger.info(
                f"Applied novelty boosting: {novel_count}/{total_candidates} novel candidates (threshold={novelty_preference})"
            )
            return boosted_candidates

        except Exception as e:
            logger.error(f"Error in _apply_novelty_boost: {str(e)}", exc_info=True)
            # Fallback: return candidates unchanged
            return candidates

    @timing_decorator(target_ms=200.0)
    def generate_recommendations(
        self,
        user_id: UUID,
        limit: int = 20,
        strategy: str = "hybrid",
        filters: Optional[Dict] = None,
    ) -> Dict:
        """
        Generate personalized recommendations for a user.

        Main entry point for recommendation generation. Implements the full pipeline:
        1. Check user interaction count for collaborative filtering eligibility
        2. Generate candidates from selected strategies
        3. Rank candidates using hybrid scoring
        4. Apply MMR diversity optimization
        5. Apply novelty boosting
        6. Apply quality filtering
        7. Return recommendations with scores breakdown and metadata

        Args:
            user_id: User UUID
            limit: Number of recommendations to return (default: 20)
            strategy: Strategy to use ('collaborative', 'content', 'graph', 'hybrid')
            filters: Optional filters dict with keys:
                - min_quality: Minimum quality threshold (0.0-1.0)
                - exclude_outliers: Exclude quality outliers (bool)

        Returns:
            Dictionary with:
            - recommendations: List of recommendation dicts
            - metadata: Metadata about the recommendation process
        """
        try:
            logger.info(
                f"Generating recommendations for user {user_id} (limit={limit}, strategy={strategy})"
            )

            # Save the original requested strategy for metadata
            requested_strategy = strategy

            # Get or create user profile
            profile = self.user_profile_service.get_or_create_profile(user_id)

            # Check interaction count for cold start handling
            interaction_count = (
                self.db.query(func.count(UserInteraction.id))
                .filter(UserInteraction.user_id == user_id)
                .scalar()
            )

            is_cold_start = interaction_count < self.cold_start_threshold

            # Adjust strategy for cold start users
            if is_cold_start and strategy == "collaborative":
                logger.info(
                    f"Cold start user {user_id} (interactions={interaction_count}), switching to content+graph"
                )
                strategy = "hybrid"  # Will use content + graph only

            # Step 1: Generate candidates
            candidates = self._generate_candidates(user_id, strategy)

            if not candidates:
                logger.warning(f"No candidates generated for user {user_id}")
                return {
                    "recommendations": [],
                    "metadata": {
                        "total": 0,
                        "strategy": requested_strategy,  # Use the originally requested strategy
                        "is_cold_start": is_cold_start,
                        "diversity_applied": False,
                        "novelty_applied": False,
                        "gini_coefficient": 0.0,
                    },
                }

            # Step 2: Rank candidates using hybrid scoring
            scoring_start = time.time()
            ranked_candidates = self._rank_candidates(user_id, candidates)
            scoring_time = time.time() - scoring_start

            if not ranked_candidates:
                logger.warning(f"No ranked candidates for user {user_id}")
                return {
                    "recommendations": [],
                    "metadata": {
                        "total": 0,
                        "strategy": strategy,
                        "is_cold_start": is_cold_start,
                        "diversity_applied": False,
                        "novelty_applied": False,
                        "gini_coefficient": 0.0,
                    },
                }

            # Step 3: Apply quality filtering
            if filters:
                min_quality = filters.get("min_quality", 0.0)
                exclude_outliers = filters.get("exclude_outliers", True)

                filtered_candidates = []
                for candidate in ranked_candidates:
                    resource = candidate["resource"]

                    # Exclude quality outliers
                    if exclude_outliers and resource.is_quality_outlier:
                        continue

                    # Apply minimum quality threshold
                    quality = (
                        resource.quality_overall if resource.quality_overall else 0.5
                    )
                    if quality < min_quality:
                        continue

                    filtered_candidates.append(candidate)

                ranked_candidates = filtered_candidates
                logger.info(
                    f"Quality filtering: {len(ranked_candidates)} candidates remaining"
                )

            # Step 4: Apply MMR diversity optimization
            mmr_start = time.time()
            diversified_candidates = self._apply_mmr(
                ranked_candidates, profile, limit * 2
            )  # Get 2x for novelty boost
            mmr_time = time.time() - mmr_start

            # Step 5: Apply novelty boosting
            novelty_start = time.time()
            boosted_candidates = self._apply_novelty_boost(
                diversified_candidates, profile
            )
            novelty_time = time.time() - novelty_start

            # Step 6: Take top limit recommendations
            final_recommendations = boosted_candidates[:limit]

            # Step 7: Compute Gini coefficient for diversity measurement
            scores = [
                rec.get("hybrid_score", rec.get("score", 0.0))
                for rec in final_recommendations
            ]
            gini_coefficient = compute_gini_coefficient(scores)

            # Step 8: Format recommendations for response
            recommendations = []
            for rank, candidate in enumerate(final_recommendations, 1):
                resource = candidate["resource"]

                # Parse subject if it's a string (JSON)
                if resource.subject:
                    if isinstance(resource.subject, list):
                        pass
                    elif isinstance(resource.subject, str):
                        try:
                            json.loads(resource.subject)
                        except (json.JSONDecodeError, TypeError):
                            pass

                recommendations.append(
                    {
                        "resource_id": str(resource.id),
                        "title": resource.title,
                        "score": candidate["hybrid_score"],
                        "strategy": candidate["source_strategy"],
                        "scores": candidate["scores"],
                        "rank": rank,
                        "novelty_score": candidate.get("novelty_score", 0.0),
                        "view_count": candidate.get("view_count", 0),
                    }
                )

            # Metadata
            metadata = {
                "total": len(recommendations),
                "strategy": requested_strategy,  # Use the originally requested strategy
                "is_cold_start": is_cold_start,
                "interaction_count": interaction_count,
                "diversity_applied": True,
                "novelty_applied": True,
                "gini_coefficient": gini_coefficient,
                "diversity_preference": profile.diversity_preference
                if profile
                else 0.5,
                "novelty_preference": profile.novelty_preference if profile else 0.3,
            }

            logger.info(
                f"Generated {len(recommendations)} recommendations for user {user_id} (Gini={gini_coefficient:.3f})"
            )

            # Record recommendation metrics
            metrics.record_recommendation_request(
                candidate_count=len(candidates),
                scoring_time=scoring_time,
                mmr_time=mmr_time,
                novelty_time=novelty_time,
            )

            return {"recommendations": recommendations, "metadata": metadata}

        except Exception as e:
            logger.error(
                f"Error in generate_recommendations for user {user_id}: {str(e)}",
                exc_info=True,
            )
            return {
                "recommendations": [],
                "metadata": {
                    "total": 0,
                    "strategy": strategy,
                    "diversity_applied": False,
                    "novelty_applied": False,
                    "error": str(e),
                },
            }

        except Exception as e:
            logger.warning(f"Error computing Gini coefficient: {str(e)}")
            return 0.0
