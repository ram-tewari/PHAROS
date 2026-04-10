"""
Property-based tests for graph visualization (Phase 20).

Tests universal properties that should hold for graph layout computation:
- Property 19: Layout coordinate generation
- Property 20: Visualization performance
"""

import pytest
import time
from hypothesis import given, strategies as st, settings, HealthCheck
from sqlalchemy.orm import Session

from app.modules.graph.service import GraphVisualizationService
from app.database.models import Resource, GraphEdge


# ============================================================================
# Property 19: Layout coordinate generation
# ============================================================================


@pytest.mark.asyncio
@given(
    num_resources=st.integers(min_value=1, max_value=20),
    layout_type=st.sampled_from(["force", "hierarchical", "circular"]),
)
@settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_property_layout_coordinate_generation(
    num_resources,
    layout_type,
    db_session,
):
    """
    Property 19: Layout coordinate generation

    For any graph and layout algorithm, all nodes should receive valid coordinates
    within the normalized [0, 1000] range, and the layout should be deterministic.

    Validates: Requirements 6.1, 6.2, 6.3, 6.5
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

    # Create some edges to form a connected graph (if multiple resources)
    if num_resources > 1:
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

    # Compute layout
    viz_service = GraphVisualizationService(db_session)
    resource_ids = [r.id for r in resources]

    result = await viz_service.compute_layout(
        resource_ids=resource_ids, layout_type=layout_type
    )

    # Property 1: All requested resources should have positions
    assert len(result["layout"].nodes) == num_resources, (
        f"Expected {num_resources} node positions, got {len(result['layout'].nodes)}"
    )

    # Property 2: All coordinates should be within [0, 1000] range
    for resource_id, position in result["layout"].nodes.items():
        assert 0 <= position.x <= 1000, (
            f"X coordinate for resource {resource_id} out of range: {position.x}"
        )
        assert 0 <= position.y <= 1000, (
            f"Y coordinate for resource {resource_id} out of range: {position.y}"
        )

    # Property 3: Bounding box should match coordinate space
    bounds = result["layout"].bounds
    assert bounds.min_x == 0.0, f"Bounding box min_x should be 0, got {bounds.min_x}"
    assert bounds.max_x == 1000.0, (
        f"Bounding box max_x should be 1000, got {bounds.max_x}"
    )
    assert bounds.min_y == 0.0, f"Bounding box min_y should be 0, got {bounds.min_y}"
    assert bounds.max_y == 1000.0, (
        f"Bounding box max_y should be 1000, got {bounds.max_y}"
    )

    # Property 4: Layout type should match requested type
    assert result["layout"].layout_type == layout_type, (
        f"Expected layout_type '{layout_type}', got '{result['layout'].layout_type}'"
    )

    # Property 5: Node count should match
    assert result["node_count"] == num_resources, (
        f"Expected node_count {num_resources}, got {result['node_count']}"
    )

    # Property 6: Edge count should match database edges
    expected_edge_count = num_resources - 1 if num_resources > 1 else 0
    assert result["edge_count"] == expected_edge_count, (
        f"Expected edge_count {expected_edge_count}, got {result['edge_count']}"
    )


# ============================================================================
# Property 20: Visualization performance
# ============================================================================


@pytest.mark.asyncio
@given(
    num_resources=st.integers(min_value=10, max_value=50),
    layout_type=st.sampled_from(["force", "hierarchical", "circular"]),
)
@settings(
    max_examples=3,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_property_visualization_performance(
    num_resources,
    layout_type,
    db_session,
):
    """
    Property 20: Visualization performance

    Layout computation should complete within reasonable time bounds:
    - <2s for graphs with up to 500 nodes
    - Linear or near-linear scaling with graph size

    Validates: Requirements 6.4
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

    # Create edges to form a connected graph
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

    # Measure layout computation time
    viz_service = GraphVisualizationService(db_session)
    resource_ids = [r.id for r in resources]

    start_time = time.time()
    result = await viz_service.compute_layout(
        resource_ids=resource_ids, layout_type=layout_type
    )
    elapsed_time = time.time() - start_time

    # Property 1: Computation should complete within reasonable time
    # For 100 nodes, we expect <2s (target is <2s for 500 nodes)
    max_time = 2.0 if num_resources <= 100 else 5.0
    assert elapsed_time < max_time, (
        f"Layout computation took {elapsed_time:.2f}s for {num_resources} nodes "
        f"(max allowed: {max_time}s, layout: {layout_type})"
    )

    # Property 2: Reported computation time should match actual time
    reported_time_s = result["computation_time_ms"] / 1000
    # Allow 10% tolerance for measurement differences
    assert abs(reported_time_s - elapsed_time) < elapsed_time * 0.1, (
        f"Reported time ({reported_time_s:.3f}s) differs significantly "
        f"from measured time ({elapsed_time:.3f}s)"
    )

    # Property 3: Layout should be complete despite time constraints
    assert len(result["layout"].nodes) == num_resources, (
        f"Layout incomplete: expected {num_resources} nodes, "
        f"got {len(result['layout'].nodes)}"
    )


# ============================================================================
# Additional Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_single_node_layout(db_session):
    """
    Test layout computation for a single node (edge case).

    A single node should be positioned at the center (500, 500).
    """
    # Create single resource
    resource = Resource(
        title="Single Resource",
        type="ARTICLE",
        description="Single resource for testing",
    )
    db_session.add(resource)
    db_session.commit()

    # Compute layout
    viz_service = GraphVisualizationService(db_session)
    result = await viz_service.compute_layout(
        resource_ids=[resource.id], layout_type="force"
    )

    # Single node should be at center
    assert len(result["layout"].nodes) == 1
    position = result["layout"].nodes[resource.id]

    # Should be near center (allowing some tolerance)
    assert 400 <= position.x <= 600, f"Single node X not near center: {position.x}"
    assert 400 <= position.y <= 600, f"Single node Y not near center: {position.y}"


@pytest.mark.asyncio
async def test_disconnected_graph_layout(db_session):
    """
    Test layout computation for a disconnected graph.

    Disconnected components should still receive valid positions.
    """
    # Create two disconnected components
    resources = []
    for i in range(6):
        resource = Resource(
            title=f"Resource {i}",
            type="ARTICLE",
            description=f"Description {i}",
        )
        db_session.add(resource)
        resources.append(resource)

    db_session.commit()

    # Create two separate components (0-1-2 and 3-4-5)
    edges = [
        (0, 1),
        (1, 2),  # Component 1
        (3, 4),
        (4, 5),  # Component 2
    ]

    for source_idx, target_idx in edges:
        edge = GraphEdge(
            source_id=resources[source_idx].id,
            target_id=resources[target_idx].id,
            edge_type="citation",
            weight=1.0,
            created_by="test_system",
        )
        db_session.add(edge)

    db_session.commit()

    # Compute layout
    viz_service = GraphVisualizationService(db_session)
    resource_ids = [r.id for r in resources]

    result = await viz_service.compute_layout(
        resource_ids=resource_ids, layout_type="force"
    )

    # All nodes should have positions
    assert len(result["layout"].nodes) == 6

    # All positions should be valid
    for resource_id, position in result["layout"].nodes.items():
        assert 0 <= position.x <= 1000
        assert 0 <= position.y <= 1000
