"""
Neo Alexandria 2.0 - Resources API Router

This module provides the REST API endpoints for resource management in Neo Alexandria 2.0.
It handles URL ingestion, CRUD operations, and resource querying with filtering and pagination.

Related files:
- service.py: Business logic for resource operations
- schema.py: Pydantic schemas for request/response validation
- model.py: Resource database model

Endpoints:
- POST /resources: URL ingestion with content processing
- GET /resources: List resources with filtering, sorting, and pagination
- GET /resources/{id}: Retrieve a specific resource
- PUT /resources/{id}: Update resource metadata
- DELETE /resources/{id}: Delete a resource
- GET /resources/health: Module health check
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    BackgroundTasks,
    Response,
    Request,
    UploadFile,
    File,
)
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
from sqlalchemy.orm import Session

from ...shared.database import get_sync_db
from ...shared.event_bus import event_bus
from ...config.settings import get_settings
from .schema import (
    ResourceRead,
    ResourceUpdate,
    ResourceStatus,
    PageParams,
    SortParams,
    ResourceFilters,
)
from .schema import RepoIngestionRequest, IngestionTaskResponse, IngestionStatusResponse
from .service import (
    create_pending_resource,
    get_resource,
    list_resources,
    update_resource,
    delete_resource,
    process_ingestion,
)


router = APIRouter(prefix="/api/resources", tags=["resources"])
logger = logging.getLogger(__name__)


class ResourceIngestRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: HttpUrl = Field(..., description="URL to ingest")
    title: Optional[str] = None
    description: Optional[str] = None
    creator: Optional[str] = None
    language: Optional[str] = None
    type: Optional[str] = None
    source: Optional[str] = None


class ResourceAccepted(BaseModel):
    id: str
    status: str = "pending"
    title: str
    ingestion_status: str = "pending"


@router.get("/health", response_model=Dict[str, Any])
async def health_check(db: Session = Depends(get_sync_db)) -> Dict[str, Any]:
    """
    Health check endpoint for Resources module.

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
    try:
        # Check database connectivity
        try:
            db.execute("SELECT 1")
            db_healthy = True
            db_message = "Database connection healthy"
        except Exception as e:
            db_healthy = False
            db_message = f"Database connection failed: {str(e)}"

        # Check event handlers registration (resources emits events but may also listen)
        handlers_registered = event_bus.get_handlers("collection.updated")
        handlers_count = len(handlers_registered)

        # Determine overall status
        overall_healthy = db_healthy

        return {
            "status": "healthy" if overall_healthy else "unhealthy",
            "module": {"name": "resources", "version": "1.0.0", "domain": "resources"},
            "database": {"healthy": db_healthy, "message": db_message},
            "event_handlers": {
                "registered": handlers_count > 0,
                "count": handlers_count,
                "events": ["collection.updated"] if handlers_count > 0 else [],
                "emits": ["resource.deleted"],
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


@router.post("/resources", response_model=ResourceAccepted)
async def create_resource_endpoint(
    payload: ResourceIngestRequest,
    background: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_sync_db),
):
    """Create resource from URL (legacy endpoint - use /resources/upload for file upload)"""
    logger.info(f"=== CREATE RESOURCE ENDPOINT CALLED ===")
    logger.info(f"Payload URL: {payload.url}")
    logger.info(f"Payload title: {payload.title}")
    
    try:
        # Convert payload to dict with string values for SQLite compatibility
        payload_dict = payload.model_dump(exclude_none=True)
        # Convert HttpUrl to string
        if "url" in payload_dict:
            payload_dict["url"] = str(payload_dict["url"])

        logger.info(f"Creating pending resource...")
        # create_pending_resource handles duplicate detection
        resource = create_pending_resource(db, payload_dict)
        logger.info(f"Resource created/found: {resource.id}, status: {resource.ingestion_status}")

        # Check if this is an existing resource (reused)
        # If the resource was just created, it will have ingestion_status="pending"
        # If it was reused, the log will say "Reusing existing resource"
        is_new = (
            resource.ingestion_status == "pending"
            and resource.ingestion_started_at is None
        )

        if not is_new:
            # Return existing resource with 200 OK
            response.status_code = status.HTTP_200_OK
        else:
            # Create new resource with 202 Accepted
            response.status_code = status.HTTP_202_ACCEPTED

        # Derive engine URL from current DB bind so background uses the same database
        engine_url = None
        try:
            bind = db.get_bind()
            if bind is not None and hasattr(bind, "url"):
                engine_url = str(bind.url)
        except Exception:
            engine_url = get_settings().DATABASE_URL
        
        logger.info(f"Adding background task for resource {resource.id}")
        logger.info(f"Engine URL: {engine_url}")
        
        # Kick off background ingestion
        background.add_task(
            process_ingestion,
            str(resource.id),
            archive_root=None,
            ai=None,
            engine_url=engine_url,
        )
        
        logger.info(f"Background task added successfully for resource {resource.id}")
        
        return ResourceAccepted(
            id=str(resource.id),
            status="pending",
            title=resource.title,
            ingestion_status=resource.ingestion_status,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as exc:  # pragma: no cover - unexpected error path
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue ingestion",
        ) from exc


@router.post("/upload", response_model=ResourceAccepted)
async def upload_resource_file(
    file: UploadFile = File(..., description="File to upload (PDF, HTML, TXT)"),
    title: Optional[str] = None,
    description: Optional[str] = None,
    creator: Optional[str] = None,
    language: Optional[str] = None,
    type: Optional[str] = None,
    background: BackgroundTasks = BackgroundTasks(),
    response: Response = Response(),
    db: Session = Depends(get_sync_db),
):
    """
    Upload a file directly (multipart/form-data).
    
    Accepts PDF, HTML, and TXT files up to 50MB.
    File is saved to storage and processed asynchronously.
    
    Returns 202 Accepted with resource ID and status.
    """
    import os
    import tempfile
    from pathlib import Path
    import chardet
    
    logger.info(f"=== UPLOAD RESOURCE FILE ENDPOINT CALLED ===")
    logger.info(f"Filename: {file.filename}")
    logger.info(f"Content type: {file.content_type}")
    
    try:
        # Validate file type and content
        allowed_types = ["application/pdf", "text/html", "text/plain"]
        allowed_extensions = [".pdf", ".html", ".htm", ".txt"]
        
        file_ext = Path(file.filename).suffix.lower() if file.filename else ""
        
        if file.content_type not in allowed_types and file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Allowed: PDF, HTML, TXT. Got: {file.content_type}"
            )
        
        # Validate file content is not corrupted
        try:
            # Try to detect encoding for text files
            if file_ext in ['.txt', '.html', '.htm']:
                detected = chardet.detect(file_content[:1024])  # Check first 1KB
                if detected['confidence'] < 0.7:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="File encoding could not be reliably detected"
                    )
        except Exception as e:
            logger.warning(f"File validation warning: {e}")
        
        # Validate file size (50MB max)
        max_size = 50 * 1024 * 1024  # 50MB
        file_content = await file.read()
        if len(file_content) > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large. Maximum size: 50MB. Got: {len(file_content) / 1024 / 1024:.2f}MB"
            )
        
        # Save file to temporary location
        storage_dir = Path("storage/uploads")
        storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}{file_ext}"
        file_path = storage_dir / safe_filename
        
        with open(file_path, "wb") as f:
            f.write(file_content)
        
        logger.info(f"File saved to: {file_path}")
        
        # Create resource record with file path as identifier
        resource_data = {
            "url": f"file://{file_path.absolute()}",
            "title": title or file.filename or "Uploaded Document",
            "description": description,
            "creator": creator,
            "language": language,
            "type": type or file_ext.lstrip("."),
            "source": str(file_path.absolute()),
            "identifier": str(file_path.absolute()),  # Store file path for direct access
        }
        
        resource = create_pending_resource(db, resource_data)
        logger.info(f"Resource created: {resource.id}, file stored at: {file_path}")
        
        # Set response status
        response.status_code = status.HTTP_202_ACCEPTED
        
        # Process file directly instead of using URL fetching
        # This avoids the need for ce.fetch_url() to handle file:// URLs
        try:
            from ...utils.content_extractor import ContentExtractor
            from ...shared.ai_core import AICore
            
            ce_instance = ContentExtractor()
            ai_instance = AICore()
            
            # Read file content
            with open(file_path, 'rb') as f:
                file_bytes = f.read()
            
            # Process based on file type
            if file_ext == '.pdf':
                # Extract from PDF
                extracted = ce_instance.extract_from_pdf(file_bytes)
            elif file_ext in ['.html', '.htm']:
                # Extract from HTML
                html_content = file_bytes.decode('utf-8', errors='ignore')
                extracted = ce_instance.extract_from_html(html_content)
            else:
                # Plain text
                text_content = file_bytes.decode('utf-8', errors='ignore')
                extracted = {"text": text_content, "title": title or file.filename}
            
            # Update resource with extracted content
            resource.title = extracted.get("title") or resource.title
            resource.format = file_ext.lstrip(".")
            
            # Generate summary and tags
            text_clean = extracted.get("text", "")
            if text_clean and len(text_clean) > 50:
                summary = ai_instance.summarize(text_clean[:5000])  # Limit for performance
                tags = ai_instance.generate_tags(text_clean[:5000])
                
                resource.description = summary
                resource.subject = tags
            
            resource.ingestion_status = "completed"
            resource.ingestion_completed_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"File upload processed successfully for resource {resource.id}")
            
        except Exception as process_error:
            logger.error(f"File processing failed: {process_error}", exc_info=True)
            # Fall back to background processing
            engine_url = None
            try:
                bind = db.get_bind()
                if bind is not None and hasattr(bind, "url"):
                    engine_url = str(bind.url)
            except Exception:
                engine_url = get_settings().DATABASE_URL
            
            background.add_task(
                process_ingestion,
                str(resource.id),
                archive_root=None,
                ai=None,
                engine_url=engine_url,
            )
        
        logger.info(f"Background processing queued for resource {resource.id}")
        
        return ResourceAccepted(
            id=str(resource.id),
            status="pending",
            title=resource.title,
            ingestion_status=resource.ingestion_status,
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"File upload failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File upload failed: {str(exc)}"
        )


@router.get("/{resource_id}", response_model=ResourceRead)
async def get_resource_endpoint(
    resource_id: uuid.UUID, db: Session = Depends(get_sync_db)
):
    resource = get_resource(db, str(resource_id))
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        )
    # computed mapping for url
    resource.url = resource.source  # type: ignore[attr-defined]
    return resource


class ResourceListResponse(BaseModel):
    items: list[ResourceRead]
    total: int


@router.get("", response_model=ResourceListResponse)
async def list_resources_endpoint(
    q: Optional[str] = None,
    classification_code: Optional[str] = None,
    type: Optional[str] = None,
    language: Optional[str] = None,
    read_status: Optional[str] = None,
    min_quality: Optional[float] = None,
    created_from: Optional[str] = None,
    created_to: Optional[str] = None,
    updated_from: Optional[str] = None,
    updated_to: Optional[str] = None,
    subject_any: Optional[str] = None,
    subject_all: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
    db: Session = Depends(get_sync_db),
):
    # Parse comma-separated subject lists
    subject_any_list = subject_any.split(",") if subject_any else None
    subject_all_list = subject_all.split(",") if subject_all else None

    # Build pydantic structures from query params
    filters = ResourceFilters(
        q=q,
        classification_code=classification_code,
        type=type,
        language=language,
        read_status=read_status,  # Pydantic will validate
        min_quality=min_quality,
        created_from=created_from,
        created_to=created_to,
        updated_from=updated_from,
        updated_to=updated_to,
        subject_any=subject_any_list,
        subject_all=subject_all_list,
    )
    page = PageParams(limit=limit, offset=offset)
    sort = SortParams(sort_by=sort_by, sort_dir=sort_dir)

    items, total = list_resources(db, filters, page, sort)
    # Map url for response
    for it in items:
        it.url = it.source  # type: ignore[attr-defined]
    return ResourceListResponse(items=items, total=total)


@router.get("/resources/{resource_id}/status", response_model=ResourceStatus)
async def get_resource_status(
    resource_id: uuid.UUID, db: Session = Depends(get_sync_db)
):
    resource = get_resource(db, str(resource_id))
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        )
    return resource  # ResourceStatus uses from_attributes


@router.put("/resources/{resource_id}", response_model=ResourceRead)
async def update_resource_endpoint(
    resource_id: uuid.UUID, payload: ResourceUpdate, db: Session = Depends(get_sync_db)
):
    try:
        updated = update_resource(db, str(resource_id), payload)
        return updated
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        )


@router.delete("/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource_endpoint(
    resource_id: uuid.UUID, db: Session = Depends(get_sync_db)
):
    try:
        delete_resource(db, str(resource_id))
        return None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        )


class ClassificationOverrideRequest(BaseModel):
    code: str = Field(
        ..., min_length=1, max_length=16, description="Classification code override"
    )


@router.put("/resources/{resource_id}/classify", response_model=ResourceRead)
async def classify_resource_override(
    resource_id: uuid.UUID,
    payload: ClassificationOverrideRequest,
    db: Session = Depends(get_sync_db),
):
    try:
        updated = update_resource(
            db, str(resource_id), ResourceUpdate(classification_code=payload.code)
        )
        return updated
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        )


# ============================================================================
# CHUNKING ENDPOINTS (Phase 17.5 - Advanced RAG)
# ============================================================================


class ChunkResourceRequest(BaseModel):
    """Request schema for chunking a resource."""

    strategy: Optional[str] = Field(
        default="semantic", description="Chunking strategy: 'semantic' or 'fixed'"
    )
    chunk_size: Optional[int] = Field(
        default=500,
        ge=50,
        le=5000,
        description="Target chunk size (words for semantic, characters for fixed)",
    )
    overlap: Optional[int] = Field(
        default=50, ge=0, le=1000, description="Overlap size between chunks"
    )
    parser_type: Optional[str] = Field(
        default="text", description="Parser type: 'text', 'code_python', etc."
    )


class ChunkListResponse(BaseModel):
    """Response schema for listing chunks."""

    items: list[ResourceRead] = Field(
        ..., description="List of chunks"
    )  # Using ResourceRead as placeholder
    total: int = Field(..., description="Total number of chunks")


@router.post("/resources/{resource_id}/chunks", status_code=status.HTTP_201_CREATED)
async def create_resource_chunks(
    resource_id: uuid.UUID,
    payload: ChunkResourceRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_sync_db),
):
    """
    Chunk a resource's content into smaller pieces.

    This endpoint triggers chunking of a resource's content using the specified
    strategy. Chunking is performed asynchronously in the background.

    Args:
        resource_id: UUID of the resource to chunk
        payload: Chunking configuration (strategy, chunk_size, overlap, parser_type)
        background: FastAPI background tasks
        db: Database session

    Returns:
        202 Accepted with task status

    Raises:
        404: Resource not found
        400: Invalid chunking parameters
        500: Chunking failed
    """
    from .service import get_resource, ChunkingService

    # Verify resource exists
    resource = get_resource(db, str(resource_id))
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource not found: {resource_id}",
        )

    # Verify resource has content
    if not resource.identifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resource has no content to chunk (ingestion may not be complete)",
        )

    # Validate chunking parameters
    if payload.strategy not in ["semantic", "fixed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid chunking strategy: {payload.strategy}. Must be 'semantic' or 'fixed'",
        )

    if payload.overlap >= payload.chunk_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Overlap must be less than chunk_size",
        )

    try:
        # Load resource content from archive
        from pathlib import Path
    import chardet

        archive_path = Path(resource.identifier)
        if not archive_path.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Resource content file not found",
            )

        # Read content from archive
        try:
            content = archive_path.read_text(encoding="utf-8")
        except Exception as read_error:
            logger.error(f"Failed to read content from {archive_path}: {read_error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to read resource content",
            )

        # Create chunking service
        chunking_service = ChunkingService(
            db=db,
            strategy=payload.strategy,
            chunk_size=payload.chunk_size,
            overlap=payload.overlap,
            parser_type=payload.parser_type,
        )

        # Perform chunking in background
        def chunk_task():
            try:
                chunks = chunking_service.chunk_resource(
                    resource_id=str(resource_id),
                    content=content,
                    chunk_metadata={"source": "api_endpoint"},
                )
                logger.info(
                    f"Successfully chunked resource {resource_id}: {len(chunks)} chunks"
                )
            except Exception as e:
                logger.error(
                    f"Background chunking failed for resource {resource_id}: {e}",
                    exc_info=True,
                )

        background.add_task(chunk_task)

        return {
            "message": "Chunking started",
            "resource_id": str(resource_id),
            "strategy": payload.strategy,
            "chunk_size": payload.chunk_size,
            "overlap": payload.overlap,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"Failed to start chunking for resource {resource_id}: {exc}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start chunking: {str(exc)}",
        )


@router.get("/resources/{resource_id}/chunks")
async def list_resource_chunks(
    resource_id: uuid.UUID,
    limit: int = 25,
    offset: int = 0,
    db: Session = Depends(get_sync_db),
):
    """
    List all chunks for a resource with pagination.

    Args:
        resource_id: UUID of the resource
        limit: Maximum number of chunks to return (default: 25, max: 100)
        offset: Number of chunks to skip (default: 0)
        db: Database session

    Returns:
        List of chunks with pagination metadata

    Raises:
        404: Resource not found
    """
    from .service import get_resource
    from ...database import models as db_models

    # Verify resource exists
    resource = get_resource(db, str(resource_id))
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource not found: {resource_id}",
        )

    # Validate pagination parameters
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit must be between 1 and 100",
        )

    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Offset must be non-negative",
        )

    try:
        # Query chunks for this resource
        query = (
            db.query(db_models.DocumentChunk)
            .filter(db_models.DocumentChunk.resource_id == resource_id)
            .order_by(db_models.DocumentChunk.chunk_index)
        )

        # Get total count
        total = query.count()

        # Apply pagination
        chunks = query.offset(offset).limit(limit).all()

        # Convert to response format
        from .schema import DocumentChunkResponse

        chunk_responses = [
            DocumentChunkResponse(
                id=str(chunk.id),
                resource_id=str(chunk.resource_id),
                content=chunk.content,
                chunk_index=chunk.chunk_index,
                chunk_metadata=chunk.chunk_metadata,
                embedding_id=str(chunk.embedding_id) if chunk.embedding_id else None,
                created_at=chunk.created_at,
            )
            for chunk in chunks
        ]

        return {
            "items": chunk_responses,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    except Exception as exc:
        logger.error(
            f"Failed to list chunks for resource {resource_id}: {exc}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chunks",
        )


@router.get("/chunks/{chunk_id}")
async def get_chunk(
    chunk_id: uuid.UUID,
    db: Session = Depends(get_sync_db),
):
    """
    Retrieve a specific chunk by ID.

    Args:
        chunk_id: UUID of the chunk
        db: Database session

    Returns:
        Chunk details

    Raises:
        404: Chunk not found
    """
    from ...database import models as db_models
    from .schema import DocumentChunkResponse

    try:
        # Query for chunk
        chunk = (
            db.query(db_models.DocumentChunk)
            .filter(db_models.DocumentChunk.id == chunk_id)
            .first()
        )

        if not chunk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chunk not found: {chunk_id}",
            )

        # Convert to response format
        return DocumentChunkResponse(
            id=str(chunk.id),
            resource_id=str(chunk.resource_id),
            content=chunk.content,
            chunk_index=chunk.chunk_index,
            chunk_metadata=chunk.chunk_metadata,
            embedding_id=str(chunk.embedding_id) if chunk.embedding_id else None,
            created_at=chunk.created_at,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to retrieve chunk {chunk_id}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chunk",
        )


# ============================================================================
# REPOSITORY INGESTION ENDPOINTS (Phase 18 - Code Intelligence)
# ============================================================================


@router.post("/resources/ingest-repo", response_model=IngestionTaskResponse)
async def ingest_repository(
    request: RepoIngestionRequest,
    req: Request,
    db: Session = Depends(get_sync_db),
):
    """
    Trigger async repository ingestion from local path or Git URL.

    This endpoint starts an asynchronous Celery task to ingest an entire
    code repository. The task will:
    1. Crawl the directory or clone the Git repository
    2. Create Resource entries for each file
    3. Respect .gitignore rules and exclude binary files
    4. Auto-classify files (PRACTICE, THEORY, GOVERNANCE)
    5. Emit resource.created events for downstream processing

    Authentication: Required (JWT token) - enforced by middleware
    Rate Limiting: Applied by middleware based on user tier

    Args:
        request: Repository ingestion request (path or git_url)
        req: FastAPI request object (contains authenticated user in state)
        db: Database session

    Returns:
        Task ID and initial status for progress tracking

    Raises:
        400: Invalid request (path doesn't exist, invalid URL, or both/neither provided)
        401: Authentication required (enforced by middleware)
        429: Rate limit exceeded (enforced by middleware)
        500: Failed to start ingestion task
    """
    from pathlib import Path
    import chardet
    from urllib.parse import urlparse
    from ...tasks.celery_tasks import ingest_repo_task

    # Validate request
    if request.path:
        # Validate local path exists
        path_obj = Path(request.path)
        if not path_obj.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Path does not exist: {request.path}",
            )
        if not path_obj.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Path is not a directory: {request.path}",
            )

    elif request.git_url:
        # Validate Git URL format
        try:
            parsed = urlparse(request.git_url)
            # Only allow https:// URLs for security
            if parsed.scheme != "https":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Only HTTPS Git URLs are allowed",
                )
            if not parsed.netloc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid Git URL format",
                )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid Git URL: {str(e)}",
            )

    try:
        # Trigger Celery task
        task = ingest_repo_task.delay(path=request.path, git_url=request.git_url)

        logger.info(
            f"Started repository ingestion task {task.id}: "
            f"path={request.path}, git_url={request.git_url}"
        )

        return IngestionTaskResponse(
            task_id=task.id, status="PENDING", message="Repository ingestion started"
        )

    except Exception as exc:
        logger.error(f"Failed to start repository ingestion: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start repository ingestion: {str(exc)}",
        )


@router.get(
    "/resources/ingest-repo/{task_id}/status", response_model=IngestionStatusResponse
)
async def get_ingestion_status(
    task_id: str,
    req: Request,
):
    """
    Get status of repository ingestion task.

    This endpoint queries the Celery task state and returns progress information
    including files processed, total files, and current file being processed.

    Authentication: Required (JWT token) - enforced by middleware

    Args:
        task_id: Celery task ID returned from ingest-repo endpoint
        req: FastAPI request object (contains authenticated user in state)

    Returns:
        Task status with progress information

    Raises:
        404: Task not found
        401: Authentication required (enforced by middleware)
        500: Failed to retrieve task status
    """
    from celery.result import AsyncResult
    from ...tasks.celery_app import celery_app

    try:
        # Get task result
        task_result = AsyncResult(task_id, app=celery_app)

        # Build response based on task state
        response = IngestionStatusResponse(task_id=task_id, status=task_result.state)

        # Add progress information if available
        if task_result.state == "PROCESSING":
            info = task_result.info or {}
            response.files_processed = info.get("current", 0)
            response.total_files = info.get("total", 0)
            response.current_file = info.get("current_file")
            response.started_at = info.get("started_at")

        elif task_result.state == "COMPLETED":
            info = task_result.info or {}
            response.files_processed = info.get("files_processed", 0)
            response.total_files = info.get("files_processed", 0)
            response.completed_at = info.get("completed_at")

        elif task_result.state == "FAILED":
            info = task_result.info or {}
            response.error = info.get("error", str(task_result.info))

        return response

    except Exception as exc:
        logger.error(
            f"Failed to retrieve task status for {task_id}: {exc}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve task status: {str(exc)}",
        )



# ============================================================================
# Auto-Linking Endpoints - Phase 20
# ============================================================================


class AutoLinkResponse(BaseModel):
    """Response schema for auto-linking endpoint."""
    
    resource_id: str
    link_count: int
    threshold: float
    message: str


@router.post("/resources/{resource_id}/auto-link", response_model=AutoLinkResponse)
async def auto_link_resource(
    resource_id: uuid.UUID,
    similarity_threshold: Optional[float] = 0.7,
    db: Session = Depends(get_sync_db)
) -> AutoLinkResponse:
    """
    Automatically link resource chunks to related chunks based on semantic similarity.
    
    This endpoint computes vector similarity between chunks of the specified resource
    and chunks from other resources, creating bidirectional links when similarity
    exceeds the threshold (default 0.7).
    
    **Use Cases**:
    - Link PDF documentation to code implementations
    - Link code files to related documentation
    - Discover semantic relationships between resources
    
    **Performance**: <5s for 100 chunks (Requirement 3.5)
    
    Args:
        resource_id: Resource ID to link
        similarity_threshold: Minimum similarity score for creating links (0.0-1.0)
        db: Database session
        
    Returns:
        AutoLinkResponse with link count and status
        
    Raises:
        404: Resource not found
        400: Invalid similarity threshold
        500: Auto-linking failed
    """
    from .service import AutoLinkingService
    
    try:
        # Validate similarity threshold
        if not 0.0 <= similarity_threshold <= 1.0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Similarity threshold must be between 0.0 and 1.0"
            )
        
        # Check if resource exists
        from .service import get_resource
        resource = get_resource(db, str(resource_id))
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resource not found: {resource_id}"
            )
        
        # Initialize auto-linking service
        auto_linking_service = AutoLinkingService(
            db=db,
            similarity_threshold=similarity_threshold
        )
        
        # Determine resource type and call appropriate linking method
        # For now, we'll try both directions (PDF to code and code to PDF)
        # In production, this would check resource format/type
        
        # Try linking as PDF to code
        links = await auto_linking_service.link_pdf_to_code(
            str(resource_id),
            similarity_threshold=similarity_threshold
        )
        
        # If no links created, try linking as code to PDF
        if not links:
            links = await auto_linking_service.link_code_to_pdfs(
                str(resource_id),
                similarity_threshold=similarity_threshold
            )
        
        logger.info(
            f"Auto-linking completed for resource {resource_id}: {len(links)} links created"
        )
        
        return AutoLinkResponse(
            resource_id=str(resource_id),
            link_count=len(links),
            threshold=similarity_threshold,
            message=f"Successfully created {len(links)} links"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auto-linking failed for resource {resource_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Auto-linking failed: {str(e)}"
        )
