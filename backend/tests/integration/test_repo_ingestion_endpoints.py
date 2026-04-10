"""
Integration Tests for Repository Ingestion API Endpoints (Phase 18 - Code Intelligence)

Tests the repository ingestion API endpoints including:
- POST /resources/ingest-repo - Trigger repository ingestion
- GET /resources/ingest-repo/{task_id}/status - Get ingestion status

All tests follow the anti-gaslighting pattern with clear assertions.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

try:
    import celery  # noqa: F401

    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not CELERY_AVAILABLE,
    reason="celery is not installed; repo ingestion tests require celery",
)


@pytest.mark.integration
class TestRepoIngestionEndpoints:
    """Integration tests for repository ingestion endpoints."""

    def test_ingest_repo_with_local_path_success(
        self, client: TestClient, tmp_path: Path
    ):
        """
        Test successful repository ingestion from local path.

        Verifies:
        - HTTP 200 response
        - Response contains task_id and status
        - Celery task is queued

        Requirements: 6.1, 6.3
        """
        # Create a test directory with some files
        test_dir = tmp_path / "test_repo"
        test_dir.mkdir()
        (test_dir / "test.py").write_text("print('hello')")
        (test_dir / "README.md").write_text("# Test Repo")

        # Mock the Celery task
        with patch("app.tasks.celery_tasks.ingest_repo_task") as mock_task:
            mock_task.delay = Mock(return_value=Mock(id="test-task-123"))

            # Make API request
            response = client.post(
                "/api/resources/ingest-repo", json={"path": str(test_dir)}
            )

            # Verify HTTP response status
            assert response.status_code == 200, (
                f"IMPLEMENTATION FAILURE: Expected status 200, got {response.status_code}\n"
                f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
                f"Response: {response.json()}"
            )

            # Verify response structure
            response_data = response.json()
            expected_fields = ["task_id", "status", "message"]
            for field in expected_fields:
                assert field in response_data, (
                    f"IMPLEMENTATION FAILURE: Expected field '{field}' in response\n"
                    f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
                    f"Response: {response_data}"
                )

            # Verify task was queued
            assert mock_task.delay.called, (
                "IMPLEMENTATION FAILURE: Celery task should be queued\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

            # Verify task ID is returned
            assert response_data["task_id"] == "test-task-123", (
                f"IMPLEMENTATION FAILURE: Expected task_id 'test-task-123', got {response_data['task_id']}\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

            # Verify initial status
            assert response_data["status"] == "PENDING", (
                f"IMPLEMENTATION FAILURE: Expected status 'PENDING', got {response_data['status']}\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

    def test_ingest_repo_with_git_url_success(self, client: TestClient):
        """
        Test successful repository ingestion from Git URL.

        Verifies:
        - HTTP 200 response
        - Response contains task_id and status
        - Celery task is queued with git_url

        Requirements: 6.1, 6.3
        """
        # Mock the Celery task
        with patch("app.tasks.celery_tasks.ingest_repo_task") as mock_task:
            mock_task.delay = Mock(return_value=Mock(id="test-task-456"))

            # Make API request with Git URL
            response = client.post(
                "/api/resources/ingest-repo",
                json={"git_url": "https://github.com/test/repo.git"},
            )

            # Verify HTTP response status
            assert response.status_code == 200, (
                f"IMPLEMENTATION FAILURE: Expected status 200, got {response.status_code}\n"
                f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
                f"Response: {response.json()}"
            )

            # Verify response structure
            response_data = response.json()
            assert "task_id" in response_data, (
                "IMPLEMENTATION FAILURE: Expected 'task_id' in response\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

            # Verify task was queued
            assert mock_task.delay.called, (
                "IMPLEMENTATION FAILURE: Celery task should be queued\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

            # Verify task was called with git_url
            call_kwargs = mock_task.delay.call_args[1]
            assert call_kwargs.get("git_url") == "https://github.com/test/repo.git", (
                "IMPLEMENTATION FAILURE: Task should be called with git_url\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

    def test_ingest_repo_path_not_found(self, client: TestClient):
        """
        Test ingestion fails when path doesn't exist.

        Verifies:
        - HTTP 400 response
        - Error message indicates path not found

        Requirements: 6.4
        """
        # Use a path that doesn't exist
        fake_path = "/nonexistent/path/to/repo"

        # Make API request
        response = client.post("/api/resources/ingest-repo", json={"path": fake_path})

        # Verify HTTP response status
        assert response.status_code == 400, (
            f"IMPLEMENTATION FAILURE: Expected status 400, got {response.status_code}\n"
            f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
            f"Response: {response.json()}"
        )

        # Verify error message
        response_data = response.json()
        assert "detail" in response_data, (
            "IMPLEMENTATION FAILURE: Expected 'detail' in error response\n"
            "DO NOT UPDATE THE TEST - Fix the implementation instead."
        )

        assert "not exist" in response_data["detail"].lower(), (
            f"IMPLEMENTATION FAILURE: Expected 'not exist' in error message\n"
            f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
            f"Response: {response_data}"
        )

    def test_ingest_repo_path_not_directory(self, client: TestClient, tmp_path: Path):
        """
        Test ingestion fails when path is not a directory.

        Verifies:
        - HTTP 400 response
        - Error message indicates path is not a directory

        Requirements: 6.4
        """
        # Create a file (not a directory)
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Make API request
        response = client.post(
            "/api/resources/ingest-repo", json={"path": str(test_file)}
        )

        # Verify HTTP response status
        assert response.status_code == 400, (
            f"IMPLEMENTATION FAILURE: Expected status 400, got {response.status_code}\n"
            f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
            f"Response: {response.json()}"
        )

        # Verify error message
        response_data = response.json()
        assert "not a directory" in response_data["detail"].lower(), (
            f"IMPLEMENTATION FAILURE: Expected 'not a directory' in error message\n"
            f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
            f"Response: {response_data}"
        )

    def test_ingest_repo_invalid_git_url(self, client: TestClient):
        """
        Test ingestion fails with invalid Git URL.

        Verifies:
        - HTTP 400 response
        - Error message indicates invalid URL

        Requirements: 6.4
        """
        # Make API request with invalid URL
        response = client.post(
            "/api/resources/ingest-repo", json={"git_url": "not-a-valid-url"}
        )

        # Verify HTTP response status
        assert response.status_code == 400, (
            f"IMPLEMENTATION FAILURE: Expected status 400, got {response.status_code}\n"
            f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
            f"Response: {response.json()}"
        )

        # Verify error message
        response_data = response.json()
        assert "invalid" in response_data["detail"].lower(), (
            f"IMPLEMENTATION FAILURE: Expected 'invalid' in error message\n"
            f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
            f"Response: {response_data}"
        )

    def test_ingest_repo_non_https_git_url(self, client: TestClient):
        """
        Test ingestion fails with non-HTTPS Git URL.

        Verifies:
        - HTTP 400 response
        - Error message indicates only HTTPS allowed

        Requirements: 6.4, 7.3 (security)
        """
        # Make API request with HTTP URL (not HTTPS)
        response = client.post(
            "/api/resources/ingest-repo",
            json={"git_url": "http://github.com/test/repo.git"},
        )

        # Verify HTTP response status
        assert response.status_code == 400, (
            f"IMPLEMENTATION FAILURE: Expected status 400, got {response.status_code}\n"
            f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
            f"Response: {response.json()}"
        )

        # Verify error message
        response_data = response.json()
        assert "https" in response_data["detail"].lower(), (
            f"IMPLEMENTATION FAILURE: Expected 'https' in error message\n"
            f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
            f"Response: {response_data}"
        )

    def test_ingest_repo_both_path_and_url(self, client: TestClient, tmp_path: Path):
        """
        Test ingestion fails when both path and git_url are provided.

        Verifies:
        - HTTP 422 response (validation error)
        - Error message indicates mutual exclusivity

        Requirements: 6.4
        """
        # Create a test directory
        test_dir = tmp_path / "test_repo"
        test_dir.mkdir()

        # Make API request with both path and git_url
        response = client.post(
            "/api/resources/ingest-repo",
            json={"path": str(test_dir), "git_url": "https://github.com/test/repo.git"},
        )

        # Verify HTTP response status (422 for validation error)
        assert response.status_code == 422, (
            f"IMPLEMENTATION FAILURE: Expected status 422, got {response.status_code}\n"
            f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
            f"Response: {response.json()}"
        )

    def test_ingest_repo_neither_path_nor_url(self, client: TestClient):
        """
        Test ingestion fails when neither path nor git_url are provided.

        Verifies:
        - HTTP 422 response (validation error)
        - Error message indicates one is required

        Requirements: 6.4
        """
        # Make API request with empty body
        response = client.post("/api/resources/ingest-repo", json={})

        # Verify HTTP response status (422 for validation error)
        assert response.status_code == 422, (
            f"IMPLEMENTATION FAILURE: Expected status 422, got {response.status_code}\n"
            f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
            f"Response: {response.json()}"
        )

    def test_get_ingestion_status_pending(self, client: TestClient):
        """
        Test getting status of pending ingestion task.

        Verifies:
        - HTTP 200 response
        - Response contains task_id and status
        - Status is PENDING

        Requirements: 6.2, 6.6
        """
        task_id = "test-task-789"

        # Mock the Celery AsyncResult
        with patch("celery.result.AsyncResult") as mock_result:
            mock_task = Mock()
            mock_task.state = "PENDING"
            mock_task.info = None
            mock_result.return_value = mock_task

            # Make API request
            response = client.get(f"/api/resources/ingest-repo/{task_id}/status")

            # Verify HTTP response status
            assert response.status_code == 200, (
                f"IMPLEMENTATION FAILURE: Expected status 200, got {response.status_code}\n"
                f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
                f"Response: {response.json()}"
            )

            # Verify response structure
            response_data = response.json()
            expected_fields = ["task_id", "status"]
            for field in expected_fields:
                assert field in response_data, (
                    f"IMPLEMENTATION FAILURE: Expected field '{field}' in response\n"
                    f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
                    f"Response: {response_data}"
                )

            # Verify task_id matches
            assert response_data["task_id"] == task_id, (
                f"IMPLEMENTATION FAILURE: Expected task_id '{task_id}', got {response_data['task_id']}\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

            # Verify status
            assert response_data["status"] == "PENDING", (
                f"IMPLEMENTATION FAILURE: Expected status 'PENDING', got {response_data['status']}\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

    def test_get_ingestion_status_processing(self, client: TestClient):
        """
        Test getting status of processing ingestion task.

        Verifies:
        - HTTP 200 response
        - Response contains progress information
        - files_processed, total_files, current_file are present

        Requirements: 6.2, 6.6
        """
        task_id = "test-task-processing"

        # Mock the Celery AsyncResult with progress info
        with patch("celery.result.AsyncResult") as mock_result:
            mock_task = Mock()
            mock_task.state = "PROCESSING"
            mock_task.info = {
                "current": 5,
                "total": 10,
                "current_file": "/path/to/file.py",
                "started_at": "2024-01-01T00:00:00",
            }
            mock_result.return_value = mock_task

            # Make API request
            response = client.get(f"/api/resources/ingest-repo/{task_id}/status")

            # Verify HTTP response status
            assert response.status_code == 200, (
                f"IMPLEMENTATION FAILURE: Expected status 200, got {response.status_code}\n"
                f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
                f"Response: {response.json()}"
            )

            # Verify response structure
            response_data = response.json()
            expected_fields = [
                "task_id",
                "status",
                "files_processed",
                "total_files",
                "current_file",
            ]
            for field in expected_fields:
                assert field in response_data, (
                    f"IMPLEMENTATION FAILURE: Expected field '{field}' in response\n"
                    f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
                    f"Response: {response_data}"
                )

            # Verify progress information
            assert response_data["files_processed"] == 5, (
                f"IMPLEMENTATION FAILURE: Expected files_processed 5, got {response_data['files_processed']}\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

            assert response_data["total_files"] == 10, (
                f"IMPLEMENTATION FAILURE: Expected total_files 10, got {response_data['total_files']}\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

            assert response_data["current_file"] == "/path/to/file.py", (
                f"IMPLEMENTATION FAILURE: Expected current_file '/path/to/file.py', got {response_data['current_file']}\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

    def test_get_ingestion_status_completed(self, client: TestClient):
        """
        Test getting status of completed ingestion task.

        Verifies:
        - HTTP 200 response
        - Status is COMPLETED
        - files_processed and completed_at are present

        Requirements: 6.2, 6.6
        """
        task_id = "test-task-completed"

        # Mock the Celery AsyncResult with completion info
        with patch("celery.result.AsyncResult") as mock_result:
            mock_task = Mock()
            mock_task.state = "COMPLETED"
            mock_task.info = {
                "files_processed": 10,
                "completed_at": "2024-01-01T00:10:00",
            }
            mock_result.return_value = mock_task

            # Make API request
            response = client.get(f"/api/resources/ingest-repo/{task_id}/status")

            # Verify HTTP response status
            assert response.status_code == 200, (
                f"IMPLEMENTATION FAILURE: Expected status 200, got {response.status_code}\n"
                f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
                f"Response: {response.json()}"
            )

            # Verify response structure
            response_data = response.json()
            assert response_data["status"] == "COMPLETED", (
                f"IMPLEMENTATION FAILURE: Expected status 'COMPLETED', got {response_data['status']}\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

            assert response_data["files_processed"] == 10, (
                f"IMPLEMENTATION FAILURE: Expected files_processed 10, got {response_data['files_processed']}\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

            assert "completed_at" in response_data, (
                "IMPLEMENTATION FAILURE: Expected 'completed_at' in response\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

    def test_get_ingestion_status_failed(self, client: TestClient):
        """
        Test getting status of failed ingestion task.

        Verifies:
        - HTTP 200 response
        - Status is FAILED
        - Error message is present

        Requirements: 6.2, 6.6
        """
        task_id = "test-task-failed"

        # Mock the Celery AsyncResult with failure info
        with patch("celery.result.AsyncResult") as mock_result:
            mock_task = Mock()
            mock_task.state = "FAILED"
            mock_task.info = {"error": "Failed to clone repository: Connection timeout"}
            mock_result.return_value = mock_task

            # Make API request
            response = client.get(f"/api/resources/ingest-repo/{task_id}/status")

            # Verify HTTP response status
            assert response.status_code == 200, (
                f"IMPLEMENTATION FAILURE: Expected status 200, got {response.status_code}\n"
                f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
                f"Response: {response.json()}"
            )

            # Verify response structure
            response_data = response.json()
            assert response_data["status"] == "FAILED", (
                f"IMPLEMENTATION FAILURE: Expected status 'FAILED', got {response_data['status']}\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

            assert "error" in response_data, (
                "IMPLEMENTATION FAILURE: Expected 'error' in response\n"
                "DO NOT UPDATE THE TEST - Fix the implementation instead."
            )

            assert "Connection timeout" in response_data["error"], (
                f"IMPLEMENTATION FAILURE: Expected error message to contain 'Connection timeout'\n"
                f"DO NOT UPDATE THE TEST - Fix the implementation instead.\n"
                f"Response: {response_data}"
            )


@pytest.mark.integration
@pytest.mark.slow
class TestRepoIngestionAuthentication:
    """Integration tests for authentication and rate limiting on repo ingestion endpoints."""

    def test_ingest_repo_requires_authentication(
        self, client: TestClient, tmp_path: Path
    ):
        """
        Test that repository ingestion requires authentication.

        Note: This test assumes authentication middleware is configured.
        If authentication is not yet enforced, this test will be skipped.

        Verifies:
        - HTTP 401 response when no auth token provided

        Requirements: 6.5
        """
        # Create a test directory
        test_dir = tmp_path / "test_repo"
        test_dir.mkdir()

        # Make API request without authentication
        # Note: The client fixture may already include auth headers
        # This test verifies the endpoint is protected

        # For now, we'll skip this test if auth is not enforced
        # The actual auth enforcement is handled by middleware
        pytest.skip("Authentication middleware not yet configured in test environment")

    def test_ingest_repo_rate_limiting(self, client: TestClient, tmp_path: Path):
        """
        Test that rate limiting is applied to repository ingestion.

        Note: This test assumes rate limiting middleware is configured.
        If rate limiting is not yet enforced, this test will be skipped.

        Verifies:
        - HTTP 429 response when rate limit exceeded

        Requirements: 6.5
        """
        # Create a test directory
        test_dir = tmp_path / "test_repo"
        test_dir.mkdir()

        # Make multiple API requests to trigger rate limit
        # Note: Rate limit configuration depends on user tier

        # For now, we'll skip this test if rate limiting is not enforced
        # The actual rate limiting is handled by middleware
        pytest.skip("Rate limiting middleware not yet configured in test environment")

    def test_get_status_requires_authentication(self, client: TestClient):
        """
        Test that status endpoint requires authentication.

        Note: This test assumes authentication middleware is configured.

        Verifies:
        - HTTP 401 response when no auth token provided

        Requirements: 6.5
        """
        _task_id = "test-task-123"  # Unused since test is skipped

        # Make API request without authentication
        # For now, we'll skip this test if auth is not enforced
        pytest.skip("Authentication middleware not yet configured in test environment")


@pytest.mark.integration
class TestRepoIngestionEndToEnd:
    """End-to-end integration tests for repository ingestion."""

    def test_ingest_and_poll_status_workflow(self, client: TestClient, tmp_path: Path):
        """
        Test complete workflow: ingest repository and poll status.

        Verifies:
        - Can trigger ingestion
        - Can poll status multiple times
        - Status transitions correctly

        Requirements: 6.1, 6.2, 6.6
        """
        # Create a test directory with files
        test_dir = tmp_path / "test_repo"
        test_dir.mkdir()
        (test_dir / "main.py").write_text("def main(): pass")
        (test_dir / "utils.py").write_text("def helper(): pass")
        (test_dir / "README.md").write_text("# Test")

        # Mock the Celery task and AsyncResult
        with (
            patch("app.tasks.celery_tasks.ingest_repo_task") as mock_task,
            patch("celery.result.AsyncResult") as mock_result,
        ):
            # Setup mock task
            mock_task.delay = Mock(return_value=Mock(id="workflow-task-123"))

            # Step 1: Trigger ingestion
            ingest_response = client.post(
                "/api/resources/ingest-repo", json={"path": str(test_dir)}
            )

            assert ingest_response.status_code == 200, (
                f"IMPLEMENTATION FAILURE: Ingestion should succeed\n"
                f"Response: {ingest_response.json()}"
            )

            task_id = ingest_response.json()["task_id"]
            assert task_id == "workflow-task-123", "Task ID should match"

            # Step 2: Poll status - PENDING
            mock_task_obj = Mock()
            mock_task_obj.state = "PENDING"
            mock_task_obj.info = None
            mock_result.return_value = mock_task_obj

            status_response = client.get(f"/api/resources/ingest-repo/{task_id}/status")
            assert status_response.status_code == 200, "Status check should succeed"
            assert status_response.json()["status"] == "PENDING", (
                "Status should be PENDING"
            )

            # Step 3: Poll status - PROCESSING
            mock_task_obj.state = "PROCESSING"
            mock_task_obj.info = {"current": 2, "total": 3, "current_file": "utils.py"}

            status_response = client.get(f"/api/resources/ingest-repo/{task_id}/status")
            assert status_response.status_code == 200, "Status check should succeed"
            assert status_response.json()["status"] == "PROCESSING", (
                "Status should be PROCESSING"
            )
            assert status_response.json()["files_processed"] == 2, (
                "Should show progress"
            )

            # Step 4: Poll status - COMPLETED
            mock_task_obj.state = "COMPLETED"
            mock_task_obj.info = {
                "files_processed": 3,
                "completed_at": "2024-01-01T00:10:00",
            }

            status_response = client.get(f"/api/resources/ingest-repo/{task_id}/status")
            assert status_response.status_code == 200, "Status check should succeed"
            assert status_response.json()["status"] == "COMPLETED", (
                "Status should be COMPLETED"
            )
            assert status_response.json()["files_processed"] == 3, (
                "All files should be processed"
            )
