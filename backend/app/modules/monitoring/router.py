"""
Monitoring and Metrics Router

Provides endpoints for:
- Performance metrics summary
- Recommendation quality metrics
- User engagement metrics
- NCF model health
- Cache statistics
- Event history
- Worker status
- Database pool status
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...shared.database import get_sync_db
from .service import MonitoringService
from .schema import (
    PerformanceMetrics,
    RecommendationQualityMetrics,
    UserEngagementMetrics,
    ModelHealthMetrics,
    DatabaseMetrics,
    EventBusMetrics,
    CacheStats,
    WorkerStatus,
    HealthCheckResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


@router.get("/performance", response_model=PerformanceMetrics)
async def get_performance_metrics() -> Dict[str, Any]:
    """
    Get performance metrics summary.

    Returns:
        Dictionary with performance metrics including:
        - Cache hit rate
        - Method execution times
        - Slow query count
        - Recommendation generation metrics
    """
    service = MonitoringService()
    return await service.get_performance_metrics()


@router.get("/recommendation-quality", response_model=RecommendationQualityMetrics)
async def get_recommendation_quality_metrics(
    time_window_days: int = Query(default=7, ge=1, le=90), db: Session = Depends(get_sync_db)
) -> Dict[str, Any]:
    """
    Get recommendation quality metrics.

    Args:
        time_window_days: Time window for metrics calculation (1-90 days)
        db: Database session

    Returns:
        Dictionary with quality metrics including:
        - Click-through rate (CTR) by strategy
        - Average diversity (Gini coefficient)
        - Novelty percentage
        - User satisfaction scores
    """
    service = MonitoringService()
    return await service.get_recommendation_quality_metrics(db, time_window_days)


@router.get("/user-engagement", response_model=UserEngagementMetrics)
async def get_user_engagement_metrics(
    time_window_days: int = Query(default=7, ge=1, le=90), db: Session = Depends(get_sync_db)
) -> Dict[str, Any]:
    """
    Get user engagement metrics.

    Args:
        time_window_days: Time window for metrics calculation (1-90 days)
        db: Database session

    Returns:
        Dictionary with engagement metrics including:
        - Total users
        - Active users
        - Total interactions
        - Interactions by type
        - Average session duration
    """
    service = MonitoringService()
    return await service.get_user_engagement_metrics(db, time_window_days)


@router.get("/model-health", response_model=ModelHealthMetrics)
async def get_model_health() -> Dict[str, Any]:
    """
    Get NCF model health metrics.

    Returns:
        Dictionary with model health information including:
        - Model availability
        - Model size (users, items)
        - Last training date
        - Prediction statistics
    """
    service = MonitoringService()
    return await service.get_model_health()


@router.get("/health/ml", response_model=Dict[str, Any])
async def ml_model_health_check() -> Dict[str, Any]:
    """
    Health check for ML classification model.

    Returns:
        Dictionary with ML model health status including:
        - Model loaded status
        - Checkpoint validity
        - Inference functionality
        - Latency metrics

    Returns 200 if healthy, 503 if unhealthy.
    """
    service = MonitoringService()
    return await service.ml_model_health_check()


@router.get("/database", response_model=DatabaseMetrics)
async def get_database_metrics(db: Session = Depends(get_sync_db)) -> Dict[str, Any]:
    """
    Get comprehensive database metrics including connection pool status,
    database type, and health information.

    This endpoint provides detailed monitoring data for database operations,
    including connection pool utilization, database type detection, and
    PostgreSQL-specific metrics when applicable.

    Args:
        db: Database session for connectivity check

    Returns:
        Dictionary with database metrics including:
        - database_type: Type of database (sqlite/postgresql)
        - connection_pool: Detailed pool statistics
        - health: Database connectivity status
        - warnings: Any warnings about pool capacity or performance
    """
    service = MonitoringService()
    return await service.get_database_metrics(db)


@router.get("/db/pool", response_model=Dict[str, Any])
async def get_db_pool_status() -> Dict[str, Any]:
    """
    Get database connection pool statistics.

    Returns detailed metrics about the current state of the database
    connection pool for monitoring and capacity planning.

    Returns:
        Dictionary with connection pool statistics including:
        - size: Total pool size (base connections)
        - checked_in: Number of connections available in the pool
        - checked_out: Number of connections currently in use
        - overflow: Number of overflow connections in use
        - total: Total connections (size + overflow)
        - utilization: Percentage of pool capacity in use
    """
    service = MonitoringService()
    return await service.get_db_pool_status()


@router.get("/events", response_model=EventBusMetrics)
async def get_event_bus_metrics() -> Dict[str, Any]:
    """
    Get comprehensive event bus metrics for monitoring.

    Returns detailed metrics about event bus performance including:
    - Total events emitted and delivered
    - Handler error counts
    - Event type breakdown
    - Handler latency percentiles (p50, p95, p99)

    These metrics are essential for monitoring inter-module communication
    health and identifying performance bottlenecks in event-driven flows.

    Returns:
        Dictionary with event bus metrics including:
        - events_emitted: Total events emitted
        - events_delivered: Total successful handler executions
        - handler_errors: Total handler failures
        - event_types: Breakdown of events by type
        - handler_latency_p50: 50th percentile latency (ms)
        - handler_latency_p95: 95th percentile latency (ms)
        - handler_latency_p99: 99th percentile latency (ms)
    """
    service = MonitoringService()
    return await service.get_event_bus_metrics()


@router.get("/events/history", response_model=Dict[str, Any])
async def get_event_history(
    limit: int = Query(
        default=100, ge=1, le=1000, description="Maximum number of events to return"
    ),
) -> Dict[str, Any]:
    """
    Get recent event history from the event system.

    Returns the most recent events emitted by the system, useful for
    debugging, auditing, and understanding system behavior.

    Args:
        limit: Maximum number of events to return (default: 100, max: 1000)

    Returns:
        Dictionary with event history including:
        - events: List of recent events with name, data, timestamp, priority
        - count: Number of events returned
        - timestamp: When the query was executed
    """
    service = MonitoringService()
    return await service.get_event_history(limit)


@router.get("/cache/stats", response_model=CacheStats)
async def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache performance statistics.

    Returns detailed metrics about cache performance including hit rate,
    miss rate, and invalidation counts. These metrics help evaluate
    caching effectiveness and identify optimization opportunities.

    Returns:
        Dictionary with cache statistics including:
        - hit_rate: Percentage of cache hits (0.0 to 1.0)
        - hits: Total number of cache hits
        - misses: Total number of cache misses
        - invalidations: Total number of cache invalidations
        - total_requests: Total cache requests (hits + misses)
        - hit_rate_percent: Hit rate as percentage (0-100)
    """
    service = MonitoringService()
    return await service.get_cache_stats()


@router.get("/workers/status", response_model=WorkerStatus)
async def get_worker_status() -> Dict[str, Any]:
    """
    Get Celery worker status and task information.

    Returns information about active Celery workers, their current tasks,
    scheduled tasks, and worker statistics. Useful for monitoring
    distributed task processing and worker health.

    Returns:
        Dictionary with worker information including:
        - active: Currently executing tasks by worker
        - scheduled: Tasks scheduled for future execution
        - stats: Worker statistics (processed tasks, etc.)
        - worker_count: Number of active workers
    """
    service = MonitoringService()
    return await service.get_worker_status()


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(db: Session = Depends(get_sync_db)) -> Dict[str, Any]:
    """
    Overall health check for the system.

    Returns:
        Dictionary with overall system health status
    """
    service = MonitoringService()
    return await service.health_check(db)


@router.get("/health/module/{module_name}", response_model=Dict[str, Any])
async def get_module_health(module_name: str) -> Dict[str, Any]:
    """
    Get health status for a specific module.

    Args:
        module_name: Name of the module to check

    Returns:
        Dictionary with module health status including:
        - status: Module health status
        - version: Module version
        - dependencies: Module dependencies status
    """
    service = MonitoringService()
    return await service.get_module_health(module_name)
