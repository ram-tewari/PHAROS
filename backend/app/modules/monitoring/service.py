"""
Monitoring Service

Provides comprehensive monitoring and metrics collection for the system.
"""

import logging
import os
from typing import Dict, Any
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from ...shared.database import get_pool_status
from ...shared.event_bus import event_bus
from ...shared.cache import cache
from ...utils.performance_monitoring import metrics as perf_metrics

logger = logging.getLogger(__name__)


# Registry for module health check functions
_module_health_checks = {}


def register_module_health_check(module_name: str, health_check_func):
    """
    Register a health check function for a module.

    Args:
        module_name: Name of the module
        health_check_func: Function that returns health status dict
    """
    _module_health_checks[module_name] = health_check_func
    logger.info(f"Registered health check for module: {module_name}")


class MonitoringService:
    """Service for monitoring and metrics collection."""

    async def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics summary.

        Returns:
            Dictionary with performance metrics
        """
        try:
            summary = perf_metrics.get_summary()

            return {
                "status": "ok",
                "timestamp": datetime.utcnow().isoformat(),
                "metrics": summary,
            }

        except Exception as e:
            logger.error(f"Error getting performance metrics: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def get_recommendation_quality_metrics(
        self, db: Session, time_window_days: int
    ) -> Dict[str, Any]:
        """
        Recommendation quality metrics (module removed — single-tenant optimization).
        """
        return {
            "status": "not_applicable",
            "message": "Recommendations module removed (single-tenant optimization)",
            "timestamp": datetime.utcnow().isoformat(),
            "time_window_days": time_window_days,
            "metrics": {},
        }

    async def get_user_engagement_metrics(
        self, db: Session, time_window_days: int
    ) -> Dict[str, Any]:
        """
        User engagement metrics (recommender removed — single-tenant optimization).

        The UserProfile / UserInteraction tables were dropped in the Phase 2
        amputation (2026-07). Pharos is single-tenant; there is no engagement to
        track. Endpoint kept for contract stability; returns a not-applicable stub.
        """
        return {
            "status": "not_applicable",
            "message": "User engagement tracking removed (single-tenant optimization)",
            "timestamp": datetime.utcnow().isoformat(),
            "time_window_days": time_window_days,
            "metrics": {},
        }

    async def get_model_health(self) -> Dict[str, Any]:
        """
        Model health metrics (NCF removed — single-tenant optimization).

        Returns:
            Dictionary with model health information
        """
        return {
            "status": "not_applicable",
            "message": "NCF model removed (single-tenant optimization)",
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def ml_model_health_check(self) -> Dict[str, Any]:
        """
        Health check for ML classification model.

        Returns:
            Dictionary with ML model health status.
            Note: Taxonomy/classification module removed (single-tenant optimization).
        """
        return {
            "status": "not_applicable",
            "timestamp": datetime.utcnow().isoformat(),
            "message": "ML classification module removed (single-tenant optimization)",
            "http_status": 200,
        }

    async def get_database_metrics(self, db: Session) -> Dict[str, Any]:
        """
        Get comprehensive database metrics.

        Args:
            db: Database session for connectivity check

        Returns:
            Dictionary with database metrics
        """
        try:
            from sqlalchemy import text

            # Get pool statistics
            pool_stats = get_pool_status()

            # Check database connectivity
            try:
                db.execute(text("SELECT 1"))
                db_healthy = True
                health_message = "Database connection healthy"
            except Exception as e:
                db_healthy = False
                health_message = f"Database connection failed: {str(e)}"
                logger.error(f"Database health check failed: {str(e)}")

            # Check for pool capacity warnings
            warnings = []
            if pool_stats["pool_usage_percent"] > 90:
                warnings.append(
                    {
                        "level": "warning",
                        "message": f"Connection pool near capacity: {pool_stats['pool_usage_percent']:.1f}% in use",
                        "recommendation": "Consider increasing pool size or investigating connection leaks",
                    }
                )
            elif pool_stats["pool_usage_percent"] > 75:
                warnings.append(
                    {
                        "level": "info",
                        "message": f"Connection pool usage elevated: {pool_stats['pool_usage_percent']:.1f}% in use",
                        "recommendation": "Monitor pool usage trends",
                    }
                )

            # Build response
            response = {
                "status": "ok" if db_healthy else "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "database": {
                    "type": pool_stats["database_type"],
                    "healthy": db_healthy,
                    "health_message": health_message,
                },
                "connection_pool": pool_stats,
                "warnings": warnings,
            }

            return response

        except Exception as e:
            logger.error(f"Error getting database metrics: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def get_db_pool_status(self) -> Dict[str, Any]:
        """
        Get database connection pool statistics.

        Returns:
            Dictionary with connection pool statistics
        """
        try:
            pool_stats = get_pool_status()

            # Calculate utilization percentage
            max_connections = 60  # pool_size (20) + max_overflow (40)
            active_overflow = max(0, pool_stats["overflow"])
            utilization = (
                (pool_stats["checked_out"] + active_overflow) / max_connections * 100
            )

            return {
                "status": "ok",
                "timestamp": datetime.utcnow().isoformat(),
                "pool": {
                    **pool_stats,
                    "max_connections": max_connections,
                    "utilization_percent": round(max(0, utilization), 2),
                },
            }

        except Exception as e:
            logger.error(f"Error getting database pool status: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def get_event_bus_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive event bus metrics.

        Returns:
            Dictionary with event bus metrics
        """
        try:
            metrics = event_bus.get_metrics()

            return {
                "status": "ok",
                "timestamp": datetime.utcnow().isoformat(),
                "metrics": metrics,
            }

        except Exception as e:
            logger.error(f"Error getting event bus metrics: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def get_event_history(self, limit: int) -> Dict[str, Any]:
        """
        Get recent event history.

        Args:
            limit: Maximum number of events to return

        Returns:
            Dictionary with event history
        """
        try:
            events = event_bus.get_event_history(limit=limit)

            return {
                "status": "ok",
                "timestamp": datetime.utcnow().isoformat(),
                "count": len(events),
                "events": events,
            }

        except Exception as e:
            logger.error(f"Error getting event history: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache performance statistics.

        Returns:
            Dictionary with cache statistics
        """
        try:
            hit_rate = cache.stats.hit_rate()
            total_requests = cache.stats.hits + cache.stats.misses

            return {
                "status": "ok",
                "timestamp": datetime.utcnow().isoformat(),
                "cache_stats": {
                    "hit_rate": round(hit_rate, 4),
                    "hit_rate_percent": round(hit_rate * 100, 2),
                    "hits": cache.stats.hits,
                    "misses": cache.stats.misses,
                    "invalidations": cache.stats.invalidations,
                    "total_requests": total_requests,
                },
            }

        except Exception as e:
            logger.error(f"Error getting cache statistics: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def get_worker_status(self, db: Session) -> Dict[str, Any]:
        """
        Ingestion worker status from the durable job table (Celery was removed;
        workers claim jobs from ``ingestion_jobs``).

        Returns:
            Dictionary with queue counts and a healthy/degraded verdict
        """
        from ...codeintel.jobs import queue_summary
        from ...config.settings import get_settings

        try:
            summary = queue_summary(db, get_settings().INGESTION_JOB_STALE_SECONDS)
            return {
                "status": "ok" if summary["status"] == "healthy" else "degraded",
                "timestamp": datetime.utcnow().isoformat(),
                "workers": summary,
            }
        except Exception as e:
            logger.error(f"Error getting worker status: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "message": "Could not read the ingestion job table.",
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def health_check(self, db: Session) -> Dict[str, Any]:
        """
        Overall health check for the system.

        Checks:
        - Database connectivity (critical)
        - Redis connectivity (non-critical, degrades gracefully)
        - Celery worker status (non-critical, background tasks)

        Args:
            db: Database session

        Returns:
            Dictionary with overall system health status including:
            - status: "healthy", "degraded", or "unhealthy"
            - message: Human-readable status message
            - timestamp: ISO timestamp of check
            - components: Status of each component
        """
        try:
            from sqlalchemy import text

            # Check database connectivity (CRITICAL)
            db_healthy = False
            db_message = ""
            try:
                db.execute(text("SELECT 1"))
                db_healthy = True
                db_message = "Connected"
            except Exception as e:
                logger.error(f"Database health check failed: {str(e)}")
                db_message = f"Connection failed: {str(e)}"

            # Check Redis connectivity (NON-CRITICAL)
            redis_healthy = False
            redis_message = ""
            try:
                redis_healthy = cache.ping()
                redis_message = "Connected" if redis_healthy else "Connection failed"
            except Exception as e:
                logger.warning(f"Redis health check failed: {str(e)}")
                redis_message = f"Connection failed: {str(e)}"

            # Ingestion workers (NON-CRITICAL): judged from the durable job
            # table -- stuck or unclaimed jobs mean no worker is making progress.
            ingestion: Dict[str, Any]
            try:
                from ...codeintel.jobs import queue_summary
                from ...config.settings import get_settings

                ingestion = queue_summary(db, get_settings().INGESTION_JOB_STALE_SECONDS)
                ingestion["message"] = (
                    f"{ingestion['queued']} queued, {ingestion['running']} running, "
                    f"{ingestion['stale_running']} stale"
                )
            except Exception as e:
                logger.warning(f"Ingestion queue health check failed: {str(e)}")
                ingestion = {"status": "unknown", "message": f"Check failed: {e}"}
            ingestion_healthy = ingestion["status"] == "healthy"

            # NCF model removed (single-tenant optimization)
            model_available = False

            # Check all registered modules
            module_health = {}
            unhealthy_modules = []
            for module_name, health_check_func in _module_health_checks.items():
                try:
                    module_health[module_name] = health_check_func()
                    if module_health[module_name].get("status") == "unhealthy":
                        unhealthy_modules.append(module_name)
                except Exception as e:
                    logger.error(
                        f"Health check failed for module {module_name}: {str(e)}"
                    )
                    module_health[module_name] = {
                        "status": "unhealthy",
                        "error": str(e),
                    }
                    unhealthy_modules.append(module_name)

            # Determine overall status
            # Database is CRITICAL - if it's down, system is unhealthy
            # Redis and ingestion workers are NON-CRITICAL - system can operate in degraded mode
            if not db_healthy:
                status = "unhealthy"
                message = "Database connection failed - system unavailable"
            elif not redis_healthy or not ingestion_healthy or unhealthy_modules:
                status = "degraded"
                issues = []
                if not redis_healthy:
                    issues.append("Redis unavailable")
                if not ingestion_healthy:
                    issues.append("ingestion jobs are stuck or unclaimed (no worker progress)")
                if unhealthy_modules:
                    issues.append(f"modules unhealthy: {', '.join(unhealthy_modules)}")
                message = f"System operational with degraded functionality: {'; '.join(issues)}"
            else:
                status = "healthy"
                message = "All systems operational"

            response = {
                "status": status,
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
                "components": {
                    "database": {
                        "status": "healthy" if db_healthy else "unhealthy",
                        "message": db_message,
                    },
                    "redis": {
                        "status": "healthy" if redis_healthy else "unhealthy",
                        "message": redis_message,
                    },
                    "ingestion": ingestion,
                    "ncf_model": {
                        "status": "not_applicable",
                        "message": "NCF model removed (single-tenant optimization)",
                    },
                    "api": {"status": "healthy", "message": "API responding"},
                },
            }

            # Add module health if any modules are registered
            if module_health:
                response["modules"] = module_health

            return response

        except Exception as e:
            logger.error(f"Health check failed: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Health check error: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
                "components": {
                    "database": {"status": "unknown", "message": "Check failed"},
                    "redis": {"status": "unknown", "message": "Check failed"},
                    "ingestion": {"status": "unknown", "message": "Check failed"},
                    "api": {"status": "healthy", "message": "API responding"},
                },
            }

    async def get_module_health(self, module_name: str) -> Dict[str, Any]:
        """
        Get health status for a specific module.

        Args:
            module_name: Name of the module

        Returns:
            Dictionary with module health status
        """
        try:
            if module_name not in _module_health_checks:
                # Module exists but hasn't registered a health check - assume healthy
                return {
                    "status": "ok",
                    "timestamp": datetime.utcnow().isoformat(),
                    "module": module_name,
                    "health": {
                        "status": "healthy",
                        "message": "Module operational (no health check registered)",
                    },
                }

            health_check_func = _module_health_checks[module_name]
            health_status = health_check_func()

            return {
                "status": "ok",
                "timestamp": datetime.utcnow().isoformat(),
                "module": module_name,
                "health": health_status,
            }

        except Exception as e:
            logger.error(
                f"Error getting module health for {module_name}: {str(e)}",
                exc_info=True,
            )
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
