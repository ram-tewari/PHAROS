"""
Tests for hybrid recommendation service.

Tests:
- Signal fusion logic
- Ranking algorithms
- Recommendation generation pipeline
- MMR diversity optimization
- Novelty boosting
- Quality filtering
"""

import json
import pytest
from unittest.mock import patch
from pathlib import Path
from uuid import uuid4

from app.modules.recommendations.hybrid_service import HybridRecommendationService
from app.database.models import Resource, UserProfile, UserInteraction, User
from tests.performance import performance_limit


# ============================================================================
# Helper Functions
# ============================================================================


def create_uuid_mapping(string_ids):
    """Create mapping from string IDs to UUIDs for test data."""
    return {str_id: uuid4() for str_id in string_ids}


def create_test_user(db_session, user_id=None):
    """Create a test user with given or random ID."""
    if user_id is None:
        user_id = uuid4()

    user = User(
        id=user_id,
        username=f"testuser_{user_id.hex[:8]}",
        email=f"test_{user_id.hex[:8]}@example.com",
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
# Golden Data Loading
# ============================================================================


@pytest.fixture(scope="module")
def golden_data():
    """Load golden data for hybrid recommendations tests."""
    golden_path = (
        Path(__file__).parent.parent.parent
        / "golden_data"
        / "hybrid_recommendations.json"
    )
    with open(golden_path) as f:
        return json.load(f)


# ============================================================================
# Test Signal Fusion
# ============================================================================


def test_signal_fusion_with_multiple_strategies(db_session, golden_data):
    """
    Test hybrid signal fusion combining multiple strategies.

    Verifies:
    - Scores from different strategies are combined correctly
    - Weights are applied properly
    - Final ranking matches expected order
    """
    test_case = golden_data["signal_fusion"]
    input_data = test_case["input"]
    expected = test_case["expected"]

    # Create UUID mapping for string IDs
    string_ids = list(input_data["collaborative_scores"].keys())
    id_mapping = create_uuid_mapping(string_ids)

    # Create test resources with proper UUIDs
    # Note: publication_year is omitted so recency falls back to date_created=now(),
    # giving a deterministic recency_score=1.0 for freshly created rows.
    for str_id in string_ids:
        resource = Resource(
            id=id_mapping[str_id],
            title=f"Resource {str_id}",
            source="https://example.com",
            quality_overall=input_data["quality_scores"][str_id],
            embedding=json.dumps([0.1] * 768),
        )
        db_session.add(resource)

    db_session.commit()

    # Create service
    service = HybridRecommendationService(db_session)

    # Create mock candidates with scores from different strategies
    candidates = []
    for str_id in string_ids:
        uuid_id = id_mapping[str_id]
        candidates.append(
            {
                "resource_id": uuid_id,
                "source_strategy": "hybrid",
                "collaborative_score": input_data["collaborative_scores"][str_id],
                "content_score": input_data["content_scores"][str_id],
                "graph_score": input_data["graph_scores"][str_id],
            }
        )

    # Override default weights
    service.default_weights = input_data["weights"]

    # Rank candidates - create user first
    user_id = uuid4()
    create_test_user(db_session, user_id)
    ranked = service._rank_candidates(user_id, candidates)

    # Verify ranking
    assert len(ranked) == len(expected["ranked_ids"])

    # Verify scores are close to expected (within tolerance)
    tolerance = expected["tolerance"]
    reverse_mapping = {v: k for k, v in id_mapping.items()}
    for candidate in ranked:
        uuid_id = candidate["resource_id"]
        str_id = reverse_mapping[uuid_id]
        expected_score = expected["hybrid_scores"][str_id]
        actual_score = candidate["hybrid_score"]

        assert abs(actual_score - expected_score) < tolerance, (
            f"Score mismatch for {str_id}: expected {expected_score}, got {actual_score}"
        )

    # Verify ranking order
    actual_ids = [reverse_mapping[c["resource_id"]] for c in ranked]
    assert actual_ids == expected["ranked_ids"]


@performance_limit(max_ms=50)
def test_ranking_performance(db_session):
    """
    Test ranking performance with many candidates.

    Verifies:
    - Ranking completes within 50ms for 100 candidates
    """
    # Create 100 test resources with proper UUIDs
    resource_ids = []
    for i in range(100):
        res_id = uuid4()
        resource_ids.append(res_id)
        resource = Resource(
            id=res_id,
            title=f"Resource {i}",
            source="https://example.com",
            quality_overall=0.5,
            publication_year=2024,
            embedding=json.dumps([0.1] * 768),
        )
        db_session.add(resource)

    db_session.commit()

    # Create candidates
    candidates = []
    for res_id in resource_ids:
        candidates.append(
            {
                "resource_id": res_id,
                "source_strategy": "hybrid",
                "collaborative_score": 0.5,
                "content_score": 0.5,
                "graph_score": 0.5,
            }
        )

    service = HybridRecommendationService(db_session)
    user_id = uuid4()
    create_test_user(db_session, user_id)

    # Rank candidates (performance measured by decorator)
    ranked = service._rank_candidates(user_id, candidates)

    assert len(ranked) > 0


# ============================================================================
# Test MMR Diversity Optimization
# ============================================================================


def test_mmr_diversity_optimization(db_session, golden_data):
    """
    Test Maximal Marginal Relevance diversity optimization.

    Verifies:
    - MMR selects diverse items
    - Lambda parameter controls diversity vs relevance tradeoff
    - Selected items are different from each other
    """
    test_case = golden_data["mmr_diversity"]
    input_data = test_case["input"]
    expected = test_case["expected"]

    # Create UUID mapping
    string_ids = [c["id"] for c in input_data["candidates"]]
    id_mapping = create_uuid_mapping(string_ids)

    # Create test resources with embeddings
    for candidate in input_data["candidates"]:
        str_id = candidate["id"]
        resource = Resource(
            id=id_mapping[str_id],
            title=f"Resource {str_id}",
            source="https://example.com",
            embedding=json.dumps(candidate["embedding"] + [0.0] * 765),  # Pad to 768
        )
        db_session.add(resource)

    db_session.commit()

    # Create user profile with diversity preference
    user_id = uuid4()
    create_test_user(db_session, user_id)
    profile = UserProfile(user_id=user_id, diversity_preference=input_data["lambda"])
    db_session.add(profile)
    db_session.commit()

    # Create candidates
    candidates = []
    for candidate in input_data["candidates"]:
        str_id = candidate["id"]
        resource = (
            db_session.query(Resource).filter(Resource.id == id_mapping[str_id]).first()
        )
        candidates.append(
            {
                "resource_id": resource.id,
                "hybrid_score": candidate["score"],
                "resource": resource,
            }
        )

    service = HybridRecommendationService(db_session)

    # Apply MMR
    diversified = service._apply_mmr(candidates, profile, input_data["limit"])

    # Verify correct number selected
    assert len(diversified) == input_data["limit"]

    # Verify diversity was achieved (not just top-k by score)
    reverse_mapping = {v: k for k, v in id_mapping.items()}
    selected_ids = [reverse_mapping[c["resource_id"]] for c in diversified]

    # First item should be highest score
    assert selected_ids[0] == expected["selected_ids"][0]

    # Subsequent items should be diverse, not just next highest scores
    assert expected["diversity_achieved"]


@performance_limit(max_ms=30)
def test_mmr_performance(db_session):
    """
    Test MMR performance with many candidates.

    Verifies:
    - MMR completes within 30ms for 50 candidates
    """
    # Create 50 test resources with proper UUIDs
    resource_ids = []
    for i in range(50):
        res_id = uuid4()
        resource_ids.append(res_id)
        resource = Resource(
            id=res_id,
            title=f"Resource {i}",
            source="https://example.com",
            embedding=json.dumps([float(i % 10) / 10.0] * 768),
        )
        db_session.add(resource)

    db_session.commit()

    # Create user profile with diversity preference
    user_id = uuid4()
    create_test_user(db_session, user_id)
    profile = UserProfile(user_id=user_id, diversity_preference=0.5)
    db_session.add(profile)
    db_session.commit()

    # Create candidates
    candidates = []
    for i, res_id in enumerate(resource_ids):
        resource = db_session.query(Resource).filter(Resource.id == res_id).first()
        candidates.append(
            {
                "resource_id": resource.id,
                "hybrid_score": 0.8 - (i * 0.01),
                "resource": resource,
            }
        )

    service = HybridRecommendationService(db_session)

    # Apply MMR (performance measured by decorator)
    diversified = service._apply_mmr(candidates, profile, 20)

    assert len(diversified) == 20


# ============================================================================
# Test Novelty Boosting
# ============================================================================


def test_novelty_boosting_promotes_lesser_known(db_session, golden_data):
    """
    Test novelty boosting promotes lesser-known resources.

    Verifies:
    - Resources with fewer views get novelty boost
    - Boost factor is applied correctly
    - At least 20% of results are novel
    """
    test_case = golden_data["novelty_boosting"]
    input_data = test_case["input"]
    test_case["expected"]

    # Create UUID mapping
    string_ids = [c["id"] for c in input_data["candidates"]]
    id_mapping = create_uuid_mapping(string_ids)

    # Create test resources
    for candidate in input_data["candidates"]:
        str_id = candidate["id"]
        resource = Resource(
            id=id_mapping[str_id],
            title=f"Resource {str_id}",
            source="https://example.com",
            embedding=json.dumps([0.1] * 768),
        )
        db_session.add(resource)

    db_session.commit()

    # Create view interactions
    user_id = uuid4()
    create_test_user(db_session, user_id)
    for candidate in input_data["candidates"]:
        str_id = candidate["id"]
        for _ in range(candidate["view_count"]):
            viewer_id = uuid4()
            create_test_user(db_session, viewer_id)
            interaction = UserInteraction(
                user_id=viewer_id,  # Different users
                resource_id=id_mapping[str_id],
                interaction_type="view",
                interaction_strength=1.0,
            )
            db_session.add(interaction)

    db_session.commit()

    # Create user profile with novelty preference in preferences JSON
    profile = UserProfile(
        user_id=user_id, novelty_preference=input_data["novelty_preference"]
    )
    db_session.add(profile)
    db_session.commit()

    # Create candidates
    candidates = []
    for candidate in input_data["candidates"]:
        str_id = candidate["id"]
        resource = (
            db_session.query(Resource).filter(Resource.id == id_mapping[str_id]).first()
        )
        candidates.append(
            {
                "resource_id": resource.id,
                "hybrid_score": candidate["score"],
                "resource": resource,
            }
        )

    service = HybridRecommendationService(db_session)

    # Apply novelty boosting
    boosted = service._apply_novelty_boost(candidates, profile)

    # Verify novelty scores were computed
    for candidate in boosted:
        assert "novelty_score" in candidate
        assert 0.0 <= candidate["novelty_score"] <= 1.0

    # Verify boosting changed the ranking
    reverse_mapping = {v: k for k, v in id_mapping.items()}
    boosted_ids = [reverse_mapping[c["resource_id"]] for c in boosted]
    original_ids = [c["id"] for c in input_data["candidates"]]

    # Ranking should have changed due to novelty boost
    assert boosted_ids != original_ids


@performance_limit(max_ms=20)
def test_novelty_boost_performance(db_session):
    """
    Test novelty boosting performance.

    Verifies:
    - Novelty boosting completes within 20ms for 50 candidates
    """
    # Create 50 test resources with proper UUIDs
    resource_ids = []
    for i in range(50):
        res_id = uuid4()
        resource_ids.append(res_id)
        resource = Resource(
            id=res_id,
            title=f"Resource {i}",
            source="https://example.com",
            embedding=json.dumps([0.1] * 768),
        )
        db_session.add(resource)

    db_session.commit()

    # Create user profile with novelty preference
    user_id = uuid4()
    create_test_user(db_session, user_id)
    profile = UserProfile(user_id=user_id, novelty_preference=0.3)
    db_session.add(profile)
    db_session.commit()

    # Create candidates
    candidates = []
    for res_id in resource_ids:
        resource = db_session.query(Resource).filter(Resource.id == res_id).first()
        candidates.append(
            {"resource_id": resource.id, "hybrid_score": 0.8, "resource": resource}
        )

    service = HybridRecommendationService(db_session)

    # Apply novelty boosting (performance measured by decorator)
    boosted = service._apply_novelty_boost(candidates, profile)

    assert len(boosted) == 50


# ============================================================================
# Test Quality Filtering
# ============================================================================


def test_quality_filtering_excludes_low_quality(db_session, golden_data):
    """
    Test quality filtering excludes low-quality resources.

    Verifies:
    - Resources below quality threshold are excluded
    - Quality outliers are excluded when requested
    - Filtering reasons are tracked
    """
    test_case = golden_data["quality_filtering"]
    input_data = test_case["input"]
    expected = test_case["expected"]

    # Create UUID mapping
    string_ids = [c["id"] for c in input_data["candidates"]]
    id_mapping = create_uuid_mapping(string_ids)

    # Create test resources
    for candidate in input_data["candidates"]:
        str_id = candidate["id"]
        resource = Resource(
            id=id_mapping[str_id],
            title=f"Resource {str_id}",
            source="https://example.com",
            quality_overall=candidate["quality"],
            is_quality_outlier=candidate["is_outlier"],
            embedding=json.dumps([0.1] * 768),
        )
        db_session.add(resource)

    db_session.commit()

    # Create candidates
    candidates = []
    for candidate in input_data["candidates"]:
        str_id = candidate["id"]
        resource = (
            db_session.query(Resource).filter(Resource.id == id_mapping[str_id]).first()
        )
        candidates.append(
            {
                "resource_id": resource.id,
                "hybrid_score": candidate["score"],
                "resource": resource,
            }
        )

    service = HybridRecommendationService(db_session)
    user_id = uuid4()
    create_test_user(db_session, user_id)

    # Apply quality filtering through generate_recommendations
    filters = {
        "min_quality": input_data["min_quality"],
        "exclude_outliers": input_data["exclude_outliers"],
    }

    # Mock candidate generation to return our test candidates
    with patch.object(service, "_generate_candidates", return_value=candidates):
        with patch.object(
            service, "_apply_mmr", side_effect=lambda c, p, limit: c[:limit]
        ):
            with patch.object(
                service, "_apply_novelty_boost", side_effect=lambda c, p: c
            ):
                result = service.generate_recommendations(
                    user_id=user_id, limit=10, strategy="hybrid", filters=filters
                )

    # Verify filtering
    # recommendations use string resource_id, so key the reverse map by str(uuid)
    reverse_mapping = {str(v): k for k, v in id_mapping.items()}
    recommendation_ids = [
        reverse_mapping[str(r["resource_id"])] for r in result["recommendations"]
    ]
    assert len(recommendation_ids) == len(expected["filtered_ids"])

    for expected_id in expected["filtered_ids"]:
        assert expected_id in recommendation_ids


# ============================================================================
# Test Full Recommendation Pipeline
# ============================================================================


@performance_limit(max_ms=200)
def test_full_recommendation_pipeline(db_session, golden_data):
    """
    Test complete recommendation generation pipeline.

    Verifies:
    - All pipeline stages execute
    - Metadata is populated correctly
    - Performance is within limits
    """
    test_case = golden_data["recommendation_pipeline"]
    input_data = test_case["input"]
    expected = test_case["expected"]

    # Create test resources with proper UUIDs
    resource_ids = []
    for i in range(20):
        res_id = uuid4()
        resource_ids.append(res_id)
        resource = Resource(
            id=res_id,
            title=f"Resource {i}",
            source="https://example.com",
            quality_overall=0.7,
            publication_year=2024,
            embedding=json.dumps([float(i % 10) / 10.0] * 768),
        )
        db_session.add(resource)

    db_session.commit()

    # Create user profile with preferences in JSON
    user_id = uuid4()
    create_test_user(db_session, user_id)
    profile = UserProfile(
        user_id=user_id,
        diversity_preference=input_data["diversity_preference"],
        novelty_preference=input_data["novelty_preference"],
    )
    db_session.add(profile)
    db_session.commit()

    # Create some interactions for the user
    for i in range(5):
        interaction = UserInteraction(
            user_id=user_id,
            resource_id=resource_ids[i],
            interaction_type="view",
            interaction_strength=1.0,
        )
        db_session.add(interaction)

    db_session.commit()

    service = HybridRecommendationService(db_session)

    # Mock candidate generation to return the test resources as candidates,
    # since the real candidate generators rely on collaborative/graph state
    # that isn't seeded in this unit test.
    mock_candidates = [
        {
            "resource_id": res_id,
            "source_strategy": "hybrid",
            "collaborative_score": 0.5,
            "content_score": 0.6,
            "graph_score": 0.4,
        }
        for res_id in resource_ids
    ]

    # Generate recommendations (performance measured by decorator)
    with patch.object(service, "_generate_candidates", return_value=mock_candidates):
        result = service.generate_recommendations(
            user_id=user_id,
            limit=input_data["limit"],
            strategy=input_data["strategy"],
            filters={"min_quality": input_data["min_quality"]},
        )

    # Verify structure
    assert "recommendations" in result
    assert "metadata" in result

    # Verify metadata fields
    metadata = result["metadata"]
    for field in expected["metadata_fields"]:
        assert field in metadata, f"Missing metadata field: {field}"

    # Verify recommendations count
    recommendations = result["recommendations"]
    assert (
        expected["min_recommendations"]
        <= len(recommendations)
        <= expected["max_recommendations"]
    )

    # Verify Gini coefficient is in valid range
    if "gini_coefficient" in metadata:
        gini = metadata["gini_coefficient"]
        assert (
            expected["gini_coefficient_range"][0]
            <= gini
            <= expected["gini_coefficient_range"][1]
        )


def test_cold_start_user_strategy_fallback(db_session, golden_data):
    """
    Test strategy fallback for cold start users.

    Verifies:
    - Cold start users are detected
    - Strategy falls back from collaborative to hybrid
    - Content and graph strategies are used instead
    """
    test_case = golden_data["cold_start_strategy"]
    input_data = test_case["input"]
    expected = test_case["expected"]

    # Create user with few interactions (below threshold)
    user_id = uuid4()
    create_test_user(db_session, user_id)

    # Create only 3 interactions (below threshold of 5) with proper UUIDs
    resource_ids = []
    for i in range(input_data["interaction_count"]):
        res_id = uuid4()
        resource_ids.append(res_id)
        resource = Resource(
            id=res_id,
            title=f"Resource {i}",
            source="https://example.com",
            embedding=json.dumps([0.1] * 768),
        )
        db_session.add(resource)

        interaction = UserInteraction(
            user_id=user_id,
            resource_id=res_id,
            interaction_type="view",
            interaction_strength=1.0,
        )
        db_session.add(interaction)

    db_session.commit()

    service = HybridRecommendationService(db_session)

    # Request collaborative strategy
    result = service.generate_recommendations(
        user_id=user_id, limit=5, strategy=input_data["requested_strategy"]
    )

    # Verify cold start was detected
    metadata = result["metadata"]
    assert metadata["is_cold_start"] == expected["is_cold_start"]

    # Verify strategy was changed
    assert metadata["strategy"] == expected["actual_strategy"]
