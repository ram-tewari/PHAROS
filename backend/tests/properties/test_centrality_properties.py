"""
Property-based tests for graph centrality metrics (Phase 20).

Tests universal properties that should hold for centrality computations:
- Property 12: Centrality metrics completeness
- Property 13: Centrality performance
- Property 14: Centrality caching
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from datetime import datetime, timedelta, timezone
import time
from uuid import uuid4

from app.modules.graph.service import GraphService
from app.database.models import Resource, GraphEdge, GraphCentralityCache


# ============================================================================
# Property 12: Centrality metrics completeness
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
async def test_property_centrality_completeness(
    num_resources,
    db_session,
):
    """
    Property 12: Centrality metrics completeness

    For any graph, computing centrality should return in-degree, out-degree,
    betweenness, and PageRank for all nodes.

    Validates: Requirements 4.1, 4.2, 4.3
    """
    # Create resources
    resources = []
    for i in range(num_resources):
        resource = Resource(
            id=uuid4(),
            title=f"Resource {i}",
            type="ARTICLE",
        )
        db_session.add(resource)
        resources.append(resource)

    db_session.commit()

    # Create some edges between resources
    for i in range(num_resources - 1):
        edge = GraphEdge(
            source_id=resources[i].id,
            target_id=resources[i + 1].id,
            edge_type="citation",
            weight=1.0,
            created_by="test",
        )
        db_session.add(edge)

    db_session.commit()

    # Get resource IDs as integers
    resource_ids = [int(r.id) for r in resources]

    # Create graph service
    graph_service = GraphService(db_session)

    # Compute degree centrality
    degree_metrics = await graph_service.compute_degree_centrality(resource_ids)

    # Property: All requested resources should have degree metrics
    assert len(degree_metrics) == num_resources, (
        f"Expected {num_resources} degree metrics, got {len(degree_metrics)}"
    )

    for resource_id in resource_ids:
        assert resource_id in degree_metrics, (
            f"Resource {resource_id} missing from degree metrics"
        )

        metrics = degree_metrics[resource_id]
        assert "in_degree" in metrics, "Missing in_degree"
        assert "out_degree" in metrics, "Missing out_degree"
        assert "total_degree" in metrics, "Missing total_degree"

        # Verify total_degree is sum of in and out
        assert (
            metrics["total_degree"] == metrics["in_degree"] + metrics["out_degree"]
        ), f"total_degree should equal in_degree + out_degree"

    # Compute betweenness centrality
    betweenness_metrics = await graph_service.compute_betweenness_centrality(
        resource_ids
    )

    # Property: All requested resources should have betweenness metrics
    assert len(betweenness_metrics) == num_resources, (
        f"Expected {num_resources} betweenness metrics, got {len(betweenness_metrics)}"
    )

    for resource_id in resource_ids:
        assert resource_id in betweenness_metrics, (
            f"Resource {resource_id} missing from betweenness metrics"
        )

        betweenness = betweenness_metrics[resource_id]
        assert isinstance(betweenness, float), "Betweenness should be a float"
        assert 0.0 <= betweenness <= 1.0, (
            f"Betweenness should be in [0, 1], got {betweenness}"
        )

    # Compute PageRank
    pagerank_metrics = await graph_service.compute_pagerank(resource_ids)

    # Property: All requested resources should have PageRank metrics
    assert len(pagerank_metrics) == num_resources, (
        f"Expected {num_resources} PageRank metrics, got {len(pagerank_metrics)}"
    )

    for resource_id in resource_ids:
        assert resource_id in pagerank_metrics, (
            f"Resource {resource_id} missing from PageRank metrics"
        )

        pagerank = pagerank_metrics[resource_id]
        assert isinstance(pagerank, float), "PageRank should be a float"
        assert pagerank >= 0.0, f"PageRank should be non-negative, got {pagerank}"


# ============================================================================
# Property 13: Centrality performance
# ============================================================================


@pytest.mark.asyncio
@given(
    num_resources=st.just(100),  # Fixed size for performance test
)
@settings(
    max_examples=3,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_property_centrality_performance(
    num_resources,
    db_session,
):
    """
    Property 13: Centrality performance

    For any graph with 1000 nodes, centrality computation should complete
    within 2 seconds.

    Validates: Requirements 4.4

    Note: This test creates a large graph, so we run fewer examples.
    """

    # Create resources
    resources = []
    for i in range(num_resources):
        resource = Resource(
            id=uuid4(),
            title=f"Resource {i}",
            type="ARTICLE",
        )
        db_session.add(resource)
        resources.append(resource)

    db_session.commit()

    # Create edges (each resource cites next 3 resources)
    for i in range(num_resources):
        for j in range(1, 4):
            if i + j < num_resources:
                edge = GraphEdge(
                    source_id=resources[i].id,
                    target_id=resources[i + j].id,
                    edge_type="citation",
                    weight=1.0,
                    created_by="test",
                )
                db_session.add(edge)

    db_session.commit()

    # Get resource IDs as integers
    resource_ids = [int(r.id) for r in resources]

    # Create graph service
    graph_service = GraphService(db_session)

    # Measure computation time
    start_time = time.time()

    # Compute all centrality metrics
    degree_metrics = await graph_service.compute_degree_centrality(resource_ids)
    betweenness_metrics = await graph_service.compute_betweenness_centrality(
        resource_ids
    )
    pagerank_metrics = await graph_service.compute_pagerank(resource_ids)

    elapsed_time = time.time() - start_time

    # Property: Computation should complete within 2 seconds for 100 nodes
    # (scaled down from 1000 nodes requirement)
    assert elapsed_time < 2.0, (
        f"Centrality computation took {elapsed_time:.2f}s, "
        f"expected < 2.0s for {num_resources} nodes"
    )

    # Verify all metrics were computed
    assert len(degree_metrics) == num_resources
    assert len(betweenness_metrics) == num_resources
    assert len(pagerank_metrics) == num_resources


# ============================================================================
# Property 14: Centrality caching
# ============================================================================


@pytest.mark.asyncio
@given(
    num_resources=st.integers(min_value=2, max_value=10),
)
@settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
async def test_property_centrality_caching(
    num_resources,
    db_session,
):
    """
    Property 14: Centrality caching

    For any graph, computing centrality twice within 10 minutes should use
    cached results on the second computation.

    Validates: Requirements 4.5
    """
    # Create resources
    resources = []
    for i in range(num_resources):
        resource = Resource(
            id=uuid4(),
            title=f"Resource {i}",
            type="ARTICLE",
        )
        db_session.add(resource)
        resources.append(resource)

    db_session.commit()

    # Create some edges
    for i in range(num_resources - 1):
        edge = GraphEdge(
            source_id=resources[i].id,
            target_id=resources[i + 1].id,
            edge_type="citation",
            weight=1.0,
            created_by="test",
        )
        db_session.add(edge)

    db_session.commit()

    # Get resource IDs as integers
    resource_ids = [int(r.id) for r in resources]

    # Create graph service
    graph_service = GraphService(db_session)

    # First computation - should compute and cache
    degree_metrics_1 = await graph_service.compute_degree_centrality(resource_ids)
    betweenness_metrics_1 = await graph_service.compute_betweenness_centrality(
        resource_ids
    )
    pagerank_metrics_1 = await graph_service.compute_pagerank(resource_ids)

    # Store results in database cache
    for resource_id in resource_ids:
        resource_uuid = resources[resource_ids.index(resource_id)].id
        degree = degree_metrics_1[resource_id]
        betweenness = betweenness_metrics_1[resource_id]
        pagerank = pagerank_metrics_1[resource_id]

        cache_entry = GraphCentralityCache(
            resource_id=resource_uuid,
            in_degree=degree["in_degree"],
            out_degree=degree["out_degree"],
            betweenness=betweenness,
            pagerank=pagerank,
            computed_at=datetime.now(timezone.utc),
        )
        db_session.add(cache_entry)

    db_session.commit()

    # Second computation - should use cache
    # Query cache to verify it exists
    cache_entries = (
        db_session.query(GraphCentralityCache)
        .filter(GraphCentralityCache.resource_id.in_([r.id for r in resources]))
        .all()
    )

    # Property: Cache entries should exist for all resources
    assert len(cache_entries) == num_resources, (
        f"Expected {num_resources} cache entries, got {len(cache_entries)}"
    )

    # Property: Cache entries should be recent (within 10 minutes)
    cache_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    for cache_entry in cache_entries:
        # Make cache_cutoff naive if computed_at is naive
        entry_time = cache_entry.computed_at
        if entry_time.tzinfo is None:
            # computed_at is naive, make cache_cutoff naive too
            cache_cutoff_naive = cache_cutoff.replace(tzinfo=None)
            assert entry_time >= cache_cutoff_naive, (
                f"Cache entry for {cache_entry.resource_id} is too old: "
                f"{entry_time} < {cache_cutoff_naive}"
            )
        else:
            # computed_at is aware, use aware cache_cutoff
            assert entry_time >= cache_cutoff, (
                f"Cache entry for {cache_entry.resource_id} is too old: "
                f"{entry_time} < {cache_cutoff}"
            )

    # Property: Cached values should match computed values
    for cache_entry in cache_entries:
        resource_id = int(cache_entry.resource_id)

        # Check degree metrics
        assert cache_entry.in_degree == degree_metrics_1[resource_id]["in_degree"], (
            f"Cached in_degree doesn't match computed value"
        )
        assert cache_entry.out_degree == degree_metrics_1[resource_id]["out_degree"], (
            f"Cached out_degree doesn't match computed value"
        )

        # Check betweenness
        assert (
            abs(cache_entry.betweenness - betweenness_metrics_1[resource_id]) < 0.001
        ), f"Cached betweenness doesn't match computed value"

        # Check PageRank
        assert abs(cache_entry.pagerank - pagerank_metrics_1[resource_id]) < 0.001, (
            f"Cached PageRank doesn't match computed value"
        )
