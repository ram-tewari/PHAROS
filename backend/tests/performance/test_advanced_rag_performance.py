"""
Performance tests for Advanced RAG Architecture.

Tests verify that all Advanced RAG operations meet performance requirements:
- Chunking: 10,000 words in < 5 seconds
- Graph extraction: 100 chunks in < 5 minutes (300ms per chunk)
- Parent-child retrieval: < 200ms
- GraphRAG retrieval: < 500ms

Validates: Requirements 12.1-12.9
"""

import pytest
import time
import uuid
from sqlalchemy.orm import Session

from app.database.models import Resource, DocumentChunk, GraphEntity, GraphRelationship
from app.modules.resources.service import ChunkingService
from app.modules.graph.service import GraphExtractionService
from app.modules.search.service import SearchService
from tests.performance import performance_limit


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def large_document_content():
    """Generate a large document with ~10,000 words."""
    # Average word length is 5 characters + 1 space = 6 characters per word
    # 10,000 words * 6 = 60,000 characters
    words = []
    for i in range(10000):
        # Create varied content to simulate real documents
        if i % 100 == 0:
            words.append(f"\n\nSection {i // 100}: ")
        words.append(f"word{i % 1000}")

    return " ".join(words)


@pytest.fixture
def chunking_service(db_session):
    """Create a ChunkingService instance."""
    return ChunkingService(
        db=db_session, strategy="semantic", chunk_size=500, overlap=50
    )


@pytest.fixture
def graph_service(db_session):
    """Create a GraphExtractionService instance."""
    return GraphExtractionService(db=db_session, extraction_method="spacy")


@pytest.fixture
def search_service(db_session):
    """Create a SearchService instance."""
    return SearchService(db=db_session)


@pytest.fixture
def test_resource(db_session):
    """Create a test resource."""
    resource = Resource(
        title="Performance Test Resource",
        description="Large document for performance testing",
        type="article",
        source="https://example.com/perf-test",
    )
    db_session.add(resource)
    db_session.commit()
    db_session.refresh(resource)
    return resource


# ============================================================================
# Chunking Performance Tests
# ============================================================================


@pytest.mark.performance
class TestChunkingPerformance:
    """Test chunking performance meets requirements."""

    def test_chunking_10k_words_under_5_seconds(
        self,
        db_session: Session,
        test_resource: Resource,
        chunking_service: ChunkingService,
        large_document_content: str,
    ):
        """
        Test chunking 10,000 words completes in < 5 seconds.

        Validates: Requirements 12.1
        """
        start_time = time.perf_counter()

        # Chunk the large document
        chunks = chunking_service.semantic_chunk(
            resource_id=str(test_resource.id), content=large_document_content
        )

        # Store chunks (part of the operation)
        chunking_service.store_chunks(chunks=chunks, resource_id=str(test_resource.id))

        end_time = time.perf_counter()
        elapsed_time = end_time - start_time

        # Verify performance requirement
        assert elapsed_time < 5.0, (
            f"Chunking 10,000 words took {elapsed_time:.2f}s, requirement is < 5s"
        )

        # Verify chunks were created
        stored_chunks = (
            db_session.query(DocumentChunk)
            .filter(DocumentChunk.resource_id == test_resource.id)
            .all()
        )
        assert len(stored_chunks) > 0, "Chunks should be created"

        print(
            f"✓ Chunked 10,000 words in {elapsed_time:.2f}s "
            f"({len(stored_chunks)} chunks)"
        )

    @performance_limit(max_ms=5000)
    def test_chunking_performance_with_decorator(
        self,
        db_session: Session,
        test_resource: Resource,
        chunking_service: ChunkingService,
        large_document_content: str,
    ):
        """
        Test chunking with performance_limit decorator.

        Validates: Requirements 12.1
        """
        # Chunk and store
        chunks = chunking_service.semantic_chunk(
            resource_id=str(test_resource.id), content=large_document_content
        )
        chunking_service.store_chunks(chunks=chunks, resource_id=str(test_resource.id))

        # Verify chunks created
        stored_chunks = (
            db_session.query(DocumentChunk)
            .filter(DocumentChunk.resource_id == test_resource.id)
            .all()
        )
        assert len(stored_chunks) > 0


# ============================================================================
# Graph Extraction Performance Tests
# ============================================================================


@pytest.mark.performance
class TestGraphExtractionPerformance:
    """Test graph extraction performance meets requirements."""

    @pytest.mark.xfail(strict=True, reason="no entity extractor works offline ('llm' needs an AI service, 'spacy' needs spaCy + en_core_web_sm); see test_extraction_without_extractor_reports_unavailable")
    def test_graph_extraction_100_chunks_under_5_minutes(
        self, db_session: Session, graph_service: GraphExtractionService
    ):
        """
        Test extracting from 100 chunks completes in < 5 minutes.

        This means each chunk should process in < 3 seconds on average.

        Validates: Requirements 12.2
        """
        # Create 100 test chunks with varied content
        chunks = []
        resource = Resource(
            title="Graph Extraction Test",
            description="Test resource",
            type="article",
            source="https://example.com/graph-test",
        )
        db_session.add(resource)
        db_session.commit()

        for i in range(100):
            chunk = DocumentChunk(
                resource_id=resource.id,
                content=f"This is test chunk {i} discussing concepts like "
                f"machine learning, neural networks, and data science. "
                f"The research by Dr. Smith extends the work of Johnson. "
                f"The method contradicts previous findings.",
                chunk_index=i,
                chunk_metadata={"test": True},
            )
            db_session.add(chunk)
            chunks.append(chunk)

        db_session.commit()

        # Refresh to get IDs
        for chunk in chunks:
            db_session.refresh(chunk)

        start_time = time.perf_counter()

        # Extract entities and relationships from all chunks
        for chunk in chunks:
            entities = graph_service.extract_entities(chunk.content)
            graph_service.extract_relationships(chunk.content, entities)

            # Store entities
            for entity_data in entities:
                entity = GraphEntity(
                    name=entity_data["name"],
                    type=entity_data["type"],
                    description=entity_data.get("description", ""),
                )
                db_session.add(entity)

            db_session.flush()

        db_session.commit()

        end_time = time.perf_counter()
        elapsed_time = end_time - start_time

        # Verify performance requirement (5 minutes = 300 seconds)
        assert elapsed_time < 300.0, (
            f"Graph extraction for 100 chunks took {elapsed_time:.2f}s, "
            f"requirement is < 300s (5 minutes)"
        )

        # Verify entities were created
        entities = db_session.query(GraphEntity).all()
        assert len(entities) > 0, "Entities should be created"

        avg_time_per_chunk = elapsed_time / 100
        print(
            f"✓ Extracted from 100 chunks in {elapsed_time:.2f}s "
            f"({avg_time_per_chunk:.2f}s per chunk, {len(entities)} entities)"
        )

    def test_single_chunk_extraction_performance(
        self, db_session: Session, graph_service: GraphExtractionService
    ):
        """
        Test single chunk extraction is reasonably fast (< 3s).

        Validates: Requirements 12.2
        """
        # Create a test chunk
        resource = Resource(
            title="Single Chunk Test",
            description="Test resource",
            type="article",
            source="https://example.com/single-test",
        )
        db_session.add(resource)
        db_session.commit()

        chunk = DocumentChunk(
            resource_id=resource.id,
            content="Machine learning research by Dr. Smith extends neural networks. "
            "The method contradicts previous findings by Johnson.",
            chunk_index=0,
            chunk_metadata={},
        )
        db_session.add(chunk)
        db_session.commit()
        db_session.refresh(chunk)

        start_time = time.perf_counter()

        # Extract entities and relationships
        entities = graph_service.extract_entities(chunk.content)
        relationships = graph_service.extract_relationships(chunk.content, entities)

        end_time = time.perf_counter()
        elapsed_time = end_time - start_time

        # Should be much faster than 3 seconds for a single chunk
        assert elapsed_time < 3.0, (
            f"Single chunk extraction took {elapsed_time:.2f}s, should be < 3s"
        )

        print(
            f"✓ Extracted from 1 chunk in {elapsed_time:.2f}s "
            f"({len(entities)} entities, {len(relationships)} relationships)"
        )


# ============================================================================
# Search Performance Tests
# ============================================================================


@pytest.mark.performance
class TestSearchPerformance:
    """Test search performance meets requirements."""

    @pytest.mark.xfail(strict=True, reason="parent-child search is PostgreSQL + pgvector SQL and this suite runs on in-memory SQLite; covered on PostgreSQL by tests/codeintel/test_legacy_search_pg.py")
    @performance_limit(max_ms=200)
    def test_parent_child_retrieval_under_200ms(
        self, db_session: Session, search_service: SearchService
    ):
        """
        Test parent-child retrieval completes in < 200ms.

        Validates: Requirements 12.3
        """
        # Create test data: resource with chunks
        resource = Resource(
            title="Parent-Child Test",
            description="Test resource",
            type="article",
            source="https://example.com/parent-child-test",
        )
        db_session.add(resource)
        db_session.commit()

        # Create chunks with embeddings
        for i in range(10):
            chunk = DocumentChunk(
                resource_id=resource.id,
                content=f"Chunk {i} content about machine learning and AI",
                chunk_index=i,
                chunk_metadata={},
                embedding_id=uuid.uuid4(),  # Use a UUID directly
            )
            db_session.add(chunk)

        db_session.commit()

        # Perform parent-child search (performance measured by decorator)
        results = search_service.parent_child_search(
            query="machine learning", top_k=5, context_window=2
        )

        # Verify results returned
        assert len(results) > 0, "Should return results"

    @performance_limit(max_ms=500)
    def test_graphrag_retrieval_under_500ms(
        self, db_session: Session, search_service: SearchService
    ):
        """
        Test GraphRAG retrieval completes in < 500ms.

        Validates: Requirements 12.4
        """
        # Create test data: entities and relationships
        entity1 = GraphEntity(
            name="Machine Learning", type="Concept", description="ML concept"
        )
        entity2 = GraphEntity(
            name="Neural Networks", type="Concept", description="NN concept"
        )
        db_session.add(entity1)
        db_session.add(entity2)
        db_session.flush()

        # Create relationship
        relationship = GraphRelationship(
            source_entity_id=entity1.id,
            target_entity_id=entity2.id,
            relation_type="EXTENDS",
            weight=0.8,
        )
        db_session.add(relationship)

        # Create resource and chunk
        resource = Resource(
            title="GraphRAG Test",
            description="Test resource",
            type="article",
            source="https://example.com/graphrag-test",
        )
        db_session.add(resource)
        db_session.flush()

        chunk = DocumentChunk(
            resource_id=resource.id,
            content="Content about machine learning",
            chunk_index=0,
            chunk_metadata={},
        )
        db_session.add(chunk)
        db_session.flush()

        # Link relationship to chunk
        relationship.provenance_chunk_id = chunk.id

        db_session.commit()

        # Perform GraphRAG search (performance measured by decorator)
        results = search_service.graphrag_search(
            query="machine learning", top_k=5, max_hops=2
        )

        # Verify results returned
        assert isinstance(results, list), "Should return list of results"


# ============================================================================
# End-to-End Performance Tests
# ============================================================================


@pytest.mark.performance
@pytest.mark.slow
class TestEndToEndPerformance:
    """Test complete RAG pipeline performance."""

    def test_complete_rag_pipeline_performance(
        self, db_session: Session, large_document_content: str
    ):
        """
        Test complete RAG pipeline from ingestion to retrieval.

        Validates: Requirements 12.1-12.9
        """
        # Create resource
        resource = Resource(
            title="E2E Performance Test",
            description="End-to-end test",
            type="article",
            source="https://example.com/e2e-test",
        )
        db_session.add(resource)
        db_session.commit()
        db_session.refresh(resource)

        # Initialize services
        chunking_service = ChunkingService(
            db=db_session, strategy="semantic", chunk_size=500, overlap=50
        )
        graph_service = GraphExtractionService(db=db_session, extraction_method="spacy")
        search_service = SearchService(db=db_session)

        # Measure chunking time
        chunk_start = time.perf_counter()
        chunks = chunking_service.semantic_chunk(
            resource_id=str(resource.id), content=large_document_content
        )
        chunking_service.store_chunks(chunks=chunks, resource_id=str(resource.id))
        chunk_time = time.perf_counter() - chunk_start

        # Get stored chunks
        stored_chunks = (
            db_session.query(DocumentChunk)
            .filter(DocumentChunk.resource_id == resource.id)
            .limit(10)
            .all()
        )  # Test with first 10 chunks

        # Measure graph extraction time (sample of chunks)
        graph_start = time.perf_counter()
        for chunk in stored_chunks[:5]:  # Extract from 5 chunks
            entities = graph_service.extract_entities(chunk.content)
            for entity_data in entities:
                entity = GraphEntity(
                    name=entity_data["name"],
                    type=entity_data["type"],
                    description=entity_data.get("description", ""),
                )
                db_session.add(entity)
        db_session.commit()
        graph_time = time.perf_counter() - graph_start

        # Measure search time
        search_start = time.perf_counter()
        search_service.parent_child_search(
            query="test query", top_k=5, context_window=2
        )
        search_time = time.perf_counter() - search_start

        # Report performance
        print("\n=== E2E Performance Report ===")
        print(f"Chunking: {chunk_time:.2f}s ({len(chunks)} chunks)")
        print(f"Graph Extraction: {graph_time:.2f}s (5 chunks)")
        print(f"Search: {search_time * 1000:.2f}ms")
        print(f"Total: {chunk_time + graph_time + search_time:.2f}s")

        # Verify individual requirements
        assert chunk_time < 5.0, f"Chunking too slow: {chunk_time:.2f}s"
        assert graph_time < 15.0, f"Graph extraction too slow: {graph_time:.2f}s"
        assert search_time < 0.2, f"Search too slow: {search_time:.2f}s"
