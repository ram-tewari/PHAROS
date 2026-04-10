"""
Tests for Advanced RAG Graph API Endpoints (Phase 17.5)

Tests the new graph extraction and traversal endpoints.
Requirements: 7.1-7.10
"""

import pytest
from uuid import uuid4
from typing import List
from sqlalchemy.orm import Session

from app.database.models import Resource, DocumentChunk, GraphEntity, GraphRelationship


@pytest.fixture
def test_resource(db_session: Session) -> Resource:
    """Create a test resource."""
    resource = Resource(
        id=uuid4(),
        title="Test Resource",
        type="article",
        description="Test description",
    )
    db_session.add(resource)
    db_session.commit()
    db_session.refresh(resource)
    return resource


@pytest.fixture
def test_chunk(db_session: Session, test_resource: Resource) -> DocumentChunk:
    """Create a test chunk."""
    chunk = DocumentChunk(
        id=uuid4(),
        resource_id=test_resource.id,
        content="Neural Networks are used in Machine Learning.",
        chunk_index=0,
        chunk_metadata={"page": 1},
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)
    return chunk


@pytest.fixture
def test_entities(db_session: Session) -> List[GraphEntity]:
    """Create test entities."""
    entities = [
        GraphEntity(id=uuid4(), name="Neural Networks", type="Concept"),
        GraphEntity(id=uuid4(), name="Machine Learning", type="Concept"),
    ]
    for entity in entities:
        db_session.add(entity)
    db_session.commit()
    for entity in entities:
        db_session.refresh(entity)
    return entities


@pytest.fixture
def test_relationships(
    db_session: Session, test_entities: List[GraphEntity], test_chunk: DocumentChunk
) -> List[GraphRelationship]:
    """Create test relationships."""
    rel = GraphRelationship(
        id=uuid4(),
        source_entity_id=test_entities[0].id,
        target_entity_id=test_entities[1].id,
        relation_type="EXTENDS",
        weight=0.8,
        provenance_chunk_id=test_chunk.id,
    )
    db_session.add(rel)
    db_session.commit()
    db_session.refresh(rel)
    return [rel]


def test_extract_from_chunk_success(client, test_chunk):
    """Test POST /api/graph/extract/{chunk_id} - Success case."""
    response = client.post(f"/api/graph/extract/{test_chunk.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "entities" in data
    assert "relationships" in data


def test_extract_from_nonexistent_chunk(client):
    """Test POST /api/graph/extract/{chunk_id} - 404 for missing chunk."""
    fake_id = uuid4()
    response = client.post(f"/api/graph/extract/{fake_id}")

    assert response.status_code == 404


def test_list_entities(client, test_entities):
    """Test GET /api/graph/entities - List all entities."""
    response = client.get("/api/graph/entities")

    assert response.status_code == 200
    data = response.json()
    assert "entities" in data
    assert "total_count" in data
    assert data["total_count"] >= len(test_entities)


def test_list_entities_with_filter(client, test_entities):
    """Test GET /api/graph/entities - Filter by type."""
    response = client.get("/api/graph/entities", params={"entity_type": "Concept"})

    assert response.status_code == 200
    data = response.json()
    for entity in data["entities"]:
        assert entity["type"] == "Concept"


def test_get_entity_relationships(client, test_entities, test_relationships):
    """Test GET /api/graph/entities/{entity_id}/relationships."""
    entity_id = test_entities[0].id
    response = client.get(f"/api/graph/entities/{entity_id}/relationships")

    assert response.status_code == 200
    data = response.json()
    assert "entity" in data
    assert "outgoing_relationships" in data
    assert "incoming_relationships" in data


def test_get_relationships_nonexistent_entity(client):
    """Test GET /api/graph/entities/{entity_id}/relationships - 404."""
    fake_id = uuid4()
    response = client.get(f"/api/graph/entities/{fake_id}/relationships")

    assert response.status_code == 404


def test_traverse_graph(client, test_entities, test_relationships):
    """Test GET /api/graph/traverse - Graph traversal."""
    entity_id = test_entities[0].id
    response = client.get(
        "/api/graph/traverse", params={"start_entity_id": str(entity_id), "max_hops": 1}
    )

    assert response.status_code == 200
    data = response.json()
    assert "start_entity" in data
    assert "entities" in data
    assert "relationships" in data
    assert "traversal_info" in data


def test_traverse_nonexistent_entity(client):
    """Test GET /api/graph/traverse - 404 for missing entity."""
    fake_id = uuid4()
    response = client.get(
        "/api/graph/traverse", params={"start_entity_id": str(fake_id), "max_hops": 1}
    )

    assert response.status_code == 404


def test_traverse_max_hops_validation(client, test_entities):
    """Test GET /api/graph/traverse - Validate max_hops range."""
    entity_id = test_entities[0].id
    response = client.get(
        "/api/graph/traverse", params={"start_entity_id": str(entity_id), "max_hops": 5}
    )

    # Should return validation error for max_hops > 3
    assert response.status_code == 422
