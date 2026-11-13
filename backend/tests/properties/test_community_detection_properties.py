"""
Property-based tests for community detection (Phase 20).

Tests universal properties that should hold for community detection:
- Property 15: Community assignment completeness
- Property 16: Modularity computation
- Property 17: Community detection performance
"""

import pytest
import time
from hypothesis import given, strategies as st, settings, HealthCheck
from sqlalchemy.orm import Session

from app.modules.graph.service import CommunityDetectionService
from app.database.models import Resource, GraphEdge


# ============================================================================
# Property 15: Community assignment completeness
# ============================================================================


@pytest.mark.asyncio
@given(
    num_resources=st.integers(min_value=2, max_value=20),
)
@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_property_community_assignment_completeness(
    num_resources,
    db_session,
):
    """
    Property 15: Community assignment completeness

    For any graph, community detection should assign every node to exactly one community.

    Validates: Requirements 5.2
    """
    # Create test resources
    resources = []
    for i in range(num_resources):
        resource = Resource(
            title=f"Test Resource {i}",
            type="ARTICLE",
            description=f"Description for resource {i}",
        )
        db_session.add(resource)
        resources.append(resource)

    db_session.commit()

    # Create some edges to form a graph
    for i in range(num_resources - 1):
        edge = GraphEdge(
            source_id=resources[i].id,
            target_id=resources[i + 1].id,
            edge_type="citation",
            weight=1.0,
            created_by="test_system",
        )
        db_session.add(edge)

    db_session.commit()

    # Run community detection
    community_service = CommunityDetectionService(db_session)
    resource_ids = [r.id for r in resources]  # Use UUID objects directly

    result = await community_service.detect_communities(
        resource_ids=resource_ids, resolution=1.0
    )

    # Property: All requested resources should have community assignments
    assert len(result["communities"]) == num_resources, (
        f"Expected {num_resources} community assignments, "
        f"got {len(result['communities'])}"
    )

    # Property: Every resource should be assigned to exactly one community
    assigned_resources = set(
        str(k) for k in result["communities"].keys()
    )  # Convert to strings for comparison
    expected_resources = set(str(rid) for rid in resource_ids)

    assert assigned_resources == expected_resources, (
        f"Community assignments don't match requested resources. "
        f"Missing: {expected_resources - assigned_resources}, "
        f"Extra: {assigned_resources - expected_resources}"
    )

    # Property: Community IDs should be non-negative integers
    for resource_id, community_id in result["communities"].items():
        assert isinstance(community_id, int), (
            f"Community ID for resource {resource_id} is not an integer: {community_id}"
        )
        assert community_id >= 0, (
            f"Community ID for resource {resource_id} is negative: {community_id}"
        )

    # Property: Number of communities should match unique community IDs
    unique_communities = set(result["communities"].values())
    assert result["num_communities"] == len(unique_communities), (
        f"num_communities ({result['num_communities']}) doesn't match "
        f"unique community IDs ({len(unique_communities)})"
    )

    # Property: Community sizes should sum to total resources
    total_size = sum(result["community_sizes"].values())
    assert total_size == num_resources, (
        f"Community sizes sum to {total_size}, expected {num_resources}"
    )


# ============================================================================
# Property 16: Modularity computation
# ============================================================================


@pytest.mark.asyncio
@given(
    num_resources=st.integers(min_value=2, max_value=20),
)
@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_property_modularity_computation(
    num_resources,
    db_session,
):
    """
    Property 16: Modularity computation

    For any detected community partition, the modularity score should be in the valid range [-1, 1].

    Validates: Requirements 5.3
    """
    # Create test resources
    resources = []
    for i in range(num_resources):
        resource = Resource(
            title=f"Test Resource {i}",
            type="ARTICLE",
            description=f"Description for resource {i}",
        )
        db_session.add(resource)
        resources.append(resource)

    db_session.commit()

    # Create edges to form a graph
    for i in range(num_resources - 1):
        edge = GraphEdge(
            source_id=resources[i].id,
            target_id=resources[i + 1].id,
            edge_type="citation",
            weight=1.0,
            created_by="test_system",
        )
        db_session.add(edge)

    db_session.commit()

    # Run community detection
    community_service = CommunityDetectionService(db_session)
    resource_ids = [r.id for r in resources]  # Use UUID objects directly

    result = await community_service.detect_communities(
        resource_ids=resource_ids, resolution=1.0
    )

    # Property: Modularity should be in valid range [-1, 1]
    modularity = result["modularity"]
    assert isinstance(modularity, (int, float)), (
        f"Modularity is not a number: {modularity}"
    )
    assert -1.0 <= modularity <= 1.0, (
        f"Modularity {modularity} is outside valid range [-1, 1]"
    )

    # Property: Higher modularity indicates better community structure
    # For a connected graph, modularity should be non-negative
    if num_resources > 2:
        assert modularity >= -0.5, (
            f"Modularity {modularity} is unexpectedly low for connected graph"
        )


# ============================================================================
# Property 17: Community detection performance
# ============================================================================


@pytest.mark.asyncio
@given(
    num_resources=st.integers(min_value=10, max_value=50),
)
@settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_property_community_detection_performance(
    num_resources,
    db_session,
):
    """
    Property 17: Community detection performance

    For any graph with 1000 nodes, community detection should complete within 10 seconds.

    Note: This test uses smaller graphs (10-50 nodes) for practical testing,
    but the performance requirement scales to 1000 nodes.

    Validates: Requirements 5.4
    """
    # Create test resources
    resources = []
    for i in range(num_resources):
        resource = Resource(
            title=f"Test Resource {i}",
            type="ARTICLE",
            description=f"Description for resource {i}",
        )
        db_session.add(resource)
        resources.append(resource)

    db_session.commit()

    # Create a denser graph for performance testing
    for i in range(num_resources):
        for j in range(i + 1, min(i + 5, num_resources)):
            edge = GraphEdge(
                source_id=resources[i].id,
                target_id=resources[j].id,
                edge_type="citation",
                weight=1.0,
                created_by="test_system",
            )
            db_session.add(edge)

    db_session.commit()

    # Measure community detection time
    community_service = CommunityDetectionService(db_session)
    resource_ids = [r.id for r in resources]  # Use UUID objects directly

    start_time = time.time()

    result = await community_service.detect_communities(
        resource_ids=resource_ids, resolution=1.0
    )

    elapsed_time = time.time() - start_time

    # Property: Community detection should complete within reasonable time
    # For 50 nodes, we expect < 1 second (scaled down from 10s for 1000 nodes)
    expected_time = 1.0 if num_resources <= 50 else 10.0

    assert elapsed_time < expected_time, (
        f"Community detection took {elapsed_time:.2f}s, "
        f"expected < {expected_time}s for {num_resources} nodes"
    )

    # Property: Result should be valid
    assert len(result["communities"]) == num_resources
    assert result["num_communities"] > 0
    assert -1.0 <= result["modularity"] <= 1.0
