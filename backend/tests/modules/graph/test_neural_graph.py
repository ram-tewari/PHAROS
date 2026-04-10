"""
Unit tests for Neural Graph Service.

These tests verify specific examples and edge cases.

NOTE: Tests that involve Node2Vec training or Qdrant uploads require:
- torch-cluster or pyg-lib (for Node2Vec)
- qdrant-client (for upload tests)

These dependencies are only available in the Edge environment (Linux with proper setup).
On Windows, only the initialization test will pass.
"""

import pytest

try:
    import torch
except ImportError:
    torch = None

if torch is None:
    pytest.skip("torch not installed", allow_module_level=True)
from unittest.mock import Mock, patch, MagicMock, call
import io
import sys

# Skip tests if torch_geometric is not installed
try:
    from app.modules.graph.neural_service import NeuralGraphService

    TORCH_GEOMETRIC_AVAILABLE = True
except ImportError:
    TORCH_GEOMETRIC_AVAILABLE = False
    pytestmark = pytest.mark.skip(reason="torch_geometric not installed")

# Check for qdrant-client availability
try:
    from qdrant_client import QdrantClient

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

# Check for Node2Vec availability (requires torch-cluster or pyg-lib)
# The import succeeds but Node2Vec fails at runtime without torch-cluster
try:
    from torch_geometric.nn import Node2Vec

    # Try to instantiate to catch runtime dependency issues
    import torch

    _test_edge = torch.tensor([[0], [1]], dtype=torch.long)
    _test_model = Node2Vec(_test_edge, embedding_dim=2, walk_length=1, context_size=1)
    NODE2VEC_AVAILABLE = True
    del _test_model, _test_edge
except (ImportError, Exception):
    NODE2VEC_AVAILABLE = False


@pytest.mark.unit
class TestNeuralGraphService:
    """Unit tests for NeuralGraphService."""

    def test_initialization(self):
        """Test service initialization with device parameter."""
        service = NeuralGraphService(device="cpu")

        assert service.device == "cpu"
        assert service.embedding_dim == 64
        assert service.walk_length == 20
        assert service.context_size == 10
        assert service.walks_per_node == 10
        assert service.num_epochs == 10
        assert service.batch_size == 128
        assert service.learning_rate == 0.01

    @pytest.mark.skipif(
        not NODE2VEC_AVAILABLE,
        reason="Requires torch-cluster or pyg-lib (Edge environment only)",
    )
    def test_training_loss_logging_every_5_epochs(self):
        """
        Test that training loss is logged every 5 epochs.

        Validates: Requirements 5.5

        NOTE: This test requires torch-cluster or pyg-lib to be installed.
        It will be skipped on Windows and run only in the Edge environment.
        """
        # Create a simple graph
        edge_index = torch.tensor([[0, 1, 2], [1, 2, 0]], dtype=torch.long)
        num_nodes = 3

        service = NeuralGraphService(device="cpu")

        # Capture stdout to check logging
        captured_output = io.StringIO()
        sys.stdout = captured_output

        try:
            embeddings = service.train_embeddings(
                edge_index=edge_index, num_nodes=num_nodes
            )

            output = captured_output.getvalue()

            # Check that epochs 5 and 10 are logged
            assert "Epoch 05:" in output, "Epoch 5 should be logged"
            assert "Epoch 10:" in output, "Epoch 10 should be logged"

            # Check that other epochs are not logged
            assert "Epoch 01:" not in output, "Epoch 1 should not be logged"
            assert "Epoch 02:" not in output, "Epoch 2 should not be logged"
            assert "Epoch 03:" not in output, "Epoch 3 should not be logged"

        finally:
            sys.stdout = sys.__stdout__

    @pytest.mark.skipif(
        not QDRANT_AVAILABLE, reason="Requires qdrant-client (Edge environment only)"
    )
    def test_batch_upload_to_qdrant(self):
        """
        Test batch upload to Qdrant with batch_size=100.

        Validates: Requirements 6.3

        NOTE: This test requires qdrant-client to be installed.
        It will be skipped on Windows and run only in the Edge environment.
        """
        # Create mock embeddings
        num_nodes = 250  # More than 2 batches
        embeddings = torch.randn(num_nodes, 64)
        file_paths = [f"file_{i}.py" for i in range(num_nodes)]
        repo_url = "github.com/test/repo"

        service = NeuralGraphService(device="cpu")

        # Mock Qdrant client and models at the import location
        with (
            patch(
                "app.modules.graph.neural_service.QdrantClient", create=True
            ) as mock_qdrant_class,
            patch(
                "app.modules.graph.neural_service.PointStruct", create=True
            ) as mock_point_struct,
            patch("app.modules.graph.neural_service.VectorParams", create=True),
            patch("app.modules.graph.neural_service.Distance", create=True),
        ):
            mock_client = MagicMock()
            mock_qdrant_class.return_value = mock_client

            # Mock PointStruct to return a mock object
            mock_point_struct.side_effect = lambda **kwargs: MagicMock(**kwargs)

            # Mock get_collection to raise exception (collection doesn't exist)
            mock_client.get_collection.side_effect = Exception("Collection not found")

            # Upload embeddings
            service.upload_embeddings(
                embeddings=embeddings, file_paths=file_paths, repo_url=repo_url
            )

            # Verify upsert was called multiple times (batches)
            assert mock_client.upsert.call_count == 3, (
                f"Expected 3 batch uploads (250/100), got {mock_client.upsert.call_count}"
            )

            # Verify batch sizes
            calls = mock_client.upsert.call_args_list
            assert len(calls[0][1]["points"]) == 100, (
                "First batch should have 100 points"
            )
            assert len(calls[1][1]["points"]) == 100, (
                "Second batch should have 100 points"
            )
            assert len(calls[2][1]["points"]) == 50, "Third batch should have 50 points"

    @pytest.mark.skipif(
        not QDRANT_AVAILABLE, reason="Requires qdrant-client (Edge environment only)"
    )
    def test_retry_logic_on_upload_failure(self):
        """
        Test retry logic with exponential backoff (3 attempts).

        Validates: Requirements 6.4

        NOTE: This test requires qdrant-client to be installed.
        It will be skipped on Windows and run only in the Edge environment.
        """
        # Create mock embeddings
        num_nodes = 10
        embeddings = torch.randn(num_nodes, 64)
        file_paths = [f"file_{i}.py" for i in range(num_nodes)]
        repo_url = "github.com/test/repo"

        service = NeuralGraphService(device="cpu")

        # Mock Qdrant client and models at the import location
        with (
            patch(
                "app.modules.graph.neural_service.QdrantClient", create=True
            ) as mock_qdrant_class,
            patch(
                "app.modules.graph.neural_service.PointStruct", create=True
            ) as mock_point_struct,
            patch("app.modules.graph.neural_service.VectorParams", create=True),
            patch("app.modules.graph.neural_service.Distance", create=True),
        ):
            mock_client = MagicMock()
            mock_qdrant_class.return_value = mock_client

            # Mock PointStruct to return a mock object
            mock_point_struct.side_effect = lambda **kwargs: MagicMock(**kwargs)

            # Mock get_collection to raise exception (collection doesn't exist)
            mock_client.get_collection.side_effect = Exception("Collection not found")

            # Mock upsert to fail twice, then succeed
            mock_client.upsert.side_effect = [
                Exception("Network error"),
                Exception("Network error"),
                None,  # Success on third attempt
            ]

            # Mock time.sleep to avoid actual delays
            with patch("app.modules.graph.neural_service.time.sleep"):
                # Upload embeddings
                service.upload_embeddings(
                    embeddings=embeddings, file_paths=file_paths, repo_url=repo_url
                )

            # Verify upsert was called 3 times (2 failures + 1 success)
            assert mock_client.upsert.call_count == 3, (
                f"Expected 3 attempts, got {mock_client.upsert.call_count}"
            )

    @pytest.mark.skipif(
        not QDRANT_AVAILABLE, reason="Requires qdrant-client (Edge environment only)"
    )
    def test_retry_logic_exhaustion(self):
        """
        Test that retry logic raises exception after 3 failed attempts.

        Validates: Requirements 6.4

        NOTE: This test requires qdrant-client to be installed.
        It will be skipped on Windows and run only in the Edge environment.
        """
        # Create mock embeddings
        num_nodes = 10
        embeddings = torch.randn(num_nodes, 64)
        file_paths = [f"file_{i}.py" for i in range(num_nodes)]
        repo_url = "github.com/test/repo"

        service = NeuralGraphService(device="cpu")

        # Mock Qdrant client and models at the import location
        with (
            patch(
                "app.modules.graph.neural_service.QdrantClient", create=True
            ) as mock_qdrant_class,
            patch(
                "app.modules.graph.neural_service.PointStruct", create=True
            ) as mock_point_struct,
            patch("app.modules.graph.neural_service.VectorParams", create=True),
            patch("app.modules.graph.neural_service.Distance", create=True),
        ):
            mock_client = MagicMock()
            mock_qdrant_class.return_value = mock_client

            # Mock PointStruct to return a mock object
            mock_point_struct.side_effect = lambda **kwargs: MagicMock(**kwargs)

            # Mock get_collection to raise exception (collection doesn't exist)
            mock_client.get_collection.side_effect = Exception("Collection not found")

            # Mock upsert to always fail
            mock_client.upsert.side_effect = Exception("Network error")

            # Mock time.sleep to avoid actual delays
            with patch("app.modules.graph.neural_service.time.sleep"):
                # Upload should raise exception after 3 attempts
                with pytest.raises(Exception, match="Network error"):
                    service.upload_embeddings(
                        embeddings=embeddings, file_paths=file_paths, repo_url=repo_url
                    )

            # Verify upsert was called 3 times
            assert mock_client.upsert.call_count == 3, (
                f"Expected 3 attempts, got {mock_client.upsert.call_count}"
            )

    @pytest.mark.skipif(
        not QDRANT_AVAILABLE, reason="Requires qdrant-client (Edge environment only)"
    )
    def test_collection_creation(self):
        """
        Test that collection is created if it doesn't exist.

        NOTE: This test requires qdrant-client to be installed.
        It will be skipped on Windows and run only in the Edge environment.
        """
        # Create mock embeddings
        num_nodes = 5
        embeddings = torch.randn(num_nodes, 64)
        file_paths = [f"file_{i}.py" for i in range(num_nodes)]
        repo_url = "github.com/test/repo"

        service = NeuralGraphService(device="cpu")

        # Mock Qdrant client and models at the import location
        with (
            patch(
                "app.modules.graph.neural_service.QdrantClient", create=True
            ) as mock_qdrant_class,
            patch(
                "app.modules.graph.neural_service.PointStruct", create=True
            ) as mock_point_struct,
            patch(
                "app.modules.graph.neural_service.VectorParams", create=True
            ) as mock_vector_params,
            patch("app.modules.graph.neural_service.Distance", create=True),
        ):
            mock_client = MagicMock()
            mock_qdrant_class.return_value = mock_client

            # Mock PointStruct to return a mock object
            mock_point_struct.side_effect = lambda **kwargs: MagicMock(**kwargs)

            # Mock VectorParams to return a mock with size attribute
            mock_vector_params_instance = MagicMock()
            mock_vector_params_instance.size = 64
            mock_vector_params.return_value = mock_vector_params_instance

            # Mock get_collection to raise exception (collection doesn't exist)
            mock_client.get_collection.side_effect = Exception("Collection not found")

            # Upload embeddings
            service.upload_embeddings(
                embeddings=embeddings, file_paths=file_paths, repo_url=repo_url
            )

            # Verify create_collection was called
            assert mock_client.create_collection.called, "Collection should be created"

            # Verify collection name
            call_args = mock_client.create_collection.call_args
            assert call_args[1]["collection_name"] == "code_structure_embeddings"

    @pytest.mark.skipif(
        not QDRANT_AVAILABLE, reason="Requires qdrant-client (Edge environment only)"
    )
    def test_existing_collection_not_recreated(self):
        """
        Test that existing collection is not recreated.

        NOTE: This test requires qdrant-client to be installed.
        It will be skipped on Windows and run only in the Edge environment.
        """
        # Create mock embeddings
        num_nodes = 5
        embeddings = torch.randn(num_nodes, 64)
        file_paths = [f"file_{i}.py" for i in range(num_nodes)]
        repo_url = "github.com/test/repo"

        service = NeuralGraphService(device="cpu")

        # Mock Qdrant client and models at the import location
        with (
            patch(
                "app.modules.graph.neural_service.QdrantClient", create=True
            ) as mock_qdrant_class,
            patch(
                "app.modules.graph.neural_service.PointStruct", create=True
            ) as mock_point_struct,
            patch("app.modules.graph.neural_service.VectorParams", create=True),
            patch("app.modules.graph.neural_service.Distance", create=True),
        ):
            mock_client = MagicMock()
            mock_qdrant_class.return_value = mock_client

            # Mock PointStruct to return a mock object
            mock_point_struct.side_effect = lambda **kwargs: MagicMock(**kwargs)

            # Mock get_collection to succeed (collection exists)
            mock_client.get_collection.return_value = {
                "name": "code_structure_embeddings"
            }

            # Upload embeddings
            service.upload_embeddings(
                embeddings=embeddings, file_paths=file_paths, repo_url=repo_url
            )

            # Verify create_collection was NOT called
            assert not mock_client.create_collection.called, (
                "Collection should not be recreated if it exists"
            )
