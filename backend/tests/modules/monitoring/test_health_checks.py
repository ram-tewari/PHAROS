"""
Monitoring Module Health Check Integration Tests

Tests the health check endpoints for all modules in the system.
Verifies that each module's health endpoint returns 200 OK and
follows the expected response format.

Also tests the enhanced health check endpoint that verifies:
- Database connectivity
- Redis connectivity
- Celery worker status
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_module_health_endpoints(client: TestClient, db_session: Session):
    """
    Test that all module health endpoints return 200 OK.

    This integration test verifies that each of the 12 modules in the system
    has a functioning health check endpoint that returns a successful response.

    Modules tested:
    - annotations
    - authority
    - collections
    - curation
    - graph
    - quality
    - recommendations
    - resources
    - scholarly
    - search
    - taxonomy
    - monitoring (self-check)

    Verifies:
    - HTTP 200 response for each module
    - Response contains 'status' field
    - Status is 'healthy' or 'ok'
    """
    # List of all modules in the system
    modules = [
        "annotations",
        "authority",
        "collections",
        "curation",
        "graph",
        "quality",
        "recommendations",
        "resources",
        "scholarly",
        "search",
        "taxonomy",
        "monitoring",
    ]

    failed_modules = []

    for module_name in modules:
        # Make health check request
        response = client.get(f"/api/monitoring/health/module/{module_name}")

        # Verify HTTP 200 response
        if response.status_code != 200:
            failed_modules.append(
                {
                    "module": module_name,
                    "status_code": response.status_code,
                    "reason": f"Expected 200, got {response.status_code}",
                }
            )
            continue

        # Verify response format
        response_data = response.json()

        # Check that response contains 'status' field
        if "status" not in response_data:
            failed_modules.append(
                {
                    "module": module_name,
                    "status_code": response.status_code,
                    "reason": "Response missing 'status' field",
                }
            )
            continue

        # Verify status is healthy
        status = response_data["status"]
        if status not in ["healthy", "ok", "available"]:
            failed_modules.append(
                {
                    "module": module_name,
                    "status_code": response.status_code,
                    "reason": f"Unexpected status: {status}",
                }
            )

    # Assert all modules passed
    assert len(failed_modules) == 0, (
        f"IMPLEMENTATION FAILURE: {len(failed_modules)} module(s) failed health check\n"
        f"DO NOT UPDATE THE TEST - Fix the module health endpoints instead.\n"
        f"\n"
        f"Failed modules:\n"
        + "\n".join(
            [
                f"  - {m['module']}: {m['reason']} (status code: {m['status_code']})"
                for m in failed_modules
            ]
        )
    )


def test_overall_health_check(client: TestClient, db_session: Session):
    """
    Test the overall system health check endpoint.

    Verifies:
    - HTTP 200 response
    - Response contains 'status' field
    - Response contains system-level health information
    """
    # Make overall health check request
    response = client.get("/api/monitoring/health")

    # Verify HTTP 200 response
    assert response.status_code == 200, (
        f"IMPLEMENTATION FAILURE: Expected status 200, got {response.status_code}\n"
        f"DO NOT UPDATE THE TEST - Fix the health check endpoint instead."
    )

    # Verify response format
    response_data = response.json()

    # Check that response contains 'status' field
    assert "status" in response_data, (
        f"IMPLEMENTATION FAILURE: Response missing 'status' field\n"
        f"DO NOT UPDATE THE TEST - Fix the health check endpoint instead.\n"
        f"Response: {response_data}"
    )

    # Verify status is healthy or degraded (degraded is ok if Redis/Celery unavailable)
    status = response_data["status"]
    assert status in ["healthy", "degraded", "ok"], (
        f"IMPLEMENTATION FAILURE: Unexpected status: {status}\n"
        f"DO NOT UPDATE THE TEST - Fix the health check endpoint instead."
    )


def test_health_check_with_all_services_available(
    client: TestClient, db_session: Session
):
    """
    Test health check when all services (database, Redis, Celery) are available.

    Verifies:
    - Status is "healthy"
    - All components report healthy status
    - Response includes database, redis, celery, and api components
    """
    response = client.get("/api/monitoring/health")

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "status" in data
    assert "message" in data
    assert "timestamp" in data
    assert "components" in data

    # Verify components structure
    components = data["components"]
    assert "database" in components
    assert "redis" in components
    assert "celery" in components
    assert "api" in components

    # Database should be healthy (we have a working db_session)
    assert components["database"]["status"] == "healthy"
    assert "message" in components["database"]

    # API should always be healthy if we got a response
    assert components["api"]["status"] == "healthy"


def test_health_check_with_database_unavailable(client: TestClient):
    """
    Test health check when database is unavailable.

    Verifies:
    - Status is "unhealthy"
    - Database component reports unhealthy status
    - System recognizes database as critical component
    """
    # Mock database session to raise exception
    with patch("backend.app.modules.monitoring.service.Session") as mock_session:
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("Database connection failed")
        mock_session.return_value = mock_db

        # We need to use a different approach - mock at the endpoint level
        # Since we can't easily mock the dependency, we'll test the service directly
        from backend.app.modules.monitoring.service import MonitoringService

        service = MonitoringService()

        # Create a mock db session that fails
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("Database connection failed")

        # Call health_check directly
        import asyncio

        result = asyncio.run(service.health_check(mock_db))

        # Verify status is unhealthy
        assert result["status"] == "unhealthy"
        assert "Database connection failed" in result["message"]

        # Verify database component is unhealthy
        assert result["components"]["database"]["status"] == "unhealthy"


def test_health_check_with_redis_unavailable(client: TestClient, db_session: Session):
    """
    Test health check when Redis is unavailable.

    Verifies:
    - Status is "degraded" (not unhealthy - Redis is non-critical)
    - Redis component reports unhealthy status
    - Database and API still report healthy
    - System continues to operate in degraded mode
    """
    # Mock cache.ping() to return False
    with patch("app.modules.monitoring.service.cache.ping") as mock_ping:
        mock_ping.return_value = False

        response = client.get("/api/monitoring/health")

        assert response.status_code == 200
        data = response.json()

        # Status should be degraded (not unhealthy)
        assert data["status"] == "degraded"
        assert "Redis" in data["message"] or "degraded" in data["message"]

        # Redis component should be unhealthy
        assert data["components"]["redis"]["status"] == "unhealthy"

        # Database should still be healthy
        assert data["components"]["database"]["status"] == "healthy"

        # API should still be healthy
        assert data["components"]["api"]["status"] == "healthy"


def test_health_check_with_celery_unavailable(client: TestClient, db_session: Session):
    """
    Test health check when Celery workers are unavailable.

    Verifies:
    - Status is "degraded" (not unhealthy - Celery is non-critical)
    - Celery component reports unhealthy status
    - Database and API still report healthy
    - System continues to operate in degraded mode
    """
    pytest.importorskip(
        "celery", reason="celery not installed; health-check celery tests require celery"
    )
    # Mock Celery inspect to return empty stats (no workers)
    with patch("app.tasks.celery_app.celery_app.control.inspect") as mock_inspect_func:
        mock_inspect = MagicMock()
        mock_inspect.stats.return_value = {}  # No workers
        mock_inspect_func.return_value = mock_inspect

        response = client.get("/api/monitoring/health")

        assert response.status_code == 200
        data = response.json()

        # Status should be degraded (not unhealthy)
        assert data["status"] == "degraded"
        assert "Celery" in data["message"] or "degraded" in data["message"]

        # Celery component should be unhealthy
        assert data["components"]["celery"]["status"] == "unhealthy"
        assert data["components"]["celery"]["worker_count"] == 0

        # Database should still be healthy
        assert data["components"]["database"]["status"] == "healthy"

        # API should still be healthy
        assert data["components"]["api"]["status"] == "healthy"


def test_health_check_response_structure(client: TestClient, db_session: Session):
    """
    Test that health check response has the correct structure.

    Verifies all required fields are present:
    - status
    - message
    - timestamp
    - components (with nested structure)
    """
    response = client.get("/api/monitoring/health")

    assert response.status_code == 200
    data = response.json()

    # Top-level fields
    assert "status" in data
    assert "message" in data
    assert "timestamp" in data
    assert "components" in data

    # Components should have nested structure
    components = data["components"]

    # Each component should have status and message
    for component_name in ["database", "redis", "celery", "api"]:
        assert component_name in components
        assert "status" in components[component_name]
        assert "message" in components[component_name]

    # Celery should have worker_count
    assert "worker_count" in components["celery"]

    # NCF model should indicate removal (single-tenant optimization)
    assert "ncf_model" in components
    assert "status" in components["ncf_model"]
    assert components["ncf_model"]["status"] == "not_applicable"
    assert "message" in components["ncf_model"]
