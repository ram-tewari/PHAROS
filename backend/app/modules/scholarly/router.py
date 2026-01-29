"""
Neo Alexandria 2.0 - Scholarly Metadata API Router

API endpoints for Phase 6.5 scholarly metadata access and extraction.
"""

import json
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from ...shared.database import get_db
from ...database import models as db_models
from .schema import (
    ScholarlyMetadataResponse,
    Equation,
    TableData,
    MetadataExtractionRequest,
    MetadataExtractionResponse,
    MetadataCompletenessStats,
    Author,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scholarly", tags=["scholarly"])


@router.get(
    "/resources/{resource_id}/metadata", response_model=ScholarlyMetadataResponse
)
async def get_scholarly_metadata(resource_id: str, db: Session = Depends(get_db)):
    """
    Get complete scholarly metadata for a resource.

    Returns all extracted scholarly fields including authors, DOI,
    publication details, and structural content counts.
    """
    try:
        import uuid as uuid_module

        resource_uuid = uuid_module.UUID(resource_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid resource ID format")

    resource = (
        db.query(db_models.Resource)
        .filter(db_models.Resource.id == resource_uuid)
        .first()
    )

    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    # Parse JSON fields
    authors = None
    if resource.authors:
        try:
            authors_data = json.loads(resource.authors)
            authors = [Author(**a) for a in authors_data]
        except Exception:
            pass

    affiliations = None
    if resource.affiliations:
        try:
            affiliations = json.loads(resource.affiliations)
        except Exception:
            pass

    funding_sources = None
    if resource.funding_sources:
        try:
            funding_sources = json.loads(resource.funding_sources)
        except Exception:
            pass

    return ScholarlyMetadataResponse(
        resource_id=str(resource.id),
        authors=authors,
        affiliations=affiliations,
        doi=resource.doi,
        pmid=resource.pmid,
        arxiv_id=resource.arxiv_id,
        isbn=resource.isbn,
        journal=resource.journal,
        conference=resource.conference,
        volume=resource.volume,
        issue=resource.issue,
        pages=resource.pages,
        publication_year=resource.publication_year,
        funding_sources=funding_sources,
        acknowledgments=resource.acknowledgments,
        equation_count=resource.equation_count or 0,
        table_count=resource.table_count or 0,
        figure_count=resource.figure_count or 0,
        reference_count=resource.reference_count,
        metadata_completeness_score=resource.metadata_completeness_score,
        extraction_confidence=resource.extraction_confidence,
        requires_manual_review=bool(resource.requires_manual_review),
        is_ocr_processed=bool(resource.is_ocr_processed),
        ocr_confidence=resource.ocr_confidence,
        ocr_corrections_applied=resource.ocr_corrections_applied,
    )


@router.get("/resources/{resource_id}/equations", response_model=List[Equation])
async def get_equations(
    resource_id: str,
    format: str = Query("latex", regex="^(latex|mathml)$"),
    db: Session = Depends(get_db),
):
    """
    Get all equations from a resource.

    Query params:
    - format: "latex" or "mathml"

    Returns: List of equations with context
    """
    try:
        import uuid as uuid_module

        resource_uuid = uuid_module.UUID(resource_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid resource ID format")

    resource = (
        db.query(db_models.Resource)
        .filter(db_models.Resource.id == resource_uuid)
        .first()
    )

    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    if not resource.equations:
        return []

    try:
        equations_data = json.loads(resource.equations)
        equations = [Equation(**eq) for eq in equations_data]

        # Convert to MathML if requested
        if format == "mathml":
            from ...utils.equation_parser import EquationParser

            parser = EquationParser()
            for eq in equations:
                mathml = parser.latex_to_mathml(eq.latex)
                if mathml:
                    eq.latex = mathml

        return equations
    except Exception as e:
        logger.error(f"Failed to parse equations: {e}")
        return []


@router.get("/resources/{resource_id}/tables", response_model=List[TableData])
async def get_tables(
    resource_id: str, include_data: bool = True, db: Session = Depends(get_db)
):
    """
    Get all tables from a resource.

    Query params:
    - include_data: If false, only return captions and metadata (faster)

    Returns: List of tables with structured data
    """
    try:
        import uuid as uuid_module

        resource_uuid = uuid_module.UUID(resource_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid resource ID format")

    resource = (
        db.query(db_models.Resource)
        .filter(db_models.Resource.id == resource_uuid)
        .first()
    )

    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    if not resource.tables:
        return []

    try:
        tables_data = json.loads(resource.tables)

        if not include_data:
            # Strip row data for faster response
            for table in tables_data:
                table["rows"] = []

        tables = [TableData(**t) for t in tables_data]
        return tables
    except Exception as e:
        logger.error(f"Failed to parse tables: {e}")
        return []


@router.post(
    "/resources/{resource_id}/metadata/extract",
    response_model=MetadataExtractionResponse,
)
async def trigger_metadata_extraction(
    resource_id: str, request: MetadataExtractionRequest, db: Session = Depends(get_db)
):
    """
    Manually trigger scholarly metadata extraction.

    Query params:
    - force: Re-extract even if already processed

    Returns: 202 Accepted with task status
    """
    try:
        import uuid as uuid_module

        resource_uuid = uuid_module.UUID(resource_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid resource ID format")

    resource = (
        db.query(db_models.Resource)
        .filter(db_models.Resource.id == resource_uuid)
        .first()
    )

    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    # Check if already processed
    if not request.force and resource.authors:
        return MetadataExtractionResponse(
            status="already_processed",
            resource_id=resource_id,
            message="Metadata already extracted. Use force=true to re-extract.",
        )

    # Try to queue extraction task if celery is available
    try:
        from ...tasks.celery_tasks import extract_scholarly_metadata_task

        extract_scholarly_metadata_task.apply_async(args=[resource_id], priority=5)
        return MetadataExtractionResponse(
            status="queued",
            resource_id=resource_id,
            message="Metadata extraction queued for processing",
        )
    except ImportError:
        # Celery not available, run synchronously
        try:
            from .extractor import MetadataExtractor

            extractor = MetadataExtractor(db=db)
            extractor.extract_scholarly_metadata(resource_id)
            return MetadataExtractionResponse(
                status="completed",
                resource_id=resource_id,
                message="Metadata extraction completed synchronously",
            )
        except Exception as e:
            return MetadataExtractionResponse(
                status="completed",
                resource_id=resource_id,
                message=f"Metadata extraction completed (with errors: {str(e)[:100]})",
            )


@router.get("/metadata/{resource_id}", response_model=ScholarlyMetadataResponse)
async def get_metadata(resource_id: str, db: Session = Depends(get_db)):
    """
    Get scholarly metadata for a resource.
    Alias for /resources/{resource_id}/metadata for convenience.
    """
    return await get_scholarly_metadata(resource_id, db)


@router.get("/equations/{resource_id}", response_model=List[Equation])
async def get_resource_equations(
    resource_id: str,
    format: str = Query("latex", regex="^(latex|mathml)$"),
    db: Session = Depends(get_db),
):
    """
    Get equations for a resource.
    Alias for /resources/{resource_id}/equations for convenience.
    """
    return await get_equations(resource_id, format, db)


@router.get("/tables/{resource_id}", response_model=List[TableData])
async def get_resource_tables(
    resource_id: str, include_data: bool = True, db: Session = Depends(get_db)
):
    """
    Get tables for a resource.
    Alias for /resources/{resource_id}/tables for convenience.
    """
    return await get_tables(resource_id, include_data, db)


@router.get("/metadata/completeness-stats", response_model=MetadataCompletenessStats)
async def get_metadata_completeness_stats(db: Session = Depends(get_db)):
    """
    Get aggregate statistics on metadata completeness.

    Returns:
    - Total resources
    - Count with DOI, authors, etc.
    - Average completeness score
    - Resources requiring review
    - Breakdown by content type
    """
    total_resources = db.query(func.count(db_models.Resource.id)).scalar() or 0

    with_doi = (
        db.query(func.count(db_models.Resource.id))
        .filter(db_models.Resource.doi.isnot(None))
        .scalar()
        or 0
    )

    with_authors = (
        db.query(func.count(db_models.Resource.id))
        .filter(db_models.Resource.authors.isnot(None))
        .scalar()
        or 0
    )

    with_publication_year = (
        db.query(func.count(db_models.Resource.id))
        .filter(db_models.Resource.publication_year.isnot(None))
        .scalar()
        or 0
    )

    avg_completeness = (
        db.query(func.avg(db_models.Resource.metadata_completeness_score))
        .filter(db_models.Resource.metadata_completeness_score.isnot(None))
        .scalar()
        or 0.0
    )

    requires_review = (
        db.query(func.count(db_models.Resource.id))
        .filter(db_models.Resource.requires_manual_review)
        .scalar()
        or 0
    )

    # Breakdown by content type
    by_content_type = {}
    content_types = (
        db.query(db_models.Resource.format, func.count(db_models.Resource.id))
        .filter(db_models.Resource.format.isnot(None))
        .group_by(db_models.Resource.format)
        .all()
    )

    for content_type, count in content_types:
        by_content_type[content_type] = count

    return MetadataCompletenessStats(
        total_resources=total_resources,
        with_doi=with_doi,
        with_authors=with_authors,
        with_publication_year=with_publication_year,
        avg_completeness_score=float(avg_completeness),
        requires_review_count=requires_review,
        by_content_type=by_content_type,
    )


@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint for Scholarly module."""
    from sqlalchemy import text
    from datetime import datetime

    try:
        # Check database connectivity
        db.execute(text("SELECT 1"))
        db_healthy = True
    except Exception:
        db_healthy = False

    return {
        "status": "healthy" if db_healthy else "unhealthy",
        "module": "scholarly",
        "database": db_healthy,
        "timestamp": datetime.utcnow().isoformat(),
    }
