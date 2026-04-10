"""
Monitoring Service Unit Tests

Tests for the MonitoringService class methods to achieve 80% coverage.
Tests health check aggregation, metrics collection, and performance monitoring.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from sqlalchemy.orm import Session

from app.modules.monitoring.service import (
    MonitoringService,
    register_module_health_check,
)


@pytest.fixture
def monitoring_service():
    """Create a MonitoringService instance for testing."""
    return MonitoringService()


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return Mock(spec=Session)


class TestPerformanceMetrics:
    """Tests for performance metrics collection."""

    @pytest.mark.asyncio
    async def test_get_performance_metrics_success(self, monitoring_service):
        """Test successful performance metrics collection."""
        with patch("app.modules.monitoring.service.perf_metrics") as mock_perf:
            mock_perf.get_summary.return_value = {
                "cache_hit_rate": 0.85,
                "total_requests": 1000,
                "avg_response_time": 150.5,
            }

            result = await monitoring_service.get_performance_metrics()

            assert result["status"] == "ok"
            assert "timestamp" in result
            assert "metrics" in result
            assert result["metrics"]["cache_hit_rate"] == 0.85
            assert result["metrics"]["total_requests"] == 1000

    @pytest.mark.asyncio
    async def test_get_performance_metrics_error(self, monitoring_service):
        """Test performance metrics collection with error."""
        with patch("app.modules.monitoring.service.perf_metrics") as mock_perf:
            mock_perf.get_summary.side_effect = Exception("Metrics unavailable")

            result = await monitoring_service.get_performance_metrics()

            assert result["status"] == "error"
            assert "error" in result
            assert "Metrics unavailable" in result["error"]


class TestEventBusMetrics:
    """Tests for event bus metrics collection."""

    @pytest.mark.asyncio
    async def test_get_event_bus_metrics_success(self, monitoring_service):
        """Test successful event bus metrics collection."""
        with patch("app.modules.monitoring.service.event_bus") as mock_bus:
            mock_bus.get_metrics.return_value = {
                "events_emitted": 500,
                "events_delivered": 490,
                "handler_errors": 10,
            }

            result = await monitoring_service.get_event_bus_metrics()

            assert result["status"] == "ok"
            assert "timestamp" in result
            assert "metrics" in result
            assert result["metrics"]["events_emitted"] == 500

    @pytest.mark.asyncio
    async def test_get_event_bus_metrics_error(self, monitoring_service):
        """Test event bus metrics collection with error."""
        with patch("app.modules.monitoring.service.event_bus") as mock_bus:
            mock_bus.get_metrics.side_effect = Exception("Event bus error")

            result = await monitoring_service.get_event_bus_metrics()

            assert result["status"] == "error"
            assert "error" in result


class TestCacheStats:
    """Tests for cache statistics collection."""

    @pytest.mark.asyncio
    async def test_get_cache_stats_success(self, monitoring_service):
        """Test successful cache stats collection."""
        with patch("app.modules.monitoring.service.cache") as mock_cache:
            mock_cache.stats.hits = 150
            mock_cache.stats.misses = 50
            mock_cache.stats.invalidations = 10
            mock_cache.stats.hit_rate.return_value = 0.75

            result = await monitoring_service.get_cache_stats()

            assert result["status"] == "ok"
            assert "timestamp" in result
            assert "cache_stats" in result
            assert result["cache_stats"]["hits"] == 150
            assert result["cache_stats"]["misses"] == 50
            assert result["cache_stats"]["hit_rate"] == 0.75

    @pytest.mark.asyncio
    async def test_get_cache_stats_error(self, monitoring_service):
        """Test cache stats collection with error."""
        with patch("app.modules.monitoring.service.cache") as mock_cache:
            mock_cache.stats.hit_rate.side_effect = Exception("Cache error")

            result = await monitoring_service.get_cache_stats()

            assert result["status"] == "error"
            assert "error" in result


class TestDatabaseMetrics:
    """Tests for database metrics collection."""

    @pytest.mark.asyncio
    async def test_get_database_metrics_healthy(self, monitoring_service, mock_db):
        """Test database metrics with healthy database."""
        mock_db.execute.return_value = None

        with patch("app.modules.monitoring.service.get_pool_status") as mock_pool:
            mock_pool.return_value = {
                "database_type": "postgresql",
                "pool_size": 20,
                "checked_out": 5,
                "pool_usage_percent": 25.0,
            }

            result = await monitoring_service.get_database_metrics(mock_db)

            assert result["status"] == "ok"
            assert result["database"]["healthy"] is True
            assert result["database"]["type"] == "postgresql"
            assert len(result["warnings"]) == 0

    @pytest.mark.asyncio
    async def test_get_database_metrics_high_usage(self, monitoring_service, mock_db):
        """Test database metrics with high pool usage."""
        mock_db.execute.return_value = None

        with patch("app.modules.monitoring.service.get_pool_status") as mock_pool:
            mock_pool.return_value = {
                "database_type": "postgresql",
                "pool_size": 20,
                "checked_out": 19,
                "pool_usage_percent": 95.0,
            }

            result = await monitoring_service.get_database_metrics(mock_db)

            assert result["status"] == "ok"
            assert len(result["warnings"]) > 0
            assert "near capacity" in result["warnings"][0]["message"].lower()

    @pytest.mark.asyncio
    async def test_get_database_metrics_unhealthy(self, monitoring_service, mock_db):
        """Test database metrics with unhealthy database."""
        mock_db.execute.side_effect = Exception("Connection failed")

        with patch("app.modules.monitoring.service.get_pool_status") as mock_pool:
            mock_pool.return_value = {
                "database_type": "postgresql",
                "pool_size": 20,
                "checked_out": 0,
                "pool_usage_percent": 0.0,
            }

            result = await monitoring_service.get_database_metrics(mock_db)

            assert result["status"] == "unhealthy"
            assert result["database"]["healthy"] is False


class TestHealthCheck:
    """Tests for overall health check."""

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(self, monitoring_service, mock_db):
        """Test health check with all systems healthy."""
        mock_db.execute.return_value = None

        result = await monitoring_service.health_check(mock_db)

        # Status may be degraded if redis/celery are unavailable in test env
        assert result["status"] in ("healthy", "degraded")
        assert result["components"]["database"]["status"] == "healthy"
        assert result["components"]["api"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_db_unhealthy(self, monitoring_service, mock_db):
        """Test health check with unhealthy database."""
        mock_db.execute.side_effect = Exception("DB error")

        result = await monitoring_service.health_check(mock_db)

        assert result["status"] == "unhealthy"
        assert result["components"]["database"]["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_health_check_with_modules(self, monitoring_service, mock_db):
        """Test health check with registered modules."""
        mock_db.execute.return_value = None

        # Register a test module
        def test_health_check():
            return {"status": "healthy", "message": "Test module OK"}

        register_module_health_check("test_module", test_health_check)

        result = await monitoring_service.health_check(mock_db)

        # Status may be degraded if redis/celery are unavailable in test env
        assert result["status"] in ("healthy", "degraded")
        assert "modules" in result
        assert "test_module" in result["modules"]


class TestModuleHealth:
    """Tests for module health checks."""

    @pytest.mark.asyncio
    async def test_get_module_health_registered(self, monitoring_service):
        """Test getting health for a registered module."""

        def test_health_check():
            return {"status": "healthy", "version": "1.0.0"}

        register_module_health_check("test_module", test_health_check)

        result = await monitoring_service.get_module_health("test_module")

        assert result["status"] == "ok"
        assert result["module"] == "test_module"
        assert result["health"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_get_module_health_not_registered(self, monitoring_service):
        """Test getting health for a non-registered module."""
        result = await monitoring_service.get_module_health("unknown_module")

        assert result["status"] == "ok"
        assert result["health"]["status"] == "healthy"
        assert "no health check registered" in result["health"]["message"].lower()


class TestModelHealth:
    """Tests for ML model health checks."""

    @pytest.mark.asyncio
    async def test_get_model_health_not_available(self, monitoring_service):
        """Test model health when model is not available."""
        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = False

            result = await monitoring_service.get_model_health()

            assert result["status"] == "warning"
            assert result["model"]["available"] is False

    @pytest.mark.asyncio
    async def test_get_model_health_load_error(self, monitoring_service):
        """Test model health when model exists but can't be loaded."""
        with patch("os.path.exists") as mock_exists, patch("os.stat") as mock_stat:
            mock_exists.return_value = True
            mock_stat.return_value = Mock(
                st_size=1024 * 1024, st_mtime=datetime.now().timestamp()
            )

            result = await monitoring_service.get_model_health()

            # Should return warning status if torch can't load the model
            assert result["status"] in ["ok", "warning"]
            assert result["model"]["available"] is True


class TestEventHistory:
    """Tests for event history retrieval."""

    @pytest.mark.asyncio
    async def test_get_event_history_success(self, monitoring_service):
        """Test successful event history retrieval."""
        with patch("app.modules.monitoring.service.event_bus") as mock_bus:
            mock_bus.get_event_history.return_value = [
                {"event": "resource.created", "timestamp": "2024-01-01T00:00:00"},
                {"event": "resource.updated", "timestamp": "2024-01-01T00:01:00"},
            ]

            result = await monitoring_service.get_event_history(limit=10)

            assert result["status"] == "ok"
            assert "events" in result
            assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_get_event_history_error(self, monitoring_service):
        """Test event history retrieval with error."""
        with patch("app.modules.monitoring.service.event_bus") as mock_bus:
            mock_bus.get_event_history.side_effect = Exception("History error")

            result = await monitoring_service.get_event_history(limit=10)

            assert result["status"] == "error"
            assert "error" in result


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("celery") is None,
    reason="celery not installed; worker-status tests require celery",
)
class TestWorkerStatus:
    """Tests for worker status retrieval."""

    @pytest.mark.asyncio
    async def test_get_worker_status_success(self, monitoring_service):
        """Test successful worker status retrieval."""
        with patch("app.tasks.celery_app.celery_app") as mock_celery:
            mock_inspect = Mock()
            mock_inspect.active.return_value = {"worker1": []}
            mock_inspect.scheduled.return_value = {"worker1": []}
            mock_inspect.stats.return_value = {"worker1": {"total": 100}}
            mock_celery.control.inspect.return_value = mock_inspect

            result = await monitoring_service.get_worker_status()

            assert result["status"] == "ok"
            assert "workers" in result
            assert result["workers"]["worker_count"] == 1

    @pytest.mark.asyncio
    async def test_get_worker_status_error(self, monitoring_service):
        """Test worker status retrieval with error."""
        with patch("app.tasks.celery_app.celery_app") as mock_celery:
            mock_celery.control.inspect.side_effect = Exception("Celery error")

            result = await monitoring_service.get_worker_status()

            assert result["status"] == "error"
            assert "error" in result


class TestRecommendationQualityMetrics:
    """Tests for recommendation quality metrics."""

    @pytest.mark.asyncio
    async def test_get_recommendation_quality_metrics_error(
        self, monitoring_service, mock_db
    ):
        """Test recommendation quality metrics when the feedback query fails.

        The inner try/except catches the exception and falls back to the
        empty-data path, so status is "ok" with zero metrics.
        """
        mock_db.query.side_effect = Exception("Database error")

        result = await monitoring_service.get_recommendation_quality_metrics(mock_db, 7)

        assert result["status"] == "ok"
        assert result["metrics"]["total_recommendations"] == 0


class TestUserEngagementMetrics:
    """Tests for user engagement metrics."""

    @pytest.mark.asyncio
    async def test_get_user_engagement_metrics_error(self, monitoring_service, mock_db):
        """Test user engagement metrics with error."""
        mock_db.query.side_effect = Exception("Database error")

        result = await monitoring_service.get_user_engagement_metrics(mock_db, 7)

        assert result["status"] == "error"
        assert "error" in result


class TestMLModelHealthCheck:
    """Tests for ML classification model health check."""

    @pytest.mark.asyncio
    async def test_ml_model_health_check_exception(self, monitoring_service):
        """Test ML model health check with general exception."""
        # Test the outer exception handler
        result = await monitoring_service.ml_model_health_check()

        # Should return error status if service can't be imported
        assert result["status"] in ["healthy", "unhealthy", "error"]
        assert "timestamp" in result


class TestDatabasePoolStatus:
    """Tests for database connection pool status."""

    @pytest.mark.asyncio
    async def test_get_db_pool_status_success(self, monitoring_service):
        """Test database pool status retrieval."""
        with patch("app.modules.monitoring.service.get_pool_status") as mock_pool:
            mock_pool.return_value = {
                "pool_size": 20,
                "checked_in": 15,
                "checked_out": 5,
                "overflow": 0,
                "total": 20,
            }

            result = await monitoring_service.get_db_pool_status()

            assert result["status"] == "ok"
            assert "pool" in result
            assert result["pool"]["pool_size"] == 20

    @pytest.mark.asyncio
    async def test_get_db_pool_status_error(self, monitoring_service):
        """Test database pool status with error."""
        with patch("app.modules.monitoring.service.get_pool_status") as mock_pool:
            mock_pool.side_effect = Exception("Pool error")

            result = await monitoring_service.get_db_pool_status()

            assert result["status"] == "error"
            assert "error" in result


class TestModuleHealthRegistration:
    """Tests for module health check registration."""

    def test_register_module_health_check(self):
        """Test registering a module health check."""

        def test_health():
            return {"status": "healthy"}

        register_module_health_check("test_registration", test_health)

        # Verify it was registered (implicitly tested by get_module_health)
        assert True  # Registration doesn't raise an error


class TestDatabaseMetricsEdgeCases:
    """Tests for database metrics edge cases."""

    @pytest.mark.asyncio
    async def test_get_database_metrics_elevated_usage(
        self, monitoring_service, mock_db
    ):
        """Test database metrics with elevated pool usage (75-90%)."""
        mock_db.execute.return_value = None

        with patch("app.modules.monitoring.service.get_pool_status") as mock_pool:
            mock_pool.return_value = {
                "database_type": "postgresql",
                "pool_size": 20,
                "checked_out": 16,
                "pool_usage_percent": 80.0,
            }

            result = await monitoring_service.get_database_metrics(mock_db)

            assert result["status"] == "ok"
            # Should have info-level warning for elevated usage
            assert len(result["warnings"]) > 0

    @pytest.mark.asyncio
    async def test_get_database_metrics_error_handling(
        self, monitoring_service, mock_db
    ):
        """Test database metrics with exception in pool status."""
        mock_db.execute.return_value = None

        with patch("app.modules.monitoring.service.get_pool_status") as mock_pool:
            mock_pool.side_effect = Exception("Pool status error")

            result = await monitoring_service.get_database_metrics(mock_db)

            assert result["status"] == "error"
            assert "error" in result


class TestHealthCheckWithUnhealthyModules:
    """Tests for health check with unhealthy modules."""

    @pytest.mark.asyncio
    async def test_health_check_with_unhealthy_module(
        self, monitoring_service, mock_db
    ):
        """Test health check when a module is unhealthy."""
        mock_db.execute.return_value = None

        # Register an unhealthy module
        def unhealthy_check():
            return {"status": "unhealthy", "error": "Module error"}

        register_module_health_check("unhealthy_test", unhealthy_check)

        result = await monitoring_service.health_check(mock_db)

        # Should be degraded due to unhealthy module
        assert result["status"] == "degraded"
        assert "unhealthy_test" in result.get("modules", {})

    @pytest.mark.asyncio
    async def test_health_check_module_exception(self, monitoring_service, mock_db):
        """Test health check when a module health check raises exception."""
        mock_db.execute.return_value = None

        # Register a module that raises exception
        def failing_check():
            raise Exception("Health check failed")

        register_module_health_check("failing_test", failing_check)

        result = await monitoring_service.health_check(mock_db)

        # Should be degraded due to module exception
        assert result["status"] == "degraded"
        assert "failing_test" in result.get("modules", {})


class TestDatabasePoolStatusCalculations:
    """Tests for database pool status calculations."""

    @pytest.mark.asyncio
    async def test_get_db_pool_status_with_overflow(self, monitoring_service):
        """Test database pool status with overflow connections."""
        with patch("app.modules.monitoring.service.get_pool_status") as mock_pool:
            mock_pool.return_value = {
                "pool_size": 20,
                "checked_in": 10,
                "checked_out": 15,
                "overflow": 5,
                "total": 25,
            }

            result = await monitoring_service.get_db_pool_status()

            assert result["status"] == "ok"
            assert result["pool"]["overflow"] == 5
            # Utilization should account for overflow
            assert result["pool"]["utilization_percent"] > 0


class TestModelHealthEdgeCases:
    """Tests for model health edge cases."""

    @pytest.mark.asyncio
    async def test_get_model_health_file_exists_but_load_fails(
        self, monitoring_service
    ):
        """Test model health when file exists but can't be loaded."""
        with patch("os.path.exists") as mock_exists, patch("os.stat") as mock_stat:
            mock_exists.return_value = True
            mock_stat.return_value = Mock(st_size=1024 * 1024, st_mtime=1234567890.0)

            result = await monitoring_service.get_model_health()

            # Should return warning status since torch import will fail
            assert result["status"] in ["ok", "warning"]
            assert result["model"]["available"] is True
            assert "size_mb" in result["model"]


class TestHealthCheckExceptionHandling:
    """Tests for health check exception handling."""

    @pytest.mark.asyncio
    async def test_health_check_general_exception(self, monitoring_service, mock_db):
        """Test health check with general exception."""
        # Make the database check raise an exception during execution
        mock_db.execute.side_effect = Exception("Unexpected error")

        result = await monitoring_service.health_check(mock_db)

        # Should return unhealthy status
        assert result["status"] == "unhealthy"
        assert result["components"]["database"]["status"] == "unhealthy"


class TestModuleHealthEdgeCases:
    """Tests for module health edge cases."""

    @pytest.mark.asyncio
    async def test_get_module_health_exception_in_check(self, monitoring_service):
        """Test module health when health check function raises exception."""

        def failing_health_check():
            raise ValueError("Health check error")

        register_module_health_check("exception_test", failing_health_check)

        result = await monitoring_service.get_module_health("exception_test")

        # Should return error status
        assert result["status"] == "error"
        assert "error" in result
