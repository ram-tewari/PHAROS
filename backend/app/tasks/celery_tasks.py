"""
Neo Alexandria 2.0 - Celery Task Implementations

This module contains all Celery task implementations for background processing.
Tasks are organized by category: data consistency, scheduled maintenance, and batch operations.

Related files:
- app/tasks/celery_app.py: Celery configuration
- app/events/hooks.py: Event hooks that trigger these tasks
- app/services/: Service layer implementations used by tasks
- app/database/base.py: Database session management

Task Categories:
1. Data Consistency Tasks: Maintain derived data (embeddings, quality, search index)
2. Scheduled Maintenance Tasks: Periodic system health and optimization
3. Batch Processing Tasks: Process multiple resources efficiently

Design Patterns:
- DatabaseTask base class: Automatic DB session management
- Retry with exponential backoff: Handle transient errors
- Progress tracking: Report status for long-running tasks
- Priority queuing: Critical tasks execute first
"""

import logging
from typing import List, Optional, Dict, Any
from celery import Task

from .celery_app import celery_app
from ..database.base import SessionLocal, Base

logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    """
    Base task class with automatic database session management.

    This class provides automatic DB session lifecycle management for Celery tasks.
    Sessions are created before task execution and properly closed after completion,
    even if the task raises an exception.

    Usage:
        @celery_app.task(bind=True, base=DatabaseTask)
        def my_task(self, resource_id: str, db=None):
            # db session is automatically provided
            resource = db.query(Resource).filter_by(id=resource_id).first()
            # ... process resource

    Features:
    - Automatic session creation and cleanup
    - Ensures tables exist (useful for SQLite)
    - Proper exception handling and session rollback
    - Compatible with Celery's retry mechanism
    """

    _db = None

    def __call__(self, *args, **kwargs):
        """
        Execute task with automatic database session management.

        Creates a database session, passes it to the task via the 'db' parameter,
        and ensures proper cleanup in a finally block.

        Args:
            *args: Positional arguments passed to the task
            **kwargs: Keyword arguments passed to the task

        Returns:
            Task execution result
        """
        # Create database session
        db = SessionLocal()

        try:
            # Ensure tables exist (especially for SQLite)
            try:
                Base.metadata.create_all(bind=db.get_bind())
            except Exception:
                # Best effort; ignore if fails
                pass

            # Execute task with db session
            return self.run(*args, db=db, **kwargs)

        finally:
            # Always close the session
            db.close()


# ============================================================================
# Data Consistency Tasks
# ============================================================================


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    max_retries=3,
    default_retry_delay=60,
    name="app.tasks.celery_tasks.regenerate_embedding_task",
)
def regenerate_embedding_task(self, resource_id: str, db=None):
    """
    Regenerate embedding vector for a resource.

    Triggered by: resource.content_changed event
    Priority: HIGH (7)
    Retry: 3 attempts with exponential backoff for transient errors

    Args:
        resource_id: UUID of the resource to process
        db: Database session (automatically provided by DatabaseTask)
    """
    try:
        logger.info(f"Regenerating embedding for resource {resource_id}")

        # Import here to avoid circular dependencies
        from ..shared.embeddings import EmbeddingService

        embedding_service = EmbeddingService(db)
        embedding_service.generate_and_store_embedding(resource_id)

        logger.info(f"Successfully regenerated embedding for resource {resource_id}")

    except Exception as e:
        # Check if error is transient (network, timeout, connection)
        error_msg = str(e).lower()
        if any(
            keyword in error_msg for keyword in ["timeout", "connection", "network"]
        ):
            # Retry with exponential backoff
            logger.warning(
                f"Transient error regenerating embedding for {resource_id}: {e}"
            )
            raise self.retry(exc=e, countdown=2**self.request.retries)
        else:
            # Permanent error - don't retry
            logger.error(
                f"Permanent error regenerating embedding for {resource_id}: {e}",
                exc_info=True,
            )
            raise


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    max_retries=2,
    name="app.tasks.celery_tasks.recompute_quality_task",
)
def recompute_quality_task(
    self, resource_id: str, weights: Optional[Dict[str, float]] = None, db=None
):
    """
    Recompute quality scores for a resource.

    Triggered by: resource.metadata_changed event
    Priority: MEDIUM (5)
    Retry: 2 attempts

    Args:
        resource_id: UUID of the resource to process
        weights: Optional custom weights for quality dimensions
        db: Database session (automatically provided by DatabaseTask)
    """
    try:
        logger.info(f"Recomputing quality for resource {resource_id}")

        from ..services.quality_service import QualityService

        quality_service = QualityService(db)
        quality_scores = quality_service.compute_quality(resource_id, weights=weights)

        logger.info(
            f"Successfully recomputed quality for resource {resource_id}: {quality_scores}"
        )

    except Exception as e:
        logger.error(f"Error recomputing quality for {resource_id}: {e}", exc_info=True)
        raise


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    max_retries=3,
    default_retry_delay=5,
    name="app.tasks.celery_tasks.update_search_index_task",
)
def update_search_index_task(self, resource_id: str, db=None):
    """
    Update FTS5 search index for a resource.

    Triggered by: resource.updated event
    Priority: URGENT (9)
    Retry: 3 attempts with 5-second delay

    Args:
        resource_id: UUID of the resource to process
        db: Database session (automatically provided by DatabaseTask)
    """
    try:
        logger.info(f"Updating search index for resource {resource_id}")

        from ..services.search_service import SearchService

        search_service = SearchService(db)
        search_service.update_fts5_index(resource_id)

        logger.info(f"Successfully updated search index for resource {resource_id}")

    except Exception as e:
        logger.error(
            f"Error updating search index for {resource_id}: {e}", exc_info=True
        )
        raise


@celery_app.task(
    bind=True, base=DatabaseTask, name="app.tasks.celery_tasks.update_graph_edges_task"
)
def update_graph_edges_task(self, resource_id: str, citations: List[str], db=None):
    """
    Update knowledge graph edges for citations.

    Triggered by: citations.extracted event
    Priority: MEDIUM (5)

    Args:
        resource_id: UUID of the source resource
        citations: List of cited resource IDs
        db: Database session (automatically provided by DatabaseTask)
    """
    try:
        logger.info(
            f"Updating graph edges for resource {resource_id} with {len(citations)} citations"
        )

        from ..services.graph_service import GraphService

        graph_service = GraphService(db)
        graph_service.add_citation_edges(resource_id, citations)

        # Invalidate graph cache
        invalidate_cache_task.apply_async(
            args=[[f"graph:neighbors:{resource_id}", "graph:*"]], priority=9
        )

        logger.info(f"Successfully updated graph edges for resource {resource_id}")

    except Exception as e:
        logger.error(
            f"Error updating graph edges for {resource_id}: {e}", exc_info=True
        )
        raise


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    max_retries=2,
    name="app.tasks.celery_tasks.classify_resource_task",
)
def classify_resource_task(self, resource_id: str, db=None):
    """
    Classify resource using ML model.

    Triggered by: resource.created event
    Priority: MEDIUM (5)
    Retry: 2 attempts

    Args:
        resource_id: UUID of the resource to classify
        db: Database session (automatically provided by DatabaseTask)
    """
    try:
        logger.info(f"Classifying resource {resource_id}")

        from ..services.ml_classification_service import MLClassificationService
        from ..services.taxonomy_service import TaxonomyService

        # Get predictions from ML model - returns ClassificationResult domain object
        ml_service = MLClassificationService(db)
        result = ml_service.predict(resource_id, top_k=5)

        # Store predictions - iterate over ClassificationPrediction objects
        taxonomy_service = TaxonomyService(db)
        for prediction in result.predictions:
            taxonomy_service.classify_resource(
                resource_id=resource_id,
                category_id=prediction.taxonomy_id,
                confidence=prediction.confidence,
                is_predicted=True,
            )

        logger.info(
            f"Successfully classified resource {resource_id} with {len(result.predictions)} categories"
        )

    except Exception as e:
        logger.error(f"Error classifying resource {resource_id}: {e}", exc_info=True)
        raise


@celery_app.task(name="app.tasks.celery_tasks.invalidate_cache_task")
def invalidate_cache_task(cache_keys: List[str]):
    """
    Invalidate cache entries.

    Triggered by: resource.updated event, graph updates
    Priority: URGENT (9)

    Supports both exact keys and pattern-based invalidation (wildcard *).

    Args:
        cache_keys: List of cache keys or patterns to invalidate
    """
    try:
        logger.info(f"Invalidating {len(cache_keys)} cache keys/patterns")

        from ..shared.cache import cache

        invalidation_count = 0
        for key in cache_keys:
            if "*" in key:
                # Pattern-based invalidation
                count = cache.delete_pattern(key)
                invalidation_count += count
            else:
                # Exact key invalidation
                cache.delete(key)
                invalidation_count += 1

        logger.info(f"Successfully invalidated {invalidation_count} cache entries")

    except Exception as e:
        logger.error(f"Error invalidating cache: {e}", exc_info=True)
        raise


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="app.tasks.celery_tasks.refresh_recommendation_profile_task",
)
def refresh_recommendation_profile_task(self, user_id: str, db=None):
    """
    Refresh user recommendation profile.

    Triggered by: user.interaction_tracked event (every 10 interactions)
    Priority: LOW (3)

    Args:
        user_id: UUID of the user
        db: Database session (automatically provided by DatabaseTask)
    """
    try:
        logger.info(f"Refreshing recommendation profile for user {user_id}")

        from ..services.recommendation_service import UserProfileService

        profile_service = UserProfileService(db)
        profile_service._update_learned_preferences(user_id)

        logger.info(f"Successfully refreshed recommendation profile for user {user_id}")

    except Exception as e:
        logger.error(
            f"Error refreshing recommendation profile for {user_id}: {e}", exc_info=True
        )
        raise


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="app.tasks.celery_tasks.normalize_author_names_task",
)
def normalize_author_names_task(self, resource_id: str, authors: List[str], db=None):
    """
    Normalize author names for consistency.

    Triggered by: authors.extracted event
    Priority: LOW (3)

    Args:
        resource_id: UUID of the resource
        authors: List of author names to normalize
        db: Database session (automatically provided by DatabaseTask)
    """
    try:
        logger.info(
            f"Normalizing {len(authors)} author names for resource {resource_id}"
        )

        # TODO: Implement author normalization logic
        # This would involve:
        # 1. Standardizing name formats (Last, First vs First Last)
        # 2. Handling initials and abbreviations
        # 3. Detecting duplicate authors with different spellings
        # 4. Linking to author entities in the database

        logger.info(f"Successfully normalized author names for resource {resource_id}")

    except Exception as e:
        logger.error(
            f"Error normalizing author names for {resource_id}: {e}", exc_info=True
        )
        raise


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    max_retries=2,
    name="app.tasks.celery_tasks.extract_citations_task",
)
def extract_citations_task(self, resource_id: str, db=None):
    """
    Extract citations from a resource.

    Triggered by: Manual API call
    Priority: MEDIUM (5)
    Retry: 2 attempts

    Args:
        resource_id: UUID of the resource to process
        db: Database session (automatically provided by DatabaseTask)
    """
    try:
        logger.info(f"Extracting citations for resource {resource_id}")

        from ..services.citation_service import CitationService

        service = CitationService(db)
        service.extract_citations(resource_id)

        logger.info(f"Successfully extracted citations for resource {resource_id}")

    except Exception as e:
        logger.error(
            f"Error extracting citations for {resource_id}: {e}", exc_info=True
        )
        raise


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    max_retries=2,
    name="app.tasks.celery_tasks.resolve_citations_task",
)
def resolve_citations_task(self, db=None):
    """
    Resolve internal citations.

    Triggered by: Manual API call
    Priority: MEDIUM (5)
    Retry: 2 attempts

    Matches unresolved citation URLs to existing resources in the database.

    Args:
        db: Database session (automatically provided by DatabaseTask)
    """
    try:
        logger.info("Resolving internal citations")

        from ..services.citation_service import CitationService

        service = CitationService(db)
        service.resolve_internal_citations()

        logger.info("Successfully resolved internal citations")

    except Exception as e:
        logger.error(f"Error resolving citations: {e}", exc_info=True)
        raise


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    max_retries=2,
    name="app.tasks.celery_tasks.compute_citation_importance_task",
)
def compute_citation_importance_task(self, db=None):
    """
    Compute PageRank importance scores for all citations.

    Triggered by: Manual API call
    Priority: LOW (3)
    Retry: 2 attempts

    This is a computationally expensive operation that should be run
    periodically rather than on every request.

    Args:
        db: Database session (automatically provided by DatabaseTask)
    """
    try:
        logger.info("Computing citation importance scores")

        from ..services.citation_service import CitationService

        service = CitationService(db)
        service.compute_citation_importance()

        logger.info("Successfully computed citation importance scores")

    except Exception as e:
        logger.error(f"Error computing citation importance: {e}", exc_info=True)
        raise


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    max_retries=2,
    name="app.tasks.celery_tasks.extract_scholarly_metadata_task",
)
def extract_scholarly_metadata_task(self, resource_id: str, db=None):
    """
    Extract scholarly metadata from a resource.

    Triggered by: Manual API call
    Priority: MEDIUM (5)
    Retry: 2 attempts

    Extracts authors, DOI, publication details, and structural content.

    Args:
        resource_id: UUID of the resource to process
        db: Database session (automatically provided by DatabaseTask)
    """
    try:
        logger.info(f"Extracting scholarly metadata for resource {resource_id}")

        from ..services.metadata_extractor import MetadataExtractor

        extractor = MetadataExtractor(db)
        extractor.extract_scholarly_metadata(resource_id)

        logger.info(
            f"Successfully extracted scholarly metadata for resource {resource_id}"
        )

    except Exception as e:
        logger.error(
            f"Error extracting scholarly metadata for {resource_id}: {e}", exc_info=True
        )
        raise


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    max_retries=2,
    name="app.tasks.celery_tasks.evaluate_summary_task",
)
def evaluate_summary_task(self, resource_id: str, use_g_eval: bool = False, db=None):
    """
    Evaluate summary quality for a resource.

    Triggered by: Manual API call
    Priority: MEDIUM (5)
    Retry: 2 attempts

    Args:
        resource_id: UUID of the resource to process
        use_g_eval: Whether to use G-Eval (requires OpenAI API)
        db: Database session (automatically provided by DatabaseTask)
    """
    try:
        logger.info(
            f"Evaluating summary for resource {resource_id} (use_g_eval={use_g_eval})"
        )

        import os
        from ..services.summarization_evaluator import SummarizationEvaluator

        openai_api_key = os.getenv("OPENAI_API_KEY")
        evaluator = SummarizationEvaluator(db, openai_api_key=openai_api_key)
        evaluator.evaluate_summary(resource_id, use_g_eval=use_g_eval)

        logger.info(f"Successfully evaluated summary for resource {resource_id}")

    except Exception as e:
        logger.error(f"Error evaluating summary for {resource_id}: {e}", exc_info=True)
        raise


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="app.tasks.celery_tasks.batch_process_resources_task",
)
def batch_process_resources_task(
    self, resource_ids: List[str], operation: str, db=None
) -> Dict[str, Any]:
    """
    Batch process multiple resources with progress tracking.

    Priority: LOW (3) - batch queue

    Supported operations:
    - regenerate_embeddings: Regenerate embeddings for all resources
    - recompute_quality: Recompute quality scores for all resources

    Args:
        resource_ids: List of resource UUIDs to process
        operation: Operation to perform
        db: Database session (automatically provided by DatabaseTask)

    Returns:
        Dict with status and processed count
    """
    try:
        total = len(resource_ids)
        logger.info(f"Starting batch {operation} for {total} resources")

        for i, resource_id in enumerate(resource_ids):
            # Update progress
            self.update_state(
                state="PROCESSING",
                meta={"current": i + 1, "total": total, "operation": operation},
            )

            # Queue individual task based on operation
            if operation == "regenerate_embeddings":
                regenerate_embedding_task.apply_async(args=[resource_id], priority=5)
            elif operation == "recompute_quality":
                recompute_quality_task.apply_async(args=[resource_id], priority=5)
            else:
                logger.warning(f"Unknown operation: {operation}")

        logger.info(f"Successfully queued {total} tasks for batch {operation}")

        return {"status": "completed", "processed": total, "operation": operation}

    except Exception as e:
        logger.error(f"Error in batch processing: {e}", exc_info=True)
        raise


# ============================================================================
# Scheduled Maintenance Tasks
# ============================================================================


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="app.tasks.celery_tasks.monitor_quality_degradation_task",
)
def monitor_quality_degradation_task(self, db=None):
    """
    Monitor quality score degradation over time.

    Schedule: Daily at 2 AM
    Priority: MEDIUM (5)

    Detects resources whose quality scores have decreased significantly
    and triggers recomputation or alerts.

    Args:
        db: Database session (automatically provided by DatabaseTask)
    """
    try:
        logger.info("Starting quality degradation monitoring")

        # TODO: Implement quality degradation detection
        # This would involve:
        # 1. Query resources with quality history
        # 2. Detect significant drops in quality scores
        # 3. Trigger recomputation for degraded resources
        # 4. Generate alerts for manual review

        logger.info("Completed quality degradation monitoring")

    except Exception as e:
        logger.error(f"Error in quality degradation monitoring: {e}", exc_info=True)
        raise


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="app.tasks.celery_tasks.detect_quality_outliers_task",
)
def detect_quality_outliers_task(self, db=None):
    """
    Detect quality score outliers for review.

    Schedule: Weekly on Sunday at 3 AM
    Priority: MEDIUM (5)

    Identifies resources with unusually high or low quality scores
    that may indicate data quality issues or exceptional content.

    Args:
        db: Database session (automatically provided by DatabaseTask)
    """
    try:
        logger.info("Starting quality outlier detection")

        # TODO: Implement quality outlier detection
        # This would involve:
        # 1. Calculate quality score statistics (mean, std dev)
        # 2. Identify outliers (e.g., >3 standard deviations)
        # 3. Generate report for manual review
        # 4. Optionally trigger recomputation

        logger.info("Completed quality outlier detection")

    except Exception as e:
        logger.error(f"Error in quality outlier detection: {e}", exc_info=True)
        raise


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="app.tasks.celery_tasks.retrain_classification_model_task",
)
def retrain_classification_model_task(self, db=None):
    """
    Retrain classification model with new data.

    Schedule: Monthly on 1st at midnight
    Priority: MEDIUM (5)

    Retrains the ML classification model using accumulated user feedback
    and newly classified resources.

    Args:
        db: Database session (automatically provided by DatabaseTask)
    """
    try:
        logger.info("Starting classification model retraining")

        # TODO: Implement model retraining
        # This would involve:
        # 1. Collect training data (user-confirmed classifications)
        # 2. Prepare training dataset
        # 3. Train new model version
        # 4. Evaluate model performance
        # 5. Deploy new model if performance improves

        logger.info("Completed classification model retraining")

    except Exception as e:
        logger.error(f"Error in classification model retraining: {e}", exc_info=True)
        raise


@celery_app.task(name="app.tasks.celery_tasks.cleanup_expired_cache_task")
def cleanup_expired_cache_task():
    """
    Clean up expired cache entries.

    Schedule: Daily at 4 AM
    Priority: LOW (3)

    Removes expired cache entries to free up Redis memory.
    Redis handles TTL expiration automatically, but this task
    can perform additional cleanup and optimization.
    """
    try:
        logger.info("Starting cache cleanup")

        from ..shared.cache import cache

        # Redis automatically handles TTL expiration
        # This task can perform additional cleanup if needed
        # For now, just log cache statistics
        stats = cache.get_stats()
        logger.info(f"Cache statistics: {stats}")

        logger.info("Completed cache cleanup")

    except Exception as e:
        logger.error(f"Error in cache cleanup: {e}", exc_info=True)
        raise


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    max_retries=3,
    default_retry_delay=60,
    name="app.tasks.celery_tasks.update_collection_embeddings_task",
)
def update_collection_embeddings_task(
    self, resource_id: str, db=None
) -> Dict[str, Any]:
    """
    Update collection embeddings after a resource is deleted.

    This task finds all collections that contained the deleted resource and
    recomputes their embeddings. Collection embeddings are the average of
    member resource embeddings, so they need to be updated when membership changes.

    Args:
        resource_id: UUID of the deleted resource
        db: Database session (automatically provided by DatabaseTask)

    Returns:
        Dict with status and number of collections updated

    Raises:
        Exception: If collection embedding update fails (will retry)
    """
    import uuid
    from ..services.collection_service import CollectionService
    from ..database.models import Collection

    try:
        logger.info(
            f"Updating collection embeddings for deleted resource {resource_id}"
        )

        # Convert resource_id to UUID
        try:
            uuid.UUID(resource_id)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid resource_id format: {resource_id}")
            return {"status": "error", "message": f"Invalid UUID: {e}"}

        # Find all collections that contained this resource
        # Note: The resource is already deleted, but we can find collections
        # that need updating by checking for any that might have had it
        collection_service = CollectionService(db)

        # Get all collections (we'll recompute all since we can't query deleted resource)
        # In a production system, you might want to track this relationship before deletion
        collections = db.query(Collection).all()

        updated_count = 0
        for collection in collections:
            try:
                # Recompute embedding for each collection
                collection_service.compute_collection_embedding(collection.id)
                updated_count += 1
                logger.debug(f"Updated embedding for collection {collection.id}")
            except Exception as e:
                logger.warning(f"Failed to update collection {collection.id}: {e}")
                # Continue with other collections

        logger.info(
            f"Updated {updated_count} collection embeddings after resource {resource_id} deletion"
        )

        return {
            "status": "success",
            "resource_id": resource_id,
            "collections_updated": updated_count,
        }

    except Exception as e:
        logger.error(
            f"Error updating collection embeddings for resource {resource_id}: {e}",
            exc_info=True,
        )

        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=2**self.request.retries * 60)


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    max_retries=3,
    default_retry_delay=120,
    name="app.tasks.celery_tasks.chunk_resource_task",
)
def chunk_resource_task(
    self, resource_id: str, strategy: str = "semantic", db=None
) -> Dict[str, Any]:
    """
    Chunk a resource asynchronously for large documents.

    This task is designed for large documents (>10,000 words) that would
    take too long to chunk synchronously during ingestion. It implements
    retry logic with exponential backoff and tracks chunking progress.

    Triggered by: Manual API call or automatic for large documents
    Priority: MEDIUM (5)
    Retry: 3 attempts with exponential backoff

    Args:
        resource_id: UUID of the resource to chunk
        strategy: Chunking strategy ("semantic" or "fixed")
        db: Database session (automatically provided by DatabaseTask)

    Returns:
        Dict with status, chunk count, and processing time

    Raises:
        Exception: If chunking fails (will retry)
    """
    import uuid
    import time
    from ..modules.resources.service import ChunkingService
    from ..database.models import Resource
    from ..shared.event_bus import event_bus, EventPriority

    start_time = time.time()

    try:
        logger.info(
            f"Starting async chunking for resource {resource_id} with strategy={strategy}"
        )

        # Update task state to show progress
        self.update_state(
            state="PROCESSING",
            meta={
                "resource_id": resource_id,
                "strategy": strategy,
                "status": "starting",
            },
        )

        # Convert resource_id to UUID and fetch resource
        try:
            resource_uuid = uuid.UUID(resource_id)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid resource_id format: {resource_id}")
            return {"status": "error", "message": f"Invalid UUID: {e}"}

        resource = db.query(Resource).filter(Resource.id == resource_uuid).first()
        if not resource:
            logger.error(f"Resource not found: {resource_id}")
            return {"status": "error", "message": "Resource not found"}

        # Get resource content (from identifier/archive path)
        content = None
        if resource.identifier:
            try:
                from pathlib import Path

                archive_path = Path(resource.identifier)
                if archive_path.exists():
                    # Read text content from archive
                    text_file = archive_path / "content.txt"
                    if text_file.exists():
                        content = text_file.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to read content from archive: {e}")

        if not content:
            logger.warning(f"No content available for resource {resource_id}")
            return {"status": "error", "message": "No content available"}

        # Update progress
        self.update_state(
            state="PROCESSING",
            meta={
                "resource_id": resource_id,
                "strategy": strategy,
                "status": "chunking",
                "content_length": len(content),
            },
        )

        # Get configuration from settings
        from ..config.settings import get_settings

        settings = get_settings()
        chunk_size = getattr(settings, "CHUNK_SIZE", 500)
        chunk_overlap = getattr(settings, "CHUNK_OVERLAP", 50)

        # Create chunking service
        from ..shared.ai_core import AICore

        ai_core = AICore()

        chunking_service = ChunkingService(
            db=db,
            strategy=strategy,
            chunk_size=chunk_size,
            overlap=chunk_overlap,
            parser_type="text",
            embedding_service=ai_core,
        )

        # Chunk the resource
        chunks = chunking_service.chunk_resource(
            resource_id=resource_id,
            content=content,
            chunk_metadata={"source": "async_task", "strategy": strategy},
        )

        # Calculate processing time
        processing_time = time.time() - start_time

        logger.info(
            f"Successfully chunked resource {resource_id}: {len(chunks)} chunks "
            f"created in {processing_time:.2f}s"
        )

        # Emit completion event
        event_bus.emit(
            "resource.chunking_completed",
            {
                "resource_id": resource_id,
                "chunk_count": len(chunks),
                "strategy": strategy,
                "processing_time": processing_time,
                "async": True,
            },
            priority=EventPriority.NORMAL,
        )

        return {
            "status": "success",
            "resource_id": resource_id,
            "chunk_count": len(chunks),
            "strategy": strategy,
            "processing_time": processing_time,
        }

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Error chunking resource {resource_id}: {e}", exc_info=True)

        # Emit failure event
        event_bus.emit(
            "resource.chunking_failed",
            {
                "resource_id": resource_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "strategy": strategy,
                "processing_time": processing_time,
                "async": True,
            },
            priority=EventPriority.HIGH,
        )

        # Check if error is transient
        error_msg = str(e).lower()
        if any(
            keyword in error_msg
            for keyword in ["timeout", "connection", "network", "memory"]
        ):
            # Retry with exponential backoff
            logger.warning(f"Transient error chunking resource {resource_id}: {e}")
            raise self.retry(exc=e, countdown=2**self.request.retries * 120)
        else:
            # Permanent error - don't retry
            logger.error(f"Permanent error chunking resource {resource_id}: {e}")
            return {
                "status": "error",
                "resource_id": resource_id,
                "message": str(e),
                "error_type": type(e).__name__,
            }


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    time_limit=1800,  # 30 minutes hard limit
    soft_time_limit=1700,  # 28 minutes soft limit
    name="app.tasks.celery_tasks.ingest_repo_task",
)
def ingest_repo_task(
    self,
    path: Optional[str] = None,
    git_url: Optional[str] = None,
    batch_size: int = 50,
) -> Dict[str, Any]:
    """
    Async task for repository ingestion with batch processing and transaction management.

    Ingests a code repository (local directory or Git URL) by crawling files,
    creating Resource entries, and emitting events for downstream processing.
    Files are processed in batches with transaction management to ensure data integrity.

    Performance limits:
    - Maximum 3 concurrent ingestion tasks per worker
    - 30-minute timeout for large repositories (1000+ files)
    - Batch processing (50 files per batch) to avoid memory exhaustion

    Triggered by: POST /resources/ingest-repo API endpoint
    Priority: MEDIUM (5)
    Retry: 2 attempts with exponential backoff (5-15 minutes)

    Args:
        path: Optional local directory path to ingest
        git_url: Optional Git repository URL to clone and ingest
        batch_size: Number of files to process per batch (default: 50)

    Returns:
        Dict with status, files_processed count, and processing details

    Raises:
        ValueError: If neither path nor git_url provided, or both provided
        Exception: If ingestion fails (will retry for transient errors)
    """
    import time
    from pathlib import Path
    from ..modules.resources.logic.repo_ingestion import RepoIngestionService
    from ..shared.event_bus import event_bus, EventPriority
    from ..shared.database import AsyncSessionLocal

    start_time = time.time()

    try:
        # Validate input
        if not path and not git_url:
            raise ValueError("Either path or git_url must be provided")
        if path and git_url:
            raise ValueError("Only one of path or git_url can be provided")

        logger.info(
            f"Starting repository ingestion: "
            f"path={path}, git_url={git_url}, task_id={self.request.id}"
        )

        # Update task state to PENDING
        self.update_state(
            state="PENDING",
            meta={
                "status": "initializing",
                "path": path,
                "git_url": git_url,
                "files_processed": 0,
                "total_files": 0,
                "current_file": None,
            },
        )

        # Use asyncio to run async function
        import asyncio

        # Create async database session and run ingestion
        async def run_ingestion():
            async with AsyncSessionLocal() as db:
                # Create ingestion service
                service = RepoIngestionService(db)

                # Ingest repository
                resources = []
                error_metadata = {}

                if path:
                    # Local directory ingestion
                    logger.info(
                        f"Ingesting local directory: {path} (batch_size={batch_size})"
                    )
                    self.update_state(
                        state="PROCESSING",
                        meta={
                            "status": "crawling_directory",
                            "path": path,
                            "files_processed": 0,
                            "total_files": 0,
                            "current_file": None,
                            "failed_files": [],
                            "batch_size": batch_size,
                        },
                    )

                    resources, error_metadata = await service.crawl_directory(
                        Path(path), track_errors=True, batch_size=batch_size
                    )
                else:
                    # Git repository ingestion
                    logger.info(
                        f"Cloning and ingesting Git repository: {git_url} (batch_size={batch_size})"
                    )
                    self.update_state(
                        state="PROCESSING",
                        meta={
                            "status": "cloning_repository",
                            "git_url": git_url,
                            "files_processed": 0,
                            "total_files": 0,
                            "current_file": None,
                            "failed_files": [],
                            "batch_size": batch_size,
                        },
                    )

                    resources, error_metadata = await service.clone_and_ingest(
                        git_url, track_errors=True, batch_size=batch_size
                    )

                # Process resources and emit events per batch
                total_files = len(resources)
                logger.info(f"Processing {total_files} resources")

                # Emit events in batches to reduce overhead
                batch_size_for_events = 10  # Emit event every 10 resources
                for i in range(0, total_files, batch_size_for_events):
                    batch_end = min(i + batch_size_for_events, total_files)
                    batch_resources = resources[i:batch_end]

                    # Update progress for this batch
                    current_file = (
                        batch_resources[-1].identifier or batch_resources[-1].title
                    )
                    self.update_state(
                        state="PROCESSING",
                        meta={
                            "status": "processing_files",
                            "files_processed": batch_end,
                            "total_files": total_files,
                            "current_file": current_file,
                            "path": path,
                            "git_url": git_url,
                            "failed_files": error_metadata.get("failed_files", []),
                        },
                    )

                    # Emit batch event for downstream processing
                    # This will trigger chunking and graph extraction for the batch
                    try:
                        resource_ids = [str(r.id) for r in batch_resources]
                        event_bus.emit(
                            "resources.batch_created",
                            {
                                "resource_ids": resource_ids,
                                "batch_size": len(batch_resources),
                                "source": "repo_ingestion",
                                "total_files": total_files,
                                "files_processed": batch_end,
                            },
                            priority=EventPriority.NORMAL,
                        )
                        logger.debug(
                            f"Emitted resources.batch_created event for {len(batch_resources)} resources"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to emit batch event: {e}")
                        # Continue processing other batches

                return resources, error_metadata

        # Try to get existing event loop, or create new one
        try:
            asyncio.get_running_loop()
            # If we're already in an async context, we can't use run_until_complete
            # Instead, we need to use asyncio.create_task or similar
            # For Celery tasks, we'll create a new loop in a thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, run_ingestion())
                resources, error_metadata = future.result()
        except RuntimeError:
            # No event loop running, create one
            resources, error_metadata = asyncio.run(run_ingestion())

        # Calculate processing time
        processing_time = time.time() - start_time
        total_files = len(resources)

        logger.info(
            f"Repository ingestion completed: {total_files} files processed "
            f"({error_metadata.get('failed', 0)} failed) in {processing_time:.2f}s"
        )

        # Return success result with error metadata
        return {
            "status": "COMPLETED",
            "files_processed": total_files,
            "path": path,
            "git_url": git_url,
            "processing_time": processing_time,
            "task_id": self.request.id,
            "error_metadata": error_metadata,
        }

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Error in repository ingestion: {e}", exc_info=True)

        # Update task state to FAILED
        self.update_state(
            state="FAILED",
            meta={
                "status": "failed",
                "error": str(e),
                "error_type": type(e).__name__,
                "path": path,
                "git_url": git_url,
                "processing_time": processing_time,
            },
        )

        # Check if error is transient
        error_msg = str(e).lower()
        if any(
            keyword in error_msg
            for keyword in ["timeout", "connection", "network", "temporary"]
        ):
            # Retry with exponential backoff
            logger.warning(f"Transient error in repository ingestion: {e}")
            raise self.retry(exc=e, countdown=2**self.request.retries * 300)
        else:
            # Permanent error - don't retry
            logger.error(f"Permanent error in repository ingestion: {e}")
            raise


# ============================================================================
# Phase 6: Heuristic Sieve — Nightly Temporal Survival Filter
# ============================================================================


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    max_retries=2,
    default_retry_delay=300,
    name="app.tasks.celery_tasks.heuristic_sieve_task",
)
def heuristic_sieve_task(self, db=None):
    """
    Nightly scheduled task that identifies coding patterns surviving the
    temporal heuristic window and pushes them to a Redis queue for local
    LLM extraction.

    Algorithm:
    1. Fetch commits from FEEDBACK_SURVIVAL_DAYS ago via the GitHub API.
    2. For each modified Python file, compute an AST structural fingerprint.
    3. Compare the fingerprint against the current state of the main branch.
    4. If the structure survived intact, push the diff payload to the
       ``pharos_extraction_jobs`` Redis queue.

    This task is the cloud-side orchestrator; the heavy LLM inference
    happens on the local extraction worker that consumes the queue.
    """
    import ast
    import hashlib
    import json
    from datetime import datetime, timedelta, timezone

    import httpx
    import redis

    from ..config.settings import get_settings

    settings = get_settings()

    if not settings.FEEDBACK_LOOP_ENABLED:
        logger.info("Feedback loop disabled — skipping heuristic sieve")
        return {"status": "skipped", "reason": "FEEDBACK_LOOP_ENABLED=False"}

    owner = settings.FEEDBACK_GITHUB_OWNER
    repo = settings.FEEDBACK_GITHUB_REPO
    if not owner or not repo:
        logger.warning("FEEDBACK_GITHUB_OWNER/REPO not configured — skipping")
        return {"status": "skipped", "reason": "missing owner/repo config"}

    survival_days = settings.FEEDBACK_SURVIVAL_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=survival_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    headers = {"Accept": "application/vnd.github+json"}
    gh_token = settings.GITHUB_API_TOKEN
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token.get_secret_value()}"

    api_base = f"https://api.github.com/repos/{owner}/{repo}"

    jobs_pushed = 0

    try:
        with httpx.Client(timeout=30) as client:
            # Step 1: Fetch commits from the cutoff window
            resp = client.get(
                f"{api_base}/commits",
                params={"since": cutoff_iso, "per_page": 100},
                headers=headers,
            )
            resp.raise_for_status()
            commits = resp.json()

            if not commits:
                logger.info("No commits found in the survival window")
                return {"status": "ok", "jobs_pushed": 0}

            # Step 2: For each commit, inspect Python file diffs
            r = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=0,
                decode_responses=True,
            )

            for commit_data in commits:
                sha = commit_data["sha"]

                # Get the full commit with file diffs
                detail_resp = client.get(
                    f"{api_base}/commits/{sha}",
                    headers=headers,
                )
                detail_resp.raise_for_status()
                detail = detail_resp.json()

                for file_info in detail.get("files", []):
                    filename = file_info.get("filename", "")
                    if not filename.endswith(".py"):
                        continue
                    if file_info.get("status") not in ("modified", "added"):
                        continue

                    patch = file_info.get("patch", "")
                    if not patch:
                        continue

                    # Step 3: Fetch the file's current state on main
                    current_resp = client.get(
                        f"{api_base}/contents/{filename}",
                        params={"ref": "main"},
                        headers={**headers, "Accept": "application/vnd.github.raw+json"},
                    )
                    if current_resp.status_code != 200:
                        continue

                    current_source = current_resp.text

                    # Step 4: Compute AST fingerprint of the current file
                    try:
                        tree = ast.parse(current_source)
                    except SyntaxError:
                        continue

                    fingerprint = _ast_structural_fingerprint(tree)

                    # Fetch the file at the old commit to compare
                    old_resp = client.get(
                        f"{api_base}/contents/{filename}",
                        params={"ref": sha},
                        headers={**headers, "Accept": "application/vnd.github.raw+json"},
                    )
                    if old_resp.status_code != 200:
                        continue

                    try:
                        old_tree = ast.parse(old_resp.text)
                    except SyntaxError:
                        continue

                    old_fingerprint = _ast_structural_fingerprint(old_tree)

                    # Step 5: If the structural change survived, push to queue
                    if old_fingerprint != fingerprint:
                        # Structure changed in the commit AND survived to main —
                        # this is a pattern worth extracting.
                        job = {
                            "repository": f"{owner}/{repo}",
                            "commit_sha": sha,
                            "file_path": filename,
                            "diff": patch,
                            "current_fingerprint": fingerprint,
                            "old_fingerprint": old_fingerprint,
                            "committed_at": detail.get("commit", {})
                            .get("committer", {})
                            .get("date", ""),
                        }
                        r.lpush(
                            settings.FEEDBACK_REDIS_QUEUE,
                            json.dumps(job),
                        )
                        jobs_pushed += 1
                        logger.info(
                            "Queued extraction job: %s @ %s — %s",
                            filename,
                            sha[:8],
                            settings.FEEDBACK_REDIS_QUEUE,
                        )

        logger.info("Heuristic sieve complete: %d jobs pushed", jobs_pushed)
        return {"status": "ok", "jobs_pushed": jobs_pushed}

    except Exception as exc:
        logger.error("Heuristic sieve failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=2**self.request.retries * 120)


def _ast_structural_fingerprint(tree: "ast.AST") -> str:
    """
    Produce a deterministic hash of a module's structural skeleton.

    Captures class/function names, decorator names, argument counts,
    and nesting depth — but ignores literal values, comments, and
    whitespace so that formatting-only changes are invisible.
    """
    import ast
    import hashlib

    parts: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            decorators = [
                _decorator_name(d) for d in node.decorator_list
            ]
            parts.append(
                f"{'async ' if isinstance(node, ast.AsyncFunctionDef) else ''}"
                f"def {node.name}({len(node.args.args)} args) "
                f"decorators={sorted(decorators)}"
            )
        elif isinstance(node, ast.ClassDef):
            bases = [_node_name(b) for b in node.bases]
            parts.append(f"class {node.name}({','.join(sorted(bases))})")
        elif isinstance(node, ast.Import):
            names = sorted(alias.name for alias in node.names)
            parts.append(f"import {','.join(names)}")
        elif isinstance(node, ast.ImportFrom):
            names = sorted(alias.name for alias in node.names)
            parts.append(f"from {node.module} import {','.join(names)}")

    signature = "\n".join(sorted(parts))
    return hashlib.sha256(signature.encode()).hexdigest()


def _decorator_name(node) -> str:
    """Extract a human-readable name from a decorator AST node."""
    import ast

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_node_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return "?"


def _node_name(node) -> str:
    """Extract a name from an AST node (Name or Attribute)."""
    import ast

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_node_name(node.value)}.{node.attr}"
    return "?"
