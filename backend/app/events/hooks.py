"""
Event hooks for automatic data consistency.

This module implements event hooks that automatically maintain data consistency
by queuing Celery tasks in response to system events. Hooks ensure that derived
data (embeddings, quality scores, search indexes, etc.) stays synchronized with
source data changes.

Hook Architecture:
- Each hook is a simple function that receives an Event object
- Hooks extract relevant data from the event payload
- Hooks queue appropriate Celery tasks with priority and delay
- Hooks use debounce delays to prevent duplicate work

Related files:
- app/events/event_system.py: Event emitter and Event class
- app/events/event_types.py: System event type definitions
- app/tasks/celery_tasks.py: Celery task implementations
- app/services/: Service layer that emits events

Design Patterns:
- Event-driven architecture: Decoupled components communicate via events
- Automatic consistency: Derived data updates happen automatically
- Priority queuing: Critical tasks (search, cache) execute first
- Debounce delays: Prevent duplicate work from rapid updates
- Batch delays: Allow grouping similar operations
"""

import logging

from ..shared.event_bus import event_bus, EventPriority
from .event_types import SystemEvent
from dataclasses import dataclass
from typing import Dict, Any
from datetime import datetime, timezone


@dataclass
class Event:
    """Compatibility wrapper for old Event class."""

    name: str
    data: Dict[str, Any]
    timestamp: datetime | None = None
    priority: EventPriority = EventPriority.NORMAL
    correlation_id: str | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
        if self.correlation_id is None:
            import uuid

            self.correlation_id = str(uuid.uuid4())


logger = logging.getLogger(__name__)


# ============================================================================
# Hook 5.1: Embedding Regeneration
# ============================================================================


def on_content_changed_regenerate_embedding(event: Event) -> None:
    """
    Hook: Regenerate embedding when resource content changes.

    Triggered by: resource.content_changed event
    Priority: HIGH (7)
    Delay: 5 seconds (debounce rapid updates)

    This hook ensures that embedding vectors stay synchronized with resource
    content. The 5-second delay prevents duplicate work if content is updated
    multiple times in quick succession.

    Args:
        event: Event object containing resource_id in data
    """
    resource_id = event.data.get("resource_id")

    if not resource_id:
        logger.warning("content_changed event missing resource_id")
        return

    try:
        # Import here to avoid circular dependencies
        from ..tasks.celery_tasks import regenerate_embedding_task

        # Queue embedding regeneration with HIGH priority and 5s debounce
        regenerate_embedding_task.apply_async(
            args=[resource_id],
            priority=7,  # HIGH priority
            countdown=5,  # 5-second debounce delay
        )

        logger.info(
            f"Queued embedding regeneration for resource {resource_id} "
            f"(priority=7, countdown=5s)"
        )

    except Exception as e:
        logger.error(
            f"Error queuing embedding regeneration for {resource_id}: {e}",
            exc_info=True,
        )


# ============================================================================
# Hook 5.2: Quality Recomputation
# ============================================================================


def on_metadata_changed_recompute_quality(event: Event) -> None:
    """
    Hook: Recompute quality when resource metadata changes.

    Triggered by: resource.metadata_changed event
    Priority: MEDIUM (5)
    Delay: 10 seconds (debounce rapid updates)

    This hook ensures that quality scores stay synchronized with resource
    metadata. The 10-second delay allows multiple metadata updates to be
    batched into a single quality recomputation.

    Args:
        event: Event object containing resource_id in data
    """
    resource_id = event.data.get("resource_id")

    if not resource_id:
        logger.warning("metadata_changed event missing resource_id")
        return

    try:
        from ..tasks.celery_tasks import recompute_quality_task

        # Queue quality recomputation with MEDIUM priority and 10s debounce
        recompute_quality_task.apply_async(
            args=[resource_id],
            priority=5,  # MEDIUM priority
            countdown=10,  # 10-second debounce delay
        )

        logger.info(
            f"Queued quality recomputation for resource {resource_id} "
            f"(priority=5, countdown=10s)"
        )

    except Exception as e:
        logger.error(
            f"Error queuing quality recomputation for {resource_id}: {e}", exc_info=True
        )


# ============================================================================
# Hook 5.3: Search Index Sync
# ============================================================================


def on_resource_updated_sync_search_index(event: Event) -> None:
    """
    Hook: Update search index when resource is updated.

    Triggered by: resource.updated event
    Priority: URGENT (9)
    Delay: 1 second (minimal delay for near-immediate update)

    This hook ensures that the FTS5 search index stays synchronized with
    resource updates. The URGENT priority and 1-second delay ensure that
    updated resources become searchable almost immediately.

    Args:
        event: Event object containing resource_id in data
    """
    resource_id = event.data.get("resource_id")

    if not resource_id:
        logger.warning("resource_updated event missing resource_id")
        return

    try:
        from ..tasks.celery_tasks import update_search_index_task

        # Queue search index update with URGENT priority and 1s delay
        update_search_index_task.apply_async(
            args=[resource_id],
            priority=9,  # URGENT priority
            countdown=1,  # 1-second minimal delay
        )

        logger.info(
            f"Queued URGENT search index update for resource {resource_id} "
            f"(priority=9, countdown=1s)"
        )

    except Exception as e:
        logger.error(
            f"Error queuing search index update for {resource_id}: {e}", exc_info=True
        )


# ============================================================================
# Hook 5.4: Graph Edge Update
# ============================================================================


def on_citation_extracted_update_graph(event: Event) -> None:
    """
    Hook: Update knowledge graph when citations are extracted.

    Triggered by: citations.extracted event
    Priority: MEDIUM (5)
    Delay: 30 seconds (batch delay for grouping)

    This hook ensures that the knowledge graph stays synchronized with
    citation relationships. The 30-second delay allows multiple citation
    extractions to be batched together for efficiency.

    Args:
        event: Event object containing resource_id and citations in data
    """
    resource_id = event.data.get("resource_id")
    citations = event.data.get("citations", [])

    if not resource_id:
        logger.warning("citations_extracted event missing resource_id")
        return

    try:
        from ..tasks.celery_tasks import update_graph_edges_task

        # Queue graph edge update with MEDIUM priority and 30s batch delay
        update_graph_edges_task.apply_async(
            args=[resource_id, citations],
            priority=5,  # MEDIUM priority
            countdown=30,  # 30-second batch delay
        )

        logger.info(
            f"Queued graph edge update for resource {resource_id} "
            f"with {len(citations)} citations (priority=5, countdown=30s)"
        )

    except Exception as e:
        logger.error(
            f"Error queuing graph edge update for {resource_id}: {e}", exc_info=True
        )


# ============================================================================
# Hook 5.5: Cache Invalidation
# ============================================================================


def on_resource_updated_invalidate_caches(event: Event) -> None:
    """
    Hook: Invalidate caches when resource is updated.

    Triggered by: resource.updated event
    Priority: URGENT (9)
    Delay: 0 seconds (immediate)

    This hook ensures that cached data doesn't become stale when resources
    are updated. It invalidates multiple cache key patterns to ensure all
    derived data caches are cleared.

    Cache keys invalidated:
    - embedding:{resource_id} - Embedding vector cache
    - quality:{resource_id} - Quality score cache
    - resource:{resource_id} - Full resource data cache
    - search_query:* - All search query result caches

    Args:
        event: Event object containing resource_id in data
    """
    resource_id = event.data.get("resource_id")

    if not resource_id:
        logger.warning("resource_updated event missing resource_id")
        return

    try:
        from ..tasks.celery_tasks import invalidate_cache_task

        # Build list of cache keys to invalidate
        cache_keys = [
            f"embedding:{resource_id}",
            f"quality:{resource_id}",
            f"resource:{resource_id}",
            "search_query:*",  # Invalidate all search query caches
        ]

        # Queue cache invalidation with URGENT priority and no delay
        invalidate_cache_task.apply_async(
            args=[cache_keys],
            priority=9,  # URGENT priority
            countdown=0,  # Immediate execution
        )

        logger.info(
            f"Queued URGENT cache invalidation for resource {resource_id} "
            f"({len(cache_keys)} keys/patterns, priority=9, immediate)"
        )

    except Exception as e:
        logger.error(
            f"Error queuing cache invalidation for {resource_id}: {e}", exc_info=True
        )


# ============================================================================
# Hook 5.6: Author Normalization
# ============================================================================


def on_author_extracted_normalize_names(event: Event) -> None:
    """
    Hook: Normalize author names when authors are extracted.

    Triggered by: authors.extracted event
    Priority: LOW (3)
    Delay: 60 seconds (batch delay)

    This hook normalizes author names for consistency across the system.
    The 60-second delay allows multiple author extractions to be batched
    together for efficient processing.

    Args:
        event: Event object containing resource_id and authors in data
    """
    resource_id = event.data.get("resource_id")
    authors = event.data.get("authors", [])

    if not resource_id:
        logger.warning("authors_extracted event missing resource_id")
        return

    try:
        from ..tasks.celery_tasks import normalize_author_names_task

        # Queue author normalization with LOW priority and 60s batch delay
        normalize_author_names_task.apply_async(
            args=[resource_id, authors],
            priority=3,  # LOW priority
            countdown=60,  # 60-second batch delay
        )

        logger.info(
            f"Queued author normalization for resource {resource_id} "
            f"({len(authors)} authors, priority=3, countdown=60s)"
        )

    except Exception as e:
        logger.error(
            f"Error queuing author normalization for {resource_id}: {e}", exc_info=True
        )


# ============================================================================
# Hook 5.7: Collection Embedding Update on Resource Deletion
# ============================================================================


def on_resource_deleted_update_collections(event: Event) -> None:
    """
    Hook: Update collection embeddings when a resource is deleted.

    Triggered by: resource.deleted event
    Priority: MEDIUM (5)
    Delay: 5 seconds (debounce)

    This hook ensures that collection embeddings are recomputed when a member
    resource is deleted. The 5-second delay allows multiple deletions to be
    batched if needed.

    Args:
        event: Event object containing resource_id in data
    """
    resource_id = event.data.get("resource_id")

    if not resource_id:
        logger.warning("resource_deleted event missing resource_id")
        return

    try:
        from ..tasks.celery_tasks import update_collection_embeddings_task

        # Queue collection embedding update with MEDIUM priority and 5s delay
        update_collection_embeddings_task.apply_async(
            args=[resource_id],
            priority=5,  # MEDIUM priority
            countdown=5,  # 5-second debounce delay
        )

        logger.info(
            f"Queued collection embedding updates for deleted resource {resource_id} "
            f"(priority=5, countdown=5s)"
        )

    except Exception as e:
        logger.error(
            f"Error queuing collection embedding update for {resource_id}: {e}",
            exc_info=True,
        )


# ============================================================================
# Hook Registration
# ============================================================================


def register_all_hooks() -> None:
    """
    Register all event hooks with the event emitter.

    This function should be called during application startup (FastAPI startup
    event) to register all hooks. Once registered, hooks will automatically
    execute when their corresponding events are emitted.

    Registered hooks:
    1. Embedding regeneration (content changes)
    2. Quality recomputation (metadata changes)
    3. Search index sync (resource updates)
    4. Graph edge update (citation extraction)
    5. Cache invalidation (resource updates)
    6. Author normalization (author extraction)
    7. Collection embedding update (resource deletion)
    """
    hooks = [
        (SystemEvent.RESOURCE_CONTENT_CHANGED, on_content_changed_regenerate_embedding),
        (SystemEvent.RESOURCE_METADATA_CHANGED, on_metadata_changed_recompute_quality),
        (SystemEvent.RESOURCE_UPDATED, on_resource_updated_sync_search_index),
        (SystemEvent.CITATIONS_EXTRACTED, on_citation_extracted_update_graph),
        (SystemEvent.RESOURCE_UPDATED, on_resource_updated_invalidate_caches),
        (SystemEvent.AUTHORS_EXTRACTED, on_author_extracted_normalize_names),
        (SystemEvent.RESOURCE_DELETED, on_resource_deleted_update_collections),
    ]

    # Create wrapper to convert dict payload to Event object for backward compatibility
    def create_handler_wrapper(handler, event_name):
        def wrapper(payload: Dict[str, Any]) -> None:
            event = Event(name=event_name.value, data=payload)
            handler(event)

        return wrapper

    for event_name, handler in hooks:
        wrapped_handler = create_handler_wrapper(handler, event_name)
        event_bus.subscribe(event_name.value, wrapped_handler)

    logger.info(f"Registered {len(hooks)} event hooks for automatic data consistency")
