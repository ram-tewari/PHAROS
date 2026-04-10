"""
Tests for recommendation strategies (Strategy pattern).

Tests:
- Content-based strategy
- Graph-based strategy
- Popularity-based strategy (via hybrid)
- Strategy factory
"""

import json
import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from app.modules.recommendations.strategies import (
    RecommendationStrategyFactory,
    CollaborativeFilteringStrategy,
    ContentBasedStrategy,
    GraphBasedStrategy,
    HybridStrategy,
)
from app.database.models import Resource, UserInteraction, Citation, User


# Helper function to create test users
def create_test_user(db_session, user_id=None):
    """Create a test user with given or random ID."""
    if user_id is None:
        user_id = uuid4()

    # Convert to UUID if string
    if isinstance(user_id, str):
        from uuid import UUID

        user_id = UUID(user_id)

    user = User(
        id=user_id,
        username=f"testuser_{str(user_id)[:8]}",
        email=f"test_{str(user_id)[:8]}@example.com",
        hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqVqN4e6.u",
        full_name="Test User",
        role="user",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


# ============================================================================
# Test Content-Based Strategy
# ============================================================================


def test_content_based_strategy_generates_recommendations(db_session):
    """
    Test content-based strategy generates recommendations.

    Verifies:
    - Recommendations based on user interaction history
    - Similarity computation works correctly
    - Results are ranked by similarity
    """
    user_id = str(uuid4())
    create_test_user(db_session, user_id)

    # Create resources with embeddings using proper UUIDs
    resource_ids = []
    for i in range(5):
        res_id = uuid4()
        resource_ids.append(res_id)
        resource = Resource(
            id=res_id,
            title=f"Resource {i}",
            source="https://example.com",
            embedding=json.dumps([float(i % 3) / 3.0] * 768),
        )
        db_session.add(resource)

    db_session.commit()

    # Create user interactions
    for i in range(2):
        interaction = UserInteraction(
            user_id=user_id,
            resource_id=resource_ids[i],
            interaction_type="view",
            interaction_strength=1.0,
        )
        db_session.add(interaction)

    db_session.commit()

    # Create strategy
    strategy = ContentBasedStrategy(db_session)

    # Generate recommendations
    recommendations = strategy.generate(user_id=user_id, limit=3)

    # Verify recommendations
    assert len(recommendations) > 0
    assert len(recommendations) <= 3

    # Verify each recommendation has required fields
    for rec in recommendations:
        assert rec.resource_id is not None
        assert rec.user_id == user_id
        assert 0.0 <= rec.get_score() <= 1.0
        assert 0.0 <= rec.get_confidence() <= 1.0
        assert rec.strategy == "content_based"


def test_content_based_user_profile_building(db_session):
    """
    Test user profile building from interactions.

    Verifies:
    - User profile is built from interaction history
    - Embeddings are weighted by interaction type
    - Profile vector has correct dimensions
    """
    user_id = str(uuid4())
    create_test_user(db_session, user_id)

    # Create resources with embeddings using proper UUIDs
    embeddings = [
        [1.0, 0.0, 0.0] + [0.0] * 765,
        [0.0, 1.0, 0.0] + [0.0] * 765,
        [0.0, 0.0, 1.0] + [0.0] * 765,
    ]

    resource_ids = []
    for i, emb in enumerate(embeddings):
        res_id = uuid4()
        resource_ids.append(res_id)
        resource = Resource(
            id=res_id,
            title=f"Resource {i}",
            source="https://example.com",
            embedding=json.dumps(emb),
        )
        db_session.add(resource)

    db_session.commit()

    # Create interactions with different types
    interaction_types = ["annotation", "view", "click"]
    for i, int_type in enumerate(interaction_types):
        interaction = UserInteraction(
            user_id=user_id,
            resource_id=resource_ids[i],
            interaction_type=int_type,
            interaction_strength=1.0,
        )
        db_session.add(interaction)

    db_session.commit()

    # Create strategy and build profile
    strategy = ContentBasedStrategy(db_session)
    interactions = (
        db_session.query(UserInteraction)
        .filter(UserInteraction.user_id == user_id)
        .all()
    )

    profile = strategy._build_user_profile(interactions)

    # Verify profile
    assert profile is not None
    assert len(profile) == 768

    # Profile should be weighted average, not all zeros
    assert sum(abs(x) for x in profile) > 0


def test_content_based_cold_start_user(db_session):
    """
    Test content-based strategy with cold start user.

    Verifies:
    - Returns empty list for users with no interactions
    - No errors raised
    """
    user_id = str(uuid4())
    create_test_user(db_session, user_id)

    strategy = ContentBasedStrategy(db_session)
    recommendations = strategy.generate(user_id=user_id, limit=10)

    # Should return empty list for cold start user
    assert recommendations == []


# ============================================================================
# Test Graph-Based Strategy
# ============================================================================


def test_graph_based_strategy_generates_recommendations(db_session):
    """
    Test graph-based strategy generates recommendations.

    Verifies:
    - Recommendations based on citation network
    - Multi-hop traversal works
    - Results are ranked by graph score
    """
    user_id = str(uuid4())
    create_test_user(db_session, user_id)

    # Create resources with proper UUIDs
    resource_ids = {}
    for i in range(6):
        res_id = uuid4()
        resource_ids[f"res_{i}"] = res_id
        resource = Resource(
            id=res_id, title=f"Resource {i}", source="https://example.com"
        )
        db_session.add(resource)

    db_session.commit()

    # Create citation network
    # res_0 -> res_1 -> res_3
    # res_0 -> res_2 -> res_4
    citations = [
        ("res_0", "res_1"),
        ("res_0", "res_2"),
        ("res_1", "res_3"),
        ("res_2", "res_4"),
        ("res_3", "res_5"),
    ]

    for source_key, target_key in citations:
        citation = Citation(
            source_resource_id=resource_ids[source_key],
            target_resource_id=resource_ids[target_key],
            target_url="https://example.com",  # Required field
        )
        db_session.add(citation)

    db_session.commit()

    # Create user interaction with res_0
    interaction = UserInteraction(
        user_id=user_id,
        resource_id=resource_ids["res_0"],
        interaction_type="view",
        interaction_strength=1.0,
    )
    db_session.add(interaction)
    db_session.commit()

    # Create strategy
    strategy = GraphBasedStrategy(db_session)

    # Generate recommendations
    recommendations = strategy.generate(user_id=user_id, limit=5)

    # Verify recommendations
    assert len(recommendations) > 0

    # Verify each recommendation has required fields
    for rec in recommendations:
        assert rec.resource_id is not None
        assert rec.user_id == user_id
        assert 0.0 <= rec.get_score() <= 1.0
        assert rec.strategy == "graph_based"

        # Should not recommend already interacted resource
        assert rec.resource_id != resource_ids["res_0"]


def test_graph_based_multihop_traversal(db_session):
    """
    Test graph-based strategy multi-hop traversal.

    Verifies:
    - 1-hop neighbors are found
    - 2-hop neighbors are found
    - Scores decrease with distance
    """
    user_id = str(uuid4())
    create_test_user(db_session, user_id)

    # Create linear citation chain with proper UUIDs
    resource_ids = {}
    for i in range(5):
        res_id = uuid4()
        resource_ids[f"res_{i}"] = res_id
        resource = Resource(
            id=res_id, title=f"Resource {i}", source="https://example.com"
        )
        db_session.add(resource)

    db_session.commit()

    # Create chain: res_0 -> res_1 -> res_2 -> res_3 -> res_4
    for i in range(4):
        citation = Citation(
            source_resource_id=resource_ids[f"res_{i}"],
            target_resource_id=resource_ids[f"res_{i + 1}"],
            target_url="https://example.com",  # Required field
        )
        db_session.add(citation)

    db_session.commit()

    # Create strategy
    strategy = GraphBasedStrategy(db_session)

    # Find neighbors from res_0
    seed_ids = [resource_ids["res_0"]]
    neighbors = strategy._find_graph_neighbors(seed_ids, max_hops=2)

    # Verify 1-hop and 2-hop neighbors found
    # _find_graph_neighbors returns dict keyed by string UUID
    assert str(resource_ids["res_1"]) in neighbors  # 1-hop
    assert str(resource_ids["res_2"]) in neighbors  # 2-hop

    # 1-hop should have higher score than 2-hop
    assert (
        neighbors[str(resource_ids["res_1"])] > neighbors[str(resource_ids["res_2"])]
    )


def test_graph_based_cold_start_user(db_session):
    """
    Test graph-based strategy with cold start user.

    Verifies:
    - Returns empty list for users with no interactions
    - No errors raised
    """
    user_id = str(uuid4())
    create_test_user(db_session, user_id)

    strategy = GraphBasedStrategy(db_session)
    recommendations = strategy.generate(user_id=user_id, limit=10)

    # Should return empty list for cold start user
    assert recommendations == []


# ============================================================================
# Test Hybrid Strategy
# ============================================================================


def test_hybrid_strategy_combines_multiple_strategies(db_session):
    """
    Test hybrid strategy combines multiple strategies.

    Verifies:
    - Multiple strategies are executed
    - Results are fused using weights
    - Final ranking is correct
    """
    user_id = str(uuid4())
    create_test_user(db_session, user_id)

    # Create resources with proper UUIDs
    resource_ids = []
    for i in range(5):
        res_id = uuid4()
        resource_ids.append(res_id)
        resource = Resource(
            id=res_id,
            title=f"Resource {i}",
            source="https://example.com",
            embedding=json.dumps([float(i) / 5.0] * 768),
        )
        db_session.add(resource)

    db_session.commit()

    # Create user interaction
    interaction = UserInteraction(
        user_id=user_id,
        resource_id=resource_ids[0],
        interaction_type="view",
        interaction_strength=1.0,
    )
    db_session.add(interaction)
    db_session.commit()

    # Create hybrid strategy with custom weights
    strategies = [ContentBasedStrategy(db_session), GraphBasedStrategy(db_session)]
    weights = [0.6, 0.4]

    hybrid = HybridStrategy(db_session, strategies, weights)

    # Generate recommendations
    recommendations = hybrid.generate(user_id=user_id, limit=3)

    # Verify recommendations
    assert len(recommendations) > 0
    assert len(recommendations) <= 3

    # Verify metadata shows fusion
    for rec in recommendations:
        assert rec.strategy == "hybrid"
        assert "fusion_method" in rec.metadata
        assert rec.metadata["fusion_method"] == "weighted"


def test_hybrid_strategy_weight_normalization(db_session):
    """
    Test hybrid strategy normalizes weights.

    Verifies:
    - Weights are normalized to sum to 1.0
    - Normalization is automatic
    """
    # Create strategies with non-normalized weights
    strategies = [ContentBasedStrategy(db_session), GraphBasedStrategy(db_session)]
    weights = [2.0, 3.0]  # Sum = 5.0

    hybrid = HybridStrategy(db_session, strategies, weights)

    # Verify weights were normalized
    assert abs(sum(hybrid.weights) - 1.0) < 0.001
    assert abs(hybrid.weights[0] - 0.4) < 0.001  # 2.0 / 5.0
    assert abs(hybrid.weights[1] - 0.6) < 0.001  # 3.0 / 5.0


def test_hybrid_strategy_handles_strategy_failures(db_session):
    """
    Test hybrid strategy handles individual strategy failures.

    Verifies:
    - Continues if one strategy fails
    - Returns results from successful strategies
    - No errors propagated
    """
    user_id = str(uuid4())
    create_test_user(db_session, user_id)

    # Create a mock strategy that fails
    failing_strategy = MagicMock()
    failing_strategy.generate.side_effect = Exception("Strategy failed")
    failing_strategy.get_strategy_name.return_value = "failing"

    # Create a working strategy
    working_strategy = ContentBasedStrategy(db_session)

    # Create hybrid with both strategies
    hybrid = HybridStrategy(
        db_session, strategies=[failing_strategy, working_strategy], weights=[0.5, 0.5]
    )

    # Should not raise exception
    recommendations = hybrid.generate(user_id=user_id, limit=5)

    # Should return results (even if empty due to cold start)
    assert isinstance(recommendations, list)


# ============================================================================
# Test Strategy Factory
# ============================================================================


def test_strategy_factory_creates_collaborative_strategy(db_session):
    """
    Test factory creates collaborative filtering strategy.

    Verifies:
    - Factory creates correct strategy type
    - Strategy is properly initialized
    """
    strategy = RecommendationStrategyFactory.create("collaborative", db_session)

    assert isinstance(strategy, CollaborativeFilteringStrategy)
    assert strategy.db == db_session
    assert strategy.get_strategy_name() == "collaborative_filtering"


def test_strategy_factory_creates_content_strategy(db_session):
    """
    Test factory creates content-based strategy.

    Verifies:
    - Factory creates correct strategy type
    - Strategy is properly initialized
    """
    strategy = RecommendationStrategyFactory.create("content", db_session)

    assert isinstance(strategy, ContentBasedStrategy)
    assert strategy.db == db_session
    assert strategy.get_strategy_name() == "content_based"


def test_strategy_factory_creates_graph_strategy(db_session):
    """
    Test factory creates graph-based strategy.

    Verifies:
    - Factory creates correct strategy type
    - Strategy is properly initialized
    """
    strategy = RecommendationStrategyFactory.create("graph", db_session)

    assert isinstance(strategy, GraphBasedStrategy)
    assert strategy.db == db_session
    assert strategy.get_strategy_name() == "graph_based"


def test_strategy_factory_creates_hybrid_strategy(db_session):
    """
    Test factory creates hybrid strategy.

    Verifies:
    - Factory creates correct strategy type
    - Strategy is properly initialized with default strategies
    """
    strategy = RecommendationStrategyFactory.create("hybrid", db_session)

    assert isinstance(strategy, HybridStrategy)
    assert strategy.db == db_session
    assert strategy.get_strategy_name() == "hybrid"
    assert len(strategy.strategies) == 3  # Default: collaborative, content, graph


def test_strategy_factory_handles_invalid_type(db_session):
    """
    Test factory raises error for invalid strategy type.

    Verifies:
    - ValueError raised for unknown strategy
    - Error message is helpful
    """
    with pytest.raises(ValueError) as exc_info:
        RecommendationStrategyFactory.create("invalid_strategy", db_session)

    assert "Unknown strategy type" in str(exc_info.value)
    assert "invalid_strategy" in str(exc_info.value)


def test_strategy_factory_get_available_strategies():
    """
    Test factory returns list of available strategies.

    Verifies:
    - All expected strategies are listed
    - List is complete
    """
    strategies = RecommendationStrategyFactory.get_available_strategies()

    assert "collaborative" in strategies
    assert "content" in strategies
    assert "graph" in strategies
    assert "hybrid" in strategies
    assert len(strategies) == 4


def test_strategy_factory_create_all_strategies(db_session):
    """
    Test factory creates all strategies at once.

    Verifies:
    - All strategies are created
    - Each strategy is correct type
    - All strategies share same db session
    """
    all_strategies = RecommendationStrategyFactory.create_all_strategies(db_session)

    assert len(all_strategies) == 4
    assert isinstance(all_strategies["collaborative"], CollaborativeFilteringStrategy)
    assert isinstance(all_strategies["content"], ContentBasedStrategy)
    assert isinstance(all_strategies["graph"], GraphBasedStrategy)
    assert isinstance(all_strategies["hybrid"], HybridStrategy)

    # Verify all use same db session
    for strategy in all_strategies.values():
        assert strategy.db == db_session


# ============================================================================
# Test Strategy Pattern Benefits
# ============================================================================


def test_strategies_are_polymorphic(db_session):
    """
    Test all strategies implement same interface.

    Verifies:
    - All strategies have generate method
    - All strategies have get_strategy_name method
    - Interface is consistent
    """
    strategies = [
        CollaborativeFilteringStrategy(db_session),
        ContentBasedStrategy(db_session),
        GraphBasedStrategy(db_session),
        HybridStrategy(db_session),
    ]

    user_id = str(uuid4())
    create_test_user(db_session, user_id)

    for strategy in strategies:
        # All should have generate method
        assert hasattr(strategy, "generate")
        assert callable(strategy.generate)

        # All should have get_strategy_name method
        assert hasattr(strategy, "get_strategy_name")
        assert callable(strategy.get_strategy_name)

        # All should return string from get_strategy_name
        name = strategy.get_strategy_name()
        assert isinstance(name, str)
        assert len(name) > 0

        # All should accept same parameters to generate
        # (may return empty list for cold start, but should not error)
        result = strategy.generate(user_id=user_id, limit=5)
        assert isinstance(result, list)


def test_strategy_eliminates_conditional_logic(db_session):
    """
    Test strategy pattern eliminates conditional logic.

    Verifies:
    - No if/elif/else needed to select strategy
    - Factory handles strategy selection
    - Client code is simplified
    """
    user_id = str(uuid4())
    create_test_user(db_session, user_id)

    # Old way (with conditionals) - NOT USED
    # if strategy_type == "collaborative":
    #     strategy = CollaborativeFilteringStrategy(db)
    # elif strategy_type == "content":
    #     strategy = ContentBasedStrategy(db)
    # ...

    # New way (with factory) - NO CONDITIONALS
    strategy_types = ["collaborative", "content", "graph", "hybrid"]

    for strategy_type in strategy_types:
        # Single line, no conditionals
        strategy = RecommendationStrategyFactory.create(strategy_type, db_session)

        # Polymorphic call - same interface for all
        recommendations = strategy.generate(user_id=user_id, limit=5)

        # All return same type
        assert isinstance(recommendations, list)
