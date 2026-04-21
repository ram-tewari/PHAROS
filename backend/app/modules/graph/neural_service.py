"""
Neural Graph Service for generating structural embeddings using PyTorch Geometric.

This service implements Node2Vec algorithm to create embeddings based on graph structure
rather than text content. This captures code organization and dependencies.
"""

import os
import time
import logging
import torch
from torch_geometric.nn import Node2Vec
from typing import List

logger = logging.getLogger(__name__)


class NeuralGraphService:
    """
    Service for generating structural embeddings using PyTorch Geometric.

    Implements Node2Vec algorithm to create embeddings based on graph structure
    rather than text content. This captures code organization and dependencies.
    """

    def __init__(self, device: str = "cuda"):
        """
        Initialize Neural Graph Service.

        Args:
            device: Device to use for training ("cuda" or "cpu")
        """
        self.device = device

        # Hyperparameters (optimized for code graphs)
        self.embedding_dim = 64  # Matryoshka-style compact embeddings
        self.walk_length = 20  # Longer walks for deep dependencies
        self.context_size = 10  # Context window for skip-gram
        self.walks_per_node = 10  # Multiple walks per node
        self.num_epochs = 10  # Fast training
        self.batch_size = 128
        self.learning_rate = 0.01

    def train_embeddings(
        self, edge_index: torch.Tensor, num_nodes: int
    ) -> torch.Tensor:
        """
        Train Node2Vec model on dependency graph.

        Args:
            edge_index: Edge list tensor of shape [2, num_edges]
            num_nodes: Total number of nodes in graph

        Returns:
            Embedding tensor of shape [num_nodes, embedding_dim] on CPU
        """
        logger.info(
            f"Training Node2Vec on {self.device} - Nodes: {num_nodes}, Edges: {edge_index.shape[1]}"
        )

        # Initialize Node2Vec model
        model = Node2Vec(
            edge_index=edge_index,
            embedding_dim=self.embedding_dim,
            walk_length=self.walk_length,
            context_size=self.context_size,
            walks_per_node=self.walks_per_node,
            sparse=True,  # Use sparse gradients for efficiency
        ).to(self.device)

        # Create data loader
        loader = model.loader(
            batch_size=self.batch_size,
            shuffle=True,
            num_workers=0,  # Single worker for GPU
        )

        # Optimizer (SparseAdam for sparse gradients)
        optimizer = torch.optim.SparseAdam(
            list(model.parameters()), lr=self.learning_rate
        )

        # Training loop
        model.train()
        for epoch in range(1, self.num_epochs + 1):
            total_loss = 0

            for pos_rw, neg_rw in loader:
                optimizer.zero_grad()

                # Compute loss
                loss = model.loss(pos_rw.to(self.device), neg_rw.to(self.device))

                loss.backward()
                optimizer.step()
                total_loss += loss.item()

            # Log progress every 5 epochs
            if epoch % 5 == 0:
                avg_loss = total_loss / len(loader)
                logger.debug(f"Epoch {epoch:02d}: Loss = {avg_loss:.4f}")

        # Extract embeddings and move to CPU
        embeddings = model.embedding.weight.data.cpu()

        logger.info(f"Training complete. Generated {num_nodes} embeddings.")
        return embeddings

    def upload_embeddings(
        self, embeddings: torch.Tensor, file_paths: List[str], repo_url: str
    ):
        """
        Upload embeddings to Qdrant Cloud.

        Args:
            embeddings: Tensor of shape [num_files, embedding_dim]
            file_paths: List of file paths corresponding to embeddings
            repo_url: Repository URL for metadata
        """
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct, Distance, VectorParams

        # Initialize Qdrant client
        client = QdrantClient(
            url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY")
        )

        collection_name = "code_structure_embeddings"

        # Create collection if it doesn't exist
        try:
            client.get_collection(collection_name)
        except Exception:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=self.embedding_dim, distance=Distance.COSINE
                ),
            )

        # Prepare points for batch upload
        points = []
        for idx, (embedding, file_path) in enumerate(zip(embeddings, file_paths)):
            point = PointStruct(
                id=idx,
                vector=embedding.numpy().tolist(),
                payload={
                    "file_path": file_path,
                    "repo_url": repo_url,
                    "embedding_type": "structural",
                    "model": "node2vec",
                },
            )
            points.append(point)

        # Batch upload with retry logic
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]

            # Retry up to 3 times with exponential backoff
            for attempt in range(3):
                try:
                    client.upsert(collection_name=collection_name, points=batch)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    logger.warning(
                        f"Retry {attempt + 1}/3 for batch {i // batch_size + 1}"
                    )
                    time.sleep(2**attempt)  # Exponential backoff

        logger.info(f"Uploaded {len(points)} embeddings to Qdrant")
