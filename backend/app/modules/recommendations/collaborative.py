"""
Collaborative Filtering Service for Hybrid Recommendation Engine.

This service implements Neural Collaborative Filtering (NCF) using PyTorch.
The NCF model learns user-item interactions from implicit feedback signals
and predicts affinity scores for user-resource pairs.

Architecture:
- User Embedding (64-dim) + Item Embedding (64-dim)
- Concatenation → MLP (128→64→32→1)
- ReLU activations, Sigmoid output

Related files:
- app.database.models: UserInteraction, Resource models
- app.services.user_profile_service: Interaction tracking
- app.services.hybrid_recommendation_service: Uses NCF predictions
"""

import logging
import os
from typing import Dict, List, Optional

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None  # type: ignore
    nn = None  # type: ignore
    optim = None  # type: ignore

from sqlalchemy.orm import Session

from app.database.models import UserInteraction

logger = logging.getLogger(__name__)


class NCFModel(nn.Module):
    """
    Neural Collaborative Filtering model.

    Combines user and item embeddings through a multi-layer perceptron
    to predict user-item affinity scores.

    Architecture:
    - User Embedding: 64 dimensions
    - Item Embedding: 64 dimensions
    - MLP: 128 → 64 → 32 → 1
    - Activations: ReLU
    - Output: Sigmoid (0-1 score)
    """

    def __init__(self, num_users: int, num_items: int, embedding_dim: int = 64):
        """
        Initialize NCF model.

        Args:
            num_users: Number of unique users
            num_items: Number of unique items (resources)
            embedding_dim: Dimension of user/item embeddings (default: 64)
        """
        super(NCFModel, self).__init__()

        self.num_users = num_users
        self.num_items = num_items
        self.embedding_dim = embedding_dim

        # User and item embeddings
        self.user_embedding = nn.Embedding(num_users, embedding_dim)
        self.item_embedding = nn.Embedding(num_items, embedding_dim)

        # MLP layers
        self.fc1 = nn.Linear(embedding_dim * 2, 128)
        self.fc2 = nn.Linear(128, 64)
        self.fc3 = nn.Linear(64, 32)
        self.fc4 = nn.Linear(32, 1)

        # Activation functions
        self.relu = nn.ReLU()
        self.sigmoid = nn.Sigmoid()

        # Initialize weights
        self._init_weights()

    def _init_weights(self):
        """Initialize model weights using Xavier initialization."""
        nn.init.xavier_uniform_(self.user_embedding.weight)
        nn.init.xavier_uniform_(self.item_embedding.weight)
        nn.init.xavier_uniform_(self.fc1.weight)
        nn.init.xavier_uniform_(self.fc2.weight)
        nn.init.xavier_uniform_(self.fc3.weight)
        nn.init.xavier_uniform_(self.fc4.weight)

    def forward(self, user_ids: torch.Tensor, item_ids: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through the network.

        Args:
            user_ids: Tensor of user indices
            item_ids: Tensor of item indices

        Returns:
            Predicted affinity scores (0-1)
        """
        # Get embeddings
        user_emb = self.user_embedding(user_ids)
        item_emb = self.item_embedding(item_ids)

        # Concatenate embeddings
        x = torch.cat([user_emb, item_emb], dim=1)

        # MLP layers with ReLU activations
        x = self.relu(self.fc1(x))
        x = self.relu(self.fc2(x))
        x = self.relu(self.fc3(x))
        x = self.fc4(x)

        # Sigmoid output
        output = self.sigmoid(x)

        return output.squeeze()


class CollaborativeFilteringService:
    """
    Service for Neural Collaborative Filtering recommendations.

    Provides methods for:
    - Model training on interaction history
    - Score prediction for user-item pairs
    - Batch recommendation generation
    - Model checkpoint management
    """

    def __init__(self, db: Session, model_path: str = "models/ncf_model.pt"):
        """
        Initialize the CollaborativeFilteringService.

        Args:
            db: SQLAlchemy database session
            model_path: Path to save/load model checkpoint
        """
        self.db = db
        self.model_path = model_path
        self.model: Optional[NCFModel] = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Mapping dictionaries for user/item IDs to indices
        self.user_id_to_idx: Dict[str, int] = {}
        self.item_id_to_idx: Dict[str, int] = {}
        self.idx_to_user_id: Dict[int, str] = {}
        self.idx_to_item_id: Dict[int, str] = {}

        logger.info(
            f"CollaborativeFilteringService initialized with device: {self.device}"
        )

        # Try to load existing model
        self._load_model()

    def _load_model(self) -> bool:
        """
        Load model checkpoint from disk.

        Returns:
            True if model loaded successfully, False otherwise
        """
        try:
            if not os.path.exists(self.model_path):
                logger.info(f"No model checkpoint found at {self.model_path}")
                return False

            checkpoint = torch.load(self.model_path, map_location=self.device)

            # Restore mappings
            self.user_id_to_idx = checkpoint["user_id_to_idx"]
            self.item_id_to_idx = checkpoint["item_id_to_idx"]
            self.idx_to_user_id = checkpoint["idx_to_user_id"]
            self.idx_to_item_id = checkpoint["idx_to_item_id"]

            # Create model with saved dimensions
            num_users = len(self.user_id_to_idx)
            num_items = len(self.item_id_to_idx)
            embedding_dim = checkpoint.get("embedding_dim", 64)

            self.model = NCFModel(num_users, num_items, embedding_dim)
            self.model.load_state_dict(checkpoint["model_state_dict"])
            self.model.to(self.device)
            self.model.eval()

            logger.info(
                f"Loaded NCF model from {self.model_path} (users={num_users}, items={num_items})"
            )
            return True

        except Exception as e:
            logger.error(f"Error loading model checkpoint: {str(e)}", exc_info=True)
            return False

    def _save_model(self) -> bool:
        """
        Save model checkpoint to disk.

        Returns:
            True if model saved successfully, False otherwise
        """
        try:
            if self.model is None:
                logger.warning("No model to save")
                return False

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)

            # Save checkpoint
            checkpoint = {
                "model_state_dict": self.model.state_dict(),
                "user_id_to_idx": self.user_id_to_idx,
                "item_id_to_idx": self.item_id_to_idx,
                "idx_to_user_id": self.idx_to_user_id,
                "idx_to_item_id": self.idx_to_item_id,
                "embedding_dim": self.model.embedding_dim,
                "num_users": self.model.num_users,
                "num_items": self.model.num_items,
            }

            torch.save(checkpoint, self.model_path)
            logger.info(f"Saved NCF model to {self.model_path}")
            return True

        except Exception as e:
            logger.error(f"Error saving model checkpoint: {str(e)}", exc_info=True)
            return False

    def train_model(
        self, epochs: int = 10, batch_size: int = 256, learning_rate: float = 0.001
    ) -> Dict:
        """
        Train NCF model on positive interactions with negative sampling.

        Queries interactions with interaction_strength > 0.5 as positive training data.
        Implements negative sampling by randomly selecting non-interacted items.
        Uses interaction_strength as continuous feedback signal.

        Args:
            epochs: Number of training epochs (default: 10)
            batch_size: Batch size for training (default: 256)
            learning_rate: Learning rate for Adam optimizer (default: 0.001)

        Returns:
            Dictionary with training metrics (loss history, final loss)
        """
        try:
            logger.info(
                f"Starting NCF model training (epochs={epochs}, batch_size={batch_size})"
            )

            # Query positive interactions (interaction_strength > 0.5 indicates positive)
            interactions = (
                self.db.query(UserInteraction)
                .filter(UserInteraction.interaction_strength > 0.5)
                .all()
            )

            if len(interactions) < 10:
                logger.warning(
                    f"Insufficient training data: {len(interactions)} interactions"
                )
                return {
                    "error": "Insufficient training data",
                    "num_interactions": len(interactions),
                }

            logger.info(f"Found {len(interactions)} positive interactions for training")

            # Build user and item mappings
            unique_users = set()
            unique_items = set()

            for interaction in interactions:
                unique_users.add(str(interaction.user_id))
                unique_items.add(str(interaction.resource_id))

            # Create ID to index mappings
            self.user_id_to_idx = {
                user_id: idx for idx, user_id in enumerate(sorted(unique_users))
            }
            self.item_id_to_idx = {
                item_id: idx for idx, item_id in enumerate(sorted(unique_items))
            }
            self.idx_to_user_id = {
                idx: user_id for user_id, idx in self.user_id_to_idx.items()
            }
            self.idx_to_item_id = {
                idx: item_id for item_id, idx in self.item_id_to_idx.items()
            }

            num_users = len(self.user_id_to_idx)
            num_items = len(self.item_id_to_idx)

            logger.info(f"Training data: {num_users} users, {num_items} items")

            # Create model
            self.model = NCFModel(num_users, num_items, embedding_dim=64)
            self.model.to(self.device)

            # Prepare training data
            user_indices = []
            item_indices = []
            labels = []

            for interaction in interactions:
                user_idx = self.user_id_to_idx[str(interaction.user_id)]
                item_idx = self.item_id_to_idx[str(interaction.resource_id)]

                user_indices.append(user_idx)
                item_indices.append(item_idx)
                labels.append(interaction.interaction_strength)

            # Negative sampling: sample non-interacted items
            user_item_set = set(zip(user_indices, item_indices))

            for user_idx, item_idx in list(user_item_set):
                # Sample negative item
                neg_item_idx = np.random.randint(0, num_items)
                while (user_idx, neg_item_idx) in user_item_set:
                    neg_item_idx = np.random.randint(0, num_items)

                user_indices.append(user_idx)
                item_indices.append(neg_item_idx)
                labels.append(0.0)  # Negative sample

            # Convert to tensors
            user_tensor = torch.LongTensor(user_indices).to(self.device)
            item_tensor = torch.LongTensor(item_indices).to(self.device)
            label_tensor = torch.FloatTensor(labels).to(self.device)

            # Training setup
            optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)
            criterion = nn.BCELoss()

            # Training loop
            self.model.train()
            loss_history = []

            for epoch in range(epochs):
                epoch_loss = 0.0
                num_batches = 0

                # Shuffle data
                perm = torch.randperm(len(user_tensor))
                user_tensor = user_tensor[perm]
                item_tensor = item_tensor[perm]
                label_tensor = label_tensor[perm]

                # Mini-batch training
                for i in range(0, len(user_tensor), batch_size):
                    batch_users = user_tensor[i : i + batch_size]
                    batch_items = item_tensor[i : i + batch_size]
                    batch_labels = label_tensor[i : i + batch_size]

                    # Forward pass
                    predictions = self.model(batch_users, batch_items)
                    loss = criterion(predictions, batch_labels)

                    # Backward pass
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()

                    epoch_loss += loss.item()
                    num_batches += 1

                avg_loss = epoch_loss / num_batches
                loss_history.append(avg_loss)

                if (epoch + 1) % 2 == 0:
                    logger.info(f"Epoch {epoch + 1}/{epochs}, Loss: {avg_loss:.4f}")

            # Save model
            self.model.eval()
            self._save_model()

            logger.info(f"Training complete. Final loss: {loss_history[-1]:.4f}")

            return {
                "success": True,
                "epochs": epochs,
                "final_loss": loss_history[-1],
                "loss_history": loss_history,
                "num_users": num_users,
                "num_items": num_items,
                "num_interactions": len(interactions),
            }

        except Exception as e:
            logger.error(f"Error in train_model: {str(e)}", exc_info=True)
            return {"error": str(e)}

    def predict_score(self, user_id: str, resource_id: str) -> Optional[float]:
        """
        Predict affinity score for a user-resource pair.

        Args:
            user_id: User UUID as string
            resource_id: Resource UUID as string

        Returns:
            Predicted score (0-1) or None if model unavailable or IDs not in training data
        """
        try:
            if self.model is None:
                logger.warning("Model not trained or loaded")
                return None

            # Check if user and item are in training data
            if user_id not in self.user_id_to_idx:
                logger.debug(f"User {user_id} not in training data")
                return None

            if resource_id not in self.item_id_to_idx:
                logger.debug(f"Resource {resource_id} not in training data")
                return None

            # Get indices
            user_idx = self.user_id_to_idx[user_id]
            item_idx = self.item_id_to_idx[resource_id]

            # Predict
            self.model.eval()
            with torch.no_grad():
                user_tensor = torch.LongTensor([user_idx]).to(self.device)
                item_tensor = torch.LongTensor([item_idx]).to(self.device)

                score = self.model(user_tensor, item_tensor)

                # Convert to Python float
                return float(score.cpu().item())

        except Exception as e:
            logger.error(f"Error in predict_score: {str(e)}", exc_info=True)
            return None

    def get_top_recommendations(
        self, user_id: str, candidate_ids: List[str], limit: int = 20
    ) -> List[Dict]:
        """
        Get top recommendations for a user from candidate resources.

        Batch scores all candidates and returns top-k by predicted score.

        Args:
            user_id: User UUID as string
            candidate_ids: List of candidate resource UUIDs as strings
            limit: Number of recommendations to return (default: 20)

        Returns:
            List of dicts with resource_id and score, sorted by score descending
        """
        try:
            if self.model is None:
                logger.warning("Model not trained or loaded")
                return []

            if user_id not in self.user_id_to_idx:
                logger.debug(f"User {user_id} not in training data")
                return []

            user_idx = self.user_id_to_idx[user_id]

            # Filter candidates to those in training data
            valid_candidates = [
                cid for cid in candidate_ids if cid in self.item_id_to_idx
            ]

            if not valid_candidates:
                logger.debug(f"No valid candidates for user {user_id}")
                return []

            # Batch prediction
            self.model.eval()
            with torch.no_grad():
                user_indices = [user_idx] * len(valid_candidates)
                item_indices = [self.item_id_to_idx[cid] for cid in valid_candidates]

                user_tensor = torch.LongTensor(user_indices).to(self.device)
                item_tensor = torch.LongTensor(item_indices).to(self.device)

                scores = self.model(user_tensor, item_tensor)
                scores = scores.cpu().numpy()

            # Create results
            results = [
                {"resource_id": cid, "score": float(score)}
                for cid, score in zip(valid_candidates, scores)
            ]

            # Sort by score descending
            results.sort(key=lambda x: x["score"], reverse=True)

            # Return top-k
            return results[:limit]

        except Exception as e:
            logger.error(f"Error in get_top_recommendations: {str(e)}", exc_info=True)
            return []
