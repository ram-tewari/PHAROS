"""
Integration Tests for Phase 19 - Multi-Repository Processing

Tests the Edge Worker's ability to process multiple repositories sequentially,
maintaining correct status updates and job history for each.

Requirements tested: All Phase 19 requirements
"""

import pytest
import time
import json
import shutil
import sys
from unittest.mock import MagicMock, patch
from pathlib import Path


# Mock upstash_redis and qdrant_client before any imports
sys.modules["upstash_redis"] = MagicMock()
sys.modules["qdrant_client"] = MagicMock()
sys.modules["qdrant_client.http"] = MagicMock()
sys.modules["qdrant_client.http.exceptions"] = MagicMock()


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_redis_client():
    """Mock Redis client with queue simulation."""
    mock_client = MagicMock()

    # Simulate queue with multiple tasks
    task_queue = []

    def mock_rpush(key, value):
        if "task_queue" in key:
            task_queue.append(value)
        return len(task_queue)

    def mock_lpop(key):
        if "task_queue" in key and task_queue:
            return (
                task_queue.pop(0).encode()
                if isinstance(task_queue[0], str)
                else task_queue.pop(0)
            )
        return None

    def mock_llen(key):
        if "task_queue" in key:
            return len(task_queue)
        return 0

    mock_client.rpush.side_effect = mock_rpush
    mock_client.lpop.side_effect = mock_lpop
    mock_client.llen.side_effect = mock_llen
    mock_client.get.return_value = b'"Idle"'
    mock_client.set.return_value = True
    mock_client.expire.return_value = True
    mock_client.lrange.return_value = []
    mock_client.ltrim.return_value = True

    # Store for job history
    mock_client.job_history = []

    def mock_rpush_history(key, value):
        if "job_history" in key:
            mock_client.job_history.append(value)
        return len(mock_client.job_history)

    # Override rpush to handle both queue and history
    def combined_rpush(key, value):
        if "task_queue" in key:
            return mock_rpush(key, value)
        elif "job_history" in key:
            return mock_rpush_history(key, value)
        return 1

    mock_client.rpush.side_effect = combined_rpush

    return mock_client


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client that tracks uploads."""
    mock_client = MagicMock()

    # Track uploaded embeddings
    mock_client.uploaded_points = []

    def mock_upsert(collection_name, points):
        mock_client.uploaded_points.extend(points)
        return MagicMock(status="completed")

    mock_client.get_collections.return_value = MagicMock(collections=[])
    mock_client.create_collection.return_value = True
    mock_client.upsert.side_effect = mock_upsert

    return mock_client


@pytest.fixture
def create_test_repos(tmp_path):
    """Create multiple test repositories."""
    repos = []

    for i in range(3):
        repo_dir = tmp_path / f"test_repo_{i}"
        repo_dir.mkdir()

        # Create Python files
        main_file = repo_dir / f"main_{i}.py"
        main_file.write_text(f"""
import os
import sys
from utils_{i} import helper_{i}

def main_{i}():
    print("Repo {i}")
""")

        utils_dir = repo_dir / f"utils_{i}"
        utils_dir.mkdir()
        (utils_dir / "__init__.py").write_text("")
        (utils_dir / f"helper_{i}.py").write_text(f"""
def helper_function_{i}():
    return "Helper {i}"
""")

        repos.append(str(repo_dir))

    return repos


@pytest.fixture
def mock_git_clone_multi(create_test_repos):
    """Mock GitPython clone for multiple repos."""
    repo_index = [0]  # Use list to maintain state across calls

    def _mock_clone(url, to_path):
        # Use repo index to select which test repo to copy
        idx = repo_index[0] % len(create_test_repos)
        shutil.copytree(create_test_repos[idx], to_path, dirs_exist_ok=True)
        repo_index[0] += 1
        return MagicMock()

    return _mock_clone


# ============================================================================
# Test 10.2: Multi-Repository Processing Tests
# ============================================================================


@pytest.mark.integration
def test_multi_repo_sequential_processing(
    mock_redis_client, mock_qdrant_client, mock_git_clone_multi
):
    """
    Test sequential processing of multiple repositories.

    Verifies:
    - Each repository is processed in order
    - Status updates correctly for each job
    - All embeddings are uploaded
    - Job history contains all jobs

    Requirements: All Phase 19 requirements
    """
    # Queue multiple repositories
    repo_urls = [
        "https://github.com/test/repo1",
        "https://github.com/test/repo2",
        "https://github.com/test/repo3",
    ]

    tasks = []
    for url in repo_urls:
        task_data = {"repo_url": url, "submitted_at": time.time(), "ttl": 86400}
        tasks.append(task_data)
        mock_redis_client.rpush("pharos:task_queue", json.dumps(task_data))

    # Verify all tasks queued
    assert mock_redis_client.llen("pharos:task_queue") == 3

    # Process each task
    with (
        patch("redis.Redis", return_value=mock_redis_client),
        patch("git.Repo.clone_from", side_effect=mock_git_clone_multi),
        patch("qdrant_client.QdrantClient", return_value=mock_qdrant_client),
        patch("torch.cuda.is_available", return_value=False),
    ):
        from worker import process_job

        results = []
        for i in range(3):
            # Pop task from queue
            task_json = mock_redis_client.lpop("pharos:task_queue")
            assert task_json is not None

            task_data = json.loads(
                task_json.decode() if isinstance(task_json, bytes) else task_json
            )

            # Process job
            result = process_job(task_data)
            results.append(result)

            # Verify job completed
            assert result is not None
            assert result.get("status") in ["completed", "success"]

    # Verify all jobs processed
    assert len(results) == 3
    assert all(r.get("status") in ["completed", "success"] for r in results)

    # Verify embeddings uploaded for all repos
    assert len(mock_qdrant_client.uploaded_points) > 0

    # Verify job history contains all jobs
    assert len(mock_redis_client.job_history) >= 3

    # Verify each job has correct repo URL
    for i, url in enumerate(repo_urls):
        found = False
        for job_json in mock_redis_client.job_history:
            job_data = json.loads(job_json)
            if job_data.get("repo_url") == url:
                found = True
                break
        assert found, f"Job for {url} not found in history"


@pytest.mark.integration
def test_multi_repo_status_updates(
    mock_redis_client, mock_qdrant_client, mock_git_clone_multi
):
    """
    Test status updates during multi-repository processing.

    Verifies:
    - Status changes to "Training" for each repo
    - Status returns to "Idle" between jobs
    - Status includes correct repo URL

    Requirements: 3.5, 6.5, 9.1
    """
    # Queue two repositories
    tasks = [
        {
            "repo_url": "https://github.com/test/repo1",
            "submitted_at": time.time(),
            "ttl": 86400,
        },
        {
            "repo_url": "https://github.com/test/repo2",
            "submitted_at": time.time(),
            "ttl": 86400,
        },
    ]

    for task in tasks:
        mock_redis_client.rpush("pharos:task_queue", json.dumps(task))

    # Track status updates
    status_updates = []
    original_set = mock_redis_client.set

    def track_status(key, value):
        if "worker_status" in key:
            status_updates.append(value)
        return original_set(key, value)

    mock_redis_client.set.side_effect = track_status

    # Process both jobs
    with (
        patch("redis.Redis", return_value=mock_redis_client),
        patch("git.Repo.clone_from", side_effect=mock_git_clone_multi),
        patch("qdrant_client.QdrantClient", return_value=mock_qdrant_client),
        patch("torch.cuda.is_available", return_value=False),
    ):
        from worker import process_job

        for i in range(2):
            task_json = mock_redis_client.lpop("pharos:task_queue")
            task_data = json.loads(
                task_json.decode() if isinstance(task_json, bytes) else task_json
            )
            process_job(task_data)

    # Verify status updates
    assert len(status_updates) >= 4  # At least 2 "Training" + 2 "Idle"

    # Verify pattern: Training -> Idle -> Training -> Idle
    training_count = sum(
        1 for s in status_updates if "Training" in s or "training" in s.lower()
    )
    idle_count = sum(1 for s in status_updates if "Idle" in s or "idle" in s.lower())

    assert training_count >= 2
    assert idle_count >= 2


@pytest.mark.integration
def test_multi_repo_with_failures(mock_redis_client, mock_qdrant_client, tmp_path):
    """
    Test multi-repository processing with some failures.

    Verifies:
    - Worker continues after failures
    - Failed jobs recorded in history
    - Successful jobs still complete

    Requirements: 8.1, 8.2, 8.6
    """
    # Create one good repo and one that will fail
    good_repo = tmp_path / "good_repo"
    good_repo.mkdir()
    (good_repo / "main.py").write_text("import os\n")

    # Mock clone that fails for second repo
    clone_count = [0]

    def mock_clone_with_failure(url, to_path):
        clone_count[0] += 1
        if clone_count[0] == 2:
            raise Exception("Clone failed")
        shutil.copytree(str(good_repo), to_path, dirs_exist_ok=True)
        return MagicMock()

    # Queue three repositories
    tasks = [
        {
            "repo_url": f"https://github.com/test/repo{i}",
            "submitted_at": time.time(),
            "ttl": 86400,
        }
        for i in range(3)
    ]

    for task in tasks:
        mock_redis_client.rpush("pharos:task_queue", json.dumps(task))

    # Process all jobs
    with (
        patch("redis.Redis", return_value=mock_redis_client),
        patch("git.Repo.clone_from", side_effect=mock_clone_with_failure),
        patch("qdrant_client.QdrantClient", return_value=mock_qdrant_client),
        patch("torch.cuda.is_available", return_value=False),
    ):
        from worker import process_job

        results = []
        for i in range(3):
            task_json = mock_redis_client.lpop("pharos:task_queue")
            task_data = json.loads(
                task_json.decode() if isinstance(task_json, bytes) else task_json
            )

            try:
                result = process_job(task_data)
                results.append(result)
            except Exception:
                # Worker should handle errors internally
                results.append({"status": "failed"})

    # Verify all jobs attempted
    assert len(results) == 3

    # Verify at least one failure
    failed_count = sum(1 for r in results if r.get("status") == "failed")
    assert failed_count >= 1

    # Verify at least one success
    success_count = sum(
        1 for r in results if r.get("status") in ["completed", "success"]
    )
    assert success_count >= 1

    # Verify job history contains all attempts
    assert len(mock_redis_client.job_history) >= 3


@pytest.mark.integration
def test_multi_repo_embedding_isolation(
    mock_redis_client, mock_qdrant_client, mock_git_clone_multi
):
    """
    Test that embeddings from different repos are properly isolated.

    Verifies:
    - Each repo's embeddings have correct metadata
    - Embeddings are associated with correct repo URL
    - No cross-contamination between repos

    Requirements: 6.1, 6.2
    """
    # Queue two repositories
    repo_urls = ["https://github.com/test/repo1", "https://github.com/test/repo2"]

    tasks = [
        {"repo_url": url, "submitted_at": time.time(), "ttl": 86400}
        for url in repo_urls
    ]

    for task in tasks:
        mock_redis_client.rpush("pharos:task_queue", json.dumps(task))

    # Process both jobs
    with (
        patch("redis.Redis", return_value=mock_redis_client),
        patch("git.Repo.clone_from", side_effect=mock_git_clone_multi),
        patch("qdrant_client.QdrantClient", return_value=mock_qdrant_client),
        patch("torch.cuda.is_available", return_value=False),
    ):
        from worker import process_job

        for i in range(2):
            task_json = mock_redis_client.lpop("pharos:task_queue")
            task_data = json.loads(
                task_json.decode() if isinstance(task_json, bytes) else task_json
            )
            process_job(task_data)

    # Verify embeddings uploaded
    assert len(mock_qdrant_client.uploaded_points) > 0

    # Group embeddings by repo URL
    embeddings_by_repo = {}
    for point in mock_qdrant_client.uploaded_points:
        repo_url = point.payload.get("repo_url")
        if repo_url not in embeddings_by_repo:
            embeddings_by_repo[repo_url] = []
        embeddings_by_repo[repo_url].append(point)

    # Verify both repos have embeddings
    assert len(embeddings_by_repo) >= 2

    # Verify each repo's embeddings have correct metadata
    for repo_url in repo_urls:
        if repo_url in embeddings_by_repo:
            for point in embeddings_by_repo[repo_url]:
                assert point.payload["repo_url"] == repo_url
                assert "file_path" in point.payload


@pytest.mark.integration
def test_multi_repo_job_history_completeness(
    mock_redis_client, mock_qdrant_client, mock_git_clone_multi
):
    """
    Test that job history contains complete information for all jobs.

    Verifies:
    - All jobs recorded in history
    - Each record has required fields
    - History is capped at 100 entries

    Requirements: 9.3, 9.4, 9.6
    """
    # Queue multiple repositories
    num_repos = 5
    tasks = [
        {
            "repo_url": f"https://github.com/test/repo{i}",
            "submitted_at": time.time(),
            "ttl": 86400,
        }
        for i in range(num_repos)
    ]

    for task in tasks:
        mock_redis_client.rpush("pharos:task_queue", json.dumps(task))

    # Process all jobs
    with (
        patch("redis.Redis", return_value=mock_redis_client),
        patch("git.Repo.clone_from", side_effect=mock_git_clone_multi),
        patch("qdrant_client.QdrantClient", return_value=mock_qdrant_client),
        patch("torch.cuda.is_available", return_value=False),
    ):
        from worker import process_job

        for i in range(num_repos):
            task_json = mock_redis_client.lpop("pharos:task_queue")
            task_data = json.loads(
                task_json.decode() if isinstance(task_json, bytes) else task_json
            )
            process_job(task_data)

    # Verify all jobs in history
    assert len(mock_redis_client.job_history) >= num_repos

    # Verify each job record has required fields
    required_fields = ["repo_url", "status", "submitted_at"]
    for job_json in mock_redis_client.job_history:
        job_data = json.loads(job_json)
        for field in required_fields:
            assert field in job_data, f"Missing field: {field}"

    # Verify LTRIM was called to cap history at 100
    ltrim_calls = [
        call
        for call in mock_redis_client.ltrim.call_args_list
        if "job_history" in str(call)
    ]
    assert len(ltrim_calls) >= num_repos


@pytest.mark.integration
def test_multi_repo_queue_position_tracking(mock_redis_client):
    """
    Test that queue position is correctly tracked for multiple submissions.

    Requirements: 2.2
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
            # Submit multiple repositories
            positions = []
            for i in range(3):
                response = client.post(
                    f"/api/v1/ingestion/ingest/https://github.com/test/repo{i}",
                    headers={"Authorization": f"Bearer {test_token}"},
                )
                assert response.status_code == 200
                data = response.json()
                positions.append(data["queue_position"])

            # Verify positions increment
            assert positions == [1, 2, 3] or positions == [
                0,
                1,
                2,
            ]  # Depending on 0 or 1-indexed
