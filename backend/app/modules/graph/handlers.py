"""
Graph Event Handlers

Emits graph-related events for knowledge graph updates and discoveries.
Subscribes to resource.chunked events for automatic graph extraction.

Events Emitted:
- citation.extracted: When citations are extracted from a resource
- graph.updated: When the knowledge graph is updated
- hypothesis.discovered: When a new hypothesis is discovered via LBD
- graph.entity_extracted: When entities are extracted from a chunk
- graph.relationship_extracted: When relationships are extracted

Events Subscribed:
- resource.chunked: Triggers automatic graph extraction if enabled
"""

import logging
from typing import Dict, Any, List

from app.shared.event_bus import event_bus, EventPriority, Event
from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def emit_citation_extracted(
    resource_id: str, citations: List[Dict[str, Any]], citation_count: int
):
    """
    Emit citation.extracted event.

    This should be called after extracting citations from a resource.

    Args:
        resource_id: UUID of the resource
        citations: List of extracted citation dictionaries
        citation_count: Number of citations extracted
    """
    try:
        event_bus.emit(
            "citation.extracted",
            {
                "resource_id": resource_id,
                "citations": citations,
                "count": citation_count,
            },
            priority=EventPriority.NORMAL,
        )
        logger.debug(f"Emitted citation.extracted event for resource {resource_id}")
    except Exception as e:
        logger.error(
            f"Error emitting citation.extracted event: {str(e)}", exc_info=True
        )


def emit_graph_updated(
    update_type: str,
    node_count: int = 0,
    edge_count: int = 0,
    affected_nodes: List[str] = None,
):
    """
    Emit graph.updated event.

    This should be called when the knowledge graph structure is updated.

    Args:
        update_type: Type of update (node_added, edge_added, node_removed, edge_removed, bulk_update)
        node_count: Number of nodes affected
        edge_count: Number of edges affected
        affected_nodes: Optional list of affected node IDs
    """
    try:
        payload = {
            "update_type": update_type,
            "node_count": node_count,
            "edge_count": edge_count,
        }

        if affected_nodes:
            payload["affected_nodes"] = affected_nodes

        event_bus.emit("graph.updated", payload, priority=EventPriority.NORMAL)
        logger.debug(f"Emitted graph.updated event: {update_type}")
    except Exception as e:
        logger.error(f"Error emitting graph.updated event: {str(e)}", exc_info=True)


def emit_hypothesis_discovered(
    hypothesis_id: str,
    concept_a: str,
    concept_c: str,
    bridging_concepts: List[str],
    plausibility_score: float,
    evidence_count: int,
):
    """
    Emit hypothesis.discovered event.

    This should be called when a new hypothesis is discovered via Literature-Based Discovery.

    Args:
        hypothesis_id: UUID of the discovered hypothesis
        concept_a: Starting concept
        concept_c: Target concept
        bridging_concepts: List of bridging concepts (B)
        plausibility_score: Plausibility score of the hypothesis
        evidence_count: Number of evidence chains supporting the hypothesis
    """
    try:
        event_bus.emit(
            "hypothesis.discovered",
            {
                "hypothesis_id": hypothesis_id,
                "concept_a": concept_a,
                "concept_c": concept_c,
                "bridging_concepts": bridging_concepts,
                "plausibility_score": plausibility_score,
                "evidence_count": evidence_count,
            },
            priority=EventPriority.HIGH,
        )
        logger.info(
            f"Emitted hypothesis.discovered event for hypothesis {hypothesis_id}"
        )
    except Exception as e:
        logger.error(
            f"Error emitting hypothesis.discovered event: {str(e)}", exc_info=True
        )


def handle_resource_chunked(event: Event) -> None:
    """
    Handle resource.chunked event to trigger automatic graph extraction.

    This handler is called when a resource is chunked. If GRAPH_EXTRACT_ON_CHUNK
    is enabled in settings, it triggers graph extraction for all chunks.

    Args:
        event: Event object containing resource chunking data
    """
    settings = get_settings()

    # Check if automatic graph extraction is enabled
    if not settings.GRAPH_EXTRACT_ON_CHUNK:
        logger.debug(
            "Automatic graph extraction disabled, skipping resource.chunked handler"
        )
        return

    payload = event.data
    resource_id = payload.get("resource_id")
    chunk_count = payload.get("chunk_count", 0)

    if not resource_id:
        logger.warning(
            "resource.chunked event missing resource_id, skipping graph extraction"
        )
        return

    logger.info(
        f"Triggering automatic graph extraction for resource {resource_id} ({chunk_count} chunks)"
    )

    try:
        # Import here to avoid circular dependencies
        from app.shared.database import SessionLocal
        from app.modules.graph.service import GraphExtractionService
        from app.database.models import DocumentChunk

        # Create database session
        db = SessionLocal()

        try:
            # Initialize graph extraction service
            graph_service = GraphExtractionService(
                db=db, extraction_method=settings.GRAPH_EXTRACTION_METHOD
            )

            # Get all chunks for this resource
            chunks = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.resource_id == resource_id)
                .all()
            )

            if not chunks:
                logger.warning(
                    f"No chunks found for resource {resource_id}, skipping graph extraction"
                )
                return

            if not graph_service.extractor_available:
                logger.warning(
                    "Graph extraction for resource %s skipped: no entity extractor is available "
                    "(GRAPH_EXTRACTION_METHOD=%s needs an AI service or spaCy + en_core_web_sm)",
                    resource_id,
                    graph_service.extraction_method,
                )
                event_bus.emit(
                    "graph.extraction_complete",
                    {
                        "resource_id": resource_id,
                        "chunk_count": len(chunks),
                        "entity_count": 0,
                        "relationship_count": 0,
                        "status": "unavailable",
                    },
                    priority=EventPriority.NORMAL,
                )
                return

            total_entities = 0
            total_relationships = 0

            # Extract entities and relationships from each chunk
            for chunk in chunks:
                try:
                    # Extract entities
                    entities = graph_service.extract_entities(chunk.content)

                    # Extract relationships
                    relationships = graph_service.extract_relationships(
                        chunk.content, entities, chunk.id
                    )

                    total_entities += len(entities)
                    total_relationships += len(relationships)

                    logger.debug(
                        f"Extracted {len(entities)} entities and {len(relationships)} relationships "
                        f"from chunk {chunk.id}"
                    )

                except Exception as chunk_error:
                    logger.error(
                        f"Error extracting from chunk {chunk.id}: {str(chunk_error)}",
                        exc_info=True,
                    )
                    # Continue with other chunks
                    continue

            logger.info(
                f"Successfully extracted {total_entities} entities and {total_relationships} relationships "
                f"from resource {resource_id}"
            )

            # Emit graph.extraction_complete event
            event_bus.emit(
                "graph.extraction_complete",
                {
                    "resource_id": resource_id,
                    "chunk_count": len(chunks),
                    "entity_count": total_entities,
                    "relationship_count": total_relationships,
                    "status": "completed",
                },
                priority=EventPriority.NORMAL,
            )

        finally:
            db.close()

    except Exception as e:
        logger.error(
            f"Error during automatic graph extraction for resource {resource_id}: {str(e)}",
            exc_info=True,
        )

        # Emit extraction failed event
        event_bus.emit(
            "graph.extraction_failed",
            {"resource_id": resource_id, "error": str(e)},
            priority=EventPriority.HIGH,
        )


def register_handlers():
    """
    Register all event handlers for the graph module.

    This function should be called during application startup.
    """
    # Subscribe to resource.chunked for automatic graph extraction
    event_bus.subscribe("resource.chunked", handle_resource_chunked)

    logger.info("Graph module event handlers registered")
