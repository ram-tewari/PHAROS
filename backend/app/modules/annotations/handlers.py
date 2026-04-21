"""
Annotations Event Handlers

Handles events from other modules and emits annotation-related events.

Events Subscribed:
- resource.deleted: Clean up annotations when a resource is deleted

Events Emitted:
- annotation.created: When a new annotation is created
- annotation.updated: When an annotation is updated
- annotation.deleted: When an annotation is deleted
"""

import logging
from typing import Dict, Any
from uuid import UUID

from app.shared.event_bus import event_bus, EventPriority
from app.shared.database import get_sync_db

logger = logging.getLogger(__name__)


def handle_resource_deleted(event):
    """
    Handle resource.deleted event to clean up annotations.

    When a resource is deleted, we:
    1. Find all annotations for that resource
    2. Delete them from the database
    3. Emit annotation.deleted events for each

    Args:
        event: Event object containing resource deletion details
            - resource_id: UUID of the deleted resource
    """
    try:
        payload = event.data
        resource_id = UUID(payload.get("resource_id"))

        # Get database session
        db = next(get_sync_db())

        try:
            from .model import Annotation
            from sqlalchemy import select

            # Find all annotations for this resource
            stmt = select(Annotation).where(Annotation.resource_id == resource_id)
            result = db.execute(stmt)
            annotations = result.scalars().all()

            # Delete each annotation and emit events
            for annotation in annotations:
                annotation_id = str(annotation.id)
                user_id = annotation.user_id

                # Delete annotation
                db.delete(annotation)

                # Emit annotation.deleted event
                event_bus.emit(
                    "annotation.deleted",
                    {
                        "annotation_id": annotation_id,
                        "resource_id": str(resource_id),
                        "user_id": user_id,
                        "reason": "resource_deleted",
                    },
                    priority=EventPriority.NORMAL,
                )

            db.commit()

            logger.info(
                f"Deleted {len(annotations)} annotations for resource {resource_id}"
            )

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error handling resource.deleted event: {str(e)}", exc_info=True)


def emit_annotation_created(
    annotation_id: str, resource_id: str, user_id: str, note: str | None = None
):
    """
    Emit annotation.created event.

    This should be called by the annotation service after creating an annotation.

    Args:
        annotation_id: UUID of the created annotation
        resource_id: UUID of the resource
        user_id: User ID who created the annotation
        note: Optional annotation note text
    """
    try:
        event_bus.emit(
            "annotation.created",
            {
                "annotation_id": annotation_id,
                "resource_id": resource_id,
                "user_id": user_id,
                "has_note": note is not None and len(note) > 0,
            },
            priority=EventPriority.NORMAL,
        )
        logger.debug(f"Emitted annotation.created event for {annotation_id}")
    except Exception as e:
        logger.error(
            f"Error emitting annotation.created event: {str(e)}", exc_info=True
        )


def emit_annotation_updated(
    annotation_id: str, resource_id: str, user_id: str, changes: Dict[str, Any]
):
    """
    Emit annotation.updated event.

    This should be called by the annotation service after updating an annotation.

    Args:
        annotation_id: UUID of the updated annotation
        resource_id: UUID of the resource
        user_id: User ID who updated the annotation
        changes: Dictionary of changed fields
    """
    try:
        event_bus.emit(
            "annotation.updated",
            {
                "annotation_id": annotation_id,
                "resource_id": resource_id,
                "user_id": user_id,
                "changes": list(changes.keys()),
            },
            priority=EventPriority.NORMAL,
        )
        logger.debug(f"Emitted annotation.updated event for {annotation_id}")
    except Exception as e:
        logger.error(
            f"Error emitting annotation.updated event: {str(e)}", exc_info=True
        )


def emit_annotation_deleted(annotation_id: str, resource_id: str, user_id: str):
    """
    Emit annotation.deleted event.

    This should be called by the annotation service after deleting an annotation.

    Args:
        annotation_id: UUID of the deleted annotation
        resource_id: UUID of the resource
        user_id: User ID who deleted the annotation
    """
    try:
        event_bus.emit(
            "annotation.deleted",
            {
                "annotation_id": annotation_id,
                "resource_id": resource_id,
                "user_id": user_id,
                "reason": "user_deleted",
            },
            priority=EventPriority.NORMAL,
        )
        logger.debug(f"Emitted annotation.deleted event for {annotation_id}")
    except Exception as e:
        logger.error(
            f"Error emitting annotation.deleted event: {str(e)}", exc_info=True
        )


def register_handlers():
    """
    Register all event handlers for the annotations module.

    This function should be called during application startup to
    subscribe to events from other modules.
    """
    # Subscribe to resource events
    event_bus.on("resource.deleted", handle_resource_deleted, async_handler=False)

    logger.info("Annotations module event handlers registered")
