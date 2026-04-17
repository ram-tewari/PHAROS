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
from sqlalchemy import func

from ...shared.database import get_pool_status
from ...shared.event_bus import event_bus
from ...shared.cache import cache
from ...database.models import UserInteraction, UserProfile
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
        Get user engagement metrics.

        Args:
            db: Database session
            time_window_days: Time window for metrics calculation

        Returns:
            Dictionary with engagement metrics
        """
        try:
            from sqlalchemy import select, func

            cutoff_date = datetime.utcnow() - timedelta(days=time_window_days)

            # Total users with profiles
            try:
                result = db.execute(select(func.count(UserProfile.id)))
                total_users = result.scalar() or 0
            except Exception:
                total_users = 0

            # Active users (with interactions in time window)
            result = db.execute(
                select(func.count(func.distinct(UserInteraction.user_id))).where(
                    UserInteraction.interaction_timestamp >= cutoff_date
                )
            )
            active_users = result.scalar() or 0

            # Total interactions
            result = db.execute(
                select(func.count(UserInteraction.id)).where(
                    UserInteraction.interaction_timestamp >= cutoff_date
                )
            )
            total_interactions = result.scalar() or 0

            # Interactions by type
            result = db.execute(
                select(
                    UserInteraction.interaction_type,
                    func.count(UserInteraction.id).label("count"),
                )
                .where(UserInteraction.interaction_timestamp >= cutoff_date)
                .group_by(UserInteraction.interaction_type)
            )
            interactions_by_type = result.all()

            interaction_breakdown = {
                itype: count for itype, count in interactions_by_type
            }

            # Average session duration
            result = db.execute(select(func.avg(UserProfile.avg_session_duration)))
            avg_session = result.scalar() or 0.0

            # Positive interaction rate
            result = db.execute(
                select(func.count(UserInteraction.id)).where(
                    UserInteraction.interaction_timestamp >= cutoff_date,
                    UserInteraction.is_positive == 1,
                )
            )
            positive_interactions = result.scalar() or 0

            positive_rate = (
                positive_interactions / total_interactions
                if total_interactions > 0
                else 0.0
            )

            return {
                "status": "ok",
                "timestamp": datetime.utcnow().isoformat(),
                "time_window_days": time_window_days,
                "metrics": {
                    "total_users": total_users,
                    "active_users": active_users,
                    "total_interactions": total_interactions,
                    "positive_interactions": positive_interactions,
                    "positive_rate": round(positive_rate, 4),
                    "interactions_by_type": interaction_breakdown,
                    "avg_session_duration_seconds": round(avg_session, 2)
                    if avg_session
                    else 0.0,
                },
            }

        except Exception as e:
            logger.error(
                f"Error getting user engagement metrics: {str(e)}", exc_info=True
            )
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def get_model_health(self) -> Dict[str, Any]:
        """
        Get NCF model health metrics.

        Returns:
            Dictionary with model health information
        """
        try:
            # Check if model file exists
            backend_dir = Path(__file__).parent.parent.parent.parent
            model_path = os.path.join(backend_dir, "models", "ncf_model.pt")

            model_exists = os.path.exists(model_path)

            if model_exists:
                # Get model file info
                model_stat = os.stat(model_path)
                model_size_mb = model_stat.st_size / (1024 * 1024)
                last_modified = datetime.fromtimestamp(model_stat.st_mtime)

                # Try to load model info
                try:
                    import torch

                    checkpoint = torch.load(model_path, map_location="cpu")

                    return {
                        "status": "ok",
                        "timestamp": datetime.utcnow().isoformat(),
                        "model": {
                            "available": True,
                            "path": model_path,
                            "size_mb": round(model_size_mb, 2),
                            "last_modified": last_modified.isoformat(),
                            "num_users": checkpoint.get("num_users", 0),
                            "num_items": checkpoint.get("num_items", 0),
                            "embedding_dim": checkpoint.get("embedding_dim", 64),
                        },
                    }
                except Exception as e:
                    return {
                        "status": "warning",
                        "timestamp": datetime.utcnow().isoformat(),
                        "model": {
                            "available": True,
                            "path": model_path,
                            "size_mb": round(model_size_mb, 2),
                            "last_modified": last_modified.isoformat(),
                            "error": f"Could not load model details: {str(e)}",
                        },
                    }
            else:
                return {
                    "status": "warning",
                    "timestamp": datetime.utcnow().isoformat(),
                    "model": {
                        "available": False,
                        "message": "NCF model not trained yet. System will use content-based and graph-based recommendations.",
                    },
                }

        except Exception as e:
            logger.error(f"Error getting model health: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
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

    async def get_worker_status(self) -> Dict[str, Any]:
        """
        Get Celery worker status.

        Returns:
            Dictionary with worker information
        """
        try:
            from ...tasks.celery_app import celery_app

            # Get Celery inspector
            inspect = celery_app.control.inspect()

            # Get worker information
            active_tasks = inspect.active() or {}
            scheduled_tasks = inspect.scheduled() or {}
            worker_stats = inspect.stats() or {}

            # Count active workers
            worker_count = len(worker_stats)

            # Count total active and scheduled tasks
            total_active = sum(len(tasks) for tasks in active_tasks.values())
            total_scheduled = sum(len(tasks) for tasks in scheduled_tasks.values())

            return {
                "status": "ok",
                "timestamp": datetime.utcnow().isoformat(),
                "workers": {
                    "worker_count": worker_count,
                    "total_active_tasks": total_active,
                    "total_scheduled_tasks": total_scheduled,
                    "active_tasks": active_tasks,
                    "scheduled_tasks": scheduled_tasks,
                    "stats": worker_stats,
                },
            }

        except Exception as e:
            logger.error(f"Error getting worker status: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "message": "Could not connect to Celery workers. Ensure Redis and workers are running.",
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

            # Check Celery worker status (NON-CRITICAL)
            celery_healthy = False
            celery_message = ""
            worker_count = 0
            try:
                from ...tasks.celery_app import celery_app

                # Get Celery inspector
                inspect = celery_app.control.inspect(timeout=2.0)

                # Get worker stats
                worker_stats = inspect.stats() or {}
                worker_count = len(worker_stats)

                if worker_count > 0:
                    celery_healthy = True
                    celery_message = f"{worker_count} worker(s) active"
                else:
                    celery_message = "No workers available"

            except Exception as e:
                logger.warning(f"Celery health check failed: {str(e)}")
                celery_message = f"Cannot connect to workers: {str(e)}"

            # Check model availability (optional - not required for healthy status)
            backend_dir = Path(__file__).parent.parent.parent.parent
            model_path = os.path.join(backend_dir, "models", "ncf_model.pt")
            model_available = os.path.exists(model_path)

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
            # Redis and Celery are NON-CRITICAL - system can operate in degraded mode
            if not db_healthy:
                status = "unhealthy"
                message = "Database connection failed - system unavailable"
            elif not redis_healthy or not celery_healthy or unhealthy_modules:
                status = "degraded"
                issues = []
                if not redis_healthy:
                    issues.append("Redis unavailable")
                if not celery_healthy:
                    issues.append("Celery workers unavailable")
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
                    "celery": {
                        "status": "healthy" if celery_healthy else "unhealthy",
                        "message": celery_message,
                        "worker_count": worker_count,
                    },
                    "ncf_model": {
                        "status": "available" if model_available else "unavailable",
                        "message": "Model loaded"
                        if model_available
                        else "Model not trained",
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
                    "celery": {"status": "unknown", "message": "Check failed"},
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
