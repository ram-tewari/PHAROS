"""
Integration tests for event handlers in Advanced RAG Architecture.

Tests automatic chunking on resource creation and automatic graph extraction
on chunking, including event emission and propagation.
"""

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session

from app.shared.event_bus import event_bus, Event, EventPriority
from app.modules.resources.handlers import (
    handle_resource_created,
    register_handlers as register_resource_handlers,
)
from app.modules.graph.handlers import (
    handle_resource_chunked,
    register_handlers as register_graph_handlers,
)
from app.database.models import DocumentChunk, GraphEntity


@pytest.fixture
def clear_event_handlers():
    """Clear event handlers before and after each test."""
    event_bus.clear_handlers()
    event_bus.clear_history()
    yield
    event_bus.clear_handlers()
    event_bus.clear_history()



# The chunking handler skips resources with < 100 characters of content.
LONG_DESCRIPTION = (
    "Machine learning is a subset of Artificial Intelligence. Neural Networks are inspired by "
    "biological neurons, and Transformers use attention to model long-range dependencies."
)

class TestResourceChunkingEventHandler:
    """Test automatic chunking on resource creation."""

    def test_handle_resource_created_when_chunking_disabled(self, clear_event_handlers):
        """Test that handler does nothing when CHUNK_ON_RESOURCE_CREATE is False."""
        # Create event
        event = Event(
            name="resource.created",
            data={"resource_id": "test-resource-id"},
            priority=EventPriority.NORMAL,
        )

        # Mock settings to disable chunking
        with patch("app.modules.resources.handlers.get_settings") as mock_settings:
            mock_settings.return_value.CHUNK_ON_RESOURCE_CREATE = False

            # Call handler
            handle_resource_created(event)

            # Verify no chunking occurred (no events emitted)
            history = event_bus.get_event_history()
            assert len(history) == 0

    def test_handle_resource_created_missing_resource_id(self, clear_event_handlers):
        """Test that handler handles missing resource_id gracefully."""
        # Create event without resource_id
        event = Event(name="resource.created", data={}, priority=EventPriority.NORMAL)

        # Mock settings to enable chunking
        with patch("app.modules.resources.handlers.get_settings") as mock_settings:
            mock_settings.return_value.CHUNK_ON_RESOURCE_CREATE = True

            # Call handler
            handle_resource_created(event)

            # Verify no chunking occurred
            history = event_bus.get_event_history()
            assert len(history) == 0

    def test_handle_resource_created_triggers_chunking(
        self, db_session: Session, clear_event_handlers, create_test_resource
    ):
        """Test that handler triggers chunking when enabled."""
        # Create a test resource
        resource = create_test_resource(title="Test Resource", description=LONG_DESCRIPTION)

        # Create event
        event = Event(
            name="resource.created",
            data={"resource_id": str(resource.id)},
            priority=EventPriority.NORMAL,
        )

        # Mock settings and the entire chunking flow
        with (
            patch("app.modules.resources.handlers.get_settings") as mock_settings,
            patch("app.shared.database.SessionLocal") as mock_session_local,
        ):
            # Configure mocks
            mock_settings.return_value.CHUNK_ON_RESOURCE_CREATE = True
            mock_settings.return_value.CHUNKING_STRATEGY = "fixed"
            mock_settings.return_value.CHUNK_SIZE = 100
            mock_settings.return_value.CHUNK_OVERLAP = 10

            # Mock session to return our test session
            mock_session_local.return_value = db_session

            # Mock ChunkingService
            with patch(
                "app.modules.resources.service.ChunkingService"
            ) as mock_chunking_service:
                mock_service_instance = MagicMock()
                mock_chunks = [
                    MagicMock(id="chunk1"),
                    MagicMock(id="chunk2"),
                    MagicMock(id="chunk3"),
                ]
                mock_service_instance.chunk_resource.return_value = mock_chunks
                mock_chunking_service.return_value = mock_service_instance

                # Call handler
                handle_resource_created(event)

                # Verify chunking service was called
                mock_chunking_service.assert_called_once()

                # Verify resource.chunked event was emitted
                history = event_bus.get_event_history()
                chunked_events = [e for e in history if e["name"] == "resource.chunked"]
                assert len(chunked_events) == 1
                assert chunked_events[0]["data"]["resource_id"] == str(resource.id)
                assert chunked_events[0]["data"]["chunk_count"] == 3

    def test_handle_resource_created_emits_failure_event_on_error(
        self, clear_event_handlers
    ):
        """Test that handler emits failure event when chunking fails."""
        # Create event with invalid resource_id
        event = Event(
            name="resource.created",
            data={"resource_id": "invalid-uuid"},
            priority=EventPriority.NORMAL,
        )

        # Mock settings to enable chunking
        with patch("app.modules.resources.handlers.get_settings") as mock_settings:
            mock_settings.return_value.CHUNK_ON_RESOURCE_CREATE = True
            mock_settings.return_value.CHUNKING_STRATEGY = "fixed"
            mock_settings.return_value.CHUNK_SIZE = 100
            mock_settings.return_value.CHUNK_OVERLAP = 10

            # Call handler
            handle_resource_created(event)

            # Verify failure event was emitted
            history = event_bus.get_event_history()
            failed_events = [
                e for e in history if e["name"] == "resource.chunking_failed"
            ]
            assert len(failed_events) == 1
            assert failed_events[0]["data"]["resource_id"] == "invalid-uuid"
            assert "error" in failed_events[0]["data"]

    def test_register_handlers_subscribes_to_resource_created(
        self, clear_event_handlers
    ):
        """Test that register_handlers subscribes to resource.created event."""
        # Register handlers
        register_resource_handlers()

        # Verify handler is subscribed
        handlers = event_bus.get_handlers("resource.created")
        assert len(handlers) > 0
        assert handle_resource_created in handlers


class TestGraphExtractionEventHandler:
    """Test automatic graph extraction on chunking."""

    def test_handle_resource_chunked_when_extraction_disabled(
        self, clear_event_handlers
    ):
        """Test that handler does nothing when GRAPH_EXTRACT_ON_CHUNK is False."""
        # Create event
        event = Event(
            name="resource.chunked",
            data={"resource_id": "test-resource-id", "chunk_count": 5},
            priority=EventPriority.NORMAL,
        )

        # Mock settings to disable extraction
        with patch("app.modules.graph.handlers.get_settings") as mock_settings:
            mock_settings.return_value.GRAPH_EXTRACT_ON_CHUNK = False

            # Call handler
            handle_resource_chunked(event)

            # Verify no extraction occurred (no events emitted)
            history = event_bus.get_event_history()
            assert len(history) == 0

    def test_handle_resource_chunked_missing_resource_id(self, clear_event_handlers):
        """Test that handler handles missing resource_id gracefully."""
        # Create event without resource_id
        event = Event(
            name="resource.chunked",
            data={"chunk_count": 5},
            priority=EventPriority.NORMAL,
        )

        # Mock settings to enable extraction
        with patch("app.modules.graph.handlers.get_settings") as mock_settings:
            mock_settings.return_value.GRAPH_EXTRACT_ON_CHUNK = True

            # Call handler
            handle_resource_chunked(event)

            # Verify no extraction occurred
            history = event_bus.get_event_history()
            assert len(history) == 0

    def test_extraction_without_extractor_reports_unavailable(
        self, db_session: Session, clear_event_handlers, create_test_resource
    ):
        """No extractor configured: no entities, and the completion event says so."""
        resource = create_test_resource(title="Test Resource", description=LONG_DESCRIPTION)
        db_session.add(DocumentChunk(resource_id=resource.id, content="Neural Networks learn.", chunk_index=0))
        db_session.commit()
        event = Event(name="resource.chunked", data={"resource_id": str(resource.id), "chunk_count": 1},
                      priority=EventPriority.NORMAL)

        with (
            patch("app.modules.graph.handlers.get_settings") as mock_settings,
            patch("app.shared.database.SessionLocal", return_value=db_session),
            patch("importlib.util.find_spec", return_value=None),  # no spaCy
        ):
            mock_settings.return_value.GRAPH_EXTRACT_ON_CHUNK = True
            mock_settings.return_value.GRAPH_EXTRACTION_METHOD = "hybrid"
            handle_resource_chunked(event)

        assert db_session.query(GraphEntity).count() == 0
        done = [e for e in event_bus.get_event_history() if e["name"] == "graph.extraction_complete"]
        assert len(done) == 1 and done[0]["data"]["status"] == "unavailable"

    @pytest.mark.xfail(strict=True, reason="No entity extractor works offline: the 'llm' method needs an AI service and 'spacy' needs spaCy + en_core_web_sm; the handler now reports status=unavailable ""(see test_extraction_without_extractor_reports_unavailable)")
    def test_handle_resource_chunked_triggers_extraction(
        self, db_session: Session, clear_event_handlers, create_test_resource
    ):
        """Test that handler triggers graph extraction when enabled."""
        # Create a test resource with chunks
        resource = create_test_resource(title="Test Resource", description=LONG_DESCRIPTION)

        # Create chunks
        chunk1 = DocumentChunk(
            resource_id=resource.id,
            content="Machine learning is a subset of artificial intelligence.",
            chunk_index=0,
        )
        chunk2 = DocumentChunk(
            resource_id=resource.id,
            content="Neural networks are inspired by biological neural networks.",
            chunk_index=1,
        )
        db_session.add_all([chunk1, chunk2])
        db_session.commit()

        # Create event
        event = Event(
            name="resource.chunked",
            data={"resource_id": str(resource.id), "chunk_count": 2},
            priority=EventPriority.NORMAL,
        )

        # Mock settings and SessionLocal
        with (
            patch("app.modules.graph.handlers.get_settings") as mock_settings,
            patch("app.shared.database.SessionLocal", return_value=db_session),
        ):
            mock_settings.return_value.GRAPH_EXTRACT_ON_CHUNK = True

            # Call handler
            handle_resource_chunked(event)

            # Verify entities were extracted
            entities = db_session.query(GraphEntity).all()
            assert len(entities) > 0

            # Verify extraction complete event was emitted
            history = event_bus.get_event_history()
            complete_events = [
                e for e in history if e["name"] == "graph.extraction_complete"
            ]
            assert len(complete_events) == 1
            assert complete_events[0]["data"]["resource_id"] == str(resource.id)
            assert complete_events[0]["data"]["chunk_count"] == 2

    def test_handle_resource_chunked_no_chunks_found(
        self, db_session: Session, clear_event_handlers, create_test_resource
    ):
        """Test that handler handles case when no chunks are found."""
        # Create a test resource without chunks
        resource = create_test_resource(title="Test Resource", description=LONG_DESCRIPTION)

        # Create event
        event = Event(
            name="resource.chunked",
            data={"resource_id": str(resource.id), "chunk_count": 0},
            priority=EventPriority.NORMAL,
        )

        # Mock settings to enable extraction
        with patch("app.modules.graph.handlers.get_settings") as mock_settings:
            mock_settings.return_value.GRAPH_EXTRACT_ON_CHUNK = True

            # Call handler
            handle_resource_chunked(event)

            # Verify no extraction occurred (no complete event)
            history = event_bus.get_event_history()
            complete_events = [
                e for e in history if e["name"] == "graph.extraction_complete"
            ]
            assert len(complete_events) == 0

    def test_handle_resource_chunked_emits_failure_event_on_error(
        self, clear_event_handlers
    ):
        """Test that handler emits failure event when extraction fails."""
        # Create event with invalid resource_id
        event = Event(
            name="resource.chunked",
            data={"resource_id": "invalid-uuid", "chunk_count": 5},
            priority=EventPriority.NORMAL,
        )

        # Mock settings to enable extraction
        with patch("app.modules.graph.handlers.get_settings") as mock_settings:
            mock_settings.return_value.GRAPH_EXTRACT_ON_CHUNK = True

            # Call handler
            handle_resource_chunked(event)

            # Verify failure event was emitted
            history = event_bus.get_event_history()
            failed_events = [
                e for e in history if e["name"] == "graph.extraction_failed"
            ]
            assert len(failed_events) == 1
            assert failed_events[0]["data"]["resource_id"] == "invalid-uuid"
            assert "error" in failed_events[0]["data"]

    def test_register_handlers_subscribes_to_resource_chunked(
        self, clear_event_handlers
    ):
        """Test that register_handlers subscribes to resource.chunked event."""
        # Register handlers
        register_graph_handlers()

        # Verify handler is subscribed
        handlers = event_bus.get_handlers("resource.chunked")
        assert len(handlers) > 0
        assert handle_resource_chunked in handlers


class TestEventPropagation:
    """Test end-to-end event propagation from resource creation to graph extraction."""

    @pytest.mark.xfail(strict=True, reason="No entity extractor works offline: the 'llm' method needs an AI service and 'spacy' needs spaCy + en_core_web_sm; the handler now reports status=unavailable ""(see test_extraction_without_extractor_reports_unavailable)")
    def test_full_event_chain(
        self, db_session: Session, clear_event_handlers, create_test_resource
    ):
        """Test complete event chain: resource.created -> chunking -> resource.chunked -> extraction."""
        # Register all handlers
        register_resource_handlers()
        register_graph_handlers()

        # Create a test resource
        resource = create_test_resource(title="Test Resource", description=LONG_DESCRIPTION)

        # Create chunks manually (simulating what chunking would do)
        chunk1 = DocumentChunk(
            resource_id=resource.id,
            content="Machine learning and artificial intelligence are related fields.",
            chunk_index=0,
        )
        chunk2 = DocumentChunk(
            resource_id=resource.id,
            content="Neural networks are a key component of modern AI systems.",
            chunk_index=1,
        )
        db_session.add_all([chunk1, chunk2])
        db_session.commit()

        # Mock settings and SessionLocal
        with (
            patch("app.modules.resources.handlers.get_settings") as mock_res_settings,
            patch("app.modules.graph.handlers.get_settings") as mock_graph_settings,
            patch("app.shared.database.SessionLocal") as mock_session_local,
        ):
            mock_res_settings.return_value.CHUNK_ON_RESOURCE_CREATE = True
            mock_res_settings.return_value.CHUNKING_STRATEGY = "fixed"
            mock_res_settings.return_value.CHUNK_SIZE = 100
            mock_res_settings.return_value.CHUNK_OVERLAP = 10

            mock_graph_settings.return_value.GRAPH_EXTRACT_ON_CHUNK = True

            # Mock session to return our test session
            mock_session_local.return_value = db_session

            # Mock ChunkingService
            with patch(
                "app.modules.resources.service.ChunkingService"
            ) as mock_chunking_service:
                mock_service_instance = MagicMock()
                mock_service_instance.chunk_resource.return_value = [chunk1, chunk2]
                mock_chunking_service.return_value = mock_service_instance

                # Emit resource.created event
                event_bus.emit(
                    "resource.created",
                    {"resource_id": str(resource.id)},
                    priority=EventPriority.NORMAL,
                )

                # Verify entities were extracted
                entities = db_session.query(GraphEntity).all()
                assert len(entities) > 0

                # Verify event chain in history
                history = event_bus.get_event_history()
                event_names = [e["name"] for e in history]

                assert "resource.created" in event_names
                assert "resource.chunked" in event_names
                assert "graph.extraction_complete" in event_names

    def test_event_chain_with_chunking_disabled(
        self, db_session: Session, clear_event_handlers, create_test_resource
    ):
        """Test that disabling chunking breaks the event chain."""
        # Register all handlers
        register_resource_handlers()
        register_graph_handlers()

        # Create a test resource
        resource = create_test_resource(title="Test Resource", description=LONG_DESCRIPTION)

        # Mock settings to disable chunking but enable extraction
        with (
            patch("app.modules.resources.handlers.get_settings") as mock_res_settings,
            patch("app.modules.graph.handlers.get_settings") as mock_graph_settings,
        ):
            mock_res_settings.return_value.CHUNK_ON_RESOURCE_CREATE = False
            mock_graph_settings.return_value.GRAPH_EXTRACT_ON_CHUNK = True

            # Emit resource.created event
            event_bus.emit(
                "resource.created",
                {"resource_id": str(resource.id)},
                priority=EventPriority.NORMAL,
            )

            # Verify no chunks were created
            chunks = (
                db_session.query(DocumentChunk)
                .filter(DocumentChunk.resource_id == resource.id)
                .all()
            )
            assert len(chunks) == 0

            # Verify no entities were extracted
            entities = db_session.query(GraphEntity).all()
            assert len(entities) == 0

            # Verify only resource.created event in history
            history = event_bus.get_event_history()
            event_names = [e["name"] for e in history]

            assert "resource.created" in event_names
            assert "resource.chunked" not in event_names
            assert "graph.extraction_complete" not in event_names

    def test_event_chain_with_extraction_disabled(
        self, db_session: Session, clear_event_handlers, create_test_resource
    ):
        """Test that disabling extraction stops at chunking."""
        # Register all handlers
        register_resource_handlers()
        register_graph_handlers()

        # Create a test resource
        resource = create_test_resource(title="Test Resource", description=LONG_DESCRIPTION)

        # Create chunks manually
        chunk1 = DocumentChunk(
            resource_id=resource.id, content="Test content chunk 1", chunk_index=0
        )
        chunk2 = DocumentChunk(
            resource_id=resource.id, content="Test content chunk 2", chunk_index=1
        )
        db_session.add_all([chunk1, chunk2])
        db_session.commit()

        # Mock settings and SessionLocal
        with (
            patch("app.modules.resources.handlers.get_settings") as mock_res_settings,
            patch("app.modules.graph.handlers.get_settings") as mock_graph_settings,
            patch("app.shared.database.SessionLocal") as mock_session_local,
        ):
            mock_res_settings.return_value.CHUNK_ON_RESOURCE_CREATE = True
            mock_res_settings.return_value.CHUNKING_STRATEGY = "fixed"
            mock_res_settings.return_value.CHUNK_SIZE = 100
            mock_res_settings.return_value.CHUNK_OVERLAP = 10

            mock_graph_settings.return_value.GRAPH_EXTRACT_ON_CHUNK = False

            # Mock session to return our test session
            mock_session_local.return_value = db_session

            # Mock ChunkingService
            with patch(
                "app.modules.resources.service.ChunkingService"
            ) as mock_chunking_service:
                mock_service_instance = MagicMock()
                mock_service_instance.chunk_resource.return_value = [chunk1, chunk2]
                mock_chunking_service.return_value = mock_service_instance

                # Emit resource.created event
                event_bus.emit(
                    "resource.created",
                    {"resource_id": str(resource.id)},
                    priority=EventPriority.NORMAL,
                )

                # Verify chunks exist
                chunks = (
                    db_session.query(DocumentChunk)
                    .filter(DocumentChunk.resource_id == resource.id)
                    .all()
                )
                assert len(chunks) == 2

                # Verify no entities were extracted
                entities = db_session.query(GraphEntity).all()
                assert len(entities) == 0

                # Verify event chain stops at chunking
                history = event_bus.get_event_history()
                event_names = [e["name"] for e in history]

                assert "resource.created" in event_names
                assert "resource.chunked" in event_names
                assert "graph.extraction_complete" not in event_names
