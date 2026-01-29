"""
Neo Alexandria 2.0 - Annotation API Endpoints (Phase 14)

This module provides REST API endpoints for annotation management, search, and export.

Related files:
- app/modules/annotations/service.py: Annotation business logic
- app/modules/annotations/schema.py: Request/response schemas
- app/modules/annotations/model.py: Annotation model
"""

import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ...shared.database import get_sync_db
from .service import AnnotationService
from .schema import (
    AnnotationCreate,
    AnnotationUpdate,
    AnnotationResponse,
    AnnotationListResponse,
    AnnotationSearchResult,
    AnnotationSearchResponse,
)

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


def _get_annotation_service(db: Session = Depends(get_sync_db)) -> AnnotationService:
    """Dependency to get annotation service instance."""
    return AnnotationService(db)


def _get_current_user_id() -> str:
    """
    Dependency to get current authenticated user ID.

    TODO: Replace with actual authentication logic.
    For now, returns a test user ID.
    """
    # This should be replaced with actual authentication
    # For example: return token_data.user_id from JWT token
    return "test-user"


@router.post(
    "/resources/{resource_id}/annotations",
    response_model=AnnotationResponse,
    status_code=201,
)
async def create_annotation(
    resource_id: str,
    annotation_data: AnnotationCreate,
    user_id: str = Depends(_get_current_user_id),
    service: AnnotationService = Depends(_get_annotation_service),
):
    """
    Create a new annotation on a resource.

    Args:
        resource_id: Resource UUID
        annotation_data: Annotation creation data
        user_id: Authenticated user ID
        service: Annotation service instance

    Returns:
        Created annotation

    Raises:
        400: Invalid offsets or validation error
        404: Resource not found
    """
    try:
        annotation = service.create_annotation(
            resource_id=resource_id,
            user_id=user_id,
            start_offset=annotation_data.start_offset,
            end_offset=annotation_data.end_offset,
            highlighted_text=annotation_data.highlighted_text,
            note=annotation_data.note,
            tags=annotation_data.tags,
            color=annotation_data.color or "#FFFF00",
            collection_ids=annotation_data.collection_ids,
        )

        return AnnotationResponse(
            id=str(annotation.id),
            resource_id=str(annotation.resource_id),
            user_id=annotation.user_id,
            start_offset=annotation.start_offset,
            end_offset=annotation.end_offset,
            highlighted_text=annotation.highlighted_text,
            note=annotation.note,
            tags=json.loads(annotation.tags) if annotation.tags else None,
            color=annotation.color,
            context_before=annotation.context_before,
            context_after=annotation.context_after,
            is_shared=bool(annotation.is_shared),
            collection_ids=json.loads(annotation.collection_ids)
            if annotation.collection_ids
            else None,
            created_at=annotation.created_at,
            updated_at=annotation.updated_at,
        )
    except ValueError as e:
        error_msg = str(e).lower()
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/resources/{resource_id}/annotations", response_model=AnnotationListResponse
)
async def list_resource_annotations(
    resource_id: str,
    include_shared: bool = Query(
        False, description="Include shared annotations from other users"
    ),
    tags: Optional[List[str]] = Query(None, description="Filter by tags"),
    user_id: str = Depends(_get_current_user_id),
    service: AnnotationService = Depends(_get_annotation_service),
):
    """
    List all annotations for a specific resource.

    Args:
        resource_id: Resource UUID
        include_shared: Whether to include shared annotations from other users
        tags: Optional list of tags to filter by
        user_id: Authenticated user ID
        service: Annotation service instance

    Returns:
        List of annotations ordered by start_offset
    """
    try:
        annotations = service.get_annotations_for_resource(
            resource_id=resource_id,
            user_id=user_id,
            include_shared=include_shared,
            tags=tags,
        )

        items = [
            AnnotationResponse(
                id=str(ann.id),
                resource_id=str(ann.resource_id),
                user_id=ann.user_id,
                start_offset=ann.start_offset,
                end_offset=ann.end_offset,
                highlighted_text=ann.highlighted_text,
                note=ann.note,
                tags=json.loads(ann.tags) if ann.tags else None,
                color=ann.color,
                context_before=ann.context_before,
                context_after=ann.context_after,
                is_shared=bool(ann.is_shared),
                collection_ids=json.loads(ann.collection_ids)
                if ann.collection_ids
                else None,
                created_at=ann.created_at,
                updated_at=ann.updated_at,
            )
            for ann in annotations
        ]

        return AnnotationListResponse(items=items, total=len(items))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/annotations", response_model=AnnotationListResponse)
async def list_user_annotations(
    limit: int = Query(50, ge=1, le=100, description="Number of annotations to return"),
    offset: int = Query(0, ge=0, description="Number of annotations to skip"),
    sort_by: str = Query("recent", regex="^(recent|oldest)$", description="Sort order"),
    user_id: str = Depends(_get_current_user_id),
    service: AnnotationService = Depends(_get_annotation_service),
):
    """
    List all annotations for the authenticated user across all resources.

    Args:
        limit: Number of annotations to return (max 100)
        offset: Number of annotations to skip for pagination
        sort_by: Sort order - "recent" or "oldest"
        user_id: Authenticated user ID
        service: Annotation service instance

    Returns:
        Paginated list of annotations with resource titles
    """
    try:
        annotations = service.get_annotations_for_user(
            user_id=user_id, limit=limit, offset=offset, sort_by=sort_by
        )

        items = [
            AnnotationResponse(
                id=str(ann.id),
                resource_id=str(ann.resource_id),
                user_id=ann.user_id,
                start_offset=ann.start_offset,
                end_offset=ann.end_offset,
                highlighted_text=ann.highlighted_text,
                note=ann.note,
                tags=json.loads(ann.tags) if ann.tags else None,
                color=ann.color,
                context_before=ann.context_before,
                context_after=ann.context_after,
                is_shared=bool(ann.is_shared),
                collection_ids=json.loads(ann.collection_ids)
                if ann.collection_ids
                else None,
                created_at=ann.created_at,
                updated_at=ann.updated_at,
                resource_title=ann.resource.title if ann.resource else None,
            )
            for ann in annotations
        ]

        # Total is the count of items returned (service handles pagination)
        # For accurate total, we'd need a separate count query, but for now use len(items)
        return AnnotationListResponse(
            items=items,
            total=len(items),
            page=(offset // limit) + 1 if limit > 0 else 1,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/annotations/{annotation_id}", response_model=AnnotationResponse)
async def get_annotation(
    annotation_id: str,
    user_id: str = Depends(_get_current_user_id),
    service: AnnotationService = Depends(_get_annotation_service),
):
    """
    Get a specific annotation by ID.

    Args:
        annotation_id: Annotation UUID
        user_id: Authenticated user ID
        service: Annotation service instance

    Returns:
        Annotation details

    Raises:
        404: Annotation not found or access denied
    """
    try:
        annotation = service.get_annotation_by_id(
            annotation_id=annotation_id, user_id=user_id
        )

        if not annotation:
            raise HTTPException(status_code=404, detail="Annotation not found")

        return AnnotationResponse(
            id=str(annotation.id),
            resource_id=str(annotation.resource_id),
            user_id=annotation.user_id,
            start_offset=annotation.start_offset,
            end_offset=annotation.end_offset,
            highlighted_text=annotation.highlighted_text,
            note=annotation.note,
            tags=json.loads(annotation.tags) if annotation.tags else None,
            color=annotation.color,
            context_before=annotation.context_before,
            context_after=annotation.context_after,
            is_shared=bool(annotation.is_shared),
            collection_ids=json.loads(annotation.collection_ids)
            if annotation.collection_ids
            else None,
            created_at=annotation.created_at,
            updated_at=annotation.updated_at,
            resource_title=annotation.resource.title if annotation.resource else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/annotations/{annotation_id}", response_model=AnnotationResponse)
async def update_annotation(
    annotation_id: str,
    updates: AnnotationUpdate,
    user_id: str = Depends(_get_current_user_id),
    service: AnnotationService = Depends(_get_annotation_service),
):
    """
    Update an existing annotation.

    Only the annotation owner can update it.
    Supports updating: note, tags, color, is_shared.

    Args:
        annotation_id: Annotation UUID
        updates: Fields to update
        user_id: Authenticated user ID
        service: Annotation service instance

    Returns:
        Updated annotation

    Raises:
        403: User is not the annotation owner
        404: Annotation not found
    """
    try:
        annotation = service.update_annotation(
            annotation_id=annotation_id,
            user_id=user_id,
            note=updates.note,
            tags=updates.tags,
            color=updates.color,
            is_shared=updates.is_shared,
        )

        return AnnotationResponse(
            id=str(annotation.id),
            resource_id=str(annotation.resource_id),
            user_id=annotation.user_id,
            start_offset=annotation.start_offset,
            end_offset=annotation.end_offset,
            highlighted_text=annotation.highlighted_text,
            note=annotation.note,
            tags=json.loads(annotation.tags) if annotation.tags else None,
            color=annotation.color,
            context_before=annotation.context_before,
            context_after=annotation.context_after,
            is_shared=bool(annotation.is_shared),
            collection_ids=json.loads(annotation.collection_ids)
            if annotation.collection_ids
            else None,
            created_at=annotation.created_at,
            updated_at=annotation.updated_at,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/annotations/{annotation_id}", status_code=204)
async def delete_annotation(
    annotation_id: str,
    user_id: str = Depends(_get_current_user_id),
    service: AnnotationService = Depends(_get_annotation_service),
):
    """
    Delete an annotation.

    Only the annotation owner can delete it.

    Args:
        annotation_id: Annotation UUID
        user_id: Authenticated user ID
        service: Annotation service instance

    Returns:
        204 No Content

    Raises:
        403: User is not the annotation owner
        404: Annotation not found
    """
    try:
        service.delete_annotation(annotation_id=annotation_id, user_id=user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/annotations/search/fulltext", response_model=AnnotationSearchResponse)
async def search_annotations_fulltext(
    query: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results to return"),
    user_id: str = Depends(_get_current_user_id),
    service: AnnotationService = Depends(_get_annotation_service),
):
    """
    Full-text search across annotation notes and highlighted text.

    Searches both the note content and highlighted text fields.

    Args:
        query: Search query string
        limit: Maximum number of results
        user_id: Authenticated user ID
        service: Annotation service instance

    Returns:
        List of matching annotations
    """
    try:
        annotations = service.search_annotations_fulltext(
            user_id=user_id, query=query, limit=limit
        )

        items = [
            AnnotationSearchResult(
                id=str(ann.id),
                resource_id=str(ann.resource_id),
                user_id=ann.user_id,
                start_offset=ann.start_offset,
                end_offset=ann.end_offset,
                highlighted_text=ann.highlighted_text,
                note=ann.note,
                tags=json.loads(ann.tags) if ann.tags else None,
                color=ann.color,
                context_before=ann.context_before,
                context_after=ann.context_after,
                is_shared=bool(ann.is_shared),
                collection_ids=json.loads(ann.collection_ids)
                if ann.collection_ids
                else None,
                created_at=ann.created_at,
                updated_at=ann.updated_at,
                resource_title=ann.resource.title if ann.resource else None,
            )
            for ann in annotations
        ]

        return AnnotationSearchResponse(items=items, total=len(items), query=query)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/annotations/search/semantic", response_model=AnnotationSearchResponse)
async def search_annotations_semantic(
    query: str = Query(..., min_length=1, description="Semantic search query"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results to return"),
    user_id: str = Depends(_get_current_user_id),
    service: AnnotationService = Depends(_get_annotation_service),
):
    """
    Semantic search across annotation notes using embeddings.

    Finds annotations with similar meaning to the query, not just keyword matches.

    Args:
        query: Search query string
        limit: Maximum number of results
        user_id: Authenticated user ID
        service: Annotation service instance

    Returns:
        List of matching annotations with similarity scores
    """
    try:
        results = service.search_annotations_semantic(
            user_id=user_id, query=query, limit=limit
        )

        items = [
            AnnotationSearchResult(
                id=str(ann.id),
                resource_id=str(ann.resource_id),
                user_id=ann.user_id,
                start_offset=ann.start_offset,
                end_offset=ann.end_offset,
                highlighted_text=ann.highlighted_text,
                note=ann.note,
                tags=json.loads(ann.tags) if ann.tags else None,
                color=ann.color,
                context_before=ann.context_before,
                context_after=ann.context_after,
                is_shared=bool(ann.is_shared),
                collection_ids=json.loads(ann.collection_ids)
                if ann.collection_ids
                else None,
                created_at=ann.created_at,
                updated_at=ann.updated_at,
                resource_title=ann.resource.title if ann.resource else None,
                similarity_score=score,
            )
            for ann, score in results
        ]

        return AnnotationSearchResponse(items=items, total=len(items), query=query)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/annotations/search/tags", response_model=AnnotationSearchResponse)
async def search_annotations_by_tags(
    tags: List[str] = Query(..., description="Tags to search for"),
    match_all: bool = Query(
        False, description="If true, match ALL tags; if false, match ANY tag"
    ),
    user_id: str = Depends(_get_current_user_id),
    service: AnnotationService = Depends(_get_annotation_service),
):
    """
    Search annotations by tags.

    Args:
        tags: List of tags to search for
        match_all: If true, annotation must have ALL tags; if false, ANY tag matches
        user_id: Authenticated user ID
        service: Annotation service instance

    Returns:
        List of matching annotations
    """
    try:
        annotations = service.search_annotations_by_tags(
            user_id=user_id, tags=tags, match_all=match_all
        )

        items = [
            AnnotationSearchResult(
                id=str(ann.id),
                resource_id=str(ann.resource_id),
                user_id=ann.user_id,
                start_offset=ann.start_offset,
                end_offset=ann.end_offset,
                highlighted_text=ann.highlighted_text,
                note=ann.note,
                tags=json.loads(ann.tags) if ann.tags else None,
                color=ann.color,
                context_before=ann.context_before,
                context_after=ann.context_after,
                is_shared=bool(ann.is_shared),
                collection_ids=json.loads(ann.collection_ids)
                if ann.collection_ids
                else None,
                created_at=ann.created_at,
                updated_at=ann.updated_at,
                resource_title=ann.resource.title if ann.resource else None,
            )
            for ann in annotations
        ]

        return AnnotationSearchResponse(
            items=items, total=len(items), query=f"tags: {', '.join(tags)}"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/annotations/export/markdown", response_class=PlainTextResponse)
async def export_annotations_markdown(
    resource_id: Optional[str] = Query(
        None, description="Optional resource ID to filter by"
    ),
    user_id: str = Depends(_get_current_user_id),
    service: AnnotationService = Depends(_get_annotation_service),
):
    """
    Export annotations to Markdown format.

    Exports all user annotations or annotations for a specific resource.
    Annotations are grouped by resource with formatted headers.

    Args:
        resource_id: Optional resource UUID to filter by
        user_id: Authenticated user ID
        service: Annotation service instance

    Returns:
        Markdown-formatted text
    """
    try:
        markdown = service.export_annotations_markdown(
            user_id=user_id, resource_id=resource_id
        )

        return PlainTextResponse(content=markdown, media_type="text/markdown")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/annotations/export/json", response_model=List[dict])
async def export_annotations_json(
    resource_id: Optional[str] = Query(
        None, description="Optional resource ID to filter by"
    ),
    user_id: str = Depends(_get_current_user_id),
    service: AnnotationService = Depends(_get_annotation_service),
):
    """
    Export annotations to JSON format.

    Exports all user annotations or annotations for a specific resource
    with complete metadata.

    Args:
        resource_id: Optional resource UUID to filter by
        user_id: Authenticated user ID
        service: Annotation service instance

    Returns:
        List of annotation objects with metadata
    """
    try:
        annotations_data = service.export_annotations_json(
            user_id=user_id, resource_id=resource_id
        )

        return annotations_data
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
