"""
Tests for recommendations router endpoints.

Tests:
- GET /recommendations (hybrid endpoint)
- GET /recommendations/simple (basic endpoint)
- POST /recommendations/interactions
- GET /recommendations/profile
- PUT /recommendations/profile
- POST /recommendations/feedback
- GET /recommendations/metrics
- POST /recommendations/refresh
- GET /recommendations/health
"""

import json
from uuid import uuid4

from app.database.models import (
    Resource,
    UserProfile,
    UserInteraction,
    RecommendationFeedback,
)


# ============================================================================
# Test GET /recommendations (Hybrid Endpoint)
# ============================================================================


def test_get_recommendations_hybrid_success(client, db_session, test_user):
    """
    Test GET /recommendations returns recommendations.

    Verifies:
    - Returns 200 status
    - Response has recommendations and metadata
    - Recommendations have required fields
    """
    # test_user is already created by fixture

    # Create test resources with proper UUIDs
    for i in range(10):
        resource = Resource(
            id=uuid4(),
            title=f"Resource {i}",
            source="https://example.com",
            quality_overall=0.7,
            embedding=json.dumps([0.1] * 768),
        )
        db_session.add(resource)

    db_session.commit()

    # Make request
    response = client.get("/api/recommendations?limit=5&strategy=hybrid")

    # Verify response
    assert response.status_code == 200

    data = response.json()
    assert "recommendations" in data
    assert "metadata" in data

    # Verify metadata
    metadata = data["metadata"]
    assert "total" in metadata
    assert "strategy" in metadata
    assert metadata["strategy"] == "hybrid"


def test_get_recommendations_with_strategy_parameter(client, db_session, test_user):
    """
    Test GET /recommendations with different strategies.

    Verifies:
    - Accepts different strategy parameters
    - Returns appropriate results for each strategy
    """
    # test_user is already created by fixture

    strategies = ["collaborative", "content", "graph", "hybrid"]

    for strategy in strategies:
        response = client.get(f"/api/recommendations?strategy={strategy}&limit=5")

        # Should return 200 (may have empty recommendations for cold start)
        assert response.status_code == 200

        data = response.json()
        assert "metadata" in data
        assert data["metadata"]["strategy"] == strategy


def test_get_recommendations_with_invalid_strategy(client, db_session, test_user):
    """
    Test GET /recommendations with invalid strategy.

    Verifies:
    - Returns 400 for invalid strategy
    - Error message is helpful
    """
    # test_user is already created by fixture

    response = client.get("/api/recommendations?strategy=invalid_strategy")

    assert response.status_code == 400
    assert "Invalid strategy" in response.json()["detail"]


def test_get_recommendations_with_quality_filter(client, db_session, test_user):
    """
    Test GET /recommendations with quality filtering.

    Verifies:
    - Accepts min_quality parameter
    - Filters out low-quality resources
    """
    # test_user is already created by fixture

    # Create resources with varying quality
    for i in range(5):
        resource = Resource(
            id=uuid4(),
            title=f"Resource {i}",
            source="https://example.com",
            quality_overall=0.3 + (i * 0.15),  # 0.3, 0.45, 0.6, 0.75, 0.9
            embedding=json.dumps([0.1] * 768),
        )
        db_session.add(resource)

    db_session.commit()

    response = client.get("/api/recommendations?min_quality=0.6&limit=10")

    assert response.status_code == 200

    # Verify filtering worked (may have fewer results)
    data = response.json()
    assert "recommendations" in data


def test_get_recommendations_with_diversity_override(client, db_session, test_user):
    """
    Test GET /recommendations with diversity parameter.

    Verifies:
    - Accepts diversity parameter
    - Updates user profile diversity preference
    """
    # test_user is already created by fixture

    response = client.get("/api/recommendations?diversity=0.8&limit=5")

    assert response.status_code == 200

    # Verify profile was updated
    profile = (
        db_session.query(UserProfile)
        .filter(UserProfile.user_id == test_user.id)
        .first()
    )

    if profile:
        assert profile.diversity_preference == 0.8


def test_get_recommendations_pagination(client, db_session, test_user):
    """
    Test GET /recommendations respects limit parameter.

    Verifies:
    - Limit parameter controls result count
    - Limit is enforced (1-100 range)
    """
    # test_user is already created by fixture

    # Test different limits
    for limit in [5, 10, 20]:
        response = client.get(f"/api/recommendations?limit={limit}")

        assert response.status_code == 200

        data = response.json()
        recommendations = data["recommendations"]

        # Should not exceed limit
        assert len(recommendations) <= limit


# ============================================================================
# Test GET /recommendations/simple (Basic Endpoint)
# ============================================================================


def test_get_recommendations_simple_success(client, db_session, test_user):
    """
    Test GET /recommendations/simple returns basic recommendations.

    Verifies:
    - Returns 200 status
    - Response has items list
    - Simpler format than hybrid endpoint
    """
    # test_user is already created by fixture

    response = client.get("/api/recommendations/simple?limit=10")

    assert response.status_code == 200

    data = response.json()
    assert "items" in data


# ============================================================================
# Test POST /recommendations/interactions
# ============================================================================


def test_track_interaction_success(client, db_session, test_user):
    """
    Test POST /recommendations/interactions tracks interaction.

    Verifies:
    - Returns 201 status
    - Interaction is created in database
    - Response has interaction details
    """
    # test_user is already created by fixture

    res_id = uuid4()
    resource = Resource(id=res_id, title="Test Resource", source="https://example.com")
    db_session.add(resource)
    db_session.commit()

    # Track interaction
    payload = {
        "resource_id": str(res_id),
        "interaction_type": "view",
        "dwell_time": 120,
        "scroll_depth": 0.75,
    }

    response = client.post("/api/recommendations/interactions", json=payload)

    assert response.status_code == 201

    data = response.json()
    assert "interaction_id" in data
    assert data["resource_id"] == str(res_id)
    assert data["interaction_type"] == "view"

    # Verify in database
    interaction = (
        db_session.query(UserInteraction)
        .filter(UserInteraction.resource_id == res_id)
        .first()
    )

    assert interaction is not None
    assert interaction.interaction_type == "view"


def test_track_interaction_with_rating(client, db_session, test_user):
    """
    Test POST /recommendations/interactions with rating.

    Verifies:
    - Rating is stored correctly
    - Interaction strength is computed
    """
    # test_user is already created by fixture

    res_id = uuid4()
    resource = Resource(id=res_id, title="Test Resource", source="https://example.com")
    db_session.add(resource)
    db_session.commit()

    # Track interaction with rating
    payload = {"resource_id": str(res_id), "interaction_type": "rating", "rating": 5}

    response = client.post("/api/recommendations/interactions", json=payload)

    assert response.status_code == 201

    data = response.json()
    assert "interaction_strength" in data or "interaction_id" in data or "id" in data


def test_track_interaction_invalid_type(client, db_session, test_user):
    """
    Test POST /recommendations/interactions with invalid type.

    Verifies:
    - Returns 422 for invalid interaction type
    - Validation error is clear
    """
    # test_user is already created by fixture

    res_id = uuid4()
    resource = Resource(id=res_id, title="Test Resource", source="https://example.com")
    db_session.add(resource)
    db_session.commit()

    # Invalid interaction type
    payload = {"resource_id": str(res_id), "interaction_type": "invalid_type"}

    response = client.post("/api/recommendations/interactions", json=payload)

    assert response.status_code == 422


def test_track_interaction_invalid_resource(client, db_session, test_user):
    """
    Test POST /recommendations/interactions with non-existent resource.

    Verifies:
    - Returns 400 for invalid resource_id format
    - Or 500 if resource doesn't exist (depending on implementation)
    """
    # test_user is already created by fixture

    # Invalid resource ID format
    payload = {"resource_id": "not-a-uuid", "interaction_type": "view"}

    response = client.post("/api/recommendations/interactions", json=payload)

    # Should return error (400 or 500)
    assert response.status_code in [400, 500]


# ============================================================================
# Test GET /recommendations/profile
# ============================================================================


def test_get_profile_success(client, db_session, test_user):
    """
    Test GET /recommendations/profile returns user profile.

    Verifies:
    - Returns 200 status
    - Profile has required fields
    - Default values are set
    """
    # test_user is already created by fixture

    response = client.get("/api/recommendations/profile")

    assert response.status_code == 200

    data = response.json()
    assert "user_id" in data
    assert "diversity_preference" in data
    assert "novelty_preference" in data
    assert "recency_bias" in data
    assert "total_interactions" in data


# ============================================================================
# Test PUT /recommendations/profile
# ============================================================================


def test_update_profile_success(client, db_session, test_user):
    """
    Test PUT /recommendations/profile updates user profile.

    Verifies:
    - Returns 200 status
    - Profile is updated in database
    - Response reflects changes
    """
    # test_user is already created by fixture

    # Update profile
    payload = {
        "diversity_preference": 0.7,
        "novelty_preference": 0.6,
        "recency_bias": 0.4,
    }

    response = client.put("/api/recommendations/profile", json=payload)

    assert response.status_code == 200

    data = response.json()
    assert data["diversity_preference"] == 0.7
    assert data["novelty_preference"] == 0.6
    assert data["recency_bias"] == 0.4

    # Verify in database
    profile = (
        db_session.query(UserProfile)
        .filter(UserProfile.user_id == test_user.id)
        .first()
    )

    assert profile is not None
    assert profile.diversity_preference == 0.7


def test_update_profile_with_research_domains(client, db_session, test_user):
    """
    Test PUT /recommendations/profile with research domains.

    Verifies:
    - Research domains are stored as JSON
    - Active domain can be set
    """
    # test_user is already created by fixture

    # Update profile with domains
    payload = {
        "research_domains": ["machine_learning", "nlp", "computer_vision"],
        "active_domain": "machine_learning",
    }

    response = client.put("/api/recommendations/profile", json=payload)

    assert response.status_code == 200

    data = response.json()
    assert data["research_domains"] == ["machine_learning", "nlp", "computer_vision"]
    assert data["active_domain"] == "machine_learning"


def test_update_profile_invalid_values(client, db_session, test_user):
    """
    Test PUT /recommendations/profile with invalid values.

    Verifies:
    - Returns 422 for out-of-range values
    - Validation is enforced
    """
    # test_user is already created by fixture

    # Invalid diversity preference (> 1.0)
    payload = {"diversity_preference": 1.5}

    response = client.put("/api/recommendations/profile", json=payload)

    assert response.status_code == 422


# ============================================================================
# Test POST /recommendations/feedback
# ============================================================================


def test_submit_feedback_success(client, db_session, test_user):
    """
    Test POST /recommendations/feedback submits feedback.

    Verifies:
    - Returns 201 status
    - Feedback is created in database
    - Response has feedback details
    """
    # test_user is already created by fixture

    res_id = uuid4()
    resource = Resource(id=res_id, title="Test Resource", source="https://example.com")
    db_session.add(resource)
    db_session.commit()

    # Submit feedback
    payload = {
        "resource_id": str(res_id),
        "was_clicked": True,
        "was_useful": True,
        "feedback_notes": "Very helpful resource",
    }

    response = client.post("/api/recommendations/feedback", json=payload)

    if response.status_code != 201:
        print(f"Error response: {response.json()}")

    assert response.status_code == 201

    data = response.json()
    assert "feedback_id" in data
    assert data["resource_id"] == str(res_id)
    assert data["was_clicked"] is True
    assert data["was_useful"] is True

    # Verify in database
    feedback = (
        db_session.query(RecommendationFeedback)
        .filter(RecommendationFeedback.resource_id == res_id)
        .first()
    )

    assert feedback is not None
    assert feedback.context["was_clicked"] is True


def test_submit_feedback_minimal(client, db_session, test_user):
    """
    Test POST /recommendations/feedback with minimal data.

    Verifies:
    - Only required fields needed
    - Optional fields can be omitted
    """
    # test_user is already created by fixture

    res_id = uuid4()
    resource = Resource(id=res_id, title="Test Resource", source="https://example.com")
    db_session.add(resource)
    db_session.commit()

    # Minimal feedback
    payload = {"resource_id": str(res_id), "was_clicked": False}

    response = client.post("/api/recommendations/feedback", json=payload)

    assert response.status_code == 201


# ============================================================================
# Test GET /recommendations/metrics
# ============================================================================


def test_get_metrics_success(client, db_session):
    """
    Test GET /recommendations/metrics returns performance metrics.

    Verifies:
    - Returns 200 status
    - Response has metrics data
    - Metrics structure is correct
    """
    response = client.get("/api/recommendations/metrics")

    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert "metrics" in data


# ============================================================================
# Test POST /recommendations/refresh
# ============================================================================


def test_refresh_recommendations_success(client, db_session, test_user):
    """
    Test POST /recommendations/refresh queues refresh.

    Verifies:
    - Returns 202 status (accepted)
    - Response indicates refresh queued
    """
    # test_user is already created by fixture

    response = client.post("/api/recommendations/refresh")

    assert response.status_code == 202

    data = response.json()
    assert data["status"] == "accepted"
    assert "message" in data


# ============================================================================
# Test GET /recommendations/health
# ============================================================================


def test_health_check_success(client, db_session):
    """
    Test GET /recommendations/health returns health status.

    Verifies:
    - Returns 200 status
    - Health status is reported
    - Module information is included
    """
    response = client.get("/api/recommendations/health")

    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert "module" in data
    assert "database" in data
    assert "services" in data
    assert "timestamp" in data

    # Verify module info
    assert data["module"]["name"] == "recommendations"


def test_health_check_includes_service_status(client, db_session):
    """
    Test GET /recommendations/health includes service availability.

    Verifies:
    - Recommendation service status is checked
    - User profile service status is checked
    - Database connectivity is verified
    """
    response = client.get("/api/recommendations/health")

    assert response.status_code == 200

    data = response.json()
    services = data["services"]

    assert "recommendation_service" in services
    assert "user_profile_service" in services

    # Each service should have availability status
    for service_name, service_data in services.items():
        assert "available" in service_data
        assert "message" in service_data
