"""
Neo Alexandria 2.0 - Collection Service

This module provides business logic for collection management operations.
It handles collection CRUD, resource membership, and collection-level embeddings
for semantic similarity and recommendations.

Related files:
- model.py: Collection and CollectionResource models
- schema.py: Pydantic schemas for validation
- router.py: API endpoints that use this service
- backend.app.shared.database: Database session management

Key Features:
- Create and manage user collections
- Add/remove resources from collections
- Compute collection embeddings (average of member resource embeddings)
- Find similar resources based on collection embedding
- Support hierarchical collections (parent/subcollections)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple

import numpy as np
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

logger = logging.getLogger(__name__)

# Import from local model file to avoid circular dependencies
from .model import Collection, CollectionResource
from .schema import CollectionUpdate


class CollectionService:
    """Service for collection management operations."""

    def __init__(self, db: Session):
        """
        Initialize collection service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def create_collection(
        self,
        name: str,
        description: Optional[str],
        owner_id: str,
        visibility: str = "private",
        parent_id: Optional[uuid.UUID] = None,
    ) -> Collection:
        """
        Create a new collection.

        Args:
            name: Collection name
            description: Optional description
            owner_id: Owner user ID
            visibility: Collection visibility ('private', 'shared', 'public')
            parent_id: Optional parent collection ID for hierarchical organization

        Returns:
            Created Collection instance

        Raises:
            ValueError: If parent collection doesn't exist or doesn't belong to owner
        """
        # Validate parent collection if specified
        if parent_id:
            parent = (
                self.db.query(Collection)
                .filter(Collection.id == parent_id, Collection.owner_id == owner_id)
                .first()
            )

            if not parent:
                raise ValueError(
                    f"Parent collection {parent_id} not found or doesn't belong to owner"
                )

        # Create collection
        collection = Collection(
            name=name,
            description=description,
            owner_id=owner_id,
            visibility=visibility,
            parent_id=parent_id,
            embedding=None,  # Will be computed when resources are added
        )

        self.db.add(collection)
        self.db.commit()
        # No need to refresh - all fields are set explicitly
        # Refresh can cause issues with relationships in test environments

        return collection

    def get_collection(
        self,
        collection_id: uuid.UUID,
        owner_id: Optional[str] = None,
        include_resources: bool = False,
    ) -> Optional[Collection]:
        """
        Retrieve a collection by ID.

        Args:
            collection_id: Collection UUID
            owner_id: Optional owner ID for access control
            include_resources: Whether to eagerly load resources

        Returns:
            Collection instance or None if not found
        """
        query = self.db.query(Collection).filter(Collection.id == collection_id)

        # Apply access control if owner_id specified
        if owner_id:
            query = query.filter(
                or_(
                    Collection.owner_id == owner_id,
                    Collection.visibility.in_(["shared", "public"]),
                )
            )

        # Eagerly load resources if requested
        if include_resources:
            query = query.options(joinedload(Collection.resources))

        return query.first()

    def list_collections(
        self,
        owner_id: Optional[str] = None,
        parent_id: Optional[uuid.UUID] = None,
        include_public: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Collection], int]:
        """
        List collections for a user.

        Args:
            owner_id: Owner user ID (optional - if None, returns only public collections)
            parent_id: Optional parent ID to filter by (None = root collections)
            include_public: Whether to include public collections from other users
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            Tuple of (collections list, total count)
        """
        # Build base query
        query = self.db.query(Collection)

        # Filter by ownership and visibility
        if owner_id is None:
            # No owner specified - only return public collections
            query = query.filter(Collection.visibility == "public")
        elif include_public:
            query = query.filter(
                or_(Collection.owner_id == owner_id, Collection.visibility == "public")
            )
        else:
            query = query.filter(Collection.owner_id == owner_id)

        # Filter by parent
        if parent_id is None:
            query = query.filter(Collection.parent_id.is_(None))
        else:
            query = query.filter(Collection.parent_id == parent_id)

        # Get total count
        total = query.count()

        # Apply pagination and ordering
        collections = (
            query.order_by(Collection.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return collections, total

    def update_collection(
        self,
        collection_id: uuid.UUID,
        owner_id: Optional[str],
        updates: CollectionUpdate,
    ) -> Collection:
        """
        Update collection metadata.

        Args:
            collection_id: Collection UUID
            owner_id: Owner user ID for access control (optional - if None, only checks collection exists)
            updates: CollectionUpdate schema with fields to update

        Returns:
            Updated Collection instance

        Raises:
            ValueError: If collection not found or access denied
        """
        query = self.db.query(Collection).filter(Collection.id == collection_id)

        # Apply owner filter only if owner_id is provided
        if owner_id is not None:
            query = query.filter(Collection.owner_id == owner_id)

        collection = query.first()

        if not collection:
            raise ValueError("Collection not found or access denied")

        # Apply updates
        update_data = updates.model_dump(exclude_unset=True)

        for key, value in update_data.items():
            if key == "parent_id" and value is not None:
                # Validate parent collection exists
                parent = (
                    self.db.query(Collection)
                    .filter(Collection.id == value, Collection.owner_id == owner_id)
                    .first()
                )

                if not parent:
                    raise ValueError(
                        f"Parent collection {value} not found or access denied"
                    )

                # Validate hierarchy to prevent circular references
                is_valid, error_msg = self.validate_parent_hierarchy(
                    collection_id, value
                )
                if not is_valid:
                    raise ValueError(error_msg)

            setattr(collection, key, value)

        collection.updated_at = datetime.now(timezone.utc)

        self.db.commit()
        # No need to refresh - all fields are set explicitly

        return collection

    def delete_collection(
        self, collection_id: uuid.UUID, owner_id: Optional[str] = None
    ) -> None:
        """
        Delete a collection.

        Args:
            collection_id: Collection UUID
            owner_id: Owner user ID for access control (optional - if None, only checks collection exists)

        Raises:
            ValueError: If collection not found or access denied
        """
        query = self.db.query(Collection).filter(Collection.id == collection_id)

        # Apply owner filter only if owner_id is provided
        if owner_id is not None:
            query = query.filter(Collection.owner_id == owner_id)

        collection = query.first()

        if not collection:
            raise ValueError("Collection not found or access denied")

        # Delete collection (cascade will handle subcollections and associations)
        self.db.delete(collection)
        self.db.commit()

    def add_resources_to_collection(
        self,
        collection_id: uuid.UUID,
        resource_ids: List[uuid.UUID],
        owner_id: Optional[str] = None,
    ) -> int:
        """
        Add resources to a collection.

        Args:
            collection_id: Collection UUID
            resource_ids: List of resource UUIDs to add
            owner_id: Owner user ID for access control (optional - if None, only checks collection exists)

        Returns:
            Number of resources added (excludes duplicates)

        Raises:
            ValueError: If collection not found or access denied
        """
        query = self.db.query(Collection).filter(Collection.id == collection_id)

        # Apply owner filter only if owner_id is provided
        if owner_id is not None:
            query = query.filter(Collection.owner_id == owner_id)

        collection = query.first()

        if not collection:
            raise ValueError("Collection not found or access denied")

        # Get existing resource IDs in collection
        existing_ids = {
            cr.resource_id
            for cr in self.db.query(CollectionResource.resource_id)
            .filter(CollectionResource.collection_id == collection_id)
            .all()
        }

        # Filter out resources that are already in collection
        new_resource_ids = [rid for rid in resource_ids if rid not in existing_ids]

        if not new_resource_ids:
            return 0

        # Verify resources exist (import Resource from database.models)
        from ...database.models import Resource

        existing_resources = (
            self.db.query(Resource.id).filter(Resource.id.in_(new_resource_ids)).all()
        )
        existing_resource_ids = {r.id for r in existing_resources}

        # Add associations
        added_count = 0
        for resource_id in new_resource_ids:
            if resource_id in existing_resource_ids:
                association = CollectionResource(
                    collection_id=collection_id, resource_id=resource_id
                )
                self.db.add(association)
                added_count += 1

        if added_count > 0:
            # Update collection timestamp
            collection.updated_at = datetime.now(timezone.utc)

            self.db.commit()

            # Recompute collection embedding
            self.compute_collection_embedding(collection_id)

            # Emit collection.resource_added events
            from .handlers import emit_collection_resource_added

            for resource_id in new_resource_ids:
                if resource_id in existing_resource_ids:
                    emit_collection_resource_added(
                        collection_id=str(collection_id),
                        resource_id=str(resource_id),
                        user_id=owner_id or "system",
                    )

        return added_count

    def add_resources(
        self, collection_id: uuid.UUID, resource_ids: List[uuid.UUID], user_id: str
    ) -> Collection:
        """
        Add resources to a collection (alias for add_resources_to_collection).

        This method provides backward compatibility with tests that use the
        add_resources naming convention. It returns the updated Collection
        instead of just the count.

        Args:
            collection_id: Collection UUID
            resource_ids: List of resource UUIDs to add
            user_id: User ID for access control (same as owner_id)

        Returns:
            Updated Collection instance with resources loaded

        Raises:
            ValueError: If collection not found or access denied
        """
        # Call the main method
        self.add_resources_to_collection(
            collection_id=collection_id, resource_ids=resource_ids, owner_id=user_id
        )

        # Return the collection with resources loaded
        return self.get_collection(
            collection_id=collection_id, owner_id=user_id, include_resources=True
        )

    def remove_resources_from_collection(
        self,
        collection_id: uuid.UUID,
        resource_ids: List[uuid.UUID],
        owner_id: Optional[str] = None,
    ) -> int:
        """
        Remove resources from a collection.

        Args:
            collection_id: Collection UUID
            resource_ids: List of resource UUIDs to remove
            owner_id: Owner user ID for access control (optional - if None, only checks collection exists)

        Returns:
            Number of resources removed

        Raises:
            ValueError: If collection not found or access denied
        """
        query = self.db.query(Collection).filter(Collection.id == collection_id)

        # Apply owner filter only if owner_id is provided
        if owner_id is not None:
            query = query.filter(Collection.owner_id == owner_id)

        collection = query.first()

        if not collection:
            raise ValueError("Collection not found or access denied")

        # Delete associations
        removed_count = (
            self.db.query(CollectionResource)
            .filter(
                CollectionResource.collection_id == collection_id,
                CollectionResource.resource_id.in_(resource_ids),
            )
            .delete(synchronize_session=False)
        )

        if removed_count > 0:
            # Update collection timestamp
            collection.updated_at = datetime.now(timezone.utc)

            self.db.commit()

            # Recompute collection embedding
            self.compute_collection_embedding(collection_id)

            # Emit collection.resource_removed events
            from .handlers import emit_collection_resource_removed

            for resource_id in resource_ids:
                emit_collection_resource_removed(
                    collection_id=str(collection_id),
                    resource_id=str(resource_id),
                    user_id=owner_id,
                    reason="user_removed",
                )

        return removed_count

    def get_collection_resources(
        self,
        collection_id: uuid.UUID,
        owner_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Any], int]:
        """
        Get resources in a collection with optional filtering.

        Args:
            collection_id: Collection UUID
            owner_id: Optional owner ID for access control
            filters: Optional filters (type, language, min_quality, etc.)
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            Tuple of (resources list, total count)

        Raises:
            ValueError: If collection not found or access denied
        """
        # Verify collection access
        collection = self.get_collection(collection_id, owner_id)
        if not collection:
            raise ValueError("Collection not found or access denied")

        # Import Resource from database.models
        from ...database.models import Resource

        # Build query
        query = (
            self.db.query(Resource)
            .join(CollectionResource, Resource.id == CollectionResource.resource_id)
            .filter(CollectionResource.collection_id == collection_id)
        )

        # Apply filters if provided
        if filters:
            if filters.get("type"):
                query = query.filter(Resource.type == filters["type"])

            if filters.get("language"):
                query = query.filter(Resource.language == filters["language"])

            if filters.get("min_quality") is not None:
                query = query.filter(Resource.quality_score >= filters["min_quality"])

            if filters.get("classification_code"):
                query = query.filter(
                    Resource.classification_code == filters["classification_code"]
                )

        # Get total count
        total = query.count()

        # Apply pagination and ordering
        resources = (
            query.order_by(CollectionResource.added_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return resources, total

    def compute_collection_embedding(
        self, collection_id: uuid.UUID
    ) -> Optional[List[float]]:
        """
        Compute collection embedding as average of member resource embeddings.

        This enables collection-level semantic similarity and recommendations.
        The embedding is computed by averaging the dense embeddings of all
        resources in the collection that have embeddings.

        Args:
            collection_id: Collection UUID

        Returns:
            Computed embedding vector or None if no resources have embeddings
        """
        # Import Resource from database.models
        from ...database.models import Resource

        # Get all resources in collection with embeddings
        resources = (
            self.db.query(Resource)
            .join(CollectionResource, Resource.id == CollectionResource.resource_id)
            .filter(
                CollectionResource.collection_id == collection_id,
                Resource.embedding.isnot(None),
            )
            .all()
        )

        if not resources:
            # No resources with embeddings - clear collection embedding
            collection = (
                self.db.query(Collection).filter(Collection.id == collection_id).first()
            )

            if collection:
                collection.embedding = None
                self.db.commit()

            return None

        # Extract embeddings - handle both JSON strings (SQLite/Text) and lists (PostgreSQL/JSON)
        import json

        embeddings = []
        for resource in resources:
            embedding = resource.embedding
            if embedding:
                # If stored as JSON string, parse it
                if isinstance(embedding, str):
                    try:
                        embedding = json.loads(embedding)
                    except (json.JSONDecodeError, TypeError):
                        continue
                if isinstance(embedding, list):
                    embeddings.append(embedding)

        if not embeddings:
            return None

        # Compute average embedding
        embeddings_array = np.array(embeddings)
        avg_embedding = np.mean(embeddings_array, axis=0)

        # Normalize to unit length for cosine similarity
        norm = np.linalg.norm(avg_embedding)
        if norm > 0:
            avg_embedding = avg_embedding / norm

        # Store in collection
        collection = (
            self.db.query(Collection).filter(Collection.id == collection_id).first()
        )

        if collection:
            collection.embedding = avg_embedding.tolist()
            collection.updated_at = datetime.now(timezone.utc)
            self.db.commit()

        return avg_embedding.tolist()

    def find_similar_resources(
        self,
        collection_id: uuid.UUID,
        owner_id: Optional[str] = None,
        limit: int = 20,
        min_similarity: float = 0.5,
        exclude_collection_resources: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Find resources similar to a collection based on collection embedding.

        Uses cosine similarity between collection embedding and resource embeddings
        to find semantically related resources.

        Args:
            collection_id: Collection UUID
            owner_id: Optional owner ID for access control
            limit: Maximum number of recommendations
            min_similarity: Minimum similarity threshold (0.0-1.0)
            exclude_collection_resources: Whether to exclude resources already in collection

        Returns:
            List of dicts with resource info and similarity scores

        Raises:
            ValueError: If collection not found, access denied, or no embedding
        """
        # Get collection with embedding
        collection = self.get_collection(collection_id, owner_id)
        if not collection:
            raise ValueError("Collection not found or access denied")

        if not collection.embedding:
            raise ValueError("Collection has no embedding - add resources first")

        collection_embedding = np.array(collection.embedding)

        # Get resources to exclude if requested
        excluded_ids = set()
        if exclude_collection_resources:
            excluded_ids = {
                cr.resource_id
                for cr in self.db.query(CollectionResource.resource_id)
                .filter(CollectionResource.collection_id == collection_id)
                .all()
            }

        # Import Resource from database.models
        from ...database.models import Resource

        # Get all resources with embeddings
        query = self.db.query(Resource).filter(Resource.embedding.isnot(None))

        if excluded_ids:
            query = query.filter(~Resource.id.in_(excluded_ids))

        resources = query.all()

        # Compute similarities - handle embeddings as either JSON strings or lists
        import json

        similarities = []
        for resource in resources:
            embedding = resource.embedding
            if not embedding:
                continue

            # Parse JSON string if needed
            if isinstance(embedding, str):
                try:
                    embedding = json.loads(embedding)
                except (json.JSONDecodeError, TypeError):
                    continue

            if not isinstance(embedding, list):
                continue

            resource_embedding = np.array(embedding)

            # Cosine similarity
            similarity = float(np.dot(collection_embedding, resource_embedding))

            if similarity >= min_similarity:
                similarities.append(
                    {
                        "resource_id": resource.id,
                        "title": resource.title,
                        "description": resource.description,
                        "similarity_score": similarity,
                        "quality_score": resource.quality_score,
                        "type": resource.type,
                        "creator": resource.creator,
                    }
                )

        # Sort by similarity and limit
        similarities.sort(key=lambda x: x["similarity_score"], reverse=True)

        return similarities[:limit]

    def find_collections_with_resource(
        self, resource_id: uuid.UUID
    ) -> List[Collection]:
        """
        Find all collections that contain a specific resource.

        This method is used by event handlers to identify collections
        that need to be updated when a resource is modified or deleted.

        Args:
            resource_id: Resource UUID

        Returns:
            List of Collection instances containing the resource
        """
        collections = (
            self.db.query(Collection)
            .join(CollectionResource, Collection.id == CollectionResource.collection_id)
            .filter(CollectionResource.resource_id == resource_id)
            .all()
        )

        return collections

    def find_similar_collections(
        self,
        collection_id: uuid.UUID,
        owner_id: Optional[str] = None,
        limit: int = 20,
        min_similarity: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Find collections similar to a given collection based on embeddings.

        Uses cosine similarity between collection embeddings to find
        semantically related collections.

        Args:
            collection_id: Source collection UUID
            owner_id: Optional owner ID for access control
            limit: Maximum number of recommendations
            min_similarity: Minimum similarity threshold (0.0-1.0)

        Returns:
            List of dicts with collection info and similarity scores

        Raises:
            ValueError: If collection not found, access denied, or no embedding
        """
        # Get source collection with embedding
        collection = self.get_collection(collection_id, owner_id)
        if not collection:
            raise ValueError("Collection not found or access denied")

        if not collection.embedding:
            raise ValueError("Collection has no embedding - add resources first")

        collection_embedding = np.array(collection.embedding)

        # Get all other collections with embeddings
        query = self.db.query(Collection).filter(
            Collection.embedding.isnot(None), Collection.id != collection_id
        )

        # Filter by visibility - include public collections and user's own collections
        if owner_id:
            query = query.filter(
                or_(Collection.owner_id == owner_id, Collection.visibility == "public")
            )
        else:
            # No owner specified - only public collections
            query = query.filter(Collection.visibility == "public")

        collections = query.all()

        # Compute similarities
        similarities = []
        for other_collection in collections:
            if not other_collection.embedding or not isinstance(
                other_collection.embedding, list
            ):
                continue

            other_embedding = np.array(other_collection.embedding)

            # Cosine similarity
            similarity = float(np.dot(collection_embedding, other_embedding))

            if similarity >= min_similarity:
                # Get resource count
                resource_count = (
                    self.db.query(CollectionResource)
                    .filter(CollectionResource.collection_id == other_collection.id)
                    .count()
                )

                similarities.append(
                    {
                        "collection_id": other_collection.id,
                        "name": other_collection.name,
                        "description": other_collection.description,
                        "similarity_score": similarity,
                        "resource_count": resource_count,
                        "visibility": other_collection.visibility,
                        "owner_id": other_collection.owner_id,
                    }
                )

        # Sort by similarity and limit
        similarities.sort(key=lambda x: x["similarity_score"], reverse=True)

        return similarities[:limit]

    def validate_parent_hierarchy(
        self, collection_id: uuid.UUID, new_parent_id: uuid.UUID
    ) -> tuple[bool, str]:
        """
        Validate that setting a parent doesn't create circular references.

        Traverses the parent chain to detect cycles. A cycle would occur if
        the new parent is the collection itself or any of its descendants.

        Args:
            collection_id: Collection UUID
            new_parent_id: Proposed parent collection UUID

        Returns:
            Tuple of (is_valid, error_message)
            - (True, "") if hierarchy is valid
            - (False, error_message) if circular reference detected
        """
        # Can't be its own parent
        if collection_id == new_parent_id:
            return False, "Collection cannot be its own parent"

        # Traverse up the parent chain from new_parent
        visited = set()
        current_id = new_parent_id

        while current_id is not None:
            # Check if we've encountered the original collection
            if current_id == collection_id:
                return (
                    False,
                    "Invalid parent assignment: would create circular reference",
                )

            # Check if we've visited this node before (another type of cycle)
            if current_id in visited:
                return (
                    False,
                    "Invalid parent assignment: cycle detected in parent chain",
                )

            visited.add(current_id)

            # Get parent of current collection
            current = (
                self.db.query(Collection).filter(Collection.id == current_id).first()
            )

            if not current:
                # Parent doesn't exist
                return False, "Parent collection does not exist"

            current_id = current.parent_id

        return True, ""

    def add_resources_batch(
        self, collection_id: uuid.UUID, resource_ids: List[uuid.UUID], owner_id: str
    ) -> Dict[str, Any]:
        """
        Add multiple resources to a collection in a single batch operation.

        This is more efficient than adding resources one at a time and
        triggers embedding recomputation only once after all resources
        are added.

        Args:
            collection_id: Collection UUID
            resource_ids: List of resource UUIDs to add (max 100)
            owner_id: Owner user ID for access control

        Returns:
            Dict with operation results:
                - added: Number of resources added
                - skipped: Number of resources already in collection
                - invalid: Number of invalid resource IDs

        Raises:
            ValueError: If collection not found, access denied, or too many resources
        """
        # Validate batch size
        if len(resource_ids) > 100:
            raise ValueError("Batch size cannot exceed 100 resources")

        # Verify collection access
        collection = self.get_collection(collection_id, owner_id)
        if not collection:
            raise ValueError("Collection not found or access denied")

        # Get existing resource IDs in collection
        existing_ids = {
            cr.resource_id
            for cr in self.db.query(CollectionResource.resource_id)
            .filter(CollectionResource.collection_id == collection_id)
            .all()
        }

        # Filter out resources already in collection
        new_resource_ids = [rid for rid in resource_ids if rid not in existing_ids]
        skipped_count = len(resource_ids) - len(new_resource_ids)

        if not new_resource_ids:
            return {"added": 0, "skipped": skipped_count, "invalid": 0}

        # Verify resources exist
        from ...database.models import Resource

        existing_resources = (
            self.db.query(Resource.id).filter(Resource.id.in_(new_resource_ids)).all()
        )
        existing_resource_ids = {r.id for r in existing_resources}

        # Separate valid and invalid resource IDs
        valid_ids = [rid for rid in new_resource_ids if rid in existing_resource_ids]
        invalid_count = len(new_resource_ids) - len(valid_ids)

        # Batch insert associations
        added_count = 0
        for resource_id in valid_ids:
            association = CollectionResource(
                collection_id=collection_id, resource_id=resource_id
            )
            self.db.add(association)
            added_count += 1

        if added_count > 0:
            # Update collection timestamp
            collection.updated_at = datetime.now(timezone.utc)

            self.db.commit()

            # Recompute collection embedding once for all added resources
            self.compute_collection_embedding(collection_id)

        return {
            "added": added_count,
            "skipped": skipped_count,
            "invalid": invalid_count,
        }

    def remove_resources_batch(
        self, collection_id: uuid.UUID, resource_ids: List[uuid.UUID], owner_id: str
    ) -> Dict[str, Any]:
        """
        Remove multiple resources from a collection in a single batch operation.

        This is more efficient than removing resources one at a time and
        triggers embedding recomputation only once after all resources
        are removed.

        Args:
            collection_id: Collection UUID
            resource_ids: List of resource UUIDs to remove (max 100)
            owner_id: Owner user ID for access control

        Returns:
            Dict with operation results:
                - removed: Number of resources removed
                - not_found: Number of resources not in collection

        Raises:
            ValueError: If collection not found, access denied, or too many resources
        """
        # Validate batch size
        if len(resource_ids) > 100:
            raise ValueError("Batch size cannot exceed 100 resources")

        # Verify collection access
        collection = self.get_collection(collection_id, owner_id)
        if not collection:
            raise ValueError("Collection not found or access denied")

        # Delete associations
        removed_count = (
            self.db.query(CollectionResource)
            .filter(
                CollectionResource.collection_id == collection_id,
                CollectionResource.resource_id.in_(resource_ids),
            )
            .delete(synchronize_session=False)
        )

        not_found_count = len(resource_ids) - removed_count

        if removed_count > 0:
            # Update collection timestamp
            collection.updated_at = datetime.now(timezone.utc)

            self.db.commit()

            # Recompute collection embedding once for all removed resources
            self.compute_collection_embedding(collection_id)

        return {"removed": removed_count, "not_found": not_found_count}
