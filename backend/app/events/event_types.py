"""System event type definitions.

Centralized registry of all system events using the naming convention:
{entity}.{action}
"""

from enum import Enum


class SystemEvent(str, Enum):
    """All system event types with consistent naming convention."""

    # Resource lifecycle events
    RESOURCE_CREATED = "resource.created"
    RESOURCE_UPDATED = "resource.updated"
    RESOURCE_DELETED = "resource.deleted"
    RESOURCE_CONTENT_CHANGED = "resource.content_changed"
    RESOURCE_METADATA_CHANGED = "resource.metadata_changed"

    # Ingestion events
    INGESTION_STARTED = "ingestion.started"
    INGESTION_COMPLETED = "ingestion.completed"
    INGESTION_FAILED = "ingestion.failed"

    # Embedding events
    EMBEDDING_GENERATED = "embedding.generated"
    EMBEDDING_REGENERATION_STARTED = "embedding.regeneration_started"
    EMBEDDING_REGENERATION_COMPLETED = "embedding.regeneration_completed"
    EMBEDDING_REGENERATION_FAILED = "embedding.regeneration_failed"

    # Quality events
    QUALITY_COMPUTED = "quality.computed"
    QUALITY_RECOMPUTATION_STARTED = "quality.recomputation_started"
    QUALITY_RECOMPUTATION_COMPLETED = "quality.recomputation_completed"
    QUALITY_RECOMPUTATION_FAILED = "quality.recomputation_failed"
    QUALITY_DEGRADATION_DETECTED = "quality.degradation_detected"
    QUALITY_OUTLIER_DETECTED = "quality.outlier_detected"

    # Search events
    SEARCH_EXECUTED = "search.executed"
    SEARCH_INDEX_UPDATED = "search.index_updated"
    SEARCH_INDEX_UPDATE_STARTED = "search.index_update_started"
    SEARCH_INDEX_UPDATE_COMPLETED = "search.index_update_completed"
    SEARCH_INDEX_UPDATE_FAILED = "search.index_update_failed"

    # Graph events
    GRAPH_EDGE_ADDED = "graph.edge_added"
    GRAPH_EDGE_REMOVED = "graph.edge_removed"
    GRAPH_CACHE_INVALIDATED = "graph.cache_invalidated"
    CITATIONS_EXTRACTED = "citations.extracted"

    # Cache events
    CACHE_HIT = "cache.hit"
    CACHE_MISS = "cache.miss"
    CACHE_INVALIDATED = "cache.invalidated"
    CACHE_CLEANUP_STARTED = "cache.cleanup_started"
    CACHE_CLEANUP_COMPLETED = "cache.cleanup_completed"

    # User events
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"

    # Author events
    AUTHORS_EXTRACTED = "authors.extracted"
    AUTHOR_NAMES_NORMALIZED = "author.names_normalized"

    # Background task events
    BACKGROUND_TASK_STARTED = "background_task.started"
    BACKGROUND_TASK_COMPLETED = "background_task.completed"
    BACKGROUND_TASK_FAILED = "background_task.failed"
    BACKGROUND_TASK_RETRY = "background_task.retry"

    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_HEALTH_CHECK = "system.health_check"
    WORKER_STARTED = "worker.started"
    WORKER_STOPPED = "worker.stopped"
    WORKER_HEALTH_CHECK = "worker.health_check"
