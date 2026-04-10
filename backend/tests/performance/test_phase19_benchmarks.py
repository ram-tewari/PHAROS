"""
Performance benchmarks for Phase 19 - Hybrid Edge-Cloud Orchestration.

Tests verify that all Phase 19 operations meet performance requirements:
- API dispatch latency: < 100ms
- Embedding generation: < 5 minutes for 100 files
- GPU utilization: > 70%
- Throughput: > 10 repos/hour

Validates: Requirements 10.1, 10.2, 10.3, 10.4
"""

import pytest
import time
import torch
import json
import os
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from upstash_redis import Redis

# Import services
from app.modules.graph.neural_service import NeuralGraphService
from app.utils.repo_parser import RepositoryParser, DependencyGraph


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
def sample_dependency_graph():
    """Create a sample dependency graph with 100 nodes."""
    num_nodes = 100

    # Create a realistic dependency graph (chain + some cross-links)
    edges = []

    # Create chain dependencies
    for i in range(num_nodes - 1):
        edges.append([i, i + 1])

    # Add some cross-links (10% of nodes)
    for i in range(0, num_nodes, 10):
        if i + 5 < num_nodes:
            edges.append([i, i + 5])

    edge_index = torch.tensor(edges, dtype=torch.long).t()
    file_paths = [f"src/module_{i}.py" for i in range(num_nodes)]

    return DependencyGraph(edge_index=edge_index, file_paths=file_paths)


# ============================================================================
# Benchmark 1: API Dispatch Latency
# ============================================================================


@pytest.mark.performance
@pytest.mark.benchmark
class TestAPIDispatchLatency:
    """Test API dispatch latency meets < 100ms requirement."""

    def test_ingest_endpoint_latency(self, cloud_api_client, mock_redis):
        """
        Benchmark: API dispatch latency should be < 100ms.

        Validates: Requirements 10.1
        """
        # Warm up
        for _ in range(5):
            cloud_api_client.post(
                "/api/v1/ingestion/ingest/github.com/test/repo",
                headers={"Authorization": "Bearer test-token-123"},
            )

        # Measure latency over 100 requests
        latencies = []

        for i in range(100):
            start_time = time.perf_counter()

            response = cloud_api_client.post(
                f"/api/v1/ingestion/ingest/github.com/test/repo{i}",
                headers={"Authorization": "Bearer test-token-123"},
            )

            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000
            latencies.append(latency_ms)

            assert response.status_code == 200

        # Calculate statistics
        avg_latency = sum(latencies) / len(latencies)
        p50_latency = sorted(latencies)[len(latencies) // 2]
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
        p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]
        max_latency = max(latencies)

        # Report results
        print("\n=== API Dispatch Latency Benchmark ===")
        print(f"Requests: 100")
        print(f"Average: {avg_latency:.2f}ms")
        print(f"P50: {p50_latency:.2f}ms")
        print(f"P95: {p95_latency:.2f}ms")
        print(f"P99: {p99_latency:.2f}ms")
        print(f"Max: {max_latency:.2f}ms")
        print(f"Target: < 100ms")

        # Verify requirement
        assert p95_latency < 100.0, (
            f"API dispatch latency P95 is {p95_latency:.2f}ms, requirement is < 100ms"
        )

    def test_worker_status_endpoint_latency(self, cloud_api_client, mock_redis):
        """
        Benchmark: Worker status endpoint should be < 50ms.

        Validates: Requirements 10.1
        """
        # Warm up
        for _ in range(5):
            cloud_api_client.get("/api/v1/ingestion/worker/status")

        # Measure latency over 100 requests
        latencies = []

        for _ in range(100):
            start_time = time.perf_counter()

            response = cloud_api_client.get("/api/v1/ingestion/worker/status")

            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000
            latencies.append(latency_ms)

            assert response.status_code == 200

        # Calculate statistics
        avg_latency = sum(latencies) / len(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

        # Report results
        print("\n=== Worker Status Endpoint Latency ===")
        print(f"Average: {avg_latency:.2f}ms")
        print(f"P95: {p95_latency:.2f}ms")
        print(f"Target: < 50ms")

        # Verify requirement (more lenient for status endpoint)
        assert p95_latency < 50.0, (
            f"Worker status latency P95 is {p95_latency:.2f}ms, requirement is < 50ms"
        )


# ============================================================================
# Benchmark 2: Embedding Generation Time
# ============================================================================


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.slow
class TestEmbeddingGenerationTime:
    """Test embedding generation time meets < 5 minutes for 100 files requirement."""

    def test_embedding_generation_100_files(
        self, neural_service, sample_dependency_graph
    ):
        """
        Benchmark: Embedding generation should be < 5 minutes for 100 files.

        Validates: Requirements 10.2
        """
        print(f"\n=== Embedding Generation Benchmark ===")
        print(f"Device: {neural_service.device}")
        print(f"Nodes: {sample_dependency_graph.num_nodes}")
        print(f"Edges: {sample_dependency_graph.edge_index.shape[1]}")

        # Measure embedding generation time
        start_time = time.perf_counter()

        embeddings = neural_service.train_embeddings(
            edge_index=sample_dependency_graph.edge_index,
            num_nodes=sample_dependency_graph.num_nodes,
        )

        end_time = time.perf_counter()
        elapsed_time = end_time - start_time

        # Verify embeddings
        assert embeddings.shape == (sample_dependency_graph.num_nodes, 64)
        assert embeddings.device.type == "cpu"

        # Report results
        print(f"Time: {elapsed_time:.2f}s ({elapsed_time / 60:.2f} minutes)")
        print(f"Target: < 300s (5 minutes)")
        print(
            f"Files per second: {sample_dependency_graph.num_nodes / elapsed_time:.2f}"
        )

        # Verify requirement (5 minutes = 300 seconds)
        assert elapsed_time < 300.0, (
            f"Embedding generation for 100 files took {elapsed_time:.2f}s, "
            f"requirement is < 300s (5 minutes)"
        )

    def test_embedding_generation_scaling(self, neural_service):
        """
        Benchmark: Test embedding generation time scales linearly with graph size.

        Validates: Requirements 10.2
        """
        sizes = [10, 50, 100]
        times = []

        print("\n=== Embedding Generation Scaling ===")

        for size in sizes:
            # Create graph of given size
            edges = [[i, (i + 1) % size] for i in range(size)]
            edge_index = torch.tensor(edges, dtype=torch.long).t()

            # Measure time
            start_time = time.perf_counter()

            embeddings = neural_service.train_embeddings(
                edge_index=edge_index, num_nodes=size
            )

            end_time = time.perf_counter()
            elapsed_time = end_time - start_time
            times.append(elapsed_time)

            print(
                f"Size {size}: {elapsed_time:.2f}s ({size / elapsed_time:.2f} files/s)"
            )

        # Verify roughly linear scaling (within 2x factor)
        time_per_file_10 = times[0] / sizes[0]
        time_per_file_100 = times[2] / sizes[2]

        scaling_factor = time_per_file_100 / time_per_file_10

        print(f"\nScaling factor (100 vs 10): {scaling_factor:.2f}x")
        print(f"Target: < 2.0x (linear scaling)")

        assert scaling_factor < 2.0, (
            f"Scaling factor is {scaling_factor:.2f}x, should be < 2.0x for linear scaling"
        )


# ============================================================================
# Benchmark 3: GPU Utilization
# ============================================================================


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA not available")
class TestGPUUtilization:
    """Test GPU utilization meets > 70% requirement."""

    def test_gpu_utilization_during_training(self, sample_dependency_graph):
        """
        Benchmark: GPU utilization should be > 70% during training.

        Validates: Requirements 10.3

        Note: This test requires nvidia-smi to be available.
        """
        import subprocess

        # Create service with GPU
        neural_service = NeuralGraphService(device="cuda")

        print("\n=== GPU Utilization Benchmark ===")
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(
            f"Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB"
        )

        # Start training in background
        import threading

        training_complete = threading.Event()
        gpu_utilizations = []

        def train():
            neural_service.train_embeddings(
                edge_index=sample_dependency_graph.edge_index,
                num_nodes=sample_dependency_graph.num_nodes,
            )
            training_complete.set()

        def monitor_gpu():
            while not training_complete.is_set():
                try:
                    # Query GPU utilization using nvidia-smi
                    result = subprocess.run(
                        [
                            "nvidia-smi",
                            "--query-gpu=utilization.gpu",
                            "--format=csv,noheader,nounits",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=1,
                    )

                    if result.returncode == 0:
                        utilization = float(result.stdout.strip())
                        gpu_utilizations.append(utilization)

                except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
                    pass

                time.sleep(0.1)  # Sample every 100ms

        # Start threads
        train_thread = threading.Thread(target=train)
        monitor_thread = threading.Thread(target=monitor_gpu)

        train_thread.start()
        monitor_thread.start()

        # Wait for completion
        train_thread.join()
        training_complete.set()
        monitor_thread.join()

        # Calculate statistics
        if gpu_utilizations:
            avg_utilization = sum(gpu_utilizations) / len(gpu_utilizations)
            max_utilization = max(gpu_utilizations)

            print(f"Samples: {len(gpu_utilizations)}")
            print(f"Average utilization: {avg_utilization:.1f}%")
            print(f"Max utilization: {max_utilization:.1f}%")
            print(f"Target: > 70%")

            # Verify requirement
            assert avg_utilization > 70.0, (
                f"GPU utilization is {avg_utilization:.1f}%, requirement is > 70%"
            )
        else:
            pytest.skip("Could not measure GPU utilization (nvidia-smi not available)")


# ============================================================================
# Benchmark 4: Throughput
# ============================================================================


@pytest.mark.performance
@pytest.mark.benchmark
@pytest.mark.slow
class TestThroughput:
    """Test throughput meets > 10 repos/hour requirement."""

    def test_repository_processing_throughput(self, neural_service):
        """
        Benchmark: System should process > 10 repos/hour.

        Validates: Requirements 10.4

        Note: This test simulates processing 3 repositories and extrapolates.
        """
        print("\n=== Repository Processing Throughput ===")

        # Simulate processing 3 repositories of varying sizes
        repo_sizes = [50, 100, 150]  # Number of files
        processing_times = []

        for size in repo_sizes:
            # Create dependency graph
            edges = [[i, (i + 1) % size] for i in range(size)]
            edge_index = torch.tensor(edges, dtype=torch.long).t()
            file_paths = [f"src/file_{i}.py" for i in range(size)]

            # Measure total processing time (parsing + training + upload)
            start_time = time.perf_counter()

            # Train embeddings
            embeddings = neural_service.train_embeddings(
                edge_index=edge_index, num_nodes=size
            )

            # Simulate upload time (assume 1ms per embedding)
            upload_time = size * 0.001
            time.sleep(upload_time)

            end_time = time.perf_counter()
            elapsed_time = end_time - start_time
            processing_times.append(elapsed_time)

            print(f"Repository {size} files: {elapsed_time:.2f}s")

        # Calculate average processing time
        avg_processing_time = sum(processing_times) / len(processing_times)

        # Calculate throughput (repos per hour)
        repos_per_hour = 3600 / avg_processing_time

        print(f"\nAverage processing time: {avg_processing_time:.2f}s")
        print(f"Throughput: {repos_per_hour:.2f} repos/hour")
        print(f"Target: > 10 repos/hour")

        # Verify requirement
        assert repos_per_hour > 10.0, (
            f"Throughput is {repos_per_hour:.2f} repos/hour, "
            f"requirement is > 10 repos/hour"
        )

    def test_concurrent_api_requests(self, cloud_api_client, mock_redis):
        """
        Benchmark: API should handle concurrent requests efficiently.

        Validates: Requirements 10.4
        """
        import concurrent.futures

        print("\n=== Concurrent API Requests Benchmark ===")

        def make_request(i):
            start_time = time.perf_counter()
            response = cloud_api_client.post(
                f"/api/v1/ingestion/ingest/github.com/test/repo{i}",
                headers={"Authorization": "Bearer test-token-123"},
            )
            end_time = time.perf_counter()
            return response.status_code, (end_time - start_time) * 1000

        # Test with 50 concurrent requests
        num_requests = 50

        start_time = time.perf_counter()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(make_request, range(num_requests)))

        end_time = time.perf_counter()
        total_time = end_time - start_time

        # Analyze results
        status_codes = [r[0] for r in results]
        latencies = [r[1] for r in results]

        success_rate = (
            sum(1 for s in status_codes if s == 200) / len(status_codes) * 100
        )
        avg_latency = sum(latencies) / len(latencies)
        throughput = num_requests / total_time

        print(f"Requests: {num_requests}")
        print(f"Total time: {total_time:.2f}s")
        print(f"Success rate: {success_rate:.1f}%")
        print(f"Average latency: {avg_latency:.2f}ms")
        print(f"Throughput: {throughput:.2f} req/s")

        # Verify requirements
        assert success_rate >= 95.0, (
            f"Success rate is {success_rate:.1f}%, should be >= 95%"
        )
        assert avg_latency < 200.0, (
            f"Average latency is {avg_latency:.2f}ms, should be < 200ms"
        )


# ============================================================================
# Summary Report
# ============================================================================


@pytest.mark.performance
@pytest.mark.benchmark
def test_generate_performance_report():
    """
    Generate a comprehensive performance report.

    This test always passes and just generates a summary report.
    """
    print("\n" + "=" * 70)
    print("PHASE 19 PERFORMANCE BENCHMARK SUMMARY")
    print("=" * 70)
    print("\nPerformance Requirements:")
    print("  1. API dispatch latency: < 100ms (P95)")
    print("  2. Embedding generation: < 5 minutes for 100 files")
    print("  3. GPU utilization: > 70% during training")
    print("  4. Throughput: > 10 repos/hour")
    print("\nRun individual benchmark tests to verify each requirement.")
    print("=" * 70)
