"""
Neo Alexandria 2.0 - Performance Monitoring

This module provides performance monitoring and metrics collection using Prometheus.
It tracks request durations, error rates, and custom business metrics.

Related files:
- app/__init__.py: FastAPI app initialization with monitoring
- app/routers/: API endpoints that are automatically monitored
- app/services/: Business logic services with custom metrics

Features:
- Request duration tracking
- Error rate monitoring
- Custom business metrics (ingestion success/failure rates)
- Database query performance tracking
- AI processing time monitoring
- Test-safe initialization (NoOp metrics in test environment)
"""

import time
import asyncio
import os
from typing import Callable, Any
from functools import wraps
from fastapi import Request, Response
from fastapi.responses import PlainTextResponse

# Lazy imports for prometheus to avoid blocking
_prometheus_imported = False
_Counter = None
_Histogram = None
_Gauge = None
_generate_latest = None
_REGISTRY = None
_Instrumentator = None
_metrics = None


def _ensure_prometheus_imported():
    """Lazy import of prometheus_client to avoid blocking on module load."""
    global \
        _prometheus_imported, \
        _Counter, \
        _Histogram, \
        _Gauge, \
        _generate_latest, \
        _REGISTRY, \
        _Instrumentator, \
        _metrics

    if not _prometheus_imported:
        from prometheus_client import (
            Counter,
            Histogram,
            Gauge,
            generate_latest,
            REGISTRY,
        )
        from prometheus_fastapi_instrumentator import (
            Instrumentator,
            metrics as prom_metrics,
        )

        _Counter = Counter
        _Histogram = Histogram
        _Gauge = Gauge
        _generate_latest = generate_latest
        _REGISTRY = REGISTRY
        _Instrumentator = Instrumentator
        _metrics = prom_metrics
        _prometheus_imported = True


# ============================================================================
# Test Environment Detection
# ============================================================================


def is_test_environment() -> bool:
    """
    Check if we're running in a test environment.

    Returns:
        True if running tests, False otherwise
    """
    return (
        os.getenv("TESTING", "false").lower() == "true"
        or os.getenv("PYTEST_CURRENT_TEST") is not None
        or "pytest" in os.getenv("_", "")
    )


# ============================================================================
# NoOp Metrics for Testing
# ============================================================================


class NoOpMetric:
    """No-operation metric that does nothing (for testing)."""

    def __init__(self, *args, **kwargs):
        pass

    def inc(self, *args, **kwargs):
        """No-op increment."""
        pass

    def dec(self, *args, **kwargs):
        """No-op decrement."""
        pass

    def observe(self, *args, **kwargs):
        """No-op observe."""
        pass

    def labels(self, *args, **kwargs):
        """Return self for chaining."""
        return self

    def set(self, *args, **kwargs):
        """No-op set."""
        pass


# Custom Prometheus metrics - use NoOp metrics in test environment
def _get_or_create_metric(metric_class_name, name, description, labelnames=None):
    """
    Get existing metric or create new one, preventing duplicates.

    In test environments, returns NoOpMetric instead of real Prometheus metrics
    to avoid registration conflicts and improve test performance.

    Args:
        metric_class_name: Name of metric class ("Counter", "Histogram", "Gauge")
        name: Metric name
        description: Metric description
        labelnames: Optional list of label names

    Returns:
        Prometheus metric or NoOpMetric (in test environment)
    """
    # Use NoOp metrics in test environment
    if is_test_environment():
        return NoOpMetric(name, description, labelnames)

    # Lazy import prometheus
    _ensure_prometheus_imported()

    # Get the metric class
    metric_class = {"Counter": _Counter, "Histogram": _Histogram, "Gauge": _Gauge}[
        metric_class_name
    ]

    # Try to get existing metric from registry
    try:
        existing = _REGISTRY._names_to_collectors.get(name)
        if existing:
            return existing
    except Exception:
        pass

    # Create new metric
    try:
        if labelnames:
            return metric_class(name, description, labelnames)
        else:
            return metric_class(name, description)
    except ValueError:
        # Metric already exists, get it from registry
        existing = _REGISTRY._names_to_collectors.get(name)
        if existing:
            return existing
        # If still not found, return NoOp to prevent errors
        return NoOpMetric(name, description, labelnames)


REQUEST_DURATION = _get_or_create_metric(
    "Histogram",
    "neo_alexandria_request_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint", "status_code"],
)

REQUEST_COUNT = _get_or_create_metric(
    "Counter",
    "neo_alexandria_requests_total",
    "Total number of requests",
    ["method", "endpoint", "status_code"],
)

INGESTION_SUCCESS = _get_or_create_metric(
    "Counter",
    "neo_alexandria_ingestion_success_total",
    "Total successful resource ingestions",
)

INGESTION_FAILURE = _get_or_create_metric(
    "Counter",
    "neo_alexandria_ingestion_failure_total",
    "Total failed resource ingestions",
    ["error_type"],
)

AI_PROCESSING_TIME = _get_or_create_metric(
    "Histogram",
    "neo_alexandria_ai_processing_seconds",
    "AI processing time in seconds",
    ["operation"],
)

DATABASE_QUERY_TIME = _get_or_create_metric(
    "Histogram",
    "neo_alexandria_database_query_seconds",
    "Database query execution time in seconds",
    ["operation"],
)

ACTIVE_INGESTIONS = _get_or_create_metric(
    "Gauge",
    "neo_alexandria_active_ingestions",
    "Number of currently active ingestion processes",
)

CACHE_HITS = _get_or_create_metric(
    "Counter", "neo_alexandria_cache_hits_total", "Total cache hits", ["cache_type"]
)

CACHE_MISSES = _get_or_create_metric(
    "Counter", "neo_alexandria_cache_misses_total", "Total cache misses", ["cache_type"]
)


def setup_monitoring(app):
    """
    Set up Prometheus monitoring for the FastAPI application.

    Args:
        app: FastAPI application instance

    Returns:
        Instrumentator: Configured Prometheus instrumentator or None in test mode
    """
    # Skip monitoring setup in test environment
    if is_test_environment():
        return None

    # Lazy import prometheus
    _ensure_prometheus_imported()

    instrumentator = _Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics"],
        env_var_name="ENABLE_METRICS",
        inprogress_name="neo_alexandria_inprogress",
        inprogress_labels=True,
    )

    # Add custom metrics
    instrumentator.add(_metrics.default())

    # Add custom business metrics
    instrumentator.add(custom_metrics)

    # Instrument the app
    instrumentator.instrument(app)

    # Add metrics endpoint
    @app.get("/metrics")
    async def metrics_endpoint():
        """Prometheus metrics endpoint."""
        return PlainTextResponse(
            _generate_latest(), media_type="text/plain; version=0.0.4; charset=utf-8"
        )

    return instrumentator


def custom_metrics(request: Request, response: Response) -> None:
    """
    Add custom metrics for business logic tracking.

    Args:
        request: FastAPI request object
        response: FastAPI response object
    """
    # Track request duration and count
    REQUEST_DURATION.labels(  # type: ignore[attr-defined]
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
    ).observe(0)  # Duration is handled by default metrics

    REQUEST_COUNT.labels(  # type: ignore[attr-defined]
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
    ).inc()


def track_ai_processing(operation: str):
    """
    Decorator to track AI processing time.

    Args:
        operation: The AI operation being performed ('summarize', 'tag', 'classify')
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                AI_PROCESSING_TIME.labels(operation=operation).observe(duration)  # type: ignore[attr-defined]

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                AI_PROCESSING_TIME.labels(operation=operation).observe(duration)  # type: ignore[attr-defined]

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def track_database_query(operation: str):
    """
    Decorator to track database query performance.

    Args:
        operation: The database operation being performed ('select', 'insert', 'update', 'delete')
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                DATABASE_QUERY_TIME.labels(operation=operation).observe(duration)  # type: ignore[attr-defined]

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                DATABASE_QUERY_TIME.labels(operation=operation).observe(duration)  # type: ignore[attr-defined]

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def track_ingestion_success():
    """Track successful resource ingestion."""
    INGESTION_SUCCESS.inc()


def track_ingestion_failure(error_type: str):
    """
    Track failed resource ingestion.

    Args:
        error_type: Type of error that caused the failure
    """
    INGESTION_FAILURE.labels(error_type=error_type).inc()  # type: ignore[attr-defined]


def track_cache_hit(cache_type: str):
    """
    Track cache hit.

    Args:
        cache_type: Type of cache ('ai_model', 'classification', 'quality')
    """
    CACHE_HITS.labels(cache_type=cache_type).inc()  # type: ignore[attr-defined]


def track_cache_miss(cache_type: str):
    """
    Track cache miss.

    Args:
        cache_type: Type of cache ('ai_model', 'classification', 'quality')
    """
    CACHE_MISSES.labels(cache_type=cache_type).inc()  # type: ignore[attr-defined]


def increment_active_ingestions():
    """Increment the number of active ingestion processes."""
    ACTIVE_INGESTIONS.inc()


def decrement_active_ingestions():
    """Decrement the number of active ingestion processes."""
    ACTIVE_INGESTIONS.dec()
