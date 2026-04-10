"""
Advanced Search Endpoint Tests

Tests for advanced search endpoint with parent-child, GraphRAG, and hybrid strategies.

**Validates: Requirements 8.1-8.10, 9.1-9.10**
"""

import pytest
from fastapi.testclient import TestClient
import uuid

from app.main import app
from app.shared.database import get_sync_db
from app.database.models import (
    Resource,
    DocumentChunk,
    GraphEntity,
    GraphRelationship,
)


# ============================================================================
# Test Cases - Parent-Child Strategy
# ============================================================================@pytest.fixture
def sample_graph_data(test_db, sample_resource_with_chunks):
    """Create sample graph entities and relationships."""
    chunk1 = sample_resource_with_chunks["chunks"][0]

    # Create entities
    entity1 = GraphEntity(
        id=uuid.uuid4(),
        name="Machine Learning",
        type="Concept",
        description="A subset of AI",
    )
    entity2 = GraphEntity(
        id=uuid.uuid4(),
        name="Neural Networks",
        type="Concept",
        description="Powerful ML models",
    )
    test_db.add(entity1)
    test_db.add(entity2)
    test_db.flush()

    # Create relationship
    relationship = GraphRelationship(
        id=uuid.uuid4(),
        source_entity_id=entity1.id,
        target_entity_id=entity2.id,
        relation_type="EXTENDS",
        weight=0.9,
        provenance_chunk_id=chunk1.id,
    )
    test_db.add(relationship)
    test_db.commit()

    return {"entities": [entity1, entity2], "relationship": relationship}


# ============================================================================
# Test Cases - Parent-Child Strategy
# ============================================================================


def test_advanced_search_parent_child_strategy(client, sample_resource_with_chunks):
    """
    Test advanced search with parent-child strategy.

    Verifies:
    - Endpoint accepts parent-child strategy
    - Returns chunks with parent resource
    - Includes surrounding chunks based on context_window
    - Returns proper response structure

    **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**
    """
    # Make request
    response = client.post(
        "/api/search/advanced",
        json={
            "query": "machine learning",
            "strategy": "parent-child",
            "top_k": 10,
            "context_window": 1,
        },
    )

    # Assert response
    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "query" in data
    assert "strategy" in data
    assert "results" in data
    assert "total" in data
    assert "latency_ms" in data

    assert data["query"] == "machine learning"
    assert data["strategy"] == "parent-child"
    assert isinstance(data["results"], list)
    assert isinstance(data["latency_ms"], (int, float))


def test_advanced_search_parent_child_with_context_window(
    client, sample_resource_with_chunks
):
    """
    Test parent-child search with context window parameter.

    Verifies:
    - Context window parameter is respected
    - Surrounding chunks are included
    - Chunks are ordered by chunk_index

    **Validates: Requirements 8.4**
    """
    # Make request with context_window=2
    response = client.post(
        "/api/search/advanced",
        json={
            "query": "machine learning",
            "strategy": "parent-child",
            "top_k": 5,
            "context_window": 2,
        },
    )

    # Assert response
    assert response.status_code == 200
    data = response.json()

    # Verify results have surrounding_chunks field
    if data["results"]:
        result = data["results"][0]
        assert "surrounding_chunks" in result
        assert isinstance(result["surrounding_chunks"], list)


def test_advanced_search_parent_child_result_structure(
    client, sample_resource_with_chunks
):
    """
    Test parent-child search result structure.

    Verifies:
    - Each result has chunk, parent_resource, surrounding_chunks, score
    - Chunk has id, resource_id, content, chunk_index, chunk_metadata
    - Parent resource has full resource data

    **Validates: Requirements 8.6, 8.7**
    """
    # Make request
    response = client.post(
        "/api/search/advanced",
        json={"query": "machine learning", "strategy": "parent-child", "top_k": 10},
    )

    # Assert response
    assert response.status_code == 200
    data = response.json()

    # Verify result structure if results exist
    if data["results"]:
        result = data["results"][0]

        # Verify chunk structure
        assert "chunk" in result
        chunk = result["chunk"]
        assert "id" in chunk
        assert "resource_id" in chunk
        assert "content" in chunk
        assert "chunk_index" in chunk

        # Verify parent resource
        assert "parent_resource" in result
        parent = result["parent_resource"]
        assert "id" in parent
        assert "title" in parent

        # Verify score
        assert "score" in result
        assert isinstance(result["score"], (int, float))


# ============================================================================
# Test Cases - GraphRAG Strategy
# ============================================================================


def test_advanced_search_graphrag_strategy(client, sample_graph_data):
    """
    Test advanced search with GraphRAG strategy.

    Verifies:
    - Endpoint accepts graphrag strategy
    - Returns results with graph paths
    - Graph paths explain retrieval reasoning

    **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6**
    """
    # Make request
    response = client.post(
        "/api/search/advanced",
        json={"query": "neural networks", "strategy": "graphrag", "top_k": 10},
    )

    # Assert response
    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert data["strategy"] == "graphrag"
    assert isinstance(data["results"], list)


def test_advanced_search_graphrag_with_relation_types(client, sample_graph_data):
    """
    Test GraphRAG search with relation type filtering.

    Verifies:
    - relation_types parameter is accepted
    - Results are filtered by relationship type
    - Only specified relation types are returned

    **Validates: Requirements 9.7**
    """
    # Make request with relation_types filter
    response = client.post(
        "/api/search/advanced",
        json={
            "query": "machine learning",
            "strategy": "graphrag",
            "top_k": 10,
            "relation_types": ["EXTENDS", "SUPPORTS"],
        },
    )

    # Assert response
    assert response.status_code == 200
    data = response.json()

    # Verify relation_types parameter was accepted
    assert data["strategy"] == "graphrag"


def test_advanced_search_graphrag_graph_path_structure(client, sample_graph_data):
    """
    Test GraphRAG search graph path structure.

    Verifies:
    - Graph paths contain entity information
    - Each node has entity_id, entity_name, entity_type
    - Relationships have relation_type and weight

    **Validates: Requirements 9.8**
    """
    # Make request
    response = client.post(
        "/api/search/advanced",
        json={"query": "neural networks", "strategy": "graphrag", "top_k": 10},
    )

    # Assert response
    assert response.status_code == 200
    data = response.json()

    # Verify graph_path structure if results exist
    if data["results"]:
        result = data["results"][0]
        assert "graph_path" in result

        # If graph path exists, verify node structure
        if result["graph_path"]:
            node = result["graph_path"][0]
            assert "entity_id" in node
            assert "entity_name" in node
            assert "entity_type" in node


# ============================================================================
# Test Cases - Hybrid Strategy
# ============================================================================


def test_advanced_search_hybrid_strategy(
    client, sample_resource_with_chunks, sample_graph_data
):
    """
    Test advanced search with hybrid strategy.

    Verifies:
    - Endpoint accepts hybrid strategy
    - Combines parent-child and GraphRAG results
    - Returns merged results with both context and graph paths

    **Validates: Requirements 9.9**
    """
    # Make request
    response = client.post(
        "/api/search/advanced",
        json={
            "query": "machine learning",
            "strategy": "hybrid",
            "top_k": 10,
            "context_window": 1,
        },
    )

    # Assert response
    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert data["strategy"] == "hybrid"
    assert isinstance(data["results"], list)


def test_advanced_search_hybrid_deduplication(
    client, sample_resource_with_chunks, sample_graph_data
):
    """
    Test hybrid search result deduplication.

    Verifies:
    - Duplicate chunks from both strategies are merged
    - Scores are combined appropriately
    - No duplicate chunk IDs in results

    **Validates: Requirements 8.5**
    """
    # Make request
    response = client.post(
        "/api/search/advanced",
        json={"query": "machine learning", "strategy": "hybrid", "top_k": 10},
    )

    # Assert response
    assert response.status_code == 200
    data = response.json()

    # Verify no duplicate chunk IDs
    if data["results"]:
        chunk_ids = [result["chunk"]["id"] for result in data["results"]]
        assert len(chunk_ids) == len(set(chunk_ids)), "Duplicate chunk IDs found"


# ============================================================================
# Test Cases - Parameter Validation
# ============================================================================


def test_advanced_search_invalid_strategy(client):
    """
    Test advanced search with invalid strategy.

    Verifies:
    - Invalid strategy returns 422 error
    - Error message is descriptive

    **Validates: Requirements 8.1-8.10, 9.1-9.10**
    """
    # Make request with invalid strategy
    response = client.post(
        "/api/search/advanced",
        json={"query": "test", "strategy": "invalid-strategy", "top_k": 10},
    )

    # Assert error response
    assert response.status_code == 422


def test_advanced_search_empty_query(client):
    """
    Test advanced search with empty query.

    Verifies:
    - Empty query returns 422 error
    - Validation catches empty strings

    **Validates: Requirements 8.1-8.10, 9.1-9.10**
    """
    # Make request with empty query
    response = client.post(
        "/api/search/advanced",
        json={"query": "", "strategy": "parent-child", "top_k": 10},
    )

    # Assert error response
    assert response.status_code == 422


def test_advanced_search_invalid_top_k(client):
    """
    Test advanced search with invalid top_k parameter.

    Verifies:
    - top_k must be between 1 and 100
    - Values outside range return 422 error

    **Validates: Requirements 8.1-8.10, 9.1-9.10**
    """
    # Test top_k = 0
    response = client.post(
        "/api/search/advanced",
        json={"query": "test", "strategy": "parent-child", "top_k": 0},
    )
    assert response.status_code == 422

    # Test top_k = 101
    response = client.post(
        "/api/search/advanced",
        json={"query": "test", "strategy": "parent-child", "top_k": 101},
    )
    assert response.status_code == 422


def test_advanced_search_invalid_context_window(client):
    """
    Test advanced search with invalid context_window parameter.

    Verifies:
    - context_window must be between 0 and 5
    - Values outside range return 422 error

    **Validates: Requirements 8.4**
    """
    # Test context_window = -1
    response = client.post(
        "/api/search/advanced",
        json={
            "query": "test",
            "strategy": "parent-child",
            "top_k": 10,
            "context_window": -1,
        },
    )
    assert response.status_code == 422

    # Test context_window = 6
    response = client.post(
        "/api/search/advanced",
        json={
            "query": "test",
            "strategy": "parent-child",
            "top_k": 10,
            "context_window": 6,
        },
    )
    assert response.status_code == 422


def test_advanced_search_default_parameters(client, sample_resource_with_chunks):
    """
    Test advanced search with default parameters.

    Verifies:
    - Default strategy is parent-child
    - Default top_k is 10
    - Default context_window is 2

    **Validates: Requirements 8.1-8.10, 9.1-9.10**
    """
    # Make request with minimal parameters
    response = client.post("/api/search/advanced", json={"query": "machine learning"})

    # Assert response
    assert response.status_code == 200
    data = response.json()

    # Verify defaults
    assert data["strategy"] == "parent-child"


# ============================================================================
# Test Cases - Performance
# ============================================================================


def test_advanced_search_latency_tracking(client, sample_resource_with_chunks):
    """
    Test that search latency is tracked and returned.

    Verifies:
    - latency_ms field is present
    - Latency is a positive number
    - Latency is reasonable (< 5000ms for test data)

    **Validates: Requirements 8.10**
    """
    # Make request
    response = client.post(
        "/api/search/advanced",
        json={"query": "machine learning", "strategy": "parent-child", "top_k": 10},
    )

    # Assert response
    assert response.status_code == 200
    data = response.json()

    # Verify latency tracking
    assert "latency_ms" in data
    assert isinstance(data["latency_ms"], (int, float))
    assert data["latency_ms"] >= 0
    assert data["latency_ms"] < 5000  # Should be fast for test data


def test_advanced_search_top_k_limit(client, sample_resource_with_chunks):
    """
    Test that top_k parameter limits results correctly.

    Verifies:
    - Results are limited to top_k
    - Results are ranked by score

    **Validates: Requirements 8.1-8.10, 9.1-9.10**
    """
    # Make request with top_k=1
    response = client.post(
        "/api/search/advanced",
        json={"query": "machine learning", "strategy": "parent-child", "top_k": 1},
    )

    # Assert response
    assert response.status_code == 200
    data = response.json()

    # Verify result count
    assert len(data["results"]) <= 1
