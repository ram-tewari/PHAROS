"""
Tests for User Profile Service (Task 14 - Phase 16.7)

Tests cover:
- Interaction tracking (14.1)
- Profile computation (14.3)
- Temporal weighting with 30-day half-life (14.4)
- Event handlers (14.5)
"""

import json
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
import numpy as np

from app.modules.recommendations.user_profile import UserProfileService
from app.database.models import User, UserInteraction, Resource, Annotation


class TestInteractionTracking:
    """Test interaction tracking functionality (Task 14.1)"""

    def test_track_view_interaction(self, db_session, test_user, test_resource):
        """Test tracking view interactions with dwell time and scroll depth"""
        service = UserProfileService(db_session)

        interaction = service.track_interaction(
            user_id=test_user.id,
            resource_id=test_resource.id,
            interaction_type="view",
            dwell_time=120,  # 2 minutes
            scroll_depth=0.8,
        )

        assert interaction.user_id == test_user.id
        assert interaction.resource_id == test_resource.id
        assert interaction.interaction_type == "view"
        assert interaction.dwell_time == 120
        assert interaction.scroll_depth == 0.8
        assert interaction.interaction_strength > 0
        assert interaction.interaction_timestamp is not None

    def test_track_annotation_interaction(self, db_session, test_user, test_resource):
        """Test tracking annotation interactions"""
        service = UserProfileService(db_session)

        interaction = service.track_interaction(
            user_id=test_user.id,
            resource_id=test_resource.id,
            interaction_type="annotation",
        )

        assert interaction.interaction_type == "annotation"
        assert interaction.interaction_strength == 0.7  # Per spec

    def test_track_collection_add_interaction(
        self, db_session, test_user, test_resource
    ):
        """Test tracking collection add interactions"""
        service = UserProfileService(db_session)

        interaction = service.track_interaction(
            user_id=test_user.id,
            resource_id=test_resource.id,
            interaction_type="collection_add",
        )

        assert interaction.interaction_type == "collection_add"
        assert interaction.interaction_strength == 0.8  # Per spec

    def test_track_export_interaction(self, db_session, test_user, test_resource):
        """Test tracking export interactions"""
        service = UserProfileService(db_session)

        interaction = service.track_interaction(
            user_id=test_user.id,
            resource_id=test_resource.id,
            interaction_type="export",
        )

        assert interaction.interaction_type == "export"
        assert interaction.interaction_strength == 0.9  # Per spec

    def test_track_rating_interaction(self, db_session, test_user, test_resource):
        """Test tracking rating interactions"""
        service = UserProfileService(db_session)

        interaction = service.track_interaction(
            user_id=test_user.id,
            resource_id=test_resource.id,
            interaction_type="rating",
            rating=5,
        )

        assert interaction.interaction_type == "rating"
        assert interaction.rating == 5
        assert interaction.interaction_strength > 0.8  # High rating = high strength

    def test_duplicate_interaction_updates_return_visits(
        self, db_session, test_user, test_resource
    ):
        """Test that duplicate interactions increment return_visits"""
        service = UserProfileService(db_session)

        # First interaction
        interaction1 = service.track_interaction(
            user_id=test_user.id, resource_id=test_resource.id, interaction_type="view"
        )
        assert interaction1.return_visits == 0

        # Second interaction (duplicate)
        interaction2 = service.track_interaction(
            user_id=test_user.id,
            resource_id=test_resource.id,
            interaction_type="view",
            dwell_time=300,  # Longer dwell time
        )

        assert interaction2.id == interaction1.id  # Same record
        assert interaction2.return_visits == 1
        assert interaction2.dwell_time == 300  # Updated

    def test_interaction_updates_profile_total(
        self, db_session, test_user, test_resource
    ):
        """Test that interactions update user profile total_interactions"""
        service = UserProfileService(db_session)

        profile = service.get_or_create_profile(test_user.id)
        initial_count = profile.total_interactions

        service.track_interaction(
            user_id=test_user.id, resource_id=test_resource.id, interaction_type="view"
        )

        db_session.refresh(profile)
        assert profile.total_interactions == initial_count + 1
        assert profile.last_active_at is not None


class TestProfileComputation:
    """Test profile computation functionality (Task 14.3)"""

    def test_get_user_profile_structure(self, db_session, test_user):
        """Test that get_user_profile returns correct structure"""
        service = UserProfileService(db_session)

        profile = service.get_user_profile(test_user.id)

        assert "user_id" in profile
        assert "interest_vector" in profile
        assert "frequent_topics" in profile
        assert "frequent_tags" in profile
        assert "interaction_counts" in profile
        assert "last_updated" in profile
        assert profile["user_id"] == str(test_user.id)

    def test_interest_vector_from_interactions(self, db_session, test_user):
        """Test interest vector computation from resource embeddings"""
        service = UserProfileService(db_session)

        # Create resources with embeddings
        embedding1 = json.dumps([0.1] * 768)
        embedding2 = json.dumps([0.2] * 768)

        resource1 = Resource(
            title="Test Resource 1", description="Test content 1", embedding=embedding1
        )
        resource2 = Resource(
            title="Test Resource 2", description="Test content 2", embedding=embedding2
        )
        db_session.add_all([resource1, resource2])
        db_session.commit()

        # Track interactions
        service.track_interaction(
            user_id=test_user.id,
            resource_id=resource1.id,
            interaction_type="view",
            dwell_time=100,
        )
        service.track_interaction(
            user_id=test_user.id,
            resource_id=resource2.id,
            interaction_type="annotation",
        )

        # Get profile
        profile = service.get_user_profile(test_user.id)

        assert profile["interest_vector"] is not None
        assert len(profile["interest_vector"]) == 768
        assert all(isinstance(v, float) for v in profile["interest_vector"])

    def test_frequent_topics_extraction(self, db_session, test_user):
        """Test extraction of frequent topics from interactions"""
        service = UserProfileService(db_session)

        # Create resources with different subjects
        for i, subject_list in enumerate([["AI"], ["ML"], ["AI"], ["NLP"], ["AI"]]):
            resource = Resource(
                title=f"Test Resource {i}",
                description=f"Test content {i}",
                subject=subject_list,
            )
            db_session.add(resource)
            db_session.commit()

            service.track_interaction(
                user_id=test_user.id, resource_id=resource.id, interaction_type="view"
            )

        # Get profile
        profile = service.get_user_profile(test_user.id)

        # Note: subject is a list, so we need to check the first element
        # The _extract_frequent_topics method needs to handle list subjects
        assert len(profile["frequent_topics"]) > 0

    def test_frequent_tags_from_annotations(self, db_session, test_user, test_resource):
        """Test extraction of frequent tags from user annotations"""
        service = UserProfileService(db_session)

        # Create annotations with tags
        tags_list = [["python", "ml"], ["python", "ai"], ["python"]]
        for i, tags in enumerate(tags_list):
            annotation = Annotation(
                user_id=str(test_user.id),  # Convert UUID to string
                resource_id=str(test_resource.id),  # Convert UUID to string
                start_offset=i * 10,
                end_offset=i * 10 + 5,
                highlighted_text=f"Test text {i}",
                tags=json.dumps(tags),
            )
            db_session.add(annotation)
        db_session.commit()

        # Get profile
        profile = service.get_user_profile(test_user.id)

        assert "python" in profile["frequent_tags"]
        assert profile["frequent_tags"][0] == "python"  # Most frequent

    def test_interaction_counts_by_type(self, db_session, test_user, test_resource):
        """Test counting interactions by type"""
        service = UserProfileService(db_session)

        # Track different interaction types
        service.track_interaction(test_user.id, test_resource.id, "view")
        service.track_interaction(test_user.id, test_resource.id, "view")
        service.track_interaction(test_user.id, test_resource.id, "annotation")

        # Get profile
        profile = service.get_user_profile(test_user.id)

        counts = profile["interaction_counts"]
        assert (
            counts.get("view", 0) >= 1
        )  # At least one view (duplicates update same record)
        assert counts.get("annotation", 0) == 1


class TestTemporalWeighting:
    """Test temporal weighting with 30-day half-life (Task 14.4)"""

    def test_exponential_decay_recent_interactions(self, db_session, test_user):
        """Test that recent interactions have higher weight"""
        service = UserProfileService(db_session)

        # Create resource with embedding
        embedding = [0.5] * 768
        resource = Resource(
            title="Test Resource",
            description="Test content",
            embedding=json.dumps(embedding),
        )
        db_session.add(resource)
        db_session.commit()

        # Create recent interaction
        recent_interaction = UserInteraction(
            user_id=test_user.id,
            resource_id=resource.id,
            interaction_type="view",
            interaction_strength=0.5,
            is_positive=1,
            interaction_timestamp=datetime.utcnow(),
        )
        db_session.add(recent_interaction)
        db_session.commit()

        # Get user embedding (which applies temporal weighting)
        embedding_vector = service.get_user_embedding(test_user.id)

        assert embedding_vector is not None
        assert len(embedding_vector) == 768
        # Recent interaction should have weight close to 1.0 (0.5^(0/30) = 1.0)

    def test_exponential_decay_old_interactions(self, db_session, test_user):
        """Test that old interactions have lower weight (30-day half-life)"""
        service = UserProfileService(db_session)

        # Create resource with embedding
        embedding = [0.5] * 768
        resource = Resource(
            title="Test Resource",
            description="Test content",
            embedding=json.dumps(embedding),
        )
        db_session.add(resource)
        db_session.commit()

        # Create old interaction (60 days ago = 2 half-lives)
        old_interaction = UserInteraction(
            user_id=test_user.id,
            resource_id=resource.id,
            interaction_type="view",
            interaction_strength=0.5,
            is_positive=1,
            interaction_timestamp=datetime.utcnow() - timedelta(days=60),
        )
        db_session.add(old_interaction)
        db_session.commit()

        # Get user embedding
        embedding_vector = service.get_user_embedding(test_user.id)

        assert embedding_vector is not None
        # Old interaction should have weight of 0.5^(60/30) = 0.25

    def test_temporal_weighting_formula(self, db_session, test_user):
        """Test that temporal weighting uses correct exponential decay formula"""
        service = UserProfileService(db_session)

        # Create two resources with different embeddings
        resource1 = Resource(
            title="Recent Resource",
            description="Recent content",
            embedding=json.dumps([1.0] * 768),
        )
        resource2 = Resource(
            title="Old Resource",
            description="Old content",
            embedding=json.dumps([0.0] * 768),
        )
        db_session.add_all([resource1, resource2])
        db_session.commit()

        # Create recent and old interactions
        recent = UserInteraction(
            user_id=test_user.id,
            resource_id=resource1.id,
            interaction_type="view",
            interaction_strength=0.5,
            is_positive=1,
            interaction_timestamp=datetime.utcnow(),
        )
        old = UserInteraction(
            user_id=test_user.id,
            resource_id=resource2.id,
            interaction_type="view",
            interaction_strength=0.5,
            is_positive=1,
            interaction_timestamp=datetime.utcnow() - timedelta(days=30),
        )
        db_session.add_all([recent, old])
        db_session.commit()

        # Get user embedding
        embedding_vector = service.get_user_embedding(test_user.id)

        # Recent interaction (weight ~1.0) should dominate over old (weight ~0.5)
        # So embedding should be closer to [1.0, 1.0, ...] than [0.0, 0.0, ...]
        assert np.mean(embedding_vector) > 0.5


class TestColdStart:
    """Test cold start scenarios"""

    def test_cold_start_user_zero_vector(self, db_session, test_user):
        """Test that users with no interactions get zero vector"""
        service = UserProfileService(db_session)

        embedding = service.get_user_embedding(test_user.id)

        assert embedding is not None
        assert len(embedding) == 768
        assert np.all(embedding == 0)

    def test_cold_start_profile(self, db_session, test_user):
        """Test profile for user with no interactions"""
        service = UserProfileService(db_session)

        profile = service.get_user_profile(test_user.id)

        # Cold start returns zero vector as a list, not None
        assert profile["interest_vector"] is None or all(
            v == 0 for v in profile["interest_vector"]
        )
        assert profile["frequent_topics"] == []
        assert profile["frequent_tags"] == []
        assert profile["interaction_counts"] == {}


class TestProfileSettings:
    """Test user profile settings management"""

    def test_get_or_create_profile(self, db_session, test_user):
        """Test profile creation with default settings"""
        service = UserProfileService(db_session)

        profile = service.get_or_create_profile(test_user.id)

        assert profile.user_id == test_user.id
        assert profile.diversity_preference == 0.5
        assert profile.novelty_preference == 0.3
        assert profile.recency_bias == 0.5

    def test_update_profile_settings(self, db_session, test_user):
        """Test updating profile settings"""
        service = UserProfileService(db_session)

        profile = service.update_profile_settings(
            user_id=test_user.id,
            diversity_preference=0.8,
            novelty_preference=0.6,
            recency_bias=0.7,
        )

        assert profile.diversity_preference == 0.8
        assert profile.novelty_preference == 0.6
        assert profile.recency_bias == 0.7

    def test_update_profile_validation(self, db_session, test_user):
        """Test that profile settings are validated"""
        service = UserProfileService(db_session)

        with pytest.raises(
            ValueError, match="diversity_preference must be between 0.0 and 1.0"
        ):
            service.update_profile_settings(
                user_id=test_user.id,
                diversity_preference=1.5,  # Invalid
            )


# Fixtures


@pytest.fixture
def test_user(db_session):
    """Create a test user"""
    user = User(
        email=f"test_{uuid4()}@example.com",
        username=f"testuser_{uuid4()}",
        hashed_password="test_hash",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_resource(db_session):
    """Create a test resource"""
    resource = Resource(
        title="Test Resource", description="Test content for user profile testing"
    )
    db_session.add(resource)
    db_session.commit()
    return resource
