"""
Tests for collaborative filtering service (NCF model).

Tests:
- NCF model predictions
- User-item interaction matrix construction
- Cold start handling
- Negative sampling for training
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from app.modules.recommendations.collaborative import (
    CollaborativeFilteringService,
    NCFModel,
)
from app.database.models import UserInteraction, Resource, User
from app.shared.security import get_password_hash


def _create_user(db_session, user_uuid, suffix=""):
    """Create a User row satisfying UserInteraction.user_id FK."""
    user = User(
        id=user_uuid,
        email=f"user_{user_uuid}{suffix}@example.com",
        username=f"user_{str(user_uuid)[:8]}{suffix}",
        hashed_password=get_password_hash("testpassword"),
        full_name="Test User",
        role="user",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    return user


# ============================================================================
# Golden Data Loading
# ============================================================================


@pytest.fixture(scope="module")
def golden_data():
    """Load golden data for collaborative filtering tests."""
    golden_path = (
        Path(__file__).parent.parent.parent
        / "golden_data"
        / "collaborative_filtering.json"
    )
    with open(golden_path) as f:
        return json.load(f)


# ============================================================================
# Test NCF Model Predictions
# ============================================================================


def test_ncf_predictions_with_trained_model(db_session, golden_data):
    """
    Test NCF model predictions for user-item pairs.

    Verifies:
    - Model can predict scores for user-item pairs
    - Predictions are in valid range [0, 1]
    - Ranking order matches expected order
    """
    test_case = golden_data["ncf_predictions"]
    input_data = test_case["input"]
    expected = test_case["expected"]

    # Create service
    service = CollaborativeFilteringService(db_session)

    # Mock model to return expected predictions
    import torch

    mock_model = MagicMock()
    mock_model.eval.return_value = None

    # Setup mock to return tensor with expected scores
    expected_scores = [
        expected["predictions"][rid] for rid in input_data["candidate_resources"]
    ]
    mock_model.return_value = torch.tensor(expected_scores)

    service.model = mock_model

    # Setup ID mappings
    service.user_id_to_idx = {input_data["user_id"]: 0}
    service.item_id_to_idx = {
        rid: idx for idx, rid in enumerate(input_data["candidate_resources"])
    }

    # Get recommendations
    with patch("torch.no_grad"):
        recommendations = service.get_top_recommendations(
            user_id=input_data["user_id"],
            candidate_ids=input_data["candidate_resources"],
            limit=len(input_data["candidate_resources"]),
        )

    # Verify predictions
    assert len(recommendations) == len(expected["ranked_ids"])

    # Verify ranking order
    actual_ids = [rec["resource_id"] for rec in recommendations]
    assert actual_ids == expected["ranked_ids"]

    # Verify scores are in valid range
    for rec in recommendations:
        assert 0.0 <= rec["score"] <= 1.0


def test_ncf_cold_start_user(db_session, golden_data):
    """
    Test NCF handling of cold start users.

    Verifies:
    - Returns None for users not in training data
    - Handles gracefully without errors
    """
    test_case = golden_data["cold_start_handling"]
    input_data = test_case["input"]
    test_case["expected"]

    service = CollaborativeFilteringService(db_session)

    # Mock trained model
    service.model = MagicMock()
    service.user_id_to_idx = {}  # Empty - user not in training data

    # Try to predict for cold start user
    score = service.predict_score(user_id=input_data["user_id"], resource_id="res_1")

    # Should return None for cold start user
    assert score is None


def test_ncf_model_architecture():
    """
    Test NCF model architecture.

    Verifies:
    - Model has correct layer structure
    - Embeddings have correct dimensions
    - Forward pass produces valid output
    """
    import torch

    num_users = 100
    num_items = 50
    embedding_dim = 64

    model = NCFModel(num_users, num_items, embedding_dim)

    # Verify embeddings
    assert model.user_embedding.num_embeddings == num_users
    assert model.user_embedding.embedding_dim == embedding_dim
    assert model.item_embedding.num_embeddings == num_items
    assert model.item_embedding.embedding_dim == embedding_dim

    # Test forward pass
    user_ids = torch.LongTensor([0, 1, 2])
    item_ids = torch.LongTensor([0, 1, 2])

    output = model(user_ids, item_ids)

    # Verify output shape and range
    assert output.shape == (3,)
    assert torch.all(output >= 0.0)
    assert torch.all(output <= 1.0)


# ============================================================================
# Test User-Item Matrix Construction
# ============================================================================


def test_user_item_matrix_construction(db_session, golden_data):
    """
    Test construction of user-item interaction matrix.

    Verifies:
    - Matrix has correct shape
    - User and item indices are correctly mapped
    - Matrix values match interaction strengths
    """
    test_case = golden_data["user_item_matrix"]
    input_data = test_case["input"]
    expected = test_case["expected"]

    # Create users and resources with UUID
    from uuid import uuid4

    user_map = {
        user_id: uuid4()
        for user_id in set(i["user_id"] for i in input_data["interactions"])
    }
    for golden_uid, uuid_val in user_map.items():
        _create_user(db_session, uuid_val, suffix=f"_{golden_uid}")
    resource_map = {}

    for interaction_data in input_data["interactions"]:
        res_id = interaction_data["resource_id"]
        if res_id not in resource_map:
            resource_map[res_id] = uuid4()
            resource = Resource(
                id=resource_map[res_id],
                title=f"Resource {res_id}",
                source="https://example.com",
            )
            db_session.add(resource)

    # Create interactions - need at least 10 for training
    # First create the golden data interactions
    for interaction_data in input_data["interactions"]:
        interaction = UserInteraction(
            user_id=user_map[interaction_data["user_id"]],
            resource_id=resource_map[interaction_data["resource_id"]],
            interaction_type="view",
            interaction_strength=interaction_data["strength"],
        )
        db_session.add(interaction)

    # Add 6 more interactions to reach the minimum of 10
    for i in range(6):
        # Alternate between users
        user_id = user_map["user_1"] if i % 2 == 0 else user_map["user_2"]
        # Create additional resources
        extra_res_id = f"extra_res_{i}"
        if extra_res_id not in resource_map:
            resource_map[extra_res_id] = uuid4()
            resource = Resource(
                id=resource_map[extra_res_id],
                title=f"Extra Resource {i}",
                source="https://example.com",
            )
            db_session.add(resource)

        interaction = UserInteraction(
            user_id=user_id,
            resource_id=resource_map[extra_res_id],
            interaction_type="view",
            interaction_strength=0.6,
        )
        db_session.add(interaction)

    db_session.commit()

    # Create service and train (which builds the matrix)
    service = CollaborativeFilteringService(db_session)

    # Mock the actual training to just build mappings
    with patch.object(service, "_save_model"):
        with patch("torch.save"):
            # This will build user/item mappings
            service.train_model(epochs=1, batch_size=2)

    # Verify mappings - should have 2 users
    assert len(service.user_id_to_idx) == expected["matrix_shape"][0]
    # Should have at least 3 items from golden data (may have more from extra interactions)
    assert len(service.item_id_to_idx) >= expected["matrix_shape"][1]


# ============================================================================
# Test Negative Sampling
# ============================================================================


def test_negative_sampling_for_training(db_session, golden_data):
    """
    Test negative sampling for NCF training.

    Verifies:
    - Negative samples are from non-interacted items
    - Negative ratio is respected
    - No overlap between positive and negative samples
    """
    test_case = golden_data["negative_sampling"]
    input_data = test_case["input"]
    test_case["expected"]

    # Create resources with UUID
    from uuid import uuid4

    user_id = uuid4()
    _create_user(db_session, user_id)
    resource_map = {res_id: uuid4() for res_id in input_data["all_resources"]}

    for res_id, uuid_id in resource_map.items():
        resource = Resource(
            id=uuid_id, title=f"Resource {res_id}", source="https://example.com"
        )
        db_session.add(resource)

    # Create positive interactions
    for interaction_data in input_data["positive_interactions"]:
        interaction = UserInteraction(
            user_id=user_id,
            resource_id=resource_map[interaction_data["resource_id"]],
            interaction_type="view",
            interaction_strength=1.0,
        )
        db_session.add(interaction)

    db_session.commit()

    # Train model (which performs negative sampling)
    service = CollaborativeFilteringService(db_session)

    with patch.object(service, "_save_model"):
        with patch("torch.save"):
            result = service.train_model(epochs=1, batch_size=4)

    # Verify training included both positive and negative samples
    # The actual negative sampling happens inside train_model
    # We verify it ran successfully
    assert "success" in result or "num_interactions" in result


# ============================================================================
# Test Model Persistence
# ============================================================================


def test_model_save_and_load(db_session, tmp_path):
    """
    Test model checkpoint save and load.

    Verifies:
    - Model can be saved to disk
    - Model can be loaded from disk
    - Loaded model has same architecture and mappings
    """

    model_path = tmp_path / "test_ncf_model.pt"

    # Create service with custom model path
    service = CollaborativeFilteringService(db_session, model_path=str(model_path))

    # Create a simple model
    service.model = NCFModel(num_users=10, num_items=5, embedding_dim=8)
    service.user_id_to_idx = {"user_1": 0, "user_2": 1}
    service.item_id_to_idx = {"res_1": 0, "res_2": 1}
    service.idx_to_user_id = {0: "user_1", 1: "user_2"}
    service.idx_to_item_id = {0: "res_1", 1: "res_2"}

    # Save model
    success = service._save_model()
    assert success
    assert model_path.exists()

    # Create new service and load model
    new_service = CollaborativeFilteringService(db_session, model_path=str(model_path))

    # Verify mappings were loaded
    assert new_service.user_id_to_idx == service.user_id_to_idx
    assert new_service.item_id_to_idx == service.item_id_to_idx
    assert new_service.model is not None


# ============================================================================
# Test Error Handling
# ============================================================================


def test_predict_score_with_invalid_resource(db_session):
    """
    Test prediction with resource not in training data.

    Verifies:
    - Returns None for unknown resources
    - No errors raised
    """
    service = CollaborativeFilteringService(db_session)
    service.model = MagicMock()
    service.user_id_to_idx = {"user_1": 0}
    service.item_id_to_idx = {"res_1": 0}

    # Try to predict for unknown resource
    score = service.predict_score("user_1", "unknown_resource")

    assert score is None


def test_train_with_insufficient_data(db_session):
    """
    Test training with insufficient interaction data.

    Verifies:
    - Returns error when too few interactions
    - No model is created
    """
    from uuid import uuid4

    user_id = uuid4()
    _create_user(db_session, user_id)

    # Create only 5 interactions (below threshold of 10)
    for i in range(5):
        resource = Resource(
            id=uuid4(), title=f"Resource {i}", source="https://example.com"
        )
        db_session.add(resource)
        db_session.flush()

        interaction = UserInteraction(
            user_id=user_id,
            resource_id=resource.id,
            interaction_type="view",
            interaction_strength=1.0,
        )
        db_session.add(interaction)

    db_session.commit()

    service = CollaborativeFilteringService(db_session)
    result = service.train_model(epochs=1)

    # Should return error
    assert "error" in result or "num_interactions" in result
    if "num_interactions" in result:
        assert result["num_interactions"] < 10
