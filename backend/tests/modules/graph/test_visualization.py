"""
Unit tests for graph visualization service (Phase 20).

Tests specific examples and edge cases for graph layout computation.
"""

import pytest
from sqlalchemy.orm import Session

from app.modules.graph.service import GraphVisualizationService
from app.database.models import Resource, GraphEdge


@pytest.mark.asyncio
async def test_small_graph_force_layout(db_session):
    """
    Test force-directed layout for a small graph (10 nodes).

    Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5
    """
    # Create 10 resources
    resources = []
    for i in range(10):
        resource = Resource(
            title=f"Resource {i}",
            type="ARTICLE",
            description=f"Description {i}",
        )
        db_session.add(resource)
        resources.append(resource)

    db_session.commit()

    # Create edges to form a connected graph
    for i in range(9):
        edge = GraphEdge(
            source_id=resources[i].id,
            target_id=resources[i + 1].id,
            edge_type="citation",
            weight=1.0,
            created_by="test_system",
        )
        db_session.add(edge)

    db_session.commit()

    # Compute force-directed layout
    viz_service = GraphVisualizationService(db_session)
    result = await viz_service.compute_layout(
        resource_ids=[r.id for r in resources], layout_type="force"
    )

    # Verify result structure
    assert "layout" in result
    assert "computation_time_ms" in result
    assert "node_count" in result
    assert "edge_count" in result

    # Verify node count
    assert result["node_count"] == 10
    assert len(result["layout"].nodes) == 10

    # Verify edge count
    assert result["edge_count"] == 9
    assert len(result["layout"].edges) == 9

    # Verify all coordinates are in range
    for resource_id, position in result["layout"].nodes.items():
        assert 0 <= position.x <= 1000
        assert 0 <= position.y <= 1000

    # Verify layout type
    assert result["layout"].layout_type == "force"

    # Verify bounding box
    bounds = result["layout"].bounds
    assert bounds.min_x == 0.0
    assert bounds.max_x == 1000.0
    assert bounds.min_y == 0.0
    assert bounds.max_y == 1000.0


@pytest.mark.asyncio
async def test_medium_graph_hierarchical_layout(db_session):
    """
    Test hierarchical layout for a medium graph (100 nodes).

    Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5
    """
    # Create 100 resources
    resources = []
    for i in range(100):
        resource = Resource(
            title=f"Resource {i}",
            type="ARTICLE",
            description=f"Description {i}",
        )
        db_session.add(resource)
        resources.append(resource)

    db_session.commit()

    # Create edges to form a connected graph
    for i in range(99):
        edge = GraphEdge(
            source_id=resources[i].id,
            target_id=resources[i + 1].id,
            edge_type="citation",
            weight=1.0,
            created_by="test_system",
        )
        db_session.add(edge)

    db_session.commit()

    # Compute hierarchical layout
    viz_service = GraphVisualizationService(db_session)
    result = await viz_service.compute_layout(
        resource_ids=[r.id for r in resources], layout_type="hierarchical"
    )

    # Verify result structure
    assert result["node_count"] == 100
    assert result["edge_count"] == 99
    assert result["layout"].layout_type == "hierarchical"

    # Verify computation time is reasonable (<2s for 100 nodes)
    assert result["computation_time_ms"] < 2000

    # Verify all coordinates are in range
    for resource_id, position in result["layout"].nodes.items():
        assert 0 <= position.x <= 1000
        assert 0 <= position.y <= 1000


@pytest.mark.asyncio
async def test_circular_layout(db_session):
    """
    Test circular layout arrangement.

    Validates: Requirements 6.1, 6.2, 6.3, 6.5
    """
    # Create 12 resources (good for circular layout)
    resources = []
    for i in range(12):
        resource = Resource(
            title=f"Resource {i}",
            type="ARTICLE",
            description=f"Description {i}",
        )
        db_session.add(resource)
        resources.append(resource)

    db_session.commit()

    # Create edges
    for i in range(11):
        edge = GraphEdge(
            source_id=resources[i].id,
            target_id=resources[i + 1].id,
            edge_type="citation",
            weight=1.0,
            created_by="test_system",
        )
        db_session.add(edge)

    db_session.commit()

    # Compute circular layout
    viz_service = GraphVisualizationService(db_session)
    result = await viz_service.compute_layout(
        resource_ids=[r.id for r in resources], layout_type="circular"
    )

    # Verify result
    assert result["node_count"] == 12
    assert result["layout"].layout_type == "circular"

    # Verify all coordinates are in range
    for resource_id, position in result["layout"].nodes.items():
        assert 0 <= position.x <= 1000
        assert 0 <= position.y <= 1000


@pytest.mark.asyncio
async def test_invalid_layout_type(db_session):
    """
    Test that invalid layout type raises ValueError.

    Validates: Requirements 6.1
    """
    # Create a single resource
    resource = Resource(
        title="Test Resource",
        type="ARTICLE",
        description="Test description",
    )
    db_session.add(resource)
    db_session.commit()

    # Try invalid layout type
    viz_service = GraphVisualizationService(db_session)

    with pytest.raises(ValueError, match="Invalid layout_type"):
        await viz_service.compute_layout(
            resource_ids=[resource.id], layout_type="invalid_layout"
        )


@pytest.mark.asyncio
async def test_empty_resource_list(db_session):
    """
    Test that empty resource list raises ValueError.

    Validates: Requirements 6.1
    """
    viz_service = GraphVisualizationService(db_session)

    with pytest.raises(ValueError, match="resource_ids cannot be empty"):
        await viz_service.compute_layout(resource_ids=[], layout_type="force")


@pytest.mark.asyncio
async def test_layout_with_no_edges(db_session):
    """
    Test layout computation for nodes with no edges (isolated nodes).

    Validates: Requirements 6.1, 6.2, 6.3, 6.5
    """
    # Create 5 isolated resources (no edges)
    resources = []
    for i in range(5):
        resource = Resource(
            title=f"Isolated Resource {i}",
            type="ARTICLE",
            description=f"Description {i}",
        )
        db_session.add(resource)
        resources.append(resource)

    db_session.commit()

    # Compute layout without any edges
    viz_service = GraphVisualizationService(db_session)
    result = await viz_service.compute_layout(
        resource_ids=[r.id for r in resources], layout_type="force"
    )

    # Verify all nodes have positions
    assert result["node_count"] == 5
    assert len(result["layout"].nodes) == 5

    # Verify no edges
    assert result["edge_count"] == 0
    assert len(result["layout"].edges) == 0

    # Verify all coordinates are valid
    for resource_id, position in result["layout"].nodes.items():
        assert 0 <= position.x <= 1000
        assert 0 <= position.y <= 1000


@pytest.mark.asyncio
async def test_layout_determinism(db_session):
    """
    Test that layout computation is deterministic (same input = same output).

    Validates: Requirements 6.5
    """
    # Create resources
    resources = []
    for i in range(5):
        resource = Resource(
            title=f"Resource {i}",
            type="ARTICLE",
            description=f"Description {i}",
        )
        db_session.add(resource)
        resources.append(resource)

    db_session.commit()

    # Create edges
    for i in range(4):
        edge = GraphEdge(
            source_id=resources[i].id,
            target_id=resources[i + 1].id,
            edge_type="citation",
            weight=1.0,
            created_by="test_system",
        )
        db_session.add(edge)

    db_session.commit()

    # Compute layout twice
    viz_service = GraphVisualizationService(db_session)
    resource_ids = [r.id for r in resources]

    result1 = await viz_service.compute_layout(
        resource_ids=resource_ids, layout_type="force"
    )

    result2 = await viz_service.compute_layout(
        resource_ids=resource_ids, layout_type="force"
    )

    # Verify positions are identical (deterministic)
    for resource_id in resource_ids:
        pos1 = result1["layout"].nodes[resource_id]
        pos2 = result2["layout"].nodes[resource_id]

        # Allow small floating point differences
        assert abs(pos1.x - pos2.x) < 0.01, f"X coordinates differ for {resource_id}"
        assert abs(pos1.y - pos2.y) < 0.01, f"Y coordinates differ for {resource_id}"
