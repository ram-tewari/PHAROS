"""
Unit tests for ChunkingService.

Tests semantic chunking, fixed-size chunking, chunk storage, and error handling.
"""

import pytest
from unittest.mock import Mock, patch
import uuid

from app.modules.resources.service import ChunkingService
from app.database import models as db_models


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = Mock()
    db.query = Mock()
    db.add = Mock()
    db.commit = Mock()
    db.flush = Mock()
    db.rollback = Mock()
    return db


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service."""
    service = Mock()
    service.generate_embedding = Mock(return_value=[0.1] * 768)
    service.model_name = "test-model"
    return service


@pytest.fixture
def sample_resource():
    """Sample resource for testing."""
    resource = Mock(spec=db_models.Resource)
    resource.id = uuid.uuid4()
    return resource


class TestSemanticChunking:
    """Tests for semantic chunking functionality."""

    def test_semantic_chunk_basic(self, mock_db, mock_embedding_service):
        """Test basic semantic chunking with simple sentences."""
        service = ChunkingService(
            db=mock_db,
            strategy="semantic",
            chunk_size=10,  # 10 words per chunk
            overlap=2,
            embedding_service=mock_embedding_service,
        )

        content = "First sentence here. Second sentence here. Third sentence here. Fourth sentence here."
        resource_id = str(uuid.uuid4())

        chunks = service.semantic_chunk(resource_id, content)

        # Should create multiple chunks
        assert len(chunks) > 0

        # Each chunk should have required fields
        for chunk in chunks:
            assert "content" in chunk
            assert "chunk_index" in chunk
            assert "chunk_metadata" in chunk
            assert isinstance(chunk["chunk_index"], int)

    def test_semantic_chunk_with_metadata(self, mock_db, mock_embedding_service):
        """Test semantic chunking with metadata."""
        service = ChunkingService(
            db=mock_db,
            strategy="semantic",
            chunk_size=10,
            overlap=2,
            embedding_service=mock_embedding_service,
        )

        content = "Test sentence one. Test sentence two."
        resource_id = str(uuid.uuid4())
        metadata = {"page": 1, "section": "intro"}

        chunks = service.semantic_chunk(resource_id, content, chunk_metadata=metadata)

        # Metadata should be attached to all chunks
        for chunk in chunks:
            assert chunk["chunk_metadata"] == metadata

    def test_semantic_chunk_empty_content(self, mock_db, mock_embedding_service):
        """Test semantic chunking with empty content."""
        service = ChunkingService(
            db=mock_db,
            strategy="semantic",
            chunk_size=10,
            overlap=2,
            embedding_service=mock_embedding_service,
        )

        resource_id = str(uuid.uuid4())

        # Empty string
        chunks = service.semantic_chunk(resource_id, "")
        assert chunks == []

        # Whitespace only
        chunks = service.semantic_chunk(resource_id, "   \n  ")
        assert chunks == []

    def test_semantic_chunk_sequential_indices(self, mock_db, mock_embedding_service):
        """Test that chunk indices are sequential."""
        service = ChunkingService(
            db=mock_db,
            strategy="semantic",
            chunk_size=5,
            overlap=1,
            embedding_service=mock_embedding_service,
        )

        content = (
            "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
        )
        resource_id = str(uuid.uuid4())

        chunks = service.semantic_chunk(resource_id, content)

        # Indices should be sequential starting from 0
        for i, chunk in enumerate(chunks):
            assert chunk["chunk_index"] == i


class TestFixedSizeChunking:
    """Tests for fixed-size chunking functionality."""

    def test_fixed_chunk_basic(self, mock_db, mock_embedding_service):
        """Test basic fixed-size chunking."""
        service = ChunkingService(
            db=mock_db,
            strategy="fixed",
            chunk_size=50,  # 50 characters per chunk
            overlap=10,
            embedding_service=mock_embedding_service,
        )

        content = "A" * 150  # 150 character string
        resource_id = str(uuid.uuid4())

        chunks = service.fixed_chunk(resource_id, content)

        # Should create multiple chunks
        assert len(chunks) > 1

        # Each chunk should have required fields
        for chunk in chunks:
            assert "content" in chunk
            assert "chunk_index" in chunk
            assert "chunk_metadata" in chunk

    def test_fixed_chunk_whitespace_boundary(self, mock_db, mock_embedding_service):
        """Test that fixed chunking breaks on whitespace."""
        service = ChunkingService(
            db=mock_db,
            strategy="fixed",
            chunk_size=20,
            overlap=5,
            embedding_service=mock_embedding_service,
        )

        content = "word1 word2 word3 word4 word5 word6 word7 word8"
        resource_id = str(uuid.uuid4())

        chunks = service.fixed_chunk(resource_id, content)

        # No chunk should end mid-word (no partial words)
        for chunk in chunks:
            # Content should not start or end with partial words
            # (this is a heuristic check - words should be complete)
            assert not chunk["content"].startswith(" ")

    def test_fixed_chunk_empty_content(self, mock_db, mock_embedding_service):
        """Test fixed chunking with empty content."""
        service = ChunkingService(
            db=mock_db,
            strategy="fixed",
            chunk_size=50,
            overlap=10,
            embedding_service=mock_embedding_service,
        )

        resource_id = str(uuid.uuid4())

        # Empty string
        chunks = service.fixed_chunk(resource_id, "")
        assert chunks == []

        # Whitespace only
        chunks = service.fixed_chunk(resource_id, "   \n  ")
        assert chunks == []

    def test_fixed_chunk_sequential_indices(self, mock_db, mock_embedding_service):
        """Test that chunk indices are sequential."""
        service = ChunkingService(
            db=mock_db,
            strategy="fixed",
            chunk_size=30,
            overlap=5,
            embedding_service=mock_embedding_service,
        )

        content = "A" * 100
        resource_id = str(uuid.uuid4())

        chunks = service.fixed_chunk(resource_id, content)

        # Indices should be sequential starting from 0
        for i, chunk in enumerate(chunks):
            assert chunk["chunk_index"] == i


class TestChunkStorage:
    """Tests for chunk storage and embedding generation."""

    def test_store_chunks_success(
        self, mock_db, mock_embedding_service, sample_resource
    ):
        """Test successful chunk storage."""
        service = ChunkingService(
            db=mock_db,
            strategy="semantic",
            chunk_size=10,
            overlap=2,
            embedding_service=mock_embedding_service,
        )

        # Mock resource query
        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_resource
        )

        chunks = [
            {"content": "Chunk 1", "chunk_index": 0, "chunk_metadata": {}},
            {"content": "Chunk 2", "chunk_index": 1, "chunk_metadata": {}},
        ]

        resource_id = str(sample_resource.id)
        stored = service.store_chunks(resource_id, chunks)

        # Should return stored chunks
        assert len(stored) == 2

        # Should have called db operations
        assert mock_db.bulk_save_objects.called
        assert mock_db.commit.called

    def test_store_chunks_empty_list(self, mock_db, mock_embedding_service):
        """Test storing empty chunk list."""
        service = ChunkingService(
            db=mock_db,
            strategy="semantic",
            chunk_size=10,
            overlap=2,
            embedding_service=mock_embedding_service,
        )

        resource_id = str(uuid.uuid4())
        stored = service.store_chunks(resource_id, [])

        # Should return empty list
        assert stored == []

        # Should not call db operations
        assert not mock_db.commit.called

    def test_store_chunks_invalid_resource_id(self, mock_db, mock_embedding_service):
        """Test storing chunks with invalid resource ID."""
        service = ChunkingService(
            db=mock_db,
            strategy="semantic",
            chunk_size=10,
            overlap=2,
            embedding_service=mock_embedding_service,
        )

        chunks = [{"content": "Test", "chunk_index": 0, "chunk_metadata": {}}]

        with pytest.raises(ValueError, match="Invalid resource_id format"):
            service.store_chunks("invalid-uuid", chunks)

    def test_store_chunks_resource_not_found(self, mock_db, mock_embedding_service):
        """Test storing chunks when resource doesn't exist."""
        service = ChunkingService(
            db=mock_db,
            strategy="semantic",
            chunk_size=10,
            overlap=2,
            embedding_service=mock_embedding_service,
        )

        # Mock resource not found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        chunks = [{"content": "Test", "chunk_index": 0, "chunk_metadata": {}}]
        resource_id = str(uuid.uuid4())

        with pytest.raises(ValueError, match="Resource not found"):
            service.store_chunks(resource_id, chunks)

    def test_store_chunks_embedding_failure(self, mock_db, sample_resource):
        """Test chunk storage when embedding generation fails.

        The service fails fast on embedding errors to preserve transaction
        integrity — no partial chunks should be stored.
        """
        # Mock embedding service that fails
        failing_service = Mock()
        failing_service.generate_embedding = Mock(
            side_effect=Exception("Embedding failed")
        )

        service = ChunkingService(
            db=mock_db,
            strategy="semantic",
            chunk_size=10,
            overlap=2,
            embedding_service=failing_service,
        )

        # Mock resource query
        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_resource
        )

        chunks = [{"content": "Test", "chunk_index": 0, "chunk_metadata": {}}]
        resource_id = str(sample_resource.id)

        # Fail-fast: exception propagates and transaction is rolled back
        with pytest.raises(Exception, match="Embedding failed"):
            service.store_chunks(resource_id, chunks)

        # Should have rolled back on failure
        assert mock_db.rollback.called


class TestChunkResourceIntegration:
    """Tests for the main chunk_resource method."""

    @patch("app.modules.resources.service.event_bus")
    def test_chunk_resource_semantic_success(
        self, mock_event_bus, mock_db, mock_embedding_service, sample_resource
    ):
        """Test successful resource chunking with semantic strategy."""
        service = ChunkingService(
            db=mock_db,
            strategy="semantic",
            chunk_size=10,
            overlap=2,
            embedding_service=mock_embedding_service,
        )

        # Mock resource query
        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_resource
        )

        content = "First sentence. Second sentence. Third sentence."
        resource_id = str(sample_resource.id)

        chunks = service.chunk_resource(resource_id, content)

        # Should return stored chunks
        assert len(chunks) > 0

        # Should emit success event
        mock_event_bus.emit.assert_called()
        call_args = mock_event_bus.emit.call_args_list
        success_event = [call for call in call_args if call[0][0] == "resource.chunked"]
        assert len(success_event) > 0

    @patch("app.modules.resources.service.event_bus")
    def test_chunk_resource_fixed_success(
        self, mock_event_bus, mock_db, mock_embedding_service, sample_resource
    ):
        """Test successful resource chunking with fixed strategy."""
        service = ChunkingService(
            db=mock_db,
            strategy="fixed",
            chunk_size=50,
            overlap=10,
            embedding_service=mock_embedding_service,
        )

        # Mock resource query
        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_resource
        )

        content = "A" * 150
        resource_id = str(sample_resource.id)

        chunks = service.chunk_resource(resource_id, content)

        # Should return stored chunks
        assert len(chunks) > 0

        # Should emit success event
        mock_event_bus.emit.assert_called()

    @patch("app.modules.resources.service.event_bus")
    def test_chunk_resource_failure(
        self, mock_event_bus, mock_db, mock_embedding_service
    ):
        """Test resource chunking failure and error event emission."""
        service = ChunkingService(
            db=mock_db,
            strategy="semantic",
            chunk_size=10,
            overlap=2,
            embedding_service=mock_embedding_service,
        )

        # Mock resource not found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        content = "Test content"
        resource_id = str(uuid.uuid4())

        with pytest.raises(ValueError):
            service.chunk_resource(resource_id, content)

        # Should emit failure event
        call_args = mock_event_bus.emit.call_args_list
        failure_event = [
            call for call in call_args if call[0][0] == "resource.chunking_failed"
        ]
        assert len(failure_event) > 0

    def test_chunk_resource_invalid_strategy(self, mock_db, mock_embedding_service):
        """Test chunking with invalid strategy."""
        service = ChunkingService(
            db=mock_db,
            strategy="invalid_strategy",
            chunk_size=10,
            overlap=2,
            embedding_service=mock_embedding_service,
        )

        content = "Test content"
        resource_id = str(uuid.uuid4())

        with pytest.raises(ValueError, match="Unknown chunking strategy"):
            service.chunk_resource(resource_id, content)


class TestErrorHandling:
    """Tests for error handling in ChunkingService."""

    def test_nltk_fallback(self, mock_db, mock_embedding_service):
        """Test fallback to simple splitting when NLTK fails."""
        service = ChunkingService(
            db=mock_db,
            strategy="semantic",
            chunk_size=10,
            overlap=2,
            embedding_service=mock_embedding_service,
        )

        # This should work even if NLTK is not available
        content = "Sentence one. Sentence two. Sentence three."
        resource_id = str(uuid.uuid4())

        chunks = service.semantic_chunk(resource_id, content)

        # Should still create chunks
        assert len(chunks) > 0
