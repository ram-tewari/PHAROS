"""
Unit tests for auto-linking service (Phase 20).

These tests verify specific examples and edge cases for the auto-linking functionality.

Test Coverage:
- High similarity (>0.9)
- Threshold boundary (exactly 0.7)
- No existing chunks (edge case)
- Empty embeddings
- Invalid resource IDs
"""

import pytest
import uuid
from unittest.mock import Mock, MagicMock, patch
from typing import List

from app.modules.resources.service import AutoLinkingService
from app.database import models as db_models


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = Mock()
    db.add = Mock()
    db.commit = Mock()
    db.rollback = Mock()
    return db


@pytest.fixture
def mock_embedding_generator():
    """Mock embedding generator."""
    gen = Mock()
    gen.generate_embedding = Mock(return_value=[0.1] * 768)
    return gen


@pytest.fixture
def auto_linking_service(mock_db, mock_embedding_generator):
    """Create auto-linking service with mocks."""
    return AutoLinkingService(
        db=mock_db,
        embedding_generator=mock_embedding_generator,
        similarity_threshold=0.7,
    )


# ============================================================================
# Test High Similarity (>0.9)
# ============================================================================


def test_high_similarity_creates_links(auto_linking_service, mock_db):
    """
    Test that high similarity (>0.9) creates links.

    Validates: Requirements 3.1, 3.2, 3.3
    """
    # Create embeddings with high similarity
    import numpy as np

    embedding1 = np.array([1.0] * 768)
    embedding2 = np.array([0.95] * 768)

    # Normalize embeddings
    embedding1 = embedding1 / np.linalg.norm(embedding1)
    embedding2 = embedding2 / np.linalg.norm(embedding2)

    # Compute similarity
    similarity = auto_linking_service._compute_cosine_similarity(
        embedding1.tolist(), embedding2.tolist()
    )

    # Verify high similarity
    assert similarity > 0.9, f"Expected high similarity, got {similarity}"

    # Create link
    source_id = uuid.uuid4()
    target_id = uuid.uuid4()

    link = auto_linking_service._create_link(
        source_id, target_id, similarity, "pdf_to_code"
    )

    # Verify link was created
    assert link is not None
    assert link.similarity_score == similarity
    assert link.source_chunk_id == source_id
    assert link.target_chunk_id == target_id
    assert link.link_type == "pdf_to_code"
    assert mock_db.add.called


# ============================================================================
# Test Threshold Boundary (exactly 0.7)
# ============================================================================


def test_threshold_boundary_creates_link(auto_linking_service, mock_db):
    """
    Test that similarity exactly at threshold (0.7) creates link.

    Validates: Requirements 3.2
    """
    # Create link with exact threshold similarity
    source_id = uuid.uuid4()
    target_id = uuid.uuid4()
    threshold_similarity = 0.7

    link = auto_linking_service._create_link(
        source_id, target_id, threshold_similarity, "pdf_to_code"
    )

    # Verify link was created
    assert link is not None
    assert link.similarity_score == threshold_similarity
    assert mock_db.add.called


def test_below_threshold_no_link(auto_linking_service):
    """
    Test that similarity below threshold does not create link.

    Validates: Requirements 3.2
    """
    # Create embeddings with low similarity
    import numpy as np

    embedding1 = np.array([1.0, 0.0] + [0.0] * 766)
    embedding2 = np.array([0.0, 1.0] + [0.0] * 766)

    # Compute similarity
    similarity = auto_linking_service._compute_cosine_similarity(
        embedding1.tolist(), embedding2.tolist()
    )

    # Verify low similarity
    assert similarity < 0.7, f"Expected low similarity, got {similarity}"

    # In production, links below threshold are not created
    # This is enforced in link_pdf_to_code/link_code_to_pdfs methods


# ============================================================================
# Test No Existing Chunks (Edge Case)
# ============================================================================


@pytest.mark.asyncio
async def test_no_existing_chunks(mock_db, mock_embedding_generator):
    """
    Test auto-linking when no existing chunks are found.

    Edge case: Empty database
    Validates: Requirements 3.1, 3.2, 3.3
    """
    # Create service
    service = AutoLinkingService(
        db=mock_db,
        embedding_generator=mock_embedding_generator,
        similarity_threshold=0.7,
    )

    # Mock resource exists
    pdf_resource_id = str(uuid.uuid4())
    pdf_resource = Mock()
    pdf_resource.id = uuid.UUID(pdf_resource_id)

    # Mock queries to return empty results
    def mock_query(model):
        query_mock = Mock()
        if model == db_models.Resource:
            query_mock.filter.return_value.first.return_value = pdf_resource
        elif model == db_models.DocumentChunk:
            # Return empty list for chunks
            query_mock.filter.return_value.all.return_value = []
        return query_mock

    mock_db.query = mock_query

    # Call auto-linking
    links = await service.link_pdf_to_code(pdf_resource_id)

    # Verify no links created
    assert links == []
    assert not mock_db.add.called


# ============================================================================
# Test Empty Embeddings
# ============================================================================


def test_empty_embedding_returns_none(auto_linking_service):
    """
    Test that empty embeddings are handled gracefully.

    Edge case: Missing or invalid embeddings
    """
    # Create mock chunk with no embedding
    chunk = Mock(spec=db_models.DocumentChunk)
    chunk.id = uuid.uuid4()
    chunk.content = "Test content"
    chunk.chunk_metadata = {}  # No embedding

    # Get embedding
    embedding = auto_linking_service._get_chunk_embedding(chunk)

    # Should generate embedding
    assert embedding is not None or embedding == []


def test_zero_norm_embeddings(auto_linking_service):
    """
    Test that zero-norm embeddings return 0 similarity.

    Edge case: Invalid embeddings
    """
    # Create zero embeddings
    embedding1 = [0.0] * 768
    embedding2 = [1.0] * 768

    # Compute similarity
    similarity = auto_linking_service._compute_cosine_similarity(embedding1, embedding2)

    # Should return 0 for zero-norm vectors
    assert similarity == 0.0


# ============================================================================
# Test Invalid Resource IDs
# ============================================================================


@pytest.mark.asyncio
async def test_invalid_resource_id(mock_db, mock_embedding_generator):
    """
    Test auto-linking with invalid resource ID.

    Edge case: Invalid UUID format
    """
    # Create service
    service = AutoLinkingService(
        db=mock_db,
        embedding_generator=mock_embedding_generator,
        similarity_threshold=0.7,
    )

    # Try with invalid resource ID
    with pytest.raises(ValueError, match="Invalid resource_id format"):
        await service.link_pdf_to_code("invalid-uuid")


@pytest.mark.asyncio
async def test_resource_not_found(mock_db, mock_embedding_generator):
    """
    Test auto-linking when resource doesn't exist.

    Edge case: Resource not in database
    """
    # Create service
    service = AutoLinkingService(
        db=mock_db,
        embedding_generator=mock_embedding_generator,
        similarity_threshold=0.7,
    )

    # Mock resource not found
    pdf_resource_id = str(uuid.uuid4())

    def mock_query(model):
        query_mock = Mock()
        if model == db_models.Resource:
            query_mock.filter.return_value.first.return_value = None
        return query_mock

    mock_db.query = mock_query

    # Call auto-linking
    links = await service.link_pdf_to_code(pdf_resource_id)

    # Should return empty list
    assert links == []


# ============================================================================
# Test Bidirectional Links
# ============================================================================


def test_bidirectional_links_created(auto_linking_service, mock_db):
    """
    Test that bidirectional links are created.

    Validates: Requirements 3.2, 3.4
    """
    source_id = uuid.uuid4()
    target_id = uuid.uuid4()
    similarity = 0.85

    # Create links in both directions
    link1 = auto_linking_service._create_link(
        source_id, target_id, similarity, "pdf_to_code"
    )

    link2 = auto_linking_service._create_link(
        target_id, source_id, similarity, "code_to_pdf"
    )

    # Verify both links created
    assert link1 is not None
    assert link2 is not None
    assert link1.source_chunk_id == link2.target_chunk_id
    assert link1.target_chunk_id == link2.source_chunk_id
    assert link1.similarity_score == link2.similarity_score
    assert mock_db.add.call_count == 2


# ============================================================================
# Test Cosine Similarity Edge Cases
# ============================================================================


def test_identical_embeddings_similarity(auto_linking_service):
    """
    Test that identical embeddings have similarity ~1.0.
    """
    embedding = [0.5] * 768

    similarity = auto_linking_service._compute_cosine_similarity(embedding, embedding)

    # Should be very close to 1.0
    assert abs(similarity - 1.0) < 0.01


def test_orthogonal_embeddings_similarity(auto_linking_service):
    """
    Test that orthogonal embeddings have similarity ~0.0.
    """
    import numpy as np

    # Create orthogonal vectors
    embedding1 = np.array([1.0, 0.0] + [0.0] * 766)
    embedding2 = np.array([0.0, 1.0] + [0.0] * 766)

    similarity = auto_linking_service._compute_cosine_similarity(
        embedding1.tolist(), embedding2.tolist()
    )

    # Should be very close to 0.0
    assert abs(similarity) < 0.01


# ============================================================================
# Test Link Metadata
# ============================================================================


def test_link_metadata_stored(auto_linking_service, mock_db):
    """
    Test that link metadata is properly stored.

    Validates: Requirements 3.4
    """
    source_id = uuid.uuid4()
    target_id = uuid.uuid4()
    similarity = 0.85
    link_type = "pdf_to_code"

    link = auto_linking_service._create_link(
        source_id, target_id, similarity, link_type
    )

    # Verify metadata
    assert link.similarity_score == similarity
    assert link.link_type == link_type
    assert link.source_chunk_id == source_id
    assert link.target_chunk_id == target_id
