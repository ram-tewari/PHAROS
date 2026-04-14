"""
Neo Alexandria 2.0 - Celery Application Configuration

This module configures the Celery distributed task queue for Neo Alexandria.
It provides reliable, prioritized background processing with automatic retries,
task routing, and scheduled task execution.

Related files:
- app/tasks/celery_tasks.py: Task implementations
- app/events/hooks.py: Event hooks that queue tasks
- app/config/settings.py: Configuration settings
- docker-compose.yml: Redis and worker deployment

Features:
- Redis-based message broker and result backend
- Priority queuing with 10 levels (0-9, higher = more urgent)
- Task routing to specialized queues (urgent, high_priority, ml_tasks, batch)
- Automatic task acknowledgment and requeuing on worker failure
- Worker optimization with prefetching and recycling
- Scheduled tasks via Celery Beat
- Result expiration after 1 hour
- Pre-loaded ML models at worker startup for performance

Architecture:
    API/Service → Event → Hook → Queue Task → Redis → Worker → Execute
"""

import logging
import time
from typing import Optional, TYPE_CHECKING

from celery import Celery
from celery.signals import worker_process_init
from celery.schedules import crontab
from kombu import Queue

from ..config.settings import get_settings

if TYPE_CHECKING:
    from ..services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)
settings = get_settings()

# Initialize Celery application
celery_app = Celery(
    "neo_alexandria",
    broker=f"redis://{getattr(settings, 'REDIS_HOST', 'localhost')}:{getattr(settings, 'REDIS_PORT', 6379)}/0",
    backend=f"redis://{getattr(settings, 'REDIS_HOST', 'localhost')}:{getattr(settings, 'REDIS_PORT', 6379)}/1",
)

# Celery Configuration
celery_app.conf.update(
    # Task serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task routing - assign tasks to appropriate queues
    task_routes={
        "app.tasks.celery_tasks.regenerate_embedding_task": {"queue": "high_priority"},
        "app.tasks.celery_tasks.recompute_quality_task": {"queue": "default"},
        "app.tasks.celery_tasks.update_search_index_task": {"queue": "urgent"},
        "app.tasks.celery_tasks.update_graph_edges_task": {"queue": "default"},
        "app.tasks.celery_tasks.invalidate_cache_task": {"queue": "urgent"},
        "app.tasks.celery_tasks.batch_process_resources_task": {"queue": "batch"},
        "app.tasks.celery_tasks.normalize_author_names_task": {"queue": "default"},
        "app.tasks.celery_tasks.ingest_repo_task": {"queue": "repo_ingestion"},
    },
    # Define task queues with priority support
    task_queues=(
        Queue("urgent", routing_key="urgent", priority=9),
        Queue("high_priority", routing_key="high_priority", priority=7),
        Queue("default", routing_key="default", priority=5),
        Queue("ml_tasks", routing_key="ml_tasks", priority=5),
        Queue("batch", routing_key="batch", priority=3),
        Queue(
            "repo_ingestion", routing_key="repo_ingestion", priority=5, max_length=10
        ),  # Limit queue size
    ),
    # Priority queuing configuration
    task_queue_max_priority=10,  # 0-9 priority levels
    task_default_priority=5,  # Medium priority by default
    # Task acknowledgment configuration
    task_acks_late=True,  # Acknowledge after task completion
    task_reject_on_worker_lost=True,  # Requeue tasks if worker crashes
    # Worker optimization
    worker_prefetch_multiplier=4,  # Prefetch 4 tasks per worker
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks (prevent memory leaks)
    worker_concurrency=4,  # Number of concurrent worker processes (default: CPU count)
    # Repository ingestion concurrency limits
    # Limit concurrent repo ingestion tasks to prevent resource exhaustion
    task_annotations={
        "app.tasks.celery_tasks.ingest_repo_task": {
            "rate_limit": "3/h",  # Max 3 ingestion tasks per hour per worker
            "time_limit": 1800,  # Hard limit: 30 minutes
            "soft_time_limit": 1700,  # Soft limit: 28 minutes
        }
    },
    # Result backend configuration
    result_expires=3600,  # Results expire after 1 hour
    result_backend_transport_options={
        "master_name": "mymaster",
    },
    # Task execution configuration
    task_track_started=True,  # Track when tasks start
    task_time_limit=3600,  # Hard time limit: 1 hour
    task_soft_time_limit=3300,  # Soft time limit: 55 minutes
    # Event monitoring
    worker_send_task_events=True,  # Send task events for monitoring
    task_send_sent_event=True,  # Send event when task is sent
)

# Celery Beat Schedule for periodic tasks
celery_app.conf.beat_schedule = {
    # Quality degradation monitoring - daily at 2 AM
    "monitor-quality-degradation": {
        "task": "app.tasks.celery_tasks.monitor_quality_degradation_task",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "default", "priority": 5},
    },
    # Quality outlier detection - weekly on Sunday at 3 AM
    "detect-quality-outliers": {
        "task": "app.tasks.celery_tasks.detect_quality_outliers_task",
        "schedule": crontab(day_of_week=0, hour=3, minute=0),
        "options": {"queue": "default", "priority": 5},
    },
    # Classification model retraining - monthly on 1st at midnight
    "retrain-classification-model": {
        "task": "app.tasks.celery_tasks.retrain_classification_model_task",
        "schedule": crontab(day_of_month=1, hour=0, minute=0),
        "options": {"queue": "ml_tasks", "priority": 5},
    },
    # Cache cleanup - daily at 4 AM
    "cleanup-expired-cache": {
        "task": "app.tasks.celery_tasks.cleanup_expired_cache_task",
        "schedule": crontab(hour=4, minute=0),
        "options": {"queue": "default", "priority": 3},
    },
    # Phase 6: Heuristic sieve - nightly at 1 AM
    "heuristic-sieve-nightly": {
        "task": "app.tasks.celery_tasks.heuristic_sieve_task",
        "schedule": crontab(hour=1, minute=0),
        "options": {"queue": "default", "priority": 5},
    },
}

# Import tasks to register them with Celery
# This must be done after celery_app is configured
try:
    from . import celery_tasks  # noqa: F401
except ImportError:
    # Tasks module not yet created
    pass


# Global embedding service instance (initialized at worker startup)
_embedding_service: Optional["EmbeddingService"] = None


@worker_process_init.connect
def init_worker_process(**kwargs):
    """Initialize worker process with pre-loaded ML models.

    This signal handler runs once when each worker process starts,
    loading ML models into memory to avoid per-task loading overhead.

    Performance Impact:
    - Eliminates ~2-5 seconds of model loading per task
    - Reduces memory fragmentation from repeated loading
    - Improves task throughput by 3-5x for embedding-heavy workloads

    Requirements: 7.1, 7.2, 7.3, 7.5, 7.6
    """
    global _embedding_service

    logger.info("=" * 60)
    logger.info("Initializing Celery worker process...")
    logger.info("=" * 60)

    start_time = time.time()

    try:
        # Import here to avoid circular dependencies
        from ..shared.embeddings import EmbeddingService

        # Pre-load embedding service and models
        logger.info("Loading embedding models...")
        _embedding_service = EmbeddingService()

        # Trigger model loading by generating a test embedding
        # This ensures the model is fully loaded into memory
        test_text = "Initialization test for worker process"
        test_embedding = _embedding_service.generate_embedding(test_text)

        elapsed_time = time.time() - start_time

        logger.info("✓ Embedding models loaded successfully")
        logger.info(f"✓ Test embedding generated: {len(test_embedding)} dimensions")
        logger.info(f"✓ Initialization completed in {elapsed_time:.2f} seconds")

        # Log memory usage if psutil is available
        try:
            import psutil
            import os

            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024 / 1024
            logger.info(f"✓ Worker memory usage: {memory_mb:.2f} MB")
        except ImportError:
            logger.debug("psutil not available - skipping memory logging")

        logger.info("=" * 60)
        logger.info("Worker process ready to accept tasks")
        logger.info("=" * 60)

    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error("=" * 60)
        logger.error(f"Failed to initialize worker process after {elapsed_time:.2f}s")
        logger.error(f"Error: {e}", exc_info=True)
        logger.error("=" * 60)

        # Retry logic with exponential backoff
        max_retries = 3
        for retry in range(max_retries):
            retry_delay = 2**retry  # Exponential backoff: 1s, 2s, 4s
            logger.warning(
                f"Retrying initialization in {retry_delay} seconds (attempt {retry + 1}/{max_retries})..."
            )
            time.sleep(retry_delay)

            try:
                from ..shared.embeddings import EmbeddingService

                _embedding_service = EmbeddingService()
                test_embedding = _embedding_service.generate_embedding("Retry test")
                logger.info(f"✓ Initialization succeeded on retry {retry + 1}")
                return
            except Exception as retry_error:
                logger.error(f"Retry {retry + 1} failed: {retry_error}")

        # All retries failed - set to None and log error
        logger.error(
            "All initialization retries failed - worker will operate without pre-loaded models"
        )
        logger.error(
            "Tasks may experience degraded performance due to per-task model loading"
        )
        _embedding_service = None


def get_embedding_service() -> "EmbeddingService":
    """Get pre-loaded embedding service instance.

    This function provides access to the embedding service that was
    pre-loaded during worker initialization. Tasks should use this
    instead of creating new EmbeddingService instances.

    Returns:
        Pre-loaded EmbeddingService instance

    Raises:
        RuntimeError: If embedding service failed to initialize

    Requirements: 7.4
    """
    if _embedding_service is None:
        raise RuntimeError(
            "Embedding service not initialized in worker process. "
            "This may indicate a failure during worker startup. "
            "Check worker logs for initialization errors."
        )
    return _embedding_service
