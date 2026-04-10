"""
Property-based tests for Neural Graph Service.

These tests verify universal properties that should hold for all valid inputs.
"""

import pytest
import torch
from hypothesis import given, strategies as st, settings
from unittest.mock import Mock, patch, MagicMock

# Skip tests if torch_geometric or required dependencies are not installed
try:
    from app.modules.graph.neural_service import NeuralGraphService

    # Try to import the required packages
    import torch_cluster
    import torch_scatter

    TORCH_GEOMETRIC_AVAILABLE = True
except ImportError as e:
    TORCH_GEOMETRIC_AVAILABLE = False
    pytestmark = pytest.mark.skip(
        reason=f"torch_geometric dependencies not installed: {e}"
    )


# Hypothesis settings for property tests
@settings(max_examples=10, deadline=None)
@pytest.mark.property
@pytest.mark.feature("phase19-hybrid-edge-cloud-orchestration")
@given(
    num_nodes=st.integers(min_value=2, max_value=100),
    num_edges=st.integers(min_value=1, max_value=200),
)
def test_property_6_embedding_dimensionality_invariant(num_nodes, num_edges):
    """
    Property 6: Embedding dimensionality invariant

    For any graph with N nodes, exactly N embeddings of 64 dimensions are generated.

    Validates: Requirements 5.2
    """
    # Create a valid edge_index tensor
    # Ensure edges reference valid node indices
    edges = []
    for _ in range(num_edges):
        src = torch.randint(0, num_nodes, (1,)).item()
        dst = torch.randint(0, num_nodes, (1,)).item()
        edges.append([src, dst])

    edge_index = torch.tensor(edges, dtype=torch.long).t()

    # Initialize service with CPU device for testing
    service = NeuralGraphService(device="cpu")

    # Train embeddings
    embeddings = service.train_embeddings(edge_index=edge_index, num_nodes=num_nodes)

    # Verify property: exactly N embeddings of 64 dimensions
    assert embeddings.shape[0] == num_nodes, (
        f"Expected {num_nodes} embeddings, got {embeddings.shape[0]}"
    )
    assert embeddings.shape[1] == 64, (
        f"Expected 64 dimensions, got {embeddings.shape[1]}"
    )


@settings(max_examples=10, deadline=None)
@pytest.mark.property
@pytest.mark.feature("phase19-hybrid-edge-cloud-orchestration")
@given(
    num_nodes=st.integers(min_value=2, max_value=50),
    num_edges=st.integers(min_value=1, max_value=100),
)
def test_property_7_embedding_device_location(num_nodes, num_edges):
    """
    Property 7: Embedding device location

    For any completed training run, all returned embeddings are CPU tensors.

    Validates: Requirements 5.6
    """
    # Create a valid edge_index tensor
    edges = []
    for _ in range(num_edges):
        src = torch.randint(0, num_nodes, (1,)).item()
        dst = torch.randint(0, num_nodes, (1,)).item()
        edges.append([src, dst])

    edge_index = torch.tensor(edges, dtype=torch.long).t()

    # Test with both CPU and CUDA (if available)
    devices = ["cpu"]
    if torch.cuda.is_available():
        devices.append("cuda")

    for device in devices:
        service = NeuralGraphService(device=device)
        embeddings = service.train_embeddings(
            edge_index=edge_index, num_nodes=num_nodes
        )

        # Verify property: embeddings are on CPU
        assert embeddings.device.type == "cpu", (
            f"Expected CPU tensor, got {embeddings.device.type}"
        )


@settings(max_examples=10, deadline=None)
@pytest.mark.property
@pytest.mark.feature("phase19-hybrid-edge-cloud-orchestration")
@given(
    num_nodes=st.integers(min_value=2, max_value=30),
    num_edges=st.integers(min_value=1, max_value=60),
)
def test_property_8_embedding_upload_completeness(num_nodes, num_edges):
    """
    Property 8: Embedding upload completeness

    For any set of generated embeddings, all embeddings are uploaded to Qdrant
    with payloads containing file_path and repo_url fields.

    Validates: Requirements 6.1, 6.2
    """
    # Create a valid edge_index tensor
    edges = []
    for _ in range(num_edges):
        src = torch.randint(0, num_nodes, (1,)).item()
        dst = torch.randint(0, num_nodes, (1,)).item()
        edges.append([src, dst])

    edge_index = torch.tensor(edges, dtype=torch.long).t()

    # Initialize service
    service = NeuralGraphService(device="cpu")

    # Generate embeddings
    embeddings = service.train_embeddings(edge_index=edge_index, num_nodes=num_nodes)

    # Create mock file paths
    file_paths = [f"file_{i}.py" for i in range(num_nodes)]
    repo_url = "github.com/test/repo"

    # Mock Qdrant client
    with patch("app.services.neural_graph.QdrantClient") as mock_qdrant_class:
        mock_client = MagicMock()
        mock_qdrant_class.return_value = mock_client

        # Mock get_collection to raise exception (collection doesn't exist)
        mock_client.get_collection.side_effect = Exception("Collection not found")

        # Upload embeddings
        service.upload_embeddings(
            embeddings=embeddings, file_paths=file_paths, repo_url=repo_url
        )

        # Verify create_collection was called
        assert mock_client.create_collection.called, "Collection should be created"

        # Verify upsert was called
        assert mock_client.upsert.called, "Embeddings should be uploaded"

        # Get all upsert calls
        upsert_calls = mock_client.upsert.call_args_list

        # Collect all uploaded points
        all_points = []
        for call in upsert_calls:
            points = call[1]["points"]
            all_points.extend(points)

        # Verify property: all embeddings uploaded with required fields
        assert len(all_points) == num_nodes, (
            f"Expected {num_nodes} points uploaded, got {len(all_points)}"
        )

        for point in all_points:
            assert "file_path" in point.payload, "Missing file_path in payload"
            assert "repo_url" in point.payload, "Missing repo_url in payload"
            assert point.payload["repo_url"] == repo_url, "Incorrect repo_url"
            assert point.payload["file_path"] in file_paths, "Invalid file_path"
