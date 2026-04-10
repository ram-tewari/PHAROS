"""
Resources Module - Event Handlers

This module defines event handlers for the Resources module to enable
event-driven communication with other modules.

Event handlers subscribe to events from other modules and perform
appropriate actions without direct service dependencies.
"""

import logging
from typing import Dict, Any

from ...shared.event_bus import event_bus, Event, EventPriority
from ...config.settings import get_settings

logger = logging.getLogger(__name__)


def handle_collection_updated(payload: Dict[str, Any]) -> None:
    """
    Handle collection.updated event.

    This is a placeholder handler for future functionality where resources
    might need to respond to collection updates.

    Args:
        payload: Event payload containing collection update information
    """
    collection_id = payload.get("collection_id")
    logger.debug(
        f"Resources module received collection.updated event for collection {collection_id}"
    )
    # Placeholder: Future implementation might update resource metadata or cache


def handle_resource_created(event: Event) -> None:
    """
    Handle resource.created event to trigger automatic chunking.

    This handler is called when a new resource is created. If CHUNK_ON_RESOURCE_CREATE
    is enabled in settings, it triggers chunking for the resource.

    Args:
        event: Event object containing resource creation data
    """
    settings = get_settings()

    # Check if automatic chunking is enabled
    if not settings.CHUNK_ON_RESOURCE_CREATE:
        logger.debug("Automatic chunking disabled, skipping resource.created handler")
        return

    payload = event.data
    resource_id = payload.get("resource_id")

    if not resource_id:
        logger.warning("resource.created event missing resource_id, skipping chunking")
        return

    logger.info(f"Triggering automatic chunking for resource {resource_id}")

    try:
        # Import here to avoid circular dependencies
        from ...shared.database import SessionLocal
        from .service import ChunkingService
        from ...database.models import Resource

        # Create database session
        db = SessionLocal()

        try:
            # Fetch the resource to get its content
            resource = db.query(Resource).filter(Resource.id == resource_id).first()

            if not resource:
                logger.warning(f"Resource {resource_id} not found, skipping chunking")
                return

            # Get content from resource description (or other text field)
            content = resource.description or ""

            if not content or len(content.strip()) < 100:
                logger.info(
                    f"Resource {resource_id} has insufficient content for chunking (length: {len(content)})"
                )
                return

            # Initialize chunking service
            chunking_service = ChunkingService(
                db=db,
                strategy=settings.CHUNKING_STRATEGY,
                chunk_size=settings.CHUNK_SIZE,
                overlap=settings.CHUNK_OVERLAP,
            )

            # Perform chunking with content
            chunks = chunking_service.chunk_resource(
                resource_id=str(resource_id), content=content
            )

            logger.info(
                f"Successfully chunked resource {resource_id} into {len(chunks)} chunks"
            )

            # Emit resource.chunked event
            event_bus.emit(
                "resource.chunked",
                {
                    "resource_id": resource_id,
                    "chunk_count": len(chunks),
                    "strategy": settings.CHUNKING_STRATEGY,
                },
                priority=EventPriority.NORMAL,
            )

        finally:
            db.close()

    except Exception as e:
        logger.error(
            f"Error during automatic chunking for resource {resource_id}: {str(e)}",
            exc_info=True,
        )

        # Emit chunking failed event
        event_bus.emit(
            "resource.chunking_failed",
            {"resource_id": resource_id, "error": str(e)},
            priority=EventPriority.HIGH,
        )


def register_handlers() -> None:
    """
    Register all event handlers for the Resources module.

    This function should be called during application startup to subscribe
    to events from other modules.
    """
    # Subscribe to collection events (placeholder for future functionality)
    event_bus.subscribe("collection.updated", handle_collection_updated)

    # Subscribe to resource.created for automatic chunking
    event_bus.subscribe("resource.created", handle_resource_created)

    logger.info("Resources module event handlers registered")
