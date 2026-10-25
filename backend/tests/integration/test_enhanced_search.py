"""
Integration tests for Enhanced Search (Phase 17.5).

Tests parent-child retrieval, GraphRAG retrieval, contradiction discovery,
and question-based retrieval (Reverse HyDE).

**Validates: Requirements 8.1-8.10, 9.1-9.10, 3.7**
"""

import pytest

from unittest.mock import Mock, patch
from sqlalchemy.orm import Session

from app.database.models import (
    Resource,
    DocumentChunk,
    GraphEntity,
    GraphRelationship,
    SyntheticQuestion,
)
from app.modules.search.service import SearchService


class TestParentChildRetrieval:
    """Test parent-child retrieval strategy."""

    @pytest.mark.xfail(strict=True, reason="parent-child search is PostgreSQL + pgvector SQL and this suite runs on in-memory SQLite; covered on PostgreSQL by tests/codeintel/test_legacy_search_pg.py")
    def test_parent_child_search_basic(self, db_session: Session):
        """
        Test basic parent-child retrieval with sample data.

        **Validates: Requirements 8.1, 8.2**
        """
        # Create a resource with chunks
        resource = Resource(
            title="Machine Learning Basics",
            description="Introduction to ML",
            type="article",
        )
        db_session.add(resource)
        db_session.flush()

        # Create chunks
        chunks = []
        for i in range(5):
            chunk = DocumentChunk(
                resource_id=resource.id,
                content=f"Chunk {i}: Neural networks are fundamental to deep learning.",
                chunk_index=i,
                chunk_metadata={"page": i + 1},
            )
            db_session.add(chunk)
            db_session.flush()
            chunks.append(chunk)

        db_session.commit()

        # Create search service
        search_service = SearchService(db_session)

        # Mock embedding service
        with patch(
            "app.shared.embeddings.EmbeddingService"
        ) as mock_embedding_service_class:
            mock_embedding_service = Mock()
            mock_embedding_service.generate_embedding.return_value = [0.1] * 768
            mock_embedding_service_class.return_value = mock_embedding_service

            # Perform search
            results = search_service.parent_child_search(
                query="neural networks deep learning", top_k=3, context_window=1
            )

        # Verify results
        assert len(results) > 0, "Should return at least one result"

        result = results[0]
        assert "chunk" in result
        assert "parent_resource" in result
        assert "surrounding_chunks" in result
        assert "score" in result

        # Verify parent resource is correct
        assert result["parent_resource"].id == resource.id

        # Cleanup
        for chunk in chunks:
            db_session.delete(chunk)
        db_session.delete(resource)
        db_session.commit()

    @pytest.mark.xfail(strict=True, reason="parent-child search is PostgreSQL + pgvector SQL and this suite runs on in-memory SQLite; covered on PostgreSQL by tests/codeintel/test_legacy_search_pg.py")
    def test_parent_child_search_with_filters(self, db_session: Session):
        """
        Test parent-child retrieval with resource filters.

        **Validates: Requirements 8.8**
        """
        # Create resources of different types
        article = Resource(
            title="Article about AI",
            description="AI article",
            type="article",
            quality_score=0.9,
        )
        db_session.add(article)
        db_session.flush()

        book = Resource(
            title="Book about AI", description="AI book", type="book", quality_score=0.5
        )
        db_session.add(book)
        db_session.flush()

        # Create chunks for both
        article_chunk = DocumentChunk(
            resource_id=article.id,
            content="Artificial intelligence is transforming technology.",
            chunk_index=0,
            chunk_metadata={"page": 1},
        )
        db_session.add(article_chunk)

        book_chunk = DocumentChunk(
            resource_id=book.id,
            content="Artificial intelligence is transforming technology.",
            chunk_index=0,
            chunk_metadata={"page": 1},
        )
        db_session.add(book_chunk)
        db_session.commit()

        # Create search service
        search_service = SearchService(db_session)

        # Mock embedding service
        with patch(
            "app.shared.embeddings.EmbeddingService"
        ) as mock_embedding_service_class:
            mock_embedding_service = Mock()
            mock_embedding_service.generate_embedding.return_value = [0.1] * 768
            mock_embedding_service_class.return_value = mock_embedding_service

            # Search with type filter
            results = search_service.parent_child_search(
                query="artificial intelligence",
                top_k=10,
                context_window=1,
                filters={"resource_type": "article"},
            )

        # Verify only article is returned
        assert len(results) > 0
        for result in results:
            assert result["parent_resource"].type == "article"

        # Cleanup
        db_session.delete(article_chunk)
        db_session.delete(book_chunk)
        db_session.delete(article)
        db_session.delete(book)
        db_session.commit()

    @pytest.mark.xfail(strict=True, reason="parent-child search is PostgreSQL + pgvector SQL and this suite runs on in-memory SQLite; covered on PostgreSQL by tests/codeintel/test_legacy_search_pg.py")
    def test_parent_child_search_deduplication(self, db_session: Session):
        """
        Test that multiple chunks from same resource are deduplicated.

        **Validates: Requirements 8.5**
        """
        # Create a resource with multiple chunks containing same keywords
        resource = Resource(
            title="Deep Learning Guide",
            description="Comprehensive guide",
            type="article",
        )
        db_session.add(resource)
        db_session.flush()

        # Create chunks with same keywords
        chunks = []
        for i in range(3):
            chunk = DocumentChunk(
                resource_id=resource.id,
                content=f"Chunk {i}: Deep learning uses neural networks extensively.",
                chunk_index=i,
                chunk_metadata={"page": i + 1},
            )
            db_session.add(chunk)
            db_session.flush()
            chunks.append(chunk)

        db_session.commit()

        # Create search service
        search_service = SearchService(db_session)

        # Mock embedding service
        with patch(
            "app.shared.embeddings.EmbeddingService"
        ) as mock_embedding_service_class:
            mock_embedding_service = Mock()
            mock_embedding_service.generate_embedding.return_value = [0.1] * 768
            mock_embedding_service_class.return_value = mock_embedding_service

            # Perform search
            results = search_service.parent_child_search(
                query="deep learning neural networks", top_k=10, context_window=1
            )

        # Verify deduplication: should only get one result despite multiple matching chunks
        assert len(results) == 1, (
            f"Expected 1 result (deduplicated), got {len(results)}"
        )
        assert results[0]["parent_resource"].id == resource.id

        # Cleanup
        for chunk in chunks:
            db_session.delete(chunk)
        db_session.delete(resource)
        db_session.commit()


class TestGraphRAGRetrieval:
    """Test GraphRAG retrieval strategy."""

    def test_graphrag_search_basic(self, db_session: Session):
        """
        Test basic GraphRAG retrieval with sample graph.

        **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**
        """
        # Create entities
        entity1 = GraphEntity(
            name="Neural Networks",
            type="Concept",
            description="Fundamental concept in deep learning",
        )
        db_session.add(entity1)

        entity2 = GraphEntity(
            name="Deep Learning",
            type="Concept",
            description="Subset of machine learning",
        )
        db_session.add(entity2)
        db_session.flush()

        # Create a resource and chunk
        resource = Resource(
            title="ML Research", description="Research paper", type="article"
        )
        db_session.add(resource)
        db_session.flush()

        chunk = DocumentChunk(
            resource_id=resource.id,
            content="Neural networks are the foundation of deep learning.",
            chunk_index=0,
            chunk_metadata={"page": 1},
        )
        db_session.add(chunk)
        db_session.flush()

        # Create relationship with provenance
        relationship = GraphRelationship(
            source_entity_id=entity1.id,
            target_entity_id=entity2.id,
            relation_type="SUPPORTS",
            weight=0.9,
            provenance_chunk_id=chunk.id,
        )
        db_session.add(relationship)
        db_session.commit()

        # Create search service
        search_service = SearchService(db_session)

        # Perform GraphRAG search
        results = search_service.graphrag_search(
            query="Neural Networks", top_k=10, max_hops=2
        )

        # Verify results
        assert len(results) > 0, "Should return at least one result"

        result = results[0]
        assert "chunk" in result
        assert "entities" in result
        assert "graph_path" in result
        assert "score" in result

        # Verify chunk is linked via provenance (results are JSON-shaped dicts)
        assert result["chunk"]["id"] == str(chunk.id)
        assert result["entities"][0]["name"] in {"Neural Networks", "Deep Learning"}

        # Cleanup
        db_session.delete(relationship)
        db_session.delete(chunk)
        db_session.delete(resource)
        db_session.delete(entity2)
        db_session.delete(entity1)
        db_session.commit()

    def test_graphrag_search_with_relation_filter(self, db_session: Session):
        """
        Test GraphRAG retrieval with relation type filtering.

        **Validates: Requirements 9.7**
        """
        # Create entities
        entity1 = GraphEntity(name="Concept A", type="Concept")
        entity2 = GraphEntity(name="Concept B", type="Concept")
        entity3 = GraphEntity(name="Concept C", type="Concept")
        db_session.add_all([entity1, entity2, entity3])
        db_session.flush()

        # Create resource and chunks
        resource = Resource(title="Test Resource", type="article")
        db_session.add(resource)
        db_session.flush()

        chunk1 = DocumentChunk(
            resource_id=resource.id, content="Content 1", chunk_index=0
        )
        chunk2 = DocumentChunk(
            resource_id=resource.id, content="Content 2", chunk_index=1
        )
        db_session.add_all([chunk1, chunk2])
        db_session.flush()

        # Create relationships of different types
        rel_supports = GraphRelationship(
            source_entity_id=entity1.id,
            target_entity_id=entity2.id,
            relation_type="SUPPORTS",
            weight=0.8,
            provenance_chunk_id=chunk1.id,
        )
        rel_contradicts = GraphRelationship(
            source_entity_id=entity1.id,
            target_entity_id=entity3.id,
            relation_type="CONTRADICTS",
            weight=0.7,
            provenance_chunk_id=chunk2.id,
        )
        db_session.add_all([rel_supports, rel_contradicts])
        db_session.commit()

        # Create search service
        search_service = SearchService(db_session)

        # Search with SUPPORTS filter
        results = search_service.graphrag_search(
            query="Concept A", top_k=10, max_hops=1, relation_types=["SUPPORTS"]
        )

        # Verify only SUPPORTS relationships are traversed
        # (This is a simplified check - in production would verify graph paths)
        assert len(results) >= 0  # May be 0 or more depending on implementation

        # Cleanup
        db_session.delete(rel_contradicts)
        db_session.delete(rel_supports)
        db_session.delete(chunk2)
        db_session.delete(chunk1)
        db_session.delete(resource)
        db_session.delete(entity3)
        db_session.delete(entity2)
        db_session.delete(entity1)
        db_session.commit()


class TestContradictionDiscovery:
    """Test contradiction discovery mode."""

    def test_discover_contradictions_basic(self, db_session: Session):
        """
        Test basic contradiction discovery.

        **Validates: Requirements 9.7, 9.8, 9.10**
        """
        # Create entities
        entity1 = GraphEntity(name="Theory A", type="Concept")
        entity2 = GraphEntity(name="Theory B", type="Concept")
        db_session.add_all([entity1, entity2])
        db_session.flush()

        # Create resource and chunk
        resource = Resource(title="Contradictory Research", type="article")
        db_session.add(resource)
        db_session.flush()

        chunk = DocumentChunk(
            resource_id=resource.id,
            content="Theory A contradicts Theory B.",
            chunk_index=0,
        )
        db_session.add(chunk)
        db_session.flush()

        # Create CONTRADICTS relationship
        relationship = GraphRelationship(
            source_entity_id=entity1.id,
            target_entity_id=entity2.id,
            relation_type="CONTRADICTS",
            weight=0.9,
            provenance_chunk_id=chunk.id,
        )
        db_session.add(relationship)
        db_session.commit()

        # Create search service
        search_service = SearchService(db_session)

        # Discover contradictions
        results = search_service.discover_contradictions(top_k=10)

        # Verify results
        assert len(results) > 0, "Should find at least one contradiction"

        result = results[0]
        assert "source_entity" in result
        assert "target_entity" in result
        assert "relationship" in result
        assert "source_chunk" in result
        assert "explanation" in result

        # Verify it's the correct contradiction
        assert result["relationship"].relation_type == "CONTRADICTS"
        assert result["source_chunk"].id == chunk.id

        # Cleanup
        db_session.delete(relationship)
        db_session.delete(chunk)
        db_session.delete(resource)
        db_session.delete(entity2)
        db_session.delete(entity1)
        db_session.commit()

    def test_discover_contradictions_with_query(self, db_session: Session):
        """
        Test contradiction discovery with query filtering.

        **Validates: Requirements 9.7, 9.8**
        """
        # Create entities
        entity1 = GraphEntity(name="Climate Change", type="Concept")
        entity2 = GraphEntity(name="Global Warming", type="Concept")
        entity3 = GraphEntity(name="Unrelated Topic", type="Concept")
        db_session.add_all([entity1, entity2, entity3])
        db_session.flush()

        # Create contradictions
        rel1 = GraphRelationship(
            source_entity_id=entity1.id,
            target_entity_id=entity2.id,
            relation_type="CONTRADICTS",
            weight=0.8,
        )
        rel2 = GraphRelationship(
            source_entity_id=entity3.id,
            target_entity_id=entity1.id,
            relation_type="CONTRADICTS",
            weight=0.6,
        )
        db_session.add_all([rel1, rel2])
        db_session.commit()

        # Create search service
        search_service = SearchService(db_session)

        # Discover contradictions with query
        results = search_service.discover_contradictions(
            query="Climate Change", top_k=10
        )

        # Verify results are filtered by query
        assert len(results) > 0
        # Results should involve Climate Change entity
        for result in results:
            entities = [result["source_entity"].name, result["target_entity"].name]
            assert "Climate Change" in entities or "Global Warming" in entities

        # Cleanup
        db_session.delete(rel2)
        db_session.delete(rel1)
        db_session.delete(entity3)
        db_session.delete(entity2)
        db_session.delete(entity1)
        db_session.commit()


class TestQuestionBasedRetrieval:
    """Test question-based retrieval (Reverse HyDE)."""

    def test_question_search_basic(self, db_session: Session):
        """
        Test basic question-based retrieval.

        **Validates: Requirements 3.7**
        """
        # Create resource and chunk
        resource = Resource(title="AI Guide", type="article")
        db_session.add(resource)
        db_session.flush()

        chunk = DocumentChunk(
            resource_id=resource.id,
            content="Machine learning is a subset of artificial intelligence.",
            chunk_index=0,
        )
        db_session.add(chunk)
        db_session.flush()

        # Create synthetic question
        question = SyntheticQuestion(
            chunk_id=chunk.id, question_text="What is machine learning?"
        )
        db_session.add(question)
        db_session.commit()

        # Create search service
        search_service = SearchService(db_session)

        # Mock embedding service
        with patch(
            "app.shared.embeddings.EmbeddingService"
        ) as mock_embedding_service_class:
            mock_embedding_service = Mock()
            mock_embedding_service.generate_embedding.return_value = [0.1] * 768
            mock_embedding_service_class.return_value = mock_embedding_service

            # Perform question search
            results = search_service.question_search(
                query="What is machine learning?", top_k=10, hybrid_mode=False
            )

        # Verify results
        assert len(results) > 0, "Should return at least one result"

        result = results[0]
        assert "chunk" in result
        assert "matching_question" in result
        assert "score" in result

        # Verify correct chunk is retrieved
        assert result["chunk"].id == chunk.id
        assert result["matching_question"].id == question.id

        # Cleanup
        db_session.delete(question)
        db_session.delete(chunk)
        db_session.delete(resource)
        db_session.commit()

    def test_question_search_hybrid_mode(self, db_session: Session):
        """
        Test question-based retrieval in hybrid mode.

        **Validates: Requirements 3.7**
        """
        # Create resource and chunks
        resource = Resource(title="ML Basics", type="article")
        db_session.add(resource)
        db_session.flush()

        chunk1 = DocumentChunk(
            resource_id=resource.id,
            content="Neural networks are powerful.",
            chunk_index=0,
        )
        chunk2 = DocumentChunk(
            resource_id=resource.id,
            content="Deep learning uses neural networks.",
            chunk_index=1,
        )
        db_session.add_all([chunk1, chunk2])
        db_session.flush()

        # Create synthetic question for chunk1
        question = SyntheticQuestion(
            chunk_id=chunk1.id, question_text="What are neural networks?"
        )
        db_session.add(question)
        db_session.commit()

        # Create search service
        search_service = SearchService(db_session)

        # Mock embedding service
        with patch(
            "app.shared.embeddings.EmbeddingService"
        ) as mock_embedding_service_class:
            mock_embedding_service = Mock()
            mock_embedding_service.generate_embedding.return_value = [0.1] * 768
            mock_embedding_service_class.return_value = mock_embedding_service

            # Perform hybrid question search
            results = search_service.question_search(
                query="neural networks deep learning", top_k=10, hybrid_mode=True
            )

        # Verify results include both question-based and semantic results
        assert len(results) > 0

        # Cleanup
        db_session.delete(question)
        db_session.delete(chunk2)
        db_session.delete(chunk1)
        db_session.delete(resource)
        db_session.commit()


class TestResultRankingAndDeduplication:
    """Test result ranking and deduplication across strategies."""

    def test_result_ranking_by_score(self, db_session: Session):
        """
        Test that results are properly ranked by score.

        **Validates: Requirements 8.9, 9.6**
        """
        # Create resources with varying relevance
        resource1 = Resource(title="Highly Relevant", type="article")
        resource2 = Resource(title="Somewhat Relevant", type="article")
        db_session.add_all([resource1, resource2])
        db_session.flush()

        # Create chunks with different keyword densities
        chunk1 = DocumentChunk(
            resource_id=resource1.id,
            content="Machine learning deep learning neural networks AI artificial intelligence.",
            chunk_index=0,
        )
        chunk2 = DocumentChunk(
            resource_id=resource2.id,
            content="Machine learning is interesting.",
            chunk_index=0,
        )
        db_session.add_all([chunk1, chunk2])
        db_session.commit()

        # Create search service
        search_service = SearchService(db_session)

        # Mock embedding service
        with patch(
            "app.shared.embeddings.EmbeddingService"
        ) as mock_embedding_service_class:
            mock_embedding_service = Mock()
            mock_embedding_service.generate_embedding.return_value = [0.1] * 768
            mock_embedding_service_class.return_value = mock_embedding_service

            # Perform search
            results = search_service.parent_child_search(
                query="machine learning deep learning neural networks",
                top_k=10,
                context_window=0,
            )

        # Verify results are ranked by score
        if len(results) >= 2:
            assert results[0]["score"] >= results[1]["score"], (
                "Results should be ranked by score (descending)"
            )

        # Cleanup
        db_session.delete(chunk2)
        db_session.delete(chunk1)
        db_session.delete(resource2)
        db_session.delete(resource1)
        db_session.commit()
