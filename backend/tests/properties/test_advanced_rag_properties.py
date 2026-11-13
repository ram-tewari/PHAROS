"""
Property-based tests for Advanced RAG models (Phase 17.5).

**Feature: phase17-5-advanced-rag-architecture**

These tests verify universal properties of the advanced RAG database models
using property-based testing with hypothesis.
"""

import pytest
import uuid
from hypothesis import given, strategies as st, settings, HealthCheck
from sqlalchemy.orm import Session

from app.database.models import Resource, DocumentChunk


# ============================================================================
# Property 2: Foreign Key Integrity
# **Validates: Requirements 1.7**
# ============================================================================


@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    resource_count=st.integers(min_value=1, max_value=5),
    chunks_per_resource=st.integers(min_value=1, max_value=10),
)
def test_property_foreign_key_integrity(
    db_session: Session, resource_count, chunks_per_resource
):
    """
    **Feature: phase17-5-advanced-rag-architecture, Property 2: Foreign Key Integrity**

    For any DocumentChunk, the resource_id must reference an existing Resource,
    and deleting a Resource must cascade delete all associated chunks.

    **Validates: Requirements 1.7**
    """
    # Rollback any pending transactions to start fresh
    db_session.rollback()

    # Generate random resources and store their IDs immediately
    resource_ids = []
    for i in range(resource_count):
        resource = Resource(
            title=f"Test Resource {i}",
            description=f"Description for resource {i}",
            type="article",
        )
        db_session.add(resource)
        db_session.flush()  # Flush to get the ID
        resource_ids.append(resource.id)

    db_session.commit()

    # Generate random chunks for each resource using the stored IDs
    all_chunk_ids = []
    for resource_id in resource_ids:
        for chunk_idx in range(chunks_per_resource):
            chunk = DocumentChunk(
                resource_id=resource_id,  # Use the stored ID directly
                content=f"Chunk {chunk_idx} content for resource {resource_id}",
                chunk_index=chunk_idx,
                chunk_metadata={"page": chunk_idx + 1},
            )
            db_session.add(chunk)
            db_session.flush()  # Flush to get the chunk ID
            all_chunk_ids.append(chunk.id)

    db_session.commit()

    # Verify all chunks reference existing resources
    for chunk_id in all_chunk_ids:
        chunk_from_db = db_session.query(DocumentChunk).filter_by(id=chunk_id).first()
        assert chunk_from_db is not None, f"Chunk {chunk_id} should exist"
        assert chunk_from_db.resource_id is not None, (
            f"Chunk {chunk_id} should have a resource_id"
        )

        resource_from_db = (
            db_session.query(Resource).filter_by(id=chunk_from_db.resource_id).first()
        )
        assert resource_from_db is not None, (
            f"Resource {chunk_from_db.resource_id} should exist"
        )

    # Delete the first resource
    resource_id_to_delete = resource_ids[0]

    # Count chunks before deletion
    chunks_before = (
        db_session.query(DocumentChunk)
        .filter_by(resource_id=resource_id_to_delete)
        .count()
    )
    assert chunks_before == chunks_per_resource, (
        f"Expected {chunks_per_resource} chunks before deletion"
    )

    # Delete the resource by ID
    resource_to_delete = (
        db_session.query(Resource).filter_by(id=resource_id_to_delete).first()
    )
    db_session.delete(resource_to_delete)
    db_session.commit()

    # Verify resource is deleted
    deleted_resource = (
        db_session.query(Resource).filter_by(id=resource_id_to_delete).first()
    )
    assert deleted_resource is None, (
        f"Resource {resource_id_to_delete} should be deleted"
    )

    # Verify all associated chunks are cascade deleted
    chunks_after = (
        db_session.query(DocumentChunk)
        .filter_by(resource_id=resource_id_to_delete)
        .count()
    )
    assert chunks_after == 0, (
        f"Expected 0 chunks after resource deletion, found {chunks_after}"
    )

    # Verify other resources' chunks are unaffected
    for resource_id in resource_ids[1:]:
        remaining_chunks = (
            db_session.query(DocumentChunk).filter_by(resource_id=resource_id).count()
        )
        assert remaining_chunks == chunks_per_resource, (
            f"Expected {chunks_per_resource} chunks for resource {resource_id}, found {remaining_chunks}"
        )


@settings(
    max_examples=5,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(
    content=st.text(min_size=10, max_size=500),
    chunk_index=st.integers(min_value=0, max_value=100),
)
def test_property_orphaned_chunks_cannot_be_created(
    db_session: Session, content, chunk_index
):
    """
    **Feature: phase17-5-advanced-rag-architecture, Property 2: Foreign Key Integrity**

    Verify that orphaned chunks (chunks without a valid resource_id) cannot be created.

    **Validates: Requirements 1.7**
    """
    from sqlalchemy.exc import IntegrityError

    # Rollback any pending transactions
    db_session.rollback()

    # Try to create a chunk with a non-existent resource_id
    fake_resource_id = uuid.uuid4()

    chunk = DocumentChunk(
        resource_id=fake_resource_id,
        content=content,
        chunk_index=chunk_index,
        chunk_metadata={"page": 1},
    )
    db_session.add(chunk)

    # This should raise an IntegrityError due to foreign key constraint
    with pytest.raises(
        (IntegrityError, Exception)
    ):  # SQLAlchemy will raise IntegrityError
        db_session.commit()

    # Rollback the failed transaction
    db_session.rollback()

    # Verify no chunks were created
    chunk_count = db_session.query(DocumentChunk).count()
    assert chunk_count == 0, f"Expected 0 chunks, found {chunk_count}"


# ============================================================================
# Property 3: Graph Triple Validity
# **Validates: Requirements 2.7**
# ============================================================================


@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    entity_count=st.integers(min_value=2, max_value=10),
    relationship_count=st.integers(min_value=1, max_value=20),
)
def test_property_graph_triple_validity(
    db_session: Session, entity_count, relationship_count
):
    """
    **Feature: phase17-5-advanced-rag-architecture, Property 3: Graph Triple Validity**

    For any GraphRelationship, both source_entity_id and target_entity_id must
    reference existing GraphEntity records.

    **Validates: Requirements 2.7**
    """
    from app.database.models import GraphEntity, GraphRelationship

    # Rollback any pending transactions
    db_session.rollback()

    # Generate random entities
    entities = []
    for i in range(entity_count):
        entity = GraphEntity(
            name=f"Entity_{i}", type="Concept", description=f"Test entity {i}"
        )
        db_session.add(entity)
        entities.append(entity)

    db_session.commit()

    # Store entity IDs for later use
    entity_ids = [e.id for e in entities]

    # Generate random relationships between entities
    relationships = []
    for i in range(relationship_count):
        # Pick random source and target entities
        source_idx = i % len(entity_ids)
        target_idx = (i + 1) % len(entity_ids)

        relationship = GraphRelationship(
            source_entity_id=entity_ids[source_idx],
            target_entity_id=entity_ids[target_idx],
            relation_type="SUPPORTS",
            weight=0.8,
        )
        db_session.add(relationship)
        relationships.append(relationship)

    db_session.commit()

    # Verify all relationships reference existing entities
    for relationship in relationships:
        rel_from_db = (
            db_session.query(GraphRelationship).filter_by(id=relationship.id).first()
        )
        assert rel_from_db is not None, f"Relationship {relationship.id} should exist"

        # Verify source entity exists
        source_entity = (
            db_session.query(GraphEntity)
            .filter_by(id=rel_from_db.source_entity_id)
            .first()
        )
        assert source_entity is not None, (
            f"Source entity {rel_from_db.source_entity_id} should exist"
        )

        # Verify target entity exists
        target_entity = (
            db_session.query(GraphEntity)
            .filter_by(id=rel_from_db.target_entity_id)
            .first()
        )
        assert target_entity is not None, (
            f"Target entity {rel_from_db.target_entity_id} should exist"
        )

    # Test cascade behavior: delete an entity and verify relationships are deleted
    entity_to_delete_id = entity_ids[0]

    # Count relationships involving this entity before deletion
    (
        db_session.query(GraphRelationship)
        .filter(
            (GraphRelationship.source_entity_id == entity_to_delete_id)
            | (GraphRelationship.target_entity_id == entity_to_delete_id)
        )
        .count()
    )

    # Delete the entity
    entity_to_delete = (
        db_session.query(GraphEntity).filter_by(id=entity_to_delete_id).first()
    )
    db_session.delete(entity_to_delete)
    db_session.commit()

    # Verify entity is deleted
    deleted_entity = (
        db_session.query(GraphEntity).filter_by(id=entity_to_delete_id).first()
    )
    assert deleted_entity is None, f"Entity {entity_to_delete_id} should be deleted"

    # Verify all relationships involving this entity are cascade deleted
    relationships_after = (
        db_session.query(GraphRelationship)
        .filter(
            (GraphRelationship.source_entity_id == entity_to_delete_id)
            | (GraphRelationship.target_entity_id == entity_to_delete_id)
        )
        .count()
    )
    assert relationships_after == 0, (
        f"Expected 0 relationships after entity deletion, found {relationships_after}"
    )


@settings(
    max_examples=5,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(
    relation_type=st.sampled_from(["SUPPORTS", "CONTRADICTS", "EXTENDS", "CITES"]),
    weight=st.floats(min_value=0.0, max_value=1.0),
)
def test_property_orphaned_relationships_cannot_be_created(
    db_session: Session, relation_type, weight
):
    """
    **Feature: phase17-5-advanced-rag-architecture, Property 3: Graph Triple Validity**

    Verify that orphaned relationships (relationships without valid entity IDs) cannot be created.

    **Validates: Requirements 2.7**
    """
    from app.database.models import GraphRelationship

    # Try to create a relationship with non-existent entity IDs
    fake_source_id = uuid.uuid4()
    fake_target_id = uuid.uuid4()

    relationship = GraphRelationship(
        source_entity_id=fake_source_id,
        target_entity_id=fake_target_id,
        relation_type=relation_type,
        weight=weight,
    )
    db_session.add(relationship)

    # This should raise an IntegrityError due to foreign key constraint
    with pytest.raises(Exception):  # SQLAlchemy will raise IntegrityError or similar
        db_session.commit()

    # Rollback the failed transaction
    db_session.rollback()

    # Verify no relationships were created
    relationship_count = db_session.query(GraphRelationship).count()
    assert relationship_count == 0, (
        f"Expected 0 relationships, found {relationship_count}"
    )


# ============================================================================
# Property 9: Chunk Content Preservation
# **Validates: Requirements 6.4**
# ============================================================================


def test_property_chunk_content_preservation_fixed_strategy(db_session: Session):
    """
    **Feature: phase17-5-advanced-rag-architecture, Property 9: Chunk Content Preservation**

    For any content using fixed chunking strategy, concatenating chunks in order should
    reconstruct the original content (allowing for overlap).

    This is a simplified unit test version that validates the property without
    hypothesis to avoid memory issues.

    **Validates: Requirements 6.4**
    """
    from app.modules.resources.service import ChunkingService
    from unittest.mock import Mock

    # Test with a simple content string
    content = "This is a test document. It has multiple sentences. We will chunk it and verify preservation."

    # Rollback any pending transactions
    db_session.rollback()

    # Create a test resource
    resource = Resource(
        title="Test Resource for Chunking", description="Test resource", type="article"
    )
    db_session.add(resource)
    db_session.commit()

    # Create mock embedding service
    mock_embedding_service = Mock()
    mock_embedding_service.generate_embedding = Mock(return_value=[0.1] * 768)
    mock_embedding_service.model_name = "test-model"

    # Create chunking service with fixed strategy
    service = ChunkingService(
        db=db_session,
        strategy="fixed",
        chunk_size=40,
        overlap=10,
        parser_type="text",
        embedding_service=mock_embedding_service,
    )

    # Chunk the content
    resource_id = str(resource.id)
    chunk_dicts = service.fixed_chunk(resource_id, content)

    # Verify chunks were created
    assert len(chunk_dicts) > 0, "Should create at least one chunk"

    # Reconstruct content by removing overlap
    reconstructed_parts = []
    for i, chunk in enumerate(chunk_dicts):
        chunk_content = chunk["content"]
        if i == 0:
            reconstructed_parts.append(chunk_content)
        else:
            # Skip overlap portion
            if len(chunk_content) > 10:
                reconstructed_parts.append(chunk_content[10:])
            else:
                reconstructed_parts.append(chunk_content)

    reconstructed = "".join(reconstructed_parts)

    # Normalize whitespace
    original_normalized = " ".join(content.split())
    reconstructed_normalized = " ".join(reconstructed.split())

    # Verify all words are preserved
    original_words = set(original_normalized.split())
    reconstructed_words = set(reconstructed_normalized.split())

    missing_words = original_words - reconstructed_words
    assert len(missing_words) == 0, f"Missing words: {missing_words}"

    # Cleanup
    db_session.query(DocumentChunk).filter_by(resource_id=resource.id).delete()
    db_session.delete(resource)
    db_session.commit()


def test_property_chunk_content_preservation_semantic_strategy(db_session: Session):
    """
    **Feature: phase17-5-advanced-rag-architecture, Property 9: Chunk Content Preservation**

    For any content using semantic chunking strategy, all words from the original
    should be present in the chunked content.

    This is a simplified unit test version that validates the property without
    hypothesis to avoid memory issues.

    **Validates: Requirements 6.4**
    """
    from app.modules.resources.service import ChunkingService
    from unittest.mock import Mock

    # Test with a simple content string
    content = "This is a test document. It has multiple sentences. We will chunk it and verify preservation. Each sentence should be handled properly."

    # Rollback any pending transactions
    db_session.rollback()

    # Create a test resource
    resource = Resource(
        title="Test Resource for Semantic Chunking",
        description="Test resource",
        type="article",
    )
    db_session.add(resource)
    db_session.commit()

    # Create mock embedding service
    mock_embedding_service = Mock()
    mock_embedding_service.generate_embedding = Mock(return_value=[0.1] * 768)
    mock_embedding_service.model_name = "test-model"

    # Create chunking service with semantic strategy
    service = ChunkingService(
        db=db_session,
        strategy="semantic",
        chunk_size=50,
        overlap=1,  # 1 sentence overlap
        parser_type="text",
        embedding_service=mock_embedding_service,
    )

    # Chunk the content
    resource_id = str(resource.id)
    chunk_dicts = service.semantic_chunk(resource_id, content)

    # Verify chunks were created
    assert len(chunk_dicts) > 0, "Should create at least one chunk"

    # Concatenate all chunks
    reconstructed = " ".join(chunk["content"] for chunk in chunk_dicts)

    # Normalize whitespace
    original_normalized = " ".join(content.split())
    reconstructed_normalized = " ".join(reconstructed.split())

    # Verify all words are preserved
    original_words = set(original_normalized.split())
    reconstructed_words = set(reconstructed_normalized.split())

    missing_words = original_words - reconstructed_words
    assert len(missing_words) == 0, f"Missing words: {missing_words}"

    # Cleanup
    db_session.query(DocumentChunk).filter_by(resource_id=resource.id).delete()
    db_session.delete(resource)
    db_session.commit()


# ============================================================================
# Property 7: Parent-Child Retrieval Consistency
# **Validates: Requirements 8.3**
# ============================================================================


@settings(
    max_examples=5,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    resource_count=st.integers(min_value=1, max_value=3),
    chunks_per_resource=st.integers(min_value=2, max_value=5),
)
def test_property_parent_child_retrieval_consistency(
    db_session: Session, resource_count, chunks_per_resource
):
    """
    **Feature: phase17-5-advanced-rag-architecture, Property 7: Parent-Child Retrieval Consistency**

    For any search query, if a chunk is retrieved, expanding to the parent resource
    must return the resource that contains that chunk.

    **Validates: Requirements 8.3**
    """
    from app.modules.search.service import SearchService
    from unittest.mock import Mock, patch

    # Rollback any pending transactions
    db_session.rollback()

    # Generate random resources with chunks
    resources = []
    all_chunks = []

    for i in range(resource_count):
        resource = Resource(
            title=f"Test Resource {i}",
            description=f"Description for resource {i}",
            type="article",
        )
        db_session.add(resource)
        db_session.flush()
        resources.append(resource)

        # Create chunks for this resource
        for chunk_idx in range(chunks_per_resource):
            chunk = DocumentChunk(
                resource_id=resource.id,
                content=f"Chunk {chunk_idx} content for resource {i}. This is test content with keywords.",
                chunk_index=chunk_idx,
                chunk_metadata={"page": chunk_idx + 1},
            )
            db_session.add(chunk)
            db_session.flush()
            all_chunks.append(chunk)

    db_session.commit()

    # Create search service
    search_service = SearchService(db_session)

    # Mock the embedding service to avoid actual embedding generation
    with patch(
        "app.shared.embeddings.EmbeddingService"
    ) as mock_embedding_service_class:
        mock_embedding_service = Mock()
        mock_embedding_service.generate_embedding.return_value = [0.1] * 768
        mock_embedding_service_class.return_value = mock_embedding_service

        # Perform parent-child search
        query = "test content keywords"
        results = search_service.parent_child_search(query, top_k=10, context_window=1)

    # Verify each result's parent-child consistency
    for result in results:
        chunk = result["chunk"]
        parent_resource = result["parent_resource"]

        # Verify the chunk's resource_id matches the parent resource's id
        assert chunk["resource_id"] == str(parent_resource.id), (
            f"Chunk {chunk['id']} resource_id {chunk['resource_id']} does not match parent resource id {parent_resource.id}"
        )

        # Verify the parent resource actually contains this chunk
        chunk_from_parent = (
            db_session.query(DocumentChunk)
            .filter_by(id=chunk["id"], resource_id=parent_resource.id)
            .first()
        )
        assert chunk_from_parent is not None, (
            f"Parent resource {parent_resource.id} does not contain chunk {chunk['id']}"
        )

        # Verify surrounding chunks are from the same resource
        surrounding_chunks = result["surrounding_chunks"]
        for surrounding_chunk in surrounding_chunks:
            assert surrounding_chunk["resource_id"] == str(parent_resource.id), (
                f"Surrounding chunk {surrounding_chunk['id']} is not from parent resource {parent_resource.id}"
            )

    # Cleanup
    for chunk in all_chunks:
        db_session.delete(chunk)
    for resource in resources:
        db_session.delete(resource)
    db_session.commit()


@pytest.mark.xfail(strict=True, reason="parent-child search is PostgreSQL + pgvector SQL and this suite runs on in-memory SQLite; covered on PostgreSQL by tests/codeintel/test_legacy_search_pg.py")
def test_property_parent_child_retrieval_deduplication(db_session: Session):
    """
    **Feature: phase17-5-advanced-rag-architecture, Property 7: Parent-Child Retrieval Consistency**

    When multiple chunks from the same resource are retrieved, the parent resource
    should only appear once in the results (deduplication).

    **Validates: Requirements 8.5**
    """
    from app.modules.search.service import SearchService
    from unittest.mock import Mock, patch

    # Rollback any pending transactions
    db_session.rollback()

    # Create a single resource with multiple chunks containing the same keywords
    resource = Resource(
        title="Test Resource with Duplicate Keywords",
        description="Test resource",
        type="article",
    )
    db_session.add(resource)
    db_session.flush()

    # Create multiple chunks with the same keywords
    chunks = []
    for i in range(5):
        chunk = DocumentChunk(
            resource_id=resource.id,
            content=f"Chunk {i}: machine learning neural networks deep learning",
            chunk_index=i,
            chunk_metadata={"page": i + 1},
        )
        db_session.add(chunk)
        db_session.flush()
        chunks.append(chunk)

    db_session.commit()

    # Create search service
    search_service = SearchService(db_session)

    # Mock the embedding service to avoid actual embedding generation
    with patch(
        "app.shared.embeddings.EmbeddingService"
    ) as mock_embedding_service_class:
        mock_embedding_service = Mock()
        mock_embedding_service.generate_embedding.return_value = [0.1] * 768
        mock_embedding_service_class.return_value = mock_embedding_service

        # Perform parent-child search with query matching all chunks
        query = "machine learning neural networks"
        results = search_service.parent_child_search(query, top_k=10, context_window=1)

    # Verify deduplication: resource should appear only once
    resource_ids = [result["parent_resource"].id for result in results]
    unique_resource_ids = set(resource_ids)

    assert len(unique_resource_ids) == 1, (
        f"Expected 1 unique resource, found {len(unique_resource_ids)}"
    )
    assert resource.id in unique_resource_ids, (
        f"Expected resource {resource.id} in results"
    )

    # Verify only one result despite multiple matching chunks
    assert len(results) == 1, f"Expected 1 result (deduplicated), found {len(results)}"

    # Cleanup
    for chunk in chunks:
        db_session.delete(chunk)
    db_session.delete(resource)
    db_session.commit()


@pytest.mark.xfail(strict=True, reason="parent-child search is PostgreSQL + pgvector SQL and this suite runs on in-memory SQLite; covered on PostgreSQL by tests/codeintel/test_legacy_search_pg.py")
def test_property_parent_child_context_window(db_session: Session):
    """
    **Feature: phase17-5-advanced-rag-architecture, Property 7: Parent-Child Retrieval Consistency**

    The context window should include the correct number of surrounding chunks
    based on the context_window parameter.

    **Validates: Requirements 8.4**
    """
    from app.modules.search.service import SearchService
    from unittest.mock import Mock, patch

    # Rollback any pending transactions
    db_session.rollback()

    # Create a resource with many chunks
    resource = Resource(
        title="Test Resource for Context Window",
        description="Test resource",
        type="article",
    )
    db_session.add(resource)
    db_session.flush()

    # Create 10 chunks
    chunks = []
    for i in range(10):
        chunk = DocumentChunk(
            resource_id=resource.id,
            content=f"Chunk {i} content. Target keyword appears in chunk 5."
            if i == 5
            else f"Chunk {i} content.",
            chunk_index=i,
            chunk_metadata={"page": i + 1},
        )
        db_session.add(chunk)
        db_session.flush()
        chunks.append(chunk)

    db_session.commit()

    # Create search service
    search_service = SearchService(db_session)

    # Mock the embedding service to avoid actual embedding generation
    with patch(
        "app.shared.embeddings.EmbeddingService"
    ) as mock_embedding_service_class:
        mock_embedding_service = Mock()
        mock_embedding_service.generate_embedding.return_value = [0.1] * 768
        mock_embedding_service_class.return_value = mock_embedding_service

        # Test with context_window=2
        query = "Target keyword"
        results = search_service.parent_child_search(query, top_k=1, context_window=2)

    assert len(results) > 0, "Should return at least one result"

    result = results[0]
    surrounding_chunks = result["surrounding_chunks"]

    # The retrieved chunk should be chunk 5 (index 5)
    # With context_window=2, we should get chunks 3, 4, 5, 6, 7 (5 chunks total)
    expected_indices = {3, 4, 5, 6, 7}
    actual_indices = {chunk["chunk_index"] for chunk in surrounding_chunks}

    assert actual_indices == expected_indices, (
        f"Expected indices {expected_indices}, got {actual_indices}"
    )

    # Verify chunks are in order
    sorted_chunks = sorted(surrounding_chunks, key=lambda c: c["chunk_index"])
    for i, chunk in enumerate(sorted_chunks):
        expected_index = 3 + i
        assert chunk["chunk_index"] == expected_index, (
            f"Expected chunk index {expected_index}, got {chunk['chunk_index']}"
        )

    # Cleanup
    for chunk in chunks:
        db_session.delete(chunk)
    db_session.delete(resource)
    db_session.commit()
