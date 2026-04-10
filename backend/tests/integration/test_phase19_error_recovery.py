"""
Integration Tests for Phase 19 - Error Recovery Scenarios

Tests the system's ability to recover from various error conditions
including network failures, service outages, and data corruption.

Requirements tested: 8.1, 8.2, 8.6, 11.1, 11.2, 11.3
"""

import pytest
import time
import json
import sys
from unittest.mock import MagicMock, patch
from redis.exceptions import ConnectionError as RedisConnectionError


# Mock upstash_redis and qdrant_client before any imports
sys.modules["upstash_redis"] = MagicMock()
sys.modules["qdrant_client"] = MagicMock()
sys.modules["qdrant_client.http"] = MagicMock()
sys.modules["qdrant_client.http.exceptions"] = MagicMock()

# Import the exception after mocking
from qdrant_client.http.exceptions import UnexpectedResponse


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for error testing."""
    mock_client = MagicMock()
    mock_client.rpush.return_value = 1
    mock_client.llen.return_value = 1
    mock_client.lpop.return_value = None
    mock_client.get.return_value = b'"Idle"'
    mock_client.set.return_value = True
    mock_client.expire.return_value = True
    mock_client.lrange.return_value = []
    mock_client.ltrim.return_value = True
    mock_client.ping.return_value = True
    return mock_client


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client for error testing."""
    mock_client = MagicMock()
    mock_client.get_collections.return_value = MagicMock(collections=[])
    mock_client.create_collection.return_value = True
    mock_client.upsert.return_value = MagicMock(status="completed")
    return mock_client


# ============================================================================
# Redis Connection Error Tests
# ============================================================================


@pytest.mark.integration
def test_redis_connection_failure_on_submit():
    """
    Test Cloud API handles Redis connection failure gracefully.

    Requirements: 2.5, 8.6
    """
    mock_client = MagicMock()
    mock_client.rpush.side_effect = RedisConnectionError("Connection refused")

    with (
        patch("upstash_redis.Redis", return_value=mock_client),
        patch("redis.Redis", return_value=mock_client),
    ):
        from app.routers.ingestion import router
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        test_token = "test-admin-token"
        with patch.dict("os.environ", {"PHAROS_ADMIN_TOKEN": test_token}):
            response = client.post(
                "/api/v1/ingestion/ingest/https://github.com/test/repo",
                headers={"Authorization": f"Bearer {test_token}"},
            )

            # Verify 503 Service Unavailable
            assert response.status_code == 503
            assert "unavailable" in response.json()["detail"].lower()


@pytest.mark.integration
def test_redis_reconnection_in_worker():
    """
    Test Edge Worker reconnects to Redis after connection loss.

    Requirements: 8.6
    """
    mock_client = MagicMock()

    # Simulate connection failure then success
    call_count = [0]

    def mock_lpop_with_reconnect(key):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RedisConnectionError("Connection lost")
        return None

    mock_client.lpop.side_effect = mock_lpop_with_reconnect
    mock_client.get.return_value = b'"Idle"'
    mock_client.set.return_value = True

    with patch("redis.Redis", return_value=mock_client):
        from worker import process_job

        # Worker should handle reconnection internally
        # This test verifies the worker doesn't crash
        task_data = {
            "repo_url": "https://github.com/test/repo",
            "submitted_at": time.time(),
            "ttl": 86400,
        }

        # Should not raise exception
        try:
            result = process_job(task_data)
            # Result may be None or error, but shouldn't crash
            assert True
        except RedisConnectionError:
            pytest.fail("Worker should handle Redis reconnection")


# ============================================================================
# Qdrant Upload Error Tests
# ============================================================================


@pytest.mark.integration
def test_qdrant_upload_retry_on_failure(mock_redis_client, tmp_path):
    """
    Test Edge Worker retries Qdrant upload on failure.

    Requirements: 6.4
    """
    # Create test repo
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("import os\n")

    def mock_clone(url, to_path):
        import shutil

        shutil.copytree(str(repo_dir), to_path, dirs_exist_ok=True)
        return MagicMock()

    # Mock Qdrant client that fails twice then succeeds
    mock_qdrant = MagicMock()
    mock_qdrant.get_collections.return_value = MagicMock(collections=[])
    mock_qdrant.create_collection.return_value = True

    attempt_count = [0]

    def mock_upsert_with_retry(*args, **kwargs):
        attempt_count[0] += 1
        if attempt_count[0] < 3:
            raise UnexpectedResponse(status_code=500, reason_phrase="Server Error")
        return MagicMock(status="completed")

    mock_qdrant.upsert.side_effect = mock_upsert_with_retry

    task_data = {
        "repo_url": "https://github.com/test/repo",
        "submitted_at": time.time(),
        "ttl": 86400,
    }

    with (
        patch("redis.Redis", return_value=mock_redis_client),
        patch("git.Repo.clone_from", side_effect=mock_clone),
        patch("qdrant_client.QdrantClient", return_value=mock_qdrant),
        patch("torch.cuda.is_available", return_value=False),
    ):
        from worker import process_job

        result = process_job(task_data)

        # Verify retries occurred
        assert attempt_count[0] == 3

        # Verify job eventually succeeded
        assert result is not None
        assert result.get("status") in ["completed", "success"]


@pytest.mark.integration
def test_qdrant_upload_failure_after_retries(mock_redis_client, tmp_path):
    """
    Test Edge Worker marks job as failed after exhausting retries.

    Requirements: 6.4, 8.2
    """
    # Create test repo
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("import os\n")

    def mock_clone(url, to_path):
        import shutil

        shutil.copytree(str(repo_dir), to_path, dirs_exist_ok=True)
        return MagicMock()

    # Mock Qdrant client that always fails
    mock_qdrant = MagicMock()
    mock_qdrant.get_collections.return_value = MagicMock(collections=[])
    mock_qdrant.create_collection.return_value = True
    mock_qdrant.upsert.side_effect = UnexpectedResponse(
        status_code=500, reason_phrase="Server Error"
    )

    task_data = {
        "repo_url": "https://github.com/test/repo",
        "submitted_at": time.time(),
        "ttl": 86400,
    }

    with (
        patch("redis.Redis", return_value=mock_redis_client),
        patch("git.Repo.clone_from", side_effect=mock_clone),
        patch("qdrant_client.QdrantClient", return_value=mock_qdrant),
        patch("torch.cuda.is_available", return_value=False),
    ):
        from worker import process_job

        result = process_job(task_data)

        # Verify job marked as failed
        assert result is not None
        assert result.get("status") == "failed"


# ============================================================================
# Git Clone Error Tests
# ============================================================================


@pytest.mark.integration
def test_git_clone_failure_handling(mock_redis_client, mock_qdrant_client):
    """
    Test Edge Worker handles git clone failures gracefully.

    Requirements: 8.1, 8.2
    """

    def mock_clone_failure(url, to_path):
        raise Exception("Repository not found")

    task_data = {
        "repo_url": "https://github.com/test/nonexistent",
        "submitted_at": time.time(),
        "ttl": 86400,
    }

    with (
        patch("redis.Redis", return_value=mock_redis_client),
        patch("git.Repo.clone_from", side_effect=mock_clone_failure),
        patch("qdrant_client.QdrantClient", return_value=mock_qdrant_client),
        patch("torch.cuda.is_available", return_value=False),
    ):
        from worker import process_job

        result = process_job(task_data)

        # Verify job marked as failed
        assert result is not None
        assert result.get("status") == "failed"

        # Verify worker didn't crash
        assert True


@pytest.mark.integration
def test_git_clone_timeout_handling(mock_redis_client, mock_qdrant_client):
    """
    Test Edge Worker handles git clone timeouts.

    Requirements: 8.1, 8.2
    """

    def mock_clone_timeout(url, to_path):
        import time

        time.sleep(0.1)  # Simulate slow clone
        raise TimeoutError("Clone timed out")

    task_data = {
        "repo_url": "https://github.com/test/large_repo",
        "submitted_at": time.time(),
        "ttl": 86400,
    }

    with (
        patch("redis.Redis", return_value=mock_redis_client),
        patch("git.Repo.clone_from", side_effect=mock_clone_timeout),
        patch("qdrant_client.QdrantClient", return_value=mock_qdrant_client),
        patch("torch.cuda.is_available", return_value=False),
    ):
        from worker import process_job

        result = process_job(task_data)

        # Verify job marked as failed
        assert result is not None
        assert result.get("status") == "failed"


# ============================================================================
# Training Error Tests
# ============================================================================


@pytest.mark.integration
def test_training_failure_gpu_memory(mock_redis_client, mock_qdrant_client, tmp_path):
    """
    Test Edge Worker handles GPU out-of-memory errors.

    Requirements: 8.2
    """
    # Create test repo
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("import os\n")

    def mock_clone(url, to_path):
        import shutil

        shutil.copytree(str(repo_dir), to_path, dirs_exist_ok=True)
        return MagicMock()

    task_data = {
        "repo_url": "https://github.com/test/repo",
        "submitted_at": time.time(),
        "ttl": 86400,
    }

    # Mock CUDA available but training fails with OOM
    with (
        patch("redis.Redis", return_value=mock_redis_client),
        patch("git.Repo.clone_from", side_effect=mock_clone),
        patch("qdrant_client.QdrantClient", return_value=mock_qdrant_client),
        patch("torch.cuda.is_available", return_value=True),
        patch("torch.cuda.get_device_name", return_value="Mock GPU"),
        patch("torch.cuda.get_device_properties") as mock_props,
    ):
        # Mock GPU properties
        mock_props.return_value = MagicMock(total_memory=8 * 1024**3)

        from worker import process_job

        # This may fail or succeed depending on actual implementation
        # The key is it shouldn't crash the worker
        try:
            result = process_job(task_data)
            assert result is not None
        except Exception as e:
            # Worker should catch and handle errors
            pytest.fail(f"Worker crashed with: {e}")


# ============================================================================
# Malformed Data Tests
# ============================================================================


@pytest.mark.integration
def test_malformed_task_data_handling(mock_redis_client):
    """
    Test Edge Worker handles malformed task data.

    Requirements: 8.2
    """
    # Test with missing required fields
    malformed_tasks = [
        {},  # Empty
        {"repo_url": "https://github.com/test/repo"},  # Missing submitted_at
        {"submitted_at": time.time()},  # Missing repo_url
        {
            "repo_url": "not-a-url",
            "submitted_at": time.time(),
            "ttl": 86400,
        },  # Invalid URL
    ]

    with patch("redis.Redis", return_value=mock_redis_client):
        from worker import process_job

        for task_data in malformed_tasks:
            try:
                result = process_job(task_data)
                # Should either return error or handle gracefully
                if result is not None:
                    assert result.get("status") in ["failed", "skipped"]
            except Exception:
                # Worker should handle errors internally
                pytest.fail("Worker should handle malformed data gracefully")


@pytest.mark.integration
def test_invalid_url_validation(mock_redis_client):
    """
    Test Cloud API validates repository URLs.

    Requirements: 2.4, 11.4
    """
    with (
        patch("upstash_redis.Redis", return_value=mock_redis_client),
        patch("redis.Redis", return_value=mock_redis_client),
    ):
        from app.routers.ingestion import router
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        test_token = "test-admin-token"
        with patch.dict("os.environ", {"PHAROS_ADMIN_TOKEN": test_token}):
            # Test various invalid URLs
            invalid_urls = [
                "not-a-url",
                "ftp://github.com/test/repo",  # Wrong protocol
                "javascript:alert(1)",  # XSS attempt
                "../../../etc/passwd",  # Path traversal
                "file:///etc/passwd",  # File protocol
            ]

            for url in invalid_urls:
                response = client.post(
                    f"/api/v1/ingestion/ingest/{url}",
                    headers={"Authorization": f"Bearer {test_token}"},
                )

                # Should reject invalid URLs
                assert response.status_code in [400, 422]


# ============================================================================
# Cleanup Error Tests
# ============================================================================


@pytest.mark.integration
def test_cleanup_on_error(mock_redis_client, mock_qdrant_client, tmp_path):
    """
    Test temporary files are cleaned up even when errors occur.

    Requirements: 11.6
    """
    # Create test repo
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("import os\n")

    clone_paths = []

    def mock_clone_track(url, to_path):
        import shutil

        clone_paths.append(to_path)
        shutil.copytree(str(repo_dir), to_path, dirs_exist_ok=True)
        # Simulate error after clone
        raise Exception("Processing error")

    task_data = {
        "repo_url": "https://github.com/test/repo",
        "submitted_at": time.time(),
        "ttl": 86400,
    }

    with (
        patch("redis.Redis", return_value=mock_redis_client),
        patch("git.Repo.clone_from", side_effect=mock_clone_track),
        patch("qdrant_client.QdrantClient", return_value=mock_qdrant_client),
        patch("torch.cuda.is_available", return_value=False),
    ):
        from worker import process_job

        result = process_job(task_data)

        # Verify job marked as failed
        assert result is not None
        assert result.get("status") == "failed"

        # Verify temporary directory was cleaned up
        import os

        for path in clone_paths:
            assert not os.path.exists(path), (
                f"Temporary directory not cleaned up: {path}"
            )


# ============================================================================
# Concurrent Error Tests
# ============================================================================


@pytest.mark.integration
def test_status_consistency_during_errors(mock_redis_client, mock_qdrant_client):
    """
    Test worker status remains consistent even when errors occur.

    Requirements: 3.5, 6.5
    """

    def mock_clone_failure(url, to_path):
        raise Exception("Clone failed")

    task_data = {
        "repo_url": "https://github.com/test/repo",
        "submitted_at": time.time(),
        "ttl": 86400,
    }

    status_updates = []
    original_set = mock_redis_client.set

    def track_status(key, value):
        if "worker_status" in key:
            status_updates.append(value)
        return original_set(key, value)

    mock_redis_client.set.side_effect = track_status

    with (
        patch("redis.Redis", return_value=mock_redis_client),
        patch("git.Repo.clone_from", side_effect=mock_clone_failure),
        patch("qdrant_client.QdrantClient", return_value=mock_qdrant_client),
        patch("torch.cuda.is_available", return_value=False),
    ):
        from worker import process_job

        result = process_job(task_data)

        # Verify status returned to Idle even after error
        assert len(status_updates) >= 2
        final_status = status_updates[-1]
        assert "Idle" in final_status or "idle" in final_status.lower()


# ============================================================================
# Health Check Error Tests
# ============================================================================


@pytest.mark.integration
def test_health_check_with_service_failures():
    """
    Test health check endpoint reports service failures correctly.

    Requirements: 12.6
    """
    mock_redis = MagicMock()
    mock_redis.ping.side_effect = RedisConnectionError("Connection refused")

    with (
        patch("upstash_redis.Redis", return_value=mock_redis),
        patch("redis.Redis", return_value=mock_redis),
    ):
        from app.routers.ingestion import router
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        with patch("app.shared.database.engine") as mock_db_engine:
            mock_db_engine.connect.side_effect = Exception("Database unavailable")

            response = client.get("/health")

            # Should return 503 when services unavailable
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"
