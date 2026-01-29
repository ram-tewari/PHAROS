"""
Neo Alexandria 2.0 - Collections API Router

This module provides the REST API endpoints for collection management in Neo Alexandria 2.0.
It handles collection CRUD operations, resource membership management, and collection-based
recommendations using semantic similarity.

Related files:
- service.py: Business logic for collection operations
- schema.py: Pydantic schemas for request/response validation
- model.py: Collection and CollectionResource models
- backend.app.shared.database: Database session management

Endpoints:
- POST /collections: Create a new collection
- GET /collections: List user's collections
- GET /collections/{id}: Retrieve a specific collection with resources
- PUT /collections/{id}: Update collection metadata
- DELETE /collections/{id}: Delete a collection
- PUT /collections/{id}/resources: Batch add/remove resources
- GET /collections/{id}/recommendations: Get collection-based recommendations
- GET /collections/health: Module health check
"""

import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from ...shared.database import get_sync_db
from ...shared.event_bus import event_bus
from .schema import (
    CollectionCreate,
    CollectionUpdate,
    CollectionRead,
    CollectionWithResources,
    CollectionResourcesUpdate,
    CollectionRecommendation,
    CollectionRecommendationsResponse,
    ResourceSummary,
)
from .service import CollectionService


router = APIRouter(prefix="/api/collections", tags=["collections"])


def get_collection_service(db: Session = Depends(get_sync_db)) -> CollectionService:
    """Dependency to get collection service instance."""
    return CollectionService(db)


@router.get("/health", response_model=Dict[str, Any])
async def health_check(db: Session = Depends(get_sync_db)) -> Dict[str, Any]:
    """
    Health check endpoint for Collections module.

    Verifies:
    - Database connectivity
    - Event handlers registration
    - Module version and status

    Returns:
        Dictionary with health status including:
        - status: "healthy" or "unhealthy"
        - module: Module name and version
        - database: Database connection status
        - event_handlers: Registered event handlers
        - timestamp: When the check was performed
    """
    from sqlalchemy import text

    try:
        # Check database connectivity
        try:
            db.execute(text("SELECT 1"))
            db_healthy = True
            db_message = "Database connection healthy"
        except Exception as e:
            db_healthy = False
            db_message = f"Database connection failed: {str(e)}"

        # Check event handlers registration - make this optional for health
        try:
            handlers_registered = event_bus.get_handlers("resource.deleted")
            handlers_count = len(handlers_registered)
        except Exception:
            handlers_count = 0

        # Determine overall status - only require database connectivity
        overall_healthy = db_healthy

        return {
            "status": "healthy" if overall_healthy else "unhealthy",
            "module": {
                "name": "collections",
                "version": "1.0.0",
                "domain": "collections",
            },
            "database": {"healthy": db_healthy, "message": db_message},
            "event_handlers": {
                "registered": handlers_count > 0,
                "count": handlers_count,
                "events": ["resource.deleted"] if handlers_count > 0 else [],
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


@router.post("", response_model=CollectionRead, status_code=status.HTTP_201_CREATED)
async def create_collection(
    payload: CollectionCreate,
    service: CollectionService = Depends(get_collection_service),
):
    """
    Create a new collection.

    Args:
        payload: Collection creation data
        service: Collection service instance

    Returns:
        Created collection

    Raises:
        400: If parent collection doesn't exist or validation fails
        500: If creation fails
    """
    try:
        collection = service.create_collection(
            name=payload.name,
            description=payload.description,
            owner_id=payload.owner_id,
            visibility=payload.visibility,
            parent_id=payload.parent_id,
        )

        # Add resource count
        collection.resource_count = 0  # type: ignore[attr-defined]

        return collection
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create collection: {str(exc)}",
        )


@router.get("", response_model=List[CollectionRead])
async def list_collections(
    owner_id: Optional[str] = Query(None, description="Owner user ID"),
    parent_id: Optional[uuid.UUID] = Query(
        None, description="Parent collection ID (None for root)"
    ),
    include_public: bool = Query(
        True, description="Include public collections from other users"
    ),
    visibility: Optional[str] = Query(None, description="Filter by visibility"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    service: CollectionService = Depends(get_collection_service),
):
    """
    List collections for a user.

    Args:
        owner_id: Owner user ID (optional - if not provided, returns public collections)
        parent_id: Optional parent collection ID filter
        include_public: Whether to include public collections
        visibility: Filter by visibility (private, shared, public)
        limit: Maximum number of results
        offset: Pagination offset
        service: Collection service instance

    Returns:
        List of collections
    """
    try:
        collections, total = service.list_collections(
            owner_id=owner_id,
            parent_id=parent_id,
            include_public=include_public,
            limit=limit,
            offset=offset,
        )

        # Filter by visibility if specified
        if visibility:
            collections = [c for c in collections if c.visibility == visibility]

        # Add resource counts
        from .model import CollectionResource

        for collection in collections:
            resource_count = (
                service.db.query(CollectionResource)
                .filter(CollectionResource.collection_id == collection.id)
                .count()
            )
            collection.resource_count = resource_count  # type: ignore[attr-defined]

        return collections
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list collections: {str(exc)}",
        )


@router.get("/{collection_id}", response_model=CollectionWithResources)
async def get_collection(
    collection_id: uuid.UUID,
    owner_id: Optional[str] = Query(
        None, description="Owner user ID for access control"
    ),
    limit: int = Query(50, ge=1, le=100, description="Maximum resources to return"),
    offset: int = Query(0, ge=0, description="Pagination offset for resources"),
    service: CollectionService = Depends(get_collection_service),
):
    """
    Retrieve a collection with its resources.

    Args:
        collection_id: Collection UUID
        owner_id: Optional owner ID for access control
        limit: Maximum resources to return
        offset: Pagination offset for resources
        service: Collection service instance

    Returns:
        Collection with populated resources

    Raises:
        404: If collection not found or access denied
    """
    try:
        collection = service.get_collection(collection_id, owner_id)
        if not collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collection not found or access denied",
            )

        # Get resources with pagination
        resources, total = service.get_collection_resources(
            collection_id=collection_id, owner_id=owner_id, limit=limit, offset=offset
        )

        # Convert to response format
        resource_summaries = [
            ResourceSummary(
                id=r.id,
                title=r.title,
                description=r.description,
                creator=r.creator,
                type=r.type,
                quality_score=r.quality_score,
                created_at=r.created_at,
            )
            for r in resources
        ]

        # Build response
        response = CollectionWithResources(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            owner_id=collection.owner_id,
            visibility=collection.visibility,
            parent_id=collection.parent_id,
            created_at=collection.created_at,
            updated_at=collection.updated_at,
            resource_count=total,
            resources=resource_summaries,
        )

        return response
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve collection: {str(exc)}",
        )


@router.put("/{collection_id}", response_model=CollectionRead)
async def update_collection(
    collection_id: uuid.UUID,
    payload: CollectionUpdate,
    owner_id: Optional[str] = Query(
        None, description="Owner user ID for access control"
    ),
    service: CollectionService = Depends(get_collection_service),
):
    """
    Update collection metadata.

    Args:
        collection_id: Collection UUID
        payload: Update data
        owner_id: Owner user ID for access control
        service: Collection service instance

    Returns:
        Updated collection

    Raises:
        400: If validation fails
        404: If collection not found or access denied
    """
    try:
        collection = service.update_collection(
            collection_id=collection_id, owner_id=owner_id, updates=payload
        )

        # Add resource count
        from .model import CollectionResource

        resource_count = (
            service.db.query(CollectionResource)
            .filter(CollectionResource.collection_id == collection.id)
            .count()
        )
        collection.resource_count = resource_count  # type: ignore[attr-defined]

        return collection
    except ValueError as ve:
        if "not found" in str(ve).lower() or "access denied" in str(ve).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update collection: {str(exc)}",
        )


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: uuid.UUID,
    owner_id: Optional[str] = Query(
        None, description="Owner user ID for access control"
    ),
    service: CollectionService = Depends(get_collection_service),
):
    """
    Delete a collection.

    Args:
        collection_id: Collection UUID
        owner_id: Owner user ID for access control
        service: Collection service instance

    Raises:
        404: If collection not found or access denied
    """
    try:
        service.delete_collection(collection_id, owner_id)
        return None
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete collection: {str(exc)}",
        )


@router.post(
    "/{collection_id}/resources",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def add_resource_to_collection(
    collection_id: uuid.UUID,
    payload: dict,
    owner_id: Optional[str] = Query(
        None, description="Owner user ID for access control"
    ),
    service: CollectionService = Depends(get_collection_service),
):
    """
    Add a single resource to a collection.

    Args:
        collection_id: Collection UUID
        payload: Dict with resource_id
        owner_id: Owner user ID for access control
        service: Collection service instance

    Returns:
        Success message

    Raises:
        404: If collection or resource not found
        400: If resource_id not provided
    """
    try:
        resource_id = payload.get("resource_id")
        if not resource_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="resource_id is required",
            )

        # Convert string to UUID if needed
        if isinstance(resource_id, str):
            resource_id = uuid.UUID(resource_id)

        added_count = service.add_resources_to_collection(
            collection_id=collection_id, resource_ids=[resource_id], owner_id=owner_id
        )

        return {
            "collection_id": str(collection_id),
            "resource_id": str(resource_id),
            "added": added_count > 0,
            "message": "Resource added to collection"
            if added_count > 0
            else "Resource already in collection",
        }
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add resource to collection: {str(exc)}",
        )


@router.get("/{collection_id}/resources", response_model=List[ResourceSummary])
async def list_collection_resources(
    collection_id: uuid.UUID,
    owner_id: Optional[str] = Query(
        None, description="Owner user ID for access control"
    ),
    limit: int = Query(50, ge=1, le=100, description="Maximum resources to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    service: CollectionService = Depends(get_collection_service),
):
    """
    List resources in a collection.

    Args:
        collection_id: Collection UUID
        owner_id: Optional owner ID for access control
        limit: Maximum resources to return
        offset: Pagination offset
        service: Collection service instance

    Returns:
        List of resources in the collection

    Raises:
        404: If collection not found or access denied
    """
    try:
        # Verify collection exists
        collection = service.get_collection(collection_id, owner_id)
        if not collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collection not found or access denied",
            )

        # Get resources with pagination
        resources, total = service.get_collection_resources(
            collection_id=collection_id, owner_id=owner_id, limit=limit, offset=offset
        )

        # Convert to response format
        return [
            ResourceSummary(
                id=r.id,
                title=r.title,
                description=r.description,
                creator=r.creator,
                type=r.type,
                quality_score=r.quality_score or 0.0,
                created_at=r.created_at,
            )
            for r in resources
        ]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list collection resources: {str(exc)}",
        )


@router.delete(
    "/{collection_id}/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_resource_from_collection(
    collection_id: uuid.UUID,
    resource_id: uuid.UUID,
    owner_id: Optional[str] = Query(
        None, description="Owner user ID for access control"
    ),
    service: CollectionService = Depends(get_collection_service),
):
    """
    Remove a single resource from a collection.

    Args:
        collection_id: Collection UUID
        resource_id: Resource UUID to remove
        owner_id: Owner user ID for access control
        service: Collection service instance

    Raises:
        404: If collection or resource not found
    """
    try:
        removed_count = service.remove_resources_from_collection(
            collection_id=collection_id, resource_ids=[resource_id], owner_id=owner_id
        )

        if removed_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found in collection",
            )

        return None
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove resource from collection: {str(exc)}",
        )


@router.put("/{collection_id}/resources", response_model=dict)
async def update_collection_resources(
    collection_id: uuid.UUID,
    payload: CollectionResourcesUpdate,
    owner_id: str = Query(..., description="Owner user ID for access control"),
    service: CollectionService = Depends(get_collection_service),
):
    """
    Batch add/remove resources from a collection.

    Args:
        collection_id: Collection UUID
        payload: Resource IDs to add/remove
        owner_id: Owner user ID for access control
        service: Collection service instance

    Returns:
        Summary of changes

    Raises:
        404: If collection not found or access denied
    """
    try:
        added_count = 0
        removed_count = 0

        # Add resources
        if payload.add_resource_ids:
            added_count = service.add_resources_to_collection(
                collection_id=collection_id,
                resource_ids=payload.add_resource_ids,
                owner_id=owner_id,
            )

        # Remove resources
        if payload.remove_resource_ids:
            removed_count = service.remove_resources_from_collection(
                collection_id=collection_id,
                resource_ids=payload.remove_resource_ids,
                owner_id=owner_id,
            )

        return {
            "collection_id": str(collection_id),
            "added": added_count,
            "removed": removed_count,
            "message": f"Added {added_count} and removed {removed_count} resources",
        }
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update collection resources: {str(exc)}",
        )


@router.get(
    "/{collection_id}/recommendations", response_model=CollectionRecommendationsResponse
)
async def get_collection_recommendations(
    collection_id: uuid.UUID,
    owner_id: Optional[str] = Query(
        None, description="Owner user ID for access control"
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum recommendations"),
    min_similarity: float = Query(
        0.5, ge=0.0, le=1.0, description="Minimum similarity threshold"
    ),
    exclude_collection_resources: bool = Query(
        True, description="Exclude resources already in collection"
    ),
    service: CollectionService = Depends(get_collection_service),
):
    """
    Get resource recommendations based on collection embedding.

    Uses semantic similarity between the collection's aggregate embedding
    and individual resource embeddings to find related content.

    Args:
        collection_id: Collection UUID
        owner_id: Optional owner ID for access control
        limit: Maximum number of recommendations
        min_similarity: Minimum similarity threshold (0.0-1.0)
        exclude_collection_resources: Whether to exclude resources already in collection
        service: Collection service instance

    Returns:
        Collection recommendations with similarity scores

    Raises:
        404: If collection not found or access denied
        400: If collection has no embedding
    """
    try:
        # Get collection
        collection = service.get_collection(collection_id, owner_id)
        if not collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collection not found or access denied",
            )

        # Find similar resources
        similar_resources = service.find_similar_resources(
            collection_id=collection_id,
            owner_id=owner_id,
            limit=limit,
            min_similarity=min_similarity,
            exclude_collection_resources=exclude_collection_resources,
        )

        # Convert to response format
        recommendations = [
            CollectionRecommendation(
                resource_id=r["resource_id"],
                title=r["title"],
                description=r["description"],
                similarity_score=r["similarity_score"],
                reason=f"Semantically similar to collection (similarity: {r['similarity_score']:.2f})",
            )
            for r in similar_resources
        ]

        return CollectionRecommendationsResponse(
            collection_id=collection_id,
            collection_name=collection.name,
            recommendations=recommendations,
            total=len(recommendations),
        )
    except ValueError as ve:
        if "no embedding" in str(ve).lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get recommendations: {str(exc)}",
        )


@router.get("/{collection_id}/similar-collections", response_model=List[Dict[str, Any]])
async def get_similar_collections(
    collection_id: uuid.UUID,
    owner_id: Optional[str] = Query(
        None, description="Owner user ID for access control"
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum recommendations"),
    min_similarity: float = Query(
        0.5, ge=0.0, le=1.0, description="Minimum similarity threshold"
    ),
    service: CollectionService = Depends(get_collection_service),
):
    """
    Get similar collections based on embedding similarity.

    Uses semantic similarity between collection embeddings to find
    related collections that might be of interest.

    Args:
        collection_id: Source collection UUID
        owner_id: Optional owner ID for access control
        limit: Maximum number of recommendations
        min_similarity: Minimum similarity threshold (0.0-1.0)
        service: Collection service instance

    Returns:
        List of similar collections with similarity scores

    Raises:
        404: If collection not found or access denied
        400: If collection has no embedding
    """
    try:
        similar_collections = service.find_similar_collections(
            collection_id=collection_id,
            owner_id=owner_id,
            limit=limit,
            min_similarity=min_similarity,
        )

        return similar_collections
    except ValueError as ve:
        if "no embedding" in str(ve).lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get similar collections: {str(exc)}",
        )


@router.post("/{collection_id}/resources/batch", response_model=dict)
async def batch_add_resources(
    collection_id: uuid.UUID,
    payload: dict,
    owner_id: str = Query(..., description="Owner user ID for access control"),
    service: CollectionService = Depends(get_collection_service),
):
    """
    Add multiple resources to a collection in a single batch operation.

    More efficient than adding resources one at a time. Supports up to
    100 resources per batch.

    Args:
        collection_id: Collection UUID
        payload: Dict with resource_ids list
        owner_id: Owner user ID for access control
        service: Collection service instance

    Returns:
        Summary of batch operation results

    Raises:
        400: If batch size exceeds limit or validation fails
        404: If collection not found or access denied
    """
    try:
        resource_ids = payload.get("resource_ids", [])

        if not resource_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="resource_ids list is required",
            )

        # Convert string IDs to UUIDs if needed
        resource_uuids = []
        for rid in resource_ids:
            if isinstance(rid, str):
                resource_uuids.append(uuid.UUID(rid))
            else:
                resource_uuids.append(rid)

        result = service.add_resources_batch(
            collection_id=collection_id, resource_ids=resource_uuids, owner_id=owner_id
        )

        return {
            "collection_id": str(collection_id),
            "added": result["added"],
            "skipped": result["skipped"],
            "invalid": result["invalid"],
            "message": f"Added {result['added']} resources, skipped {result['skipped']} duplicates, {result['invalid']} invalid",
        }
    except ValueError as ve:
        if "exceed" in str(ve).lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to batch add resources: {str(exc)}",
        )


@router.delete("/{collection_id}/resources/batch", response_model=dict)
async def batch_remove_resources(
    collection_id: uuid.UUID,
    payload: dict,
    owner_id: str = Query(..., description="Owner user ID for access control"),
    service: CollectionService = Depends(get_collection_service),
):
    """
    Remove multiple resources from a collection in a single batch operation.

    More efficient than removing resources one at a time. Supports up to
    100 resources per batch.

    Args:
        collection_id: Collection UUID
        payload: Dict with resource_ids list
        owner_id: Owner user ID for access control
        service: Collection service instance

    Returns:
        Summary of batch operation results

    Raises:
        400: If batch size exceeds limit or validation fails
        404: If collection not found or access denied
    """
    try:
        resource_ids = payload.get("resource_ids", [])

        if not resource_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="resource_ids list is required",
            )

        # Convert string IDs to UUIDs if needed
        resource_uuids = []
        for rid in resource_ids:
            if isinstance(rid, str):
                resource_uuids.append(uuid.UUID(rid))
            else:
                resource_uuids.append(rid)

        result = service.remove_resources_batch(
            collection_id=collection_id, resource_ids=resource_uuids, owner_id=owner_id
        )

        return {
            "collection_id": str(collection_id),
            "removed": result["removed"],
            "not_found": result["not_found"],
            "message": f"Removed {result['removed']} resources, {result['not_found']} not found in collection",
        }
    except ValueError as ve:
        if "exceed" in str(ve).lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to batch remove resources: {str(exc)}",
        )
