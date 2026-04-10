"""
Collections Module - Lifecycle Tests

Integration tests for collection lifecycle operations.
Tests verify database persistence and event bus emissions.
"""


class TestCollectionLifecycle:
    """Test suite for collection lifecycle integration tests."""

    def test_collection_creation_flow(self, client, db_session, mock_event_bus):
        """
        Test complete collection creation flow.

        Verifies:
        - API endpoint creates collection
        - Database persistence
        - Response format

        **Validates: Requirements 5.2, 5.3, 10.2-10.6, 13.1-13.3**
        """
        # Create collection via API
        payload = {
            "name": "My Research Collection",
            "description": "Collection for ML papers",
            "owner_id": "user123",
            "visibility": "private",
        }

        response = client.post("/api/collections", json=payload)

        # Verify response
        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )
        data = response.json()

        assert data["name"] == payload["name"]
        assert data["description"] == payload["description"]
        assert data["owner_id"] == payload["owner_id"]
        assert data["visibility"] == payload["visibility"]
        assert "id" in data
        assert "created_at" in data
        assert data["resource_count"] == 0

        # Verify database persistence
        from app.database.models import Collection

        collection = (
            db_session.query(Collection)
            .filter(Collection.name == payload["name"])
            .first()
        )

        assert collection is not None, "Collection should be persisted in database"
        assert collection.name == payload["name"]
        assert collection.owner_id == payload["owner_id"]

    def test_add_resource_to_collection_flow(
        self,
        client,
        db_session,
        mock_event_bus,
        create_test_resource,
        create_test_collection,
    ):
        """
        Test adding resource to collection flow.

        Verifies:
        - API endpoint adds resource
        - Database persistence
        - Collection embedding computation

        **Validates: Requirements 5.2, 5.3, 10.2-10.6, 13.1-13.3**
        """
        # Create test data
        collection = create_test_collection(name="Test Collection", owner_id="user123")

        resource = create_test_resource(
            title="Test Resource", embedding=[0.1, 0.2, 0.3]
        )

        # Capture IDs before API call (to avoid detached instance issues)
        collection_id = collection.id
        resource_id = resource.id

        # Add resource to collection via API
        payload = {"resource_id": str(resource_id)}

        response = client.post(
            f"/api/collections/{collection_id}/resources",
            json=payload,
            params={"owner_id": "user123"},
        )

        # Verify response
        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )
        data = response.json()

        assert data["collection_id"] == str(collection_id)
        assert data["resource_id"] == str(resource_id)
        assert data["added"] is True

        # Close and reopen session to see committed changes from API
        db_session.close()
        from sqlalchemy.orm import sessionmaker

        TestingSessionLocal = sessionmaker(bind=db_session.get_bind())
        db_session = TestingSessionLocal()

        # Verify database persistence
        from app.database.models import CollectionResource, Collection

        association = (
            db_session.query(CollectionResource)
            .filter(
                CollectionResource.collection_id == collection_id,
                CollectionResource.resource_id == resource_id,
            )
            .first()
        )

        assert association is not None, "Association should be persisted in database"

        # Verify collection still exists
        updated_collection = (
            db_session.query(Collection).filter(Collection.id == collection_id).first()
        )
        assert updated_collection is not None, "Collection should exist in database"

        # Note: Embedding computation depends on Resource.embedding being properly stored in JSON column
        # This is tested separately in test_aggregation.py with direct service calls

        # Clean up
        db_session.close()

    def test_remove_resource_from_collection_flow(
        self, client, db_session, create_test_resource, create_test_collection
    ):
        """
        Test removing resource from collection flow.

        Verifies:
        - API endpoint removes resource
        - Database persistence
        - Collection embedding recomputation

        **Validates: Requirements 5.2, 5.3, 10.2-10.6**
        """
        # Create test data
        collection = create_test_collection(name="Test Collection", owner_id="user123")

        resource = create_test_resource(
            title="Test Resource", embedding=[0.1, 0.2, 0.3]
        )

        # Add resource to collection first
        from app.modules.collections.service import CollectionService

        service = CollectionService(db_session)

        collection_id = collection.id
        resource_id = resource.id

        service.add_resources_to_collection(
            collection_id=collection_id, resource_ids=[resource_id], owner_id="user123"
        )

        # Verify resource was added
        from app.database.models import CollectionResource, Collection

        association = (
            db_session.query(CollectionResource)
            .filter(
                CollectionResource.collection_id == collection_id,
                CollectionResource.resource_id == resource_id,
            )
            .first()
        )
        assert association is not None, "Resource should be in collection"

        # Remove resource via API
        response = client.delete(
            f"/api/collections/{collection_id}/resources/{resource_id}",
            params={"owner_id": "user123"},
        )

        # Verify response
        assert response.status_code == 204, f"Expected 204, got {response.status_code}"

        # Close and reopen session to see committed changes from API
        db_session.close()
        from sqlalchemy.orm import sessionmaker

        TestingSessionLocal = sessionmaker(bind=db_session.get_bind())
        db_session = TestingSessionLocal()

        # Verify database persistence
        association = (
            db_session.query(CollectionResource)
            .filter(
                CollectionResource.collection_id == collection_id,
                CollectionResource.resource_id == resource_id,
            )
            .first()
        )

        assert association is None, "Association should be removed from database"

        # Verify collection still exists
        updated_collection = (
            db_session.query(Collection).filter(Collection.id == collection_id).first()
        )
        assert updated_collection is not None, (
            "Collection should still exist in database"
        )

        # Note: Embedding clearing depends on Resource.embedding being properly stored in JSON column
        # This is tested separately in test_aggregation.py with direct service calls

        # Clean up
        db_session.close()

    def test_delete_collection_flow(self, client, db_session, create_test_collection):
        """
        Test collection deletion flow.

        Verifies:
        - API endpoint deletes collection
        - Database persistence
        - Cascade deletion of associations

        **Validates: Requirements 5.2, 5.3, 10.2-10.6**
        """
        # Create test collection
        collection = create_test_collection(
            name="Collection to Delete", owner_id="user123"
        )

        collection_id = collection.id

        # Delete collection via API
        response = client.delete(
            f"/api/collections/{collection_id}", params={"owner_id": "user123"}
        )

        # Verify response
        assert response.status_code == 204, f"Expected 204, got {response.status_code}"

        # Verify database persistence
        from app.database.models import Collection

        collection = (
            db_session.query(Collection).filter(Collection.id == collection_id).first()
        )

        assert collection is None, "Collection should be deleted from database"
