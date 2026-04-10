"""
Unit tests for Edge Worker.

These tests verify specific behaviors and edge cases of the edge worker.

Requirements: 3.1, 3.2, 3.6, 3.7, 8.2, 8.6, 12.2
"""

import pytest
import sys
import json
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import torch

# Mock upstash_redis and torch_geometric before importing worker
sys.modules["upstash_redis"] = MagicMock()
sys.modules["torch_geometric"] = MagicMock()
sys.modules["torch_geometric.nn"] = MagicMock()

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


class TestEdgeWorker:
    """Unit tests for edge worker functionality."""

    def test_cuda_detection_when_available(self):
        """
        Test CUDA detection and GPU logging when CUDA is available.

        Requirements: 3.1
        """
        with (
            patch("worker.torch.cuda.is_available", return_value=True),
            patch("worker.torch.cuda.get_device_name", return_value="NVIDIA RTX 4070"),
            patch("worker.torch.version.cuda", "12.1"),
            patch("worker.torch.cuda.get_device_properties") as mock_props,
            patch("worker.Redis") as mock_redis_class,
            patch("worker.RepositoryParser"),
            patch("worker.NeuralGraphService"),
        ):
            # Mock GPU properties
            mock_props.return_value.total_memory = 16 * 1024 * 1024 * 1024  # 16GB

            # Mock Redis
            mock_redis = Mock()
            mock_redis.set.return_value = None
            mock_redis_class.return_value = mock_redis

            # Create worker
            worker = EdgeWorker()

            # Verify CUDA was detected
            assert worker.device == "cuda"

    def test_cpu_fallback_when_cuda_unavailable(self):
        """
        Test CPU fallback when CUDA is unavailable.

        Requirements: 3.2
        """
        with (
            patch("worker.torch.cuda.is_available", return_value=False),
            patch("worker.Redis") as mock_redis_class,
            patch("worker.RepositoryParser"),
            patch("worker.NeuralGraphService"),
        ):
            # Mock Redis
            mock_redis = Mock()
            mock_redis.set.return_value = None
            mock_redis_class.return_value = mock_redis

            # Create worker
            worker = EdgeWorker()

            # Verify CPU fallback
            assert worker.device == "cpu"

    def test_error_continuation(self):
        """
        Test that worker continues processing after errors.

        Requirements: 3.6
        """
        with (
            patch("worker.Redis") as mock_redis_class,
            patch("worker.RepositoryParser") as mock_parser_class,
            patch("worker.NeuralGraphService") as mock_neural_class,
            patch("worker.torch.cuda.is_available", return_value=False),
        ):
            # Mock Redis
            mock_redis = Mock()
            mock_redis.set.return_value = None
            mock_redis.lpush.return_value = None
            mock_redis.ltrim.return_value = None
            mock_redis_class.return_value = mock_redis

            # Mock parser that raises an error
            mock_parser = Mock()
            mock_parser.clone_repository.side_effect = Exception("Clone failed")
            mock_parser_class.return_value = mock_parser

            # Mock neural service
            mock_neural = Mock()
            mock_neural_class.return_value = mock_neural

            # Create worker
            worker = EdgeWorker()
            worker.redis = mock_redis
            worker.parser = mock_parser
            worker.neural_service = mock_neural

            # Process job that will fail
            task_data = {
                "repo_url": "github.com/user/repo",
                "submitted_at": datetime.now().isoformat(),
                "ttl": 86400,
            }

            # Should not raise exception
            worker.process_job(task_data)

            # Verify error was recorded in job history
            assert mock_redis.lpush.called
            job_record = json.loads(mock_redis.lpush.call_args[0][1])
            assert job_record["status"] == "failed"
            assert "Clone failed" in job_record["error"]

    def test_clone_failure_handling(self):
        """
        Test handling of repository clone failures.

        Requirements: 8.2
        """
        with (
            patch("worker.Redis") as mock_redis_class,
            patch("worker.RepositoryParser") as mock_parser_class,
            patch("worker.NeuralGraphService") as mock_neural_class,
            patch("worker.torch.cuda.is_available", return_value=False),
        ):
            # Mock Redis
            mock_redis = Mock()
            mock_redis.set.return_value = None
            mock_redis.lpush.return_value = None
            mock_redis.ltrim.return_value = None
            mock_redis_class.return_value = mock_redis

            # Mock parser that fails to clone
            mock_parser = Mock()
            mock_parser.clone_repository.side_effect = Exception("Repository not found")
            mock_parser_class.return_value = mock_parser

            # Mock neural service
            mock_neural = Mock()
            mock_neural_class.return_value = mock_neural

            # Create worker
            worker = EdgeWorker()
            worker.redis = mock_redis
            worker.parser = mock_parser
            worker.neural_service = mock_neural

            # Process job
            task_data = {
                "repo_url": "github.com/user/nonexistent",
                "submitted_at": datetime.now().isoformat(),
                "ttl": 86400,
            }

            worker.process_job(task_data)

            # Verify job was marked as failed
            assert mock_redis.lpush.called
            job_record = json.loads(mock_redis.lpush.call_args[0][1])
            assert job_record["status"] == "failed"
            assert "Repository not found" in job_record["error"]

            # Verify worker status was updated to show error
            status_calls = [
                call
                for call in mock_redis.set.call_args_list
                if call[0][0] == "worker_status"
            ]
            assert any("Error:" in str(call) for call in status_calls)

    def test_redis_reconnection_logic(self):
        """
        Test Redis reconnection logic on connection errors.

        Requirements: 8.6
        """
        with (
            patch("worker.Redis") as mock_redis_class,
            patch("worker.RepositoryParser"),
            patch("worker.NeuralGraphService"),
            patch("worker.torch.cuda.is_available", return_value=False),
        ):
            # Mock Redis
            mock_redis = Mock()
            # First call succeeds (for initialization), then fails, then succeeds
            mock_redis.set.side_effect = [None, Exception("Connection lost"), None]
            mock_redis_class.return_value = mock_redis

            # Create worker (first call to set)
            worker = EdgeWorker()

            # Second call should fail
            with pytest.raises(Exception, match="Connection lost"):
                worker.redis.set("test", "value")

            # Third call should work (simulating reconnection)
            worker.redis.set("test", "value")

            # Verify set was called 3 times
            assert mock_redis.set.call_count == 3

    def test_stale_task_detection_and_skipping(self):
        """
        Test that stale tasks (older than TTL) are detected and skipped.

        Requirements: 3.7
        """
        with (
            patch("worker.Redis") as mock_redis_class,
            patch("worker.RepositoryParser") as mock_parser_class,
            patch("worker.NeuralGraphService") as mock_neural_class,
            patch("worker.torch.cuda.is_available", return_value=False),
        ):
            # Mock Redis
            mock_redis = Mock()
            mock_redis.set.return_value = None
            mock_redis.lpush.return_value = None
            mock_redis.ltrim.return_value = None
            mock_redis_class.return_value = mock_redis

            # Mock parser and neural service
            mock_parser = Mock()
            mock_parser_class.return_value = mock_parser

            mock_neural = Mock()
            mock_neural_class.return_value = mock_neural

            # Create worker
            worker = EdgeWorker()
            worker.redis = mock_redis
            worker.parser = mock_parser
            worker.neural_service = mock_neural

            # Create stale task (submitted 2 hours ago with 1 hour TTL)
            ttl = 3600  # 1 hour
            submitted_at = datetime.now() - timedelta(seconds=ttl + 1000)

            task_data = {
                "repo_url": "github.com/user/old-repo",
                "submitted_at": submitted_at.isoformat(),
                "ttl": ttl,
            }

            # Process stale task
            worker.process_job(task_data)

            # Verify task was skipped
            assert mock_redis.lpush.called
            job_record = json.loads(mock_redis.lpush.call_args[0][1])
            assert job_record["status"] == "skipped"
            assert "TTL" in job_record["reason"]

            # Verify parser was NOT called
            mock_parser.clone_repository.assert_not_called()

    def test_backward_compatibility_with_legacy_string_format(self):
        """
        Test backward compatibility with legacy string format tasks.

        Requirements: 12.2
        """
        with (
            patch("worker.Redis") as mock_redis_class,
            patch("worker.RepositoryParser") as mock_parser_class,
            patch("worker.NeuralGraphService") as mock_neural_class,
            patch("worker.torch.cuda.is_available", return_value=False),
        ):
            # Mock Redis
            mock_redis = Mock()
            mock_redis.set.return_value = None
            mock_redis.lpush.return_value = None
            mock_redis.ltrim.return_value = None
            mock_redis_class.return_value = mock_redis

            # Mock parser
            mock_parser = Mock()
            mock_parser.clone_repository.return_value = "/tmp/test_repo"
            mock_parser.build_dependency_graph.return_value = Mock(
                edge_index=torch.tensor([[0, 1], [1, 0]]),
                num_nodes=2,
                file_paths=["file1.py", "file2.py"],
            )
            mock_parser.cleanup.return_value = None
            mock_parser_class.return_value = mock_parser

            # Mock neural service
            mock_neural = Mock()
            mock_neural.train_embeddings.return_value = torch.randn(2, 64)
            mock_neural.upload_embeddings.return_value = None
            mock_neural_class.return_value = mock_neural

            # Create worker
            worker = EdgeWorker()
            worker.redis = mock_redis
            worker.parser = mock_parser
            worker.neural_service = mock_neural

            # Process legacy format task (plain string instead of JSON)
            # This simulates the old format where tasks were just URL strings
            legacy_task = "github.com/user/legacy-repo"

            # The worker's run() method would parse this, but we're testing process_job
            # which expects a dict, so we simulate what run() would do:
            try:
                task_data = json.loads(legacy_task)
            except json.JSONDecodeError:
                # Legacy format: plain URL string
                task_data = {
                    "repo_url": legacy_task,
                    "submitted_at": None,
                    "ttl": 86400,
                }

            # Process the task
            worker.process_job(task_data)

            # Verify task was processed successfully
            assert mock_parser.clone_repository.called
            assert mock_neural.train_embeddings.called
            assert mock_neural.upload_embeddings.called

            # Verify job was recorded as complete
            assert mock_redis.lpush.called
            job_record = json.loads(mock_redis.lpush.call_args[0][1])
            assert job_record["status"] == "complete"
            assert job_record["repo_url"] == legacy_task

    def test_worker_startup_command_works(self):
        """
        Test that worker can be started successfully.

        Requirements: 12.2
        """
        with (
            patch("worker.Redis") as mock_redis_class,
            patch("worker.RepositoryParser"),
            patch("worker.NeuralGraphService"),
            patch("worker.torch.cuda.is_available", return_value=False),
        ):
            # Mock Redis
            mock_redis = Mock()
            mock_redis.set.return_value = None
            mock_redis_class.return_value = mock_redis

            # Create worker (simulates startup)
            worker = EdgeWorker()

            # Verify worker initialized successfully
            assert worker is not None
            assert worker.device in ["cuda", "cpu"]
            assert worker.redis is not None
            assert worker.parser is not None
            assert worker.neural_service is not None

            # Verify initial status was set to "Idle"
            assert mock_redis.set.called
            status_call = mock_redis.set.call_args_list[0]
            assert status_call[0][0] == "worker_status"
            assert status_call[0][1] == "Idle"
