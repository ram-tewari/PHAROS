"""
Property-based tests for Edge Worker.

These tests verify universal properties that should hold across all
valid executions of the edge worker.

Requirements: 3.5, 3.7, 6.5, 9.1, 9.3, 9.4, 9.6
"""

import pytest
import json
import sys
import os
import time
from datetime import datetime, timedelta
from hypothesis import given, strategies as st, settings
from unittest.mock import Mock, patch, MagicMock, create_autospec
import torch

# Mock upstash_redis before importing worker
sys.modules["upstash_redis"] = MagicMock()

# Import worker components
from worker import EdgeWorker


@pytest.fixture(autouse=True)
def mock_redis_env_vars():
    """Mock Redis environment variables for all tests."""
    with patch.dict(
        os.environ,
        {
            "UPSTASH_REDIS_REST_URL": "https://test-redis.upstash.io",
            "UPSTASH_REDIS_REST_TOKEN": "test-token",
        },
    ):
        yield


# Hypothesis strategies for generating test data
@st.composite
def valid_task_data(draw):
    """Generate valid task data for testing."""
    repo_url = draw(
        st.sampled_from(
            [
                "github.com/user/repo1",
                "github.com/user/repo2",
                "gitlab.com/org/project",
                "bitbucket.org/team/code",
            ]
        )
    )

    # Generate timestamp within last hour
    now = datetime.now()
    submitted_at = now - timedelta(
        seconds=draw(st.integers(min_value=0, max_value=3600))
    )

    return {
        "repo_url": repo_url,
        "submitted_at": submitted_at.isoformat(),
        "ttl": draw(st.integers(min_value=3600, max_value=86400)),
    }


@st.composite
def stale_task_data(draw):
    """Generate stale task data (older than TTL)."""
    repo_url = draw(
        st.sampled_from(["github.com/user/old-repo", "gitlab.com/org/legacy"])
    )

    # Generate old timestamp (beyond TTL)
    ttl = draw(st.integers(min_value=3600, max_value=86400))
    now = datetime.now()
    submitted_at = now - timedelta(
        seconds=ttl + draw(st.integers(min_value=1, max_value=3600))
    )

    return {"repo_url": repo_url, "submitted_at": submitted_at.isoformat(), "ttl": ttl}


class TestEdgeWorkerProperties:
    """Property-based tests for edge worker."""

    @pytest.mark.property
    @pytest.mark.feature("phase19-hybrid-edge-cloud-orchestration")
    @given(task_data=valid_task_data())
    @settings(max_examples=10, deadline=None)
    def test_property_2_worker_status_consistency(self, task_data):
        """
        Property 2: Worker status consistency

        For any job processed by the Edge Worker, the worker status in Redis
        should transition from "Idle" → "Training Graph on {repo}" → "Idle"
        (or "Error: {message}").

        Validates: Requirements 3.5, 6.5
        """
        # Mock Redis client
        mock_redis = Mock()
        mock_redis.lpush.return_value = None
        mock_redis.ltrim.return_value = None
        mock_redis.set.return_value = None

        # Mock parser and neural service
        mock_parser = Mock()
        mock_parser.clone_repository.return_value = "/tmp/test_repo"
        mock_parser.build_dependency_graph.return_value = Mock(
            edge_index=torch.tensor([[0, 1], [1, 0]]),
            num_nodes=2,
            file_paths=["file1.py", "file2.py"],
        )
        mock_parser.cleanup.return_value = None

        mock_neural = Mock()
        mock_neural.train_embeddings.return_value = torch.randn(2, 64)
        mock_neural.upload_embeddings.return_value = None

        # Create worker with mocked dependencies
        with (
            patch("worker.Redis", return_value=mock_redis),
            patch("worker.RepositoryParser", return_value=mock_parser),
            patch("worker.NeuralGraphService", return_value=mock_neural),
            patch("worker.torch.cuda.is_available", return_value=False),
        ):
            worker = EdgeWorker()

            # Inject the mocks after initialization
            worker.redis = mock_redis
            worker.parser = mock_parser
            worker.neural_service = mock_neural

            # Reset mock to clear initialization calls
            mock_redis.set.reset_mock()

            # Process job
            worker.process_job(task_data)

        # Extract status updates from mock calls
        status_updates = [
            call.args[1]
            for call in mock_redis.set.call_args_list
            if len(call.args) >= 2 and call.args[0] == "worker_status"
        ]

        # Verify status transitions (should have at least 2: Training -> Idle)
        assert len(status_updates) >= 2, (
            f"Should have at least 2 status updates, got {len(status_updates)}: {status_updates}"
        )

        # First update: Training
        assert status_updates[0].startswith("Training Graph on"), (
            f"First status should be Training, got: {status_updates[0]}"
        )
        assert task_data["repo_url"] in status_updates[0]

        # Last update: Idle or Error
        final_status = status_updates[-1]
        assert final_status == "Idle" or final_status.startswith("Error:"), (
            f"Final status should be Idle or Error, got: {final_status}"
        )

    @pytest.mark.property
    @pytest.mark.feature("phase19-hybrid-edge-cloud-orchestration")
    @given(task_data=valid_task_data())
    @settings(max_examples=10, deadline=None)
    def test_property_9_job_history_record_completeness(self, task_data):
        """
        Property 9: Job history record completeness

        For any completed job, the job history record should contain
        repo_url, status, duration_seconds, files_processed,
        embeddings_generated, and timestamp fields.

        Validates: Requirements 9.3, 9.4
        """
        # Mock Redis client
        mock_redis = Mock()
        job_records = []

        def capture_job_record(key, value):
            if key == "job_history":
                job_records.append(json.loads(value))

        mock_redis.lpush.side_effect = capture_job_record
        mock_redis.ltrim.return_value = None
        mock_redis.set.return_value = None

        # Mock parser and neural service
        mock_parser = Mock()
        mock_parser.clone_repository.return_value = "/tmp/test_repo"
        mock_parser.build_dependency_graph.return_value = Mock(
            edge_index=torch.tensor([[0, 1], [1, 0]]),
            num_nodes=2,
            file_paths=["file1.py", "file2.py"],
        )
        mock_parser.cleanup.return_value = None

        mock_neural = Mock()
        mock_neural.train_embeddings.return_value = torch.randn(2, 64)
        mock_neural.upload_embeddings.return_value = None

        # Create worker with mocked dependencies
        with (
            patch("worker.Redis", return_value=mock_redis),
            patch("worker.RepositoryParser", return_value=mock_parser),
            patch("worker.NeuralGraphService", return_value=mock_neural),
            patch("worker.torch.cuda.is_available", return_value=False),
        ):
            worker = EdgeWorker()
            # Inject the mock redis after initialization
            worker.redis = mock_redis
            worker.parser = mock_parser
            worker.neural_service = mock_neural

            # Process job
            worker.process_job(task_data)

        # Verify job record completeness
        assert len(job_records) > 0, "Should have at least one job record"

        job_record = job_records[0]

        # Check all required fields are present
        required_fields = [
            "repo_url",
            "status",
            "duration_seconds",
            "files_processed",
            "embeddings_generated",
            "timestamp",
        ]

        for field in required_fields:
            assert field in job_record, f"Job record missing required field: {field}"

        # Verify field types and values
        assert isinstance(job_record["repo_url"], str)
        assert job_record["status"] in ["complete", "failed", "skipped"]
        assert isinstance(job_record["duration_seconds"], (int, float))
        assert isinstance(job_record["files_processed"], int)
        assert isinstance(job_record["embeddings_generated"], int)
        assert isinstance(job_record["timestamp"], str)

        # Verify timestamp is valid ISO format
        datetime.fromisoformat(job_record["timestamp"])

    @pytest.mark.property
    @pytest.mark.feature("phase19-hybrid-edge-cloud-orchestration")
    @given(num_jobs=st.integers(min_value=101, max_value=200))
    @settings(max_examples=10, deadline=None)
    def test_property_10_job_history_size_cap(self, num_jobs):
        """
        Property 10: Job history size cap

        For any sequence of more than 100 jobs, the job_history list in Redis
        should contain exactly 100 entries (the most recent ones).

        Validates: Requirements 9.6
        """
        # Mock Redis client
        mock_redis = Mock()
        ltrim_calls = []

        def capture_ltrim(key, start, end):
            if key == "job_history":
                ltrim_calls.append((start, end))

        mock_redis.lpush.return_value = None
        mock_redis.ltrim.side_effect = capture_ltrim
        mock_redis.set.return_value = None

        # Mock parser and neural service
        mock_parser = Mock()
        mock_parser.clone_repository.return_value = "/tmp/test_repo"
        mock_parser.build_dependency_graph.return_value = Mock(
            edge_index=torch.tensor([[0, 1], [1, 0]]),
            num_nodes=2,
            file_paths=["file1.py", "file2.py"],
        )
        mock_parser.cleanup.return_value = None

        mock_neural = Mock()
        mock_neural.train_embeddings.return_value = torch.randn(2, 64)
        mock_neural.upload_embeddings.return_value = None

        # Create worker with mocked dependencies
        with (
            patch("worker.Redis", return_value=mock_redis),
            patch("worker.RepositoryParser", return_value=mock_parser),
            patch("worker.NeuralGraphService", return_value=mock_neural),
            patch("worker.torch.cuda.is_available", return_value=False),
        ):
            worker = EdgeWorker()
            # Inject the mock redis after initialization
            worker.redis = mock_redis
            worker.parser = mock_parser
            worker.neural_service = mock_neural

            # Process multiple jobs
            for i in range(num_jobs):
                task_data = {
                    "repo_url": f"github.com/user/repo{i}",
                    "submitted_at": datetime.now().isoformat(),
                    "ttl": 86400,
                }
                worker.process_job(task_data)

        # Verify LTRIM was called to cap at 100 entries
        assert len(ltrim_calls) == num_jobs, "LTRIM should be called for each job"

        # Verify all LTRIM calls cap at 100 entries (0 to 99)
        for start, end in ltrim_calls:
            assert start == 0, "LTRIM should start at index 0"
            assert end == 99, "LTRIM should end at index 99 (100 entries)"

    @pytest.mark.property
    @pytest.mark.feature("phase19-hybrid-edge-cloud-orchestration")
    @given(task_data=valid_task_data())
    @settings(max_examples=10, deadline=None)
    def test_property_11_status_format_validation(self, task_data):
        """
        Property 11: Status format validation

        For any worker status update, the status string should match one of
        the patterns: "Idle", "Training Graph on {repo_url}", or "Error: {error_message}".

        Validates: Requirements 9.1
        """
        # Mock Redis client
        mock_redis = Mock()
        mock_redis.lpush.return_value = None
        mock_redis.ltrim.return_value = None
        mock_redis.set.return_value = None

        # Mock parser and neural service
        mock_parser = Mock()
        mock_parser.clone_repository.return_value = "/tmp/test_repo"
        mock_parser.build_dependency_graph.return_value = Mock(
            edge_index=torch.tensor([[0, 1], [1, 0]]),
            num_nodes=2,
            file_paths=["file1.py", "file2.py"],
        )
        mock_parser.cleanup.return_value = None

        mock_neural = Mock()
        mock_neural.train_embeddings.return_value = torch.randn(2, 64)
        mock_neural.upload_embeddings.return_value = None

        # Create worker with mocked dependencies
        with (
            patch("worker.Redis", return_value=mock_redis),
            patch("worker.RepositoryParser", return_value=mock_parser),
            patch("worker.NeuralGraphService", return_value=mock_neural),
            patch("worker.torch.cuda.is_available", return_value=False),
        ):
            worker = EdgeWorker()

            # Inject the mocks after initialization
            worker.redis = mock_redis
            worker.parser = mock_parser
            worker.neural_service = mock_neural

            # Reset mock to clear initialization calls
            mock_redis.set.reset_mock()

            # Process job
            worker.process_job(task_data)

        # Extract status updates from mock calls
        status_updates = [
            call.args[1]
            for call in mock_redis.set.call_args_list
            if len(call.args) >= 2 and call.args[0] == "worker_status"
        ]

        # Verify all status updates match expected patterns
        assert len(status_updates) > 0, "Should have at least one status update"

        for status in status_updates:
            assert (
                status == "Idle"
                or status.startswith("Training Graph on ")
                or status.startswith("Error:")
            ), f"Invalid status format: {status}"

    @pytest.mark.property
    @pytest.mark.feature("phase19-hybrid-edge-cloud-orchestration")
    @given(task_data=stale_task_data())
    @settings(max_examples=10, deadline=None)
    def test_property_18_stale_task_handling(self, task_data):
        """
        Property 18: Stale task handling

        For any task in the queue older than its TTL, the Edge Worker should
        skip it and record it as "skipped" in job history.

        Validates: Requirements 3.7
        """
        # Mock Redis client
        mock_redis = Mock()
        job_records = []

        def capture_job_record(key, value):
            if key == "job_history":
                job_records.append(json.loads(value))

        mock_redis.lpush.side_effect = capture_job_record
        mock_redis.ltrim.return_value = None
        mock_redis.set.return_value = None

        # Mock parser and neural service (should NOT be called for stale tasks)
        mock_parser = Mock()
        mock_neural = Mock()

        # Create worker with mocked dependencies
        with (
            patch("worker.Redis", return_value=mock_redis),
            patch("worker.RepositoryParser", return_value=mock_parser),
            patch("worker.NeuralGraphService", return_value=mock_neural),
            patch("worker.torch.cuda.is_available", return_value=False),
        ):
            worker = EdgeWorker()
            # Inject the mock redis after initialization
            worker.redis = mock_redis
            worker.parser = mock_parser
            worker.neural_service = mock_neural

            # Process job
            worker.process_job(task_data)

        # Verify task was skipped
        assert len(job_records) > 0, "Should have job record for skipped task"

        job_record = job_records[0]

        # Verify status is "skipped"
        assert job_record["status"] == "skipped", (
            "Stale task should be marked as skipped"
        )

        # Verify reason is provided
        assert "reason" in job_record
        assert "TTL" in job_record["reason"]

        # Verify age and TTL are recorded
        assert "age_seconds" in job_record
        assert "ttl" in job_record
        assert job_record["age_seconds"] > job_record["ttl"]

        # Verify parser and neural service were NOT called
        mock_parser.clone_repository.assert_not_called()
        mock_neural.train_embeddings.assert_not_called()
        mock_neural.upload_embeddings.assert_not_called()
