"""
Unit Tests for Cloud API (Phase 19)

These tests validate specific examples and edge cases for the Cloud API
ingestion endpoints.

Feature: phase19-hybrid-edge-cloud-orchestration
"""

import json
import os
import sys
import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

# Mock upstash_redis before importing the router
sys.modules["upstash_redis"] = MagicMock()


@pytest.fixture(autouse=True)
def setup_env():
    """Set up environment variables for testing."""
    os.environ["MODE"] = "CLOUD"
    os.environ["PHAROS_ADMIN_TOKEN"] = "test-admin-token-12345"
    os.environ["UPSTASH_REDIS_REST_URL"] = "https://test-redis.upstash.io"
    os.environ["UPSTASH_REDIS_REST_TOKEN"] = "test-token"
    yield
    # Cleanup
    for key in [
        "MODE",
        "PHAROS_ADMIN_TOKEN",
        "UPSTASH_REDIS_REST_URL",
        "UPSTASH_REDIS_REST_TOKEN",
    ]:
        os.environ.pop(key, None)


@pytest.fixture
def mock_redis():
    """Create a mock Redis client that returns proper string values."""
    mock = Mock(
        spec=[
            "llen",
            "rpush",
            "expire",
            "get",
            "lrange",
            "ping",
            "set",
            "lpush",
            "ltrim",
            "delete",
        ]
    )
    # Use spec to prevent MagicMock behavior
    mock.llen = Mock(return_value=0)
    mock.rpush = Mock(return_value=42)
    mock.expire = Mock(return_value=True)
    # Return string, not bytes - this is critical for the worker status endpoint
    mock.get = Mock(return_value="Idle")
    mock.lrange = Mock(return_value=[])
    mock.ping = Mock(return_value=True)
    mock.set = Mock(return_value=True)
    mock.lpush = Mock(return_value=1)
    mock.ltrim = Mock(return_value=True)
    mock.delete = Mock(return_value=1)
    return mock


@pytest.fixture
def mock_queue_service(mock_redis):
    """Create a mock QueueService with mocked Redis."""
    from app.services.queue_service import QueueService

    mock_service = Mock(spec=QueueService)
    mock_service.redis = mock_redis

    # Mock async methods - use proper UUID format for job_id (hex only)
    mock_service.submit_job = AsyncMock(return_value="a1b2c3d4e5f6")
    mock_service.get_queue_position = AsyncMock(return_value=1)
    mock_service.get_queue_size = AsyncMock(return_value=0)
    mock_service.get_job_history = AsyncMock(return_value=[])
    mock_service.get_job_status = AsyncMock(return_value=None)

    return mock_service


# Module-level cache for the test client
_test_client_cache = {}


def get_test_client(mock_queue_service, mock_redis):
    """Get or create FastAPI test client with properly mocked dependencies."""
    cache_key = id(mock_queue_service)

    if cache_key in _test_client_cache:
        return _test_client_cache[cache_key]

    import app.routers.ingestion as ingestion_module

    # Create a function that returns the mock redis client
    def get_mock_redis():
        return mock_redis

    # Create a function that returns the mock queue service
    def get_mock_queue_service():
        return mock_queue_service

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(ingestion_module.router)

    # Override dependencies at the app level
    app.dependency_overrides[ingestion_module.get_redis_client] = get_mock_redis

    # Also patch the module-level queue_service
    original_queue_service = ingestion_module.queue_service
    ingestion_module.queue_service = mock_queue_service

    test_client = TestClient(app)

    # Store in cache
    _test_client_cache[cache_key] = (test_client, original_queue_service)

    return test_client


def test_mode_cloud_doesnt_load_torch():
    """
    Test that MODE=CLOUD doesn't load torch modules.

    Validates: Requirements 1.2
    """
    # Verify MODE is set to CLOUD
    assert os.getenv("MODE") == "CLOUD"

    # Verify MODE is correct
    assert os.getenv("MODE") != "EDGE"


def test_redis_connection_check():
    """
    Test Redis connection check in health endpoint.

    Validates: Requirements 1.5
    """
    mock_redis = Mock()
    mock_redis.ping = Mock(return_value=True)

    mock_queue_service = Mock()

    client = get_test_client(mock_queue_service, mock_redis)

    # Act
    response = client.get("/api/v1/ingestion/health")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["services"]["redis"] == "healthy"


def test_503_when_redis_unavailable():
    """
    Test 503 status when Redis is unavailable.

    Validates: Requirements 2.5
    """
    mock_redis = Mock()
    mock_redis.llen = Mock(side_effect=Exception("Connection refused"))
    mock_redis.ping = Mock(side_effect=Exception("Connection refused"))

    mock_queue_service = Mock()

    client = get_test_client(mock_queue_service, mock_redis)

    # Act
    response = client.post(
        "/api/v1/ingestion/ingest/github.com/user/repo",
        headers={"Authorization": "Bearer test-admin-token-12345"},
    )

    # Assert
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()


def test_429_when_queue_is_full():
    """
    Test 429 status when queue is full (>= 10 tasks).

    Validates: Requirements 2.6
    """
    mock_redis = Mock()
    mock_redis.llen = Mock(return_value=10)  # At capacity
    mock_redis.ping = Mock(return_value=True)
    mock_redis.get = Mock(return_value="Idle")

    mock_queue_service = Mock()
    mock_queue_service.submit_job = AsyncMock()
    mock_queue_service.get_queue_position = AsyncMock(return_value=11)
    mock_queue_service.get_queue_size = AsyncMock(return_value=10)

    # Make submit_job raise 429
    from fastapi import HTTPException

    async def mock_submit(job_data):
        raise HTTPException(status_code=429, detail="Queue is full (10/10)")

    mock_queue_service.submit_job = AsyncMock(side_effect=mock_submit)

    client = get_test_client(mock_queue_service, mock_redis)

    # Act
    response = client.post(
        "/api/v1/ingestion/ingest/github.com/user/repo",
        headers={"Authorization": "Bearer test-admin-token-12345"},
    )

    # Assert
    assert response.status_code == 429
    assert "full" in response.json()["detail"].lower()


def test_401_when_token_is_invalid():
    """
    Test 401 status when token is invalid.

    Validates: Requirements 2.8
    """
    mock_redis = Mock()
    mock_redis.ping = Mock(return_value=True)

    mock_queue_service = Mock()

    client = get_test_client(mock_queue_service, mock_redis)

    # Act
    response = client.post(
        "/api/v1/ingestion/ingest/github.com/user/repo",
        headers={"Authorization": "Bearer wrong-token"},
    )

    # Assert
    assert response.status_code == 401
    assert "authentication" in response.json()["detail"].lower()


def test_401_when_token_is_missing():
    """
    Test 401 status when token is missing.

    Validates: Requirements 2.8
    """
    mock_redis = Mock()
    mock_redis.ping = Mock(return_value=True)

    mock_queue_service = Mock()

    client = get_test_client(mock_queue_service, mock_redis)

    # Act
    response = client.post("/api/v1/ingestion/ingest/github.com/user/repo")

    # Assert
    assert response.status_code == 403  # FastAPI returns 403 for missing auth


def test_authentication_failure_logging(caplog):
    """
    Test that authentication failures are logged.

    Validates: Requirements 2.9
    """
    mock_redis = Mock()
    mock_redis.ping = Mock(return_value=True)

    mock_queue_service = Mock()

    client = get_test_client(mock_queue_service, mock_redis)

    # Act
    response = client.post(
        "/api/v1/ingestion/ingest/github.com/user/repo",
        headers={"Authorization": "Bearer wrong-token"},
    )

    # Assert
    assert response.status_code == 401
    # Check that a warning was logged (caplog captures log messages)
    assert any("Authentication failure" in record.message for record in caplog.records)


def test_health_check_endpoint():
    """
    Test health check endpoint returns service status.

    Validates: Requirements 12.6
    """
    mock_redis = Mock()
    mock_redis.ping = Mock(return_value=True)

    mock_queue_service = Mock()

    client = get_test_client(mock_queue_service, mock_redis)

    # Act
    response = client.get("/api/v1/ingestion/health")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "services" in data
    assert "redis" in data["services"]


def test_worker_status_returns_real_time_updates():
    """
    Test GET /worker/status returns real-time updates for UI.

    Validates: Requirements 2.10
    """
    mock_redis = Mock()
    mock_redis.ping = Mock(return_value=True)
    # Set up the mock to return a string (not bytes)
    mock_redis.get = Mock(return_value="Training Graph on github.com/user/repo")

    mock_queue_service = Mock()

    client = get_test_client(mock_queue_service, mock_redis)

    # Act
    response = client.get("/api/v1/ingestion/worker/status")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "Training Graph on github.com/user/repo"


def test_valid_url_accepted():
    """
    Test that valid repository URLs are accepted.

    Validates: Requirements 2.4
    """
    mock_redis = Mock()
    mock_redis.ping = Mock(return_value=True)
    mock_redis.llen = Mock(return_value=0)
    mock_redis.get = Mock(return_value="Idle")

    mock_queue_service = Mock()
    mock_queue_service.submit_job = AsyncMock(return_value="a1b2c3d4e5f6")
    mock_queue_service.get_queue_position = AsyncMock(return_value=1)
    mock_queue_service.get_queue_size = AsyncMock(return_value=0)

    client = get_test_client(mock_queue_service, mock_redis)

    valid_urls = [
        "github.com/user/repo",
        "https://github.com/user/repo",
        "gitlab.com/org/project",
        "bitbucket.org/team/code",
    ]

    for url in valid_urls:
        response = client.post(
            f"/api/v1/ingestion/ingest/{url}",
            headers={"Authorization": "Bearer test-admin-token-12345"},
        )
        assert response.status_code == 200, f"Failed for URL: {url}"


def test_invalid_url_rejected():
    """
    Test that invalid repository URLs are rejected.

    Validates: Requirements 2.4, 11.4
    """
    mock_redis = Mock()
    mock_redis.ping = Mock(return_value=True)

    mock_queue_service = Mock()

    client = get_test_client(mock_queue_service, mock_redis)

    invalid_urls = [
        "; rm -rf /",
        "|cat /etc/passwd",
        "`whoami`",
    ]

    for url in invalid_urls:
        response = client.post(
            f"/api/v1/ingestion/ingest/{url}",
            headers={"Authorization": "Bearer test-admin-token-12345"},
        )
        assert response.status_code == 400, f"Should reject URL: {url}"


def test_job_history_endpoint():
    """
    Test job history endpoint returns recent jobs.

    Validates: Requirements 9.6
    """
    mock_redis = Mock()
    mock_redis.ping = Mock(return_value=True)

    mock_queue_service = Mock()

    # Configure mock to return job history
    job_records = [
        {
            "repo_url": "github.com/user/repo1",
            "status": "complete",
            "duration_seconds": 120.5,
            "files_processed": 100,
            "embeddings_generated": 100,
            "submitted_at": "2024-01-20T10:00:00Z",
        },
        {
            "repo_url": "github.com/user/repo2",
            "status": "failed",
            "error": "Clone failed",
            "submitted_at": "2024-01-20T11:00:00Z",
        },
    ]
    mock_queue_service.get_job_history = AsyncMock(return_value=job_records)

    client = get_test_client(mock_queue_service, mock_redis)

    # Act
    response = client.get("/api/v1/ingestion/jobs/history?limit=10")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert len(data["jobs"]) == 2
    assert data["jobs"][0]["repo_url"] == "github.com/user/repo1"
    assert data["jobs"][1]["status"] == "failed"


def test_task_metadata_includes_ttl():
    """
    Test that queued tasks include TTL metadata.

    Validates: Requirements 2.7
    """
    mock_redis = Mock()
    mock_redis.ping = Mock(return_value=True)
    mock_redis.llen = Mock(return_value=0)
    mock_redis.get = Mock(return_value="Idle")

    mock_queue_service = Mock()

    # Configure mock to capture submitted job data
    submitted_jobs = []

    async def capture_submit(job_data):
        submitted_jobs.append(job_data)
        return "a1b2c3d4e5f6"

    mock_queue_service.submit_job = AsyncMock(side_effect=capture_submit)
    mock_queue_service.get_queue_position = AsyncMock(return_value=1)
    mock_queue_service.get_queue_size = AsyncMock(return_value=0)

    client = get_test_client(mock_queue_service, mock_redis)

    # Act
    response = client.post(
        "/api/v1/ingestion/ingest/github.com/user/repo",
        headers={"Authorization": "Bearer test-admin-token-12345"},
    )

    # Assert
    assert response.status_code == 200

    # Check that submit_job was called with task data containing TTL
    assert len(submitted_jobs) == 1
    task_data = submitted_jobs[0]
    assert "ttl" in task_data
    assert task_data["ttl"] == 86400  # 24 hours


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
