"""
Stress tests for Phase 19 - Hybrid Edge-Cloud Orchestration.

Tests verify system behavior under extreme conditions:
- Large repository (10,000 files)
- 100 concurrent API requests
- Queue of 1000 repositories
- Limited GPU memory scenarios

Validates: Requirements 10.5
"""

import pytest
import time
import torch
import json
import os
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from upstash_redis import Redis
import concurrent.futures

# Import services
from app.modules.graph.neural_service import NeuralGraphService
from app.utils.repo_parser import DependencyGraph


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis = Mock(spec=Redis)
    redis.rpush = Mock(return_value=1)
    redis.llen = Mock(return_value=0)
    redis.expire = Mock(return_value=True)
    redis.get = Mock(return_value="Idle")
    redis.set = Mock(return_value=True)
    redis.lpush = Mock(return_value=True)
    redis.ltrim = Mock(return_value=True)
    return redis


@pytest.fixture
def cloud_api_client(mock_redis):
    """FastAPI test client in CLOUD mode."""
    os.environ["MODE"] = "CLOUD"
    os.environ["PHAROS_ADMIN_TOKEN"] = "test-token-123"

    # Mock Redis dependency
    with patch("app.routers.ingestion.get_redis_client", return_value=mock_redis):
        from app.main import app

        client = TestClient(app)
        yield client


@pytest.fixture
def neural_service():
    """Neural graph service for testing."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return NeuralGraphService(device=device)


@pytest.fixture
def large_dependency_graph():
    """Create a large dependency graph with 10,000 nodes."""
    num_nodes = 10000

    # Create a realistic dependency graph structure
    edges = []

    # Create hierarchical structure (modules -> submodules -> files)
    num_modules = 100
    files_per_module = num_nodes // num_modules

    for module_idx in range(num_modules):
        module_start = module_idx * files_per_module
        module_end = min((module_idx + 1) * files_per_module, num_nodes)

        # Chain within module
        for i in range(module_start, module_end - 1):
            edges.append([i, i + 1])

        # Cross-module dependencies (10% of modules)
        if module_idx % 10 == 0 and module_idx + 1 < num_modules:
            next_module_start = (module_idx + 1) * files_per_module
            if next_module_start < num_nodes:
                edges.append([module_start, next_module_start])

    edge_index = torch.tensor(edges, dtype=torch.long).t()
    file_paths = [
        f"src/module_{i // files_per_module}/file_{i % files_per_module}.py"
        for i in range(num_nodes)
    ]

    return DependencyGraph(edge_index=edge_index, file_paths=file_paths)


# ============================================================================
# Stress Test 1: Large Repository
# ============================================================================


@pytest.mark.stress
@pytest.mark.slow
class TestLargeRepositoryStress:
    """Test system behavior with large repository (10,000 files)."""

    def test_large_repository_processing(self, neural_service, large_dependency_graph):
        """
        Stress Test: Process repository with 10,000 files.

        Validates: Requirements 10.5
        """
        print("\n=== Large Repository Stress Test ===")
        print(f"Device: {neural_service.device}")
        print(f"Nodes: {large_dependency_graph.num_nodes}")
        print(f"Edges: {large_dependency_graph.edge_index.shape[1]}")

        # Measure memory before
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
            initial_memory = torch.cuda.memory_allocated() / 1e9
            print(f"Initial GPU memory: {initial_memory:.2f} GB")

        # Process large repository
        start_time = time.perf_counter()

        try:
            embeddings = neural_service.train_embeddings(
                edge_index=large_dependency_graph.edge_index,
                num_nodes=large_dependency_graph.num_nodes,
            )

            end_time = time.perf_counter()
            elapsed_time = end_time - start_time

            # Verify embeddings
            assert embeddings.shape == (large_dependency_graph.num_nodes, 64)
            assert embeddings.device.type == "cpu"

            # Measure memory after
            if torch.cuda.is_available():
                peak_memory = torch.cuda.max_memory_allocated() / 1e9
                final_memory = torch.cuda.memory_allocated() / 1e9
                print(f"Peak GPU memory: {peak_memory:.2f} GB")
                print(f"Final GPU memory: {final_memory:.2f} GB")

            # Report results
            print(
                f"Processing time: {elapsed_time:.2f}s ({elapsed_time / 60:.2f} minutes)"
            )
            print(
                f"Files per second: {large_dependency_graph.num_nodes / elapsed_time:.2f}"
            )
            print(f"Status: SUCCESS")

            # Verify reasonable performance (should complete, even if slow)
            assert elapsed_time < 3600, (
                f"Processing 10,000 files took {elapsed_time:.2f}s (> 1 hour), "
                f"this is too slow"
            )

        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                print(f"Status: OUT OF MEMORY")
                print(f"Error: {e}")
                pytest.skip(
                    "GPU out of memory - expected for large graphs on limited hardware"
                )
            else:
                raise

    def test_large_repository_memory_efficiency(self, neural_service):
        """
        Stress Test: Verify memory efficiency with large graphs.

        Validates: Requirements 10.5
        """
        print("\n=== Memory Efficiency Stress Test ===")

        # Test with increasing graph sizes
        sizes = [1000, 2000, 5000, 10000]
        memory_usage = []

        for size in sizes:
            # Create graph
            edges = [[i, (i + 1) % size] for i in range(size)]
            edge_index = torch.tensor(edges, dtype=torch.long).t()

            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()

            try:
                # Train embeddings
                embeddings = neural_service.train_embeddings(
                    edge_index=edge_index, num_nodes=size
                )

                # Measure memory
                if torch.cuda.is_available():
                    peak_memory = torch.cuda.max_memory_allocated() / 1e9
                    memory_usage.append((size, peak_memory))
                    print(f"Size {size}: {peak_memory:.2f} GB")
                else:
                    print(f"Size {size}: CPU mode (no memory tracking)")

                # Clean up
                del embeddings
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

            except RuntimeError as e:
                if "out of memory" in str(e).lower():
                    print(f"Size {size}: OUT OF MEMORY")
                    break
                else:
                    raise

        # Verify memory scales reasonably (should be roughly linear)
        if len(memory_usage) >= 2:
            size_ratio = memory_usage[-1][0] / memory_usage[0][0]
            memory_ratio = memory_usage[-1][1] / memory_usage[0][1]

            print(f"\nSize ratio: {size_ratio:.2f}x")
            print(f"Memory ratio: {memory_ratio:.2f}x")
            print(f"Memory efficiency: {size_ratio / memory_ratio:.2f}")

            # Memory should scale sub-linearly (due to fixed overhead)
            assert memory_ratio < size_ratio * 1.5, (
                f"Memory scaling is inefficient: {memory_ratio:.2f}x for {size_ratio:.2f}x size"
            )


# ============================================================================
# Stress Test 2: Concurrent API Requests
# ============================================================================


@pytest.mark.stress
class TestConcurrentAPIStress:
    """Test system behavior with 100 concurrent API requests."""

    def test_100_concurrent_requests(self, cloud_api_client, mock_redis):
        """
        Stress Test: Handle 100 concurrent API requests.

        Validates: Requirements 10.5
        """
        print("\n=== Concurrent API Requests Stress Test ===")

        num_requests = 100
        max_workers = 20

        def make_request(i):
            try:
                start_time = time.perf_counter()
                response = cloud_api_client.post(
                    f"/api/v1/ingestion/ingest/github.com/stress/repo{i}",
                    headers={"Authorization": "Bearer test-token-123"},
                )
                end_time = time.perf_counter()

                return {
                    "index": i,
                    "status_code": response.status_code,
                    "latency_ms": (end_time - start_time) * 1000,
                    "success": response.status_code == 200,
                }
            except Exception as e:
                return {
                    "index": i,
                    "status_code": 500,
                    "latency_ms": 0,
                    "success": False,
                    "error": str(e),
                }

        # Execute concurrent requests
        start_time = time.perf_counter()

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(make_request, range(num_requests)))

        end_time = time.perf_counter()
        total_time = end_time - start_time

        # Analyze results
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]
        latencies = [r["latency_ms"] for r in successful]

        success_rate = len(successful) / num_requests * 100
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0
        max_latency = max(latencies) if latencies else 0
        throughput = num_requests / total_time

        # Report results
        print(f"Total requests: {num_requests}")
        print(f"Concurrent workers: {max_workers}")
        print(f"Total time: {total_time:.2f}s")
        print(f"Success rate: {success_rate:.1f}%")
        print(f"Failed requests: {len(failed)}")
        print(f"Average latency: {avg_latency:.2f}ms")
        print(f"P95 latency: {p95_latency:.2f}ms")
        print(f"Max latency: {max_latency:.2f}ms")
        print(f"Throughput: {throughput:.2f} req/s")

        # Verify requirements
        assert success_rate >= 90.0, (
            f"Success rate is {success_rate:.1f}%, should be >= 90% under stress"
        )

        assert p95_latency < 500.0, (
            f"P95 latency is {p95_latency:.2f}ms, should be < 500ms under stress"
        )

    def test_sustained_load(self, cloud_api_client, mock_redis):
        """
        Stress Test: Handle sustained load over time.

        Validates: Requirements 10.5
        """
        print("\n=== Sustained Load Stress Test ===")

        duration_seconds = 30
        requests_per_second = 10

        results = []
        start_time = time.perf_counter()
        request_count = 0

        while time.perf_counter() - start_time < duration_seconds:
            batch_start = time.perf_counter()

            # Send batch of requests
            for i in range(requests_per_second):
                try:
                    response = cloud_api_client.post(
                        f"/api/v1/ingestion/ingest/github.com/sustained/repo{request_count}",
                        headers={"Authorization": "Bearer test-token-123"},
                    )
                    results.append(response.status_code == 200)
                    request_count += 1
                except Exception:
                    results.append(False)
                    request_count += 1

            # Sleep to maintain rate
            batch_time = time.perf_counter() - batch_start
            sleep_time = max(0, 1.0 - batch_time)
            time.sleep(sleep_time)

        total_time = time.perf_counter() - start_time

        # Analyze results
        success_rate = sum(results) / len(results) * 100
        actual_rps = len(results) / total_time

        print(f"Duration: {total_time:.2f}s")
        print(f"Total requests: {len(results)}")
        print(f"Target RPS: {requests_per_second}")
        print(f"Actual RPS: {actual_rps:.2f}")
        print(f"Success rate: {success_rate:.1f}%")

        # Verify requirements
        assert success_rate >= 95.0, (
            f"Success rate is {success_rate:.1f}%, should be >= 95% under sustained load"
        )


# ============================================================================
# Stress Test 3: Queue Overflow
# ============================================================================


@pytest.mark.stress
class TestQueueOverflowStress:
    """Test system behavior with queue of 1000 repositories."""

    def test_queue_overflow_handling(self, cloud_api_client):
        """
        Stress Test: Handle queue overflow with 1000 repositories.

        Validates: Requirements 10.5
        """
        print("\n=== Queue Overflow Stress Test ===")

        # Create mock Redis that tracks queue size
        queue = []
        max_queue_size = 10

        mock_redis = Mock(spec=Redis)

        def mock_llen(key):
            return len(queue)

        def mock_rpush(key, value):
            if len(queue) < max_queue_size:
                queue.append(value)
                return len(queue)
            return len(queue)

        mock_redis.llen = Mock(side_effect=mock_llen)
        mock_redis.rpush = Mock(side_effect=mock_rpush)
        mock_redis.expire = Mock(return_value=True)

        # Test with mock Redis
        with patch("app.routers.ingestion.get_redis_client", return_value=mock_redis):
            from app.main import app

            client = TestClient(app)

            # Try to submit 1000 repositories
            num_attempts = 1000
            accepted = 0
            rejected = 0

            for i in range(num_attempts):
                response = client.post(
                    f"/api/v1/ingestion/ingest/github.com/overflow/repo{i}",
                    headers={"Authorization": "Bearer test-token-123"},
                )

                if response.status_code == 200:
                    accepted += 1
                elif response.status_code == 429:
                    rejected += 1

            # Report results
            print(f"Attempts: {num_attempts}")
            print(f"Accepted: {accepted}")
            print(f"Rejected (429): {rejected}")
            print(f"Queue size: {len(queue)}")
            print(f"Max queue size: {max_queue_size}")

            # Verify queue cap enforcement
            assert len(queue) <= max_queue_size, (
                f"Queue size is {len(queue)}, should be <= {max_queue_size}"
            )

            assert rejected > 0, "Should reject requests when queue is full"

            assert accepted == max_queue_size, (
                f"Should accept exactly {max_queue_size} requests, got {accepted}"
            )


# ============================================================================
# Stress Test 4: Limited GPU Memory
# ============================================================================


@pytest.mark.stress
@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA not available")
class TestLimitedGPUMemoryStress:
    """Test system behavior with limited GPU memory scenarios."""

    def test_gpu_memory_pressure(self, neural_service):
        """
        Stress Test: Handle GPU memory pressure gracefully.

        Validates: Requirements 10.5
        """
        print("\n=== GPU Memory Pressure Stress Test ===")

        # Get GPU info
        device_props = torch.cuda.get_device_properties(0)
        total_memory = device_props.total_memory / 1e9
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"Total memory: {total_memory:.2f} GB")

        # Try progressively larger graphs until OOM
        sizes = [1000, 2000, 5000, 10000, 20000, 50000]
        max_successful_size = 0

        for size in sizes:
            print(f"\nTrying size: {size} nodes")

            # Create graph
            edges = [[i, (i + 1) % size] for i in range(size)]
            edge_index = torch.tensor(edges, dtype=torch.long).t()

            torch.cuda.reset_peak_memory_stats()

            try:
                # Train embeddings
                embeddings = neural_service.train_embeddings(
                    edge_index=edge_index, num_nodes=size
                )

                # Measure memory
                peak_memory = torch.cuda.max_memory_allocated() / 1e9
                print(f"  Peak memory: {peak_memory:.2f} GB")
                print(f"  Status: SUCCESS")

                max_successful_size = size

                # Clean up
                del embeddings
                torch.cuda.empty_cache()

            except RuntimeError as e:
                if "out of memory" in str(e).lower():
                    print(f"  Status: OUT OF MEMORY")
                    print(f"  Max successful size: {max_successful_size}")
                    break
                else:
                    raise

        # Report results
        print(f"\n=== Results ===")
        print(f"Max successful size: {max_successful_size} nodes")
        print(f"GPU memory: {total_memory:.2f} GB")

        # Verify we can handle at least 1000 nodes
        assert max_successful_size >= 1000, (
            f"Should handle at least 1000 nodes, max was {max_successful_size}"
        )

    def test_memory_cleanup_after_oom(self, neural_service):
        """
        Stress Test: Verify memory cleanup after OOM error.

        Validates: Requirements 10.5
        """
        print("\n=== Memory Cleanup After OOM Test ===")

        # Try to cause OOM
        large_size = 100000
        edges = [[i, (i + 1) % large_size] for i in range(large_size)]
        edge_index = torch.tensor(edges, dtype=torch.long).t()

        initial_memory = torch.cuda.memory_allocated() / 1e9
        print(f"Initial memory: {initial_memory:.2f} GB")

        try:
            embeddings = neural_service.train_embeddings(
                edge_index=edge_index, num_nodes=large_size
            )
            print("No OOM occurred (GPU has sufficient memory)")
            del embeddings
        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                print("OOM occurred as expected")
            else:
                raise

        # Clean up
        torch.cuda.empty_cache()

        # Verify memory is cleaned up
        final_memory = torch.cuda.memory_allocated() / 1e9
        print(f"Final memory: {final_memory:.2f} GB")

        # Memory should be close to initial (within 0.5 GB)
        memory_diff = abs(final_memory - initial_memory)
        print(f"Memory difference: {memory_diff:.2f} GB")

        assert memory_diff < 0.5, (
            f"Memory not properly cleaned up: {memory_diff:.2f} GB difference"
        )


# ============================================================================
# Summary Report
# ============================================================================


@pytest.mark.stress
def test_generate_stress_report():
    """
    Generate a comprehensive stress test report.

    This test always passes and just generates a summary report.
    """
    print("\n" + "=" * 70)
    print("PHASE 19 STRESS TEST SUMMARY")
    print("=" * 70)
    print("\nStress Test Scenarios:")
    print("  1. Large repository: 10,000 files")
    print("  2. Concurrent requests: 100 simultaneous API calls")
    print("  3. Queue overflow: 1000 repository submissions")
    print("  4. GPU memory pressure: Progressive size increase until OOM")
    print("\nRun individual stress tests to verify system resilience.")
    print("=" * 70)
