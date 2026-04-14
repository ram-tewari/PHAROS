from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func, or_, asc, desc, String, cast, select

from ...database import models as db_models
from ...shared.database import Base, SessionLocal
from ...utils import content_extractor as ce
from ...utils.text_processor import clean_text, readability_scores
from .schema import ResourceUpdate, PageParams, SortParams, ResourceFilters
from ...shared.ai_core import AICore
from ...monitoring import (
    track_ingestion_success,
    track_ingestion_failure,
    increment_active_ingestions,
    decrement_active_ingestions,
)
from ...shared.event_bus import event_bus, EventPriority
from ...events.event_types import SystemEvent


ARCHIVE_ROOT = Path("storage/archive")
logger = logging.getLogger(__name__)


def _find_existing_resource_by_url(
    db: Session, url: str
) -> Optional[db_models.Resource]:
    """
    Query for existing resource by source URL.

    Args:
        db: Database session
        url: Source URL to search for

    Returns:
        Existing resource if found, None otherwise
    """
    result = db.execute(
        select(db_models.Resource)
        .filter(db_models.Resource.source == url)
        .order_by(db_models.Resource.created_at.desc())
    )
    return result.scalar_one_or_none()


def create_pending_resource(db: Session, payload: Dict[str, Any]) -> db_models.Resource:
    """
    Create a pending resource row and return it. Idempotent on URL/source.

    Args:
        db: Database session
        payload: Resource data including required 'url' field

    Returns:
        Created or existing resource

    Raises:
        ValueError: If url is not provided
    """
    try:
        Base.metadata.create_all(bind=db.get_bind())
    except Exception:
        pass

    url = payload.get("url")
    if not url:
        raise ValueError("url is required")

    # Query: Check for existing resource (no side effects)
    existing = _find_existing_resource_by_url(db, url)
    if existing:
        logger.info(f"Reusing existing resource for URL: {url}")
        return existing

    # Modifier: Create new resource
    logger.info(f"Creating new pending resource for URL: {url}")
    now = datetime.now(timezone.utc)

    # Import authority control service (optional - gracefully handle if not available)
    creator_value = payload.get("creator")
    publisher_value = payload.get("publisher")

    try:
        from ...modules.authority.service import AuthorityControl

        authority = AuthorityControl(db)
        if creator_value:
            creator_value = authority.normalize_creator(creator_value)
        if publisher_value:
            publisher_value = authority.normalize_publisher(publisher_value)
    except Exception as e:
        logger.warning(f"Authority control not available, using raw values: {e}")

    resource = db_models.Resource(
        title=payload.get("title") or "Untitled",
        description=payload.get("description"),
        creator=creator_value,
        publisher=publisher_value,
        contributor=payload.get("contributor"),
        date_created=payload.get("date_created"),
        date_modified=payload.get("date_modified") or now,
        type=payload.get("type"),
        format=payload.get("format"),
        identifier=None,
        source=payload.get("source") or url,
        language=payload.get("language"),
        coverage=payload.get("coverage"),
        rights=payload.get("rights"),
        subject=payload.get("subject") or [],
        relation=payload.get("relation") or [],
        classification_code=None,
        read_status=payload.get("read_status") or "unread",
        quality_score=0.0,
        ingestion_status="pending",
        ingestion_error=None,
        ingestion_started_at=None,
        ingestion_completed_at=None,
    )
    db.add(resource)
    db.commit()
    # No need to refresh - all fields are set explicitly
    logger.info(f"Created pending resource with source: {url}")

    # Emit resource.created event
    try:
        # Ensure handlers are registered (in case app didn't initialize them)
        from .handlers import register_handlers

        if (
            "resource.created" not in event_bus._handlers
            or len(event_bus._handlers.get("resource.created", [])) == 0
        ):
            logger.info("Registering resource handlers (not initialized by app)")
            register_handlers()

        event_bus.emit(
            SystemEvent.RESOURCE_CREATED.value,
            {
                "resource_id": str(resource.id),
                "title": resource.title,
                "source": resource.source,
            },
            priority=EventPriority.NORMAL,
        )
        logger.info(f"Emitted resource.created event for {resource.id}")
    except Exception as e:
        logger.error(f"Failed to emit resource.created event: {e}", exc_info=True)

    return resource


def _mark_ingestion_started(session: Session, resource: db_models.Resource) -> None:
    """
    Mark resource ingestion as started (modifier).

    Args:
        session: Database session
        resource: Resource to update
    """
    resource.ingestion_status = "processing"
    resource.ingestion_error = None
    resource.ingestion_started_at = datetime.now(timezone.utc)
    session.add(resource)
    session.commit()
    logger.info(f"Resource {resource.id} marked as processing")


def _mark_ingestion_failed(
    session: Session, resource: db_models.Resource, error: str
) -> None:
    """
    Mark resource ingestion as failed (modifier).

    Args:
        session: Database session
        resource: Resource to update
        error: Error message
    """
    resource.ingestion_status = "failed"
    resource.ingestion_error = error
    resource.ingestion_completed_at = datetime.now(timezone.utc)
    session.add(resource)
    session.commit()
    logger.error(f"Resource {resource.id} marked as failed: {error}")


def _mark_ingestion_completed(session: Session, resource: db_models.Resource) -> None:
    """
    Mark resource ingestion as completed (modifier).

    Args:
        session: Database session
        resource: Resource to update
    """
    resource.ingestion_status = "completed"
    resource.ingestion_completed_at = datetime.now(timezone.utc)
    session.add(resource)
    session.commit()
    logger.info(f"Resource {resource.id} marked as completed")


def _fetch_and_extract_content(
    target_url: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """
    Fetch and extract content from URL (query with external side effects).

    Args:
        target_url: URL to fetch

    Returns:
        Tuple of (fetched_data, extracted_data, cleaned_text)
    """
    logger.info(f"Fetching content from {target_url}")
    fetched = ce.fetch_url(target_url)
    logger.info("Content fetched successfully, extracting text")

    # Extract metadata for PDFs
    content_type = (fetched.get("content_type") or "").lower()
    is_pdf = "application/pdf" in content_type or target_url.lower().endswith(".pdf")

    extracted = ce.extract_from_fetched(fetched, extract_metadata=is_pdf)
    text_clean = clean_text(extracted.get("text", ""))
    logger.info(f"Text extracted and cleaned, length: {len(text_clean)} characters")

    if is_pdf and extracted.get("page_boundaries"):
        logger.info(
            f"Extracted {len(extracted.get('page_boundaries', []))} page boundaries from PDF"
        )

    return fetched, extracted, text_clean


def _generate_ai_content(ai_core: AICore, text_clean: str) -> Tuple[str, List[str]]:
    """
    Generate AI summary and tags (query with external side effects).

    Args:
        ai_core: AI core service
        text_clean: Cleaned text

    Returns:
        Tuple of (summary, tags)
    """
    summary = ai_core.summarize(text_clean)
    tags_raw = ai_core.generate_tags(text_clean)
    return summary, tags_raw


def _generate_embeddings(
    ai_core: AICore,
    resource: db_models.Resource,
    session: Session,
    title: str,
    description: str,
    tags: List[str],
) -> None:
    """
    Generate dense and sparse embeddings for resource (modifier).

    Args:
        ai_core: AI core service
        resource: Resource to update
        session: Database session
        title: Resource title
        description: Resource description
        tags: Resource tags
    """
    # Generate dense embedding
    try:
        from ...shared.embeddings import create_composite_text

        temp_resource = type(
            "obj",
            (object,),
            {"title": title, "description": description, "subject": tags},
        )()
        composite_text = create_composite_text(temp_resource)
        if composite_text.strip():
            embedding = ai_core.generate_embedding(composite_text)
            if embedding:
                resource.embedding = embedding
                logger.info(f"Generated dense embedding for resource {resource.id}")
    except Exception as e:
        logger.warning(f"Dense embedding generation failed: {e}")

    # Generate sparse embedding
    try:
        from ..search.sparse_embeddings import SparseEmbeddingService

        sparse_service = SparseEmbeddingService(session, model_name="BAAI/bge-m3")

        text_parts = []
        if title:
            text_parts.append(title)
        if description:
            text_parts.append(description)
        if tags:
            subjects_text = " ".join(tags)
            if subjects_text.strip():
                text_parts.append(f"Keywords: {subjects_text}")

        composite_text = " ".join(text_parts)

        if not composite_text.strip():
            resource.sparse_embedding = None
            resource.sparse_embedding_model = None
            resource.sparse_embedding_updated_at = datetime.now(timezone.utc)
        else:
            sparse_vec = sparse_service.generate_sparse_embedding(composite_text)
            if sparse_vec:
                resource.sparse_embedding = json.dumps(sparse_vec)
                resource.sparse_embedding_model = "BAAI/bge-m3"
                resource.sparse_embedding_updated_at = datetime.now(timezone.utc)
                logger.info(f"Generated sparse embedding for resource {resource.id}")
            else:
                resource.sparse_embedding = None
                resource.sparse_embedding_model = None
                resource.sparse_embedding_updated_at = None
    except Exception as e:
        logger.warning(f"Sparse embedding generation failed: {e}")
        resource.sparse_embedding = None
        resource.sparse_embedding_model = None
        resource.sparse_embedding_updated_at = None


def _perform_ml_classification(session: Session, resource_id) -> None:
    """
    Perform ML classification on resource (modifier).

    Args:
        session: Database session
        resource_id: Resource ID
    """
    try:
        from ...services.classification_service import ClassificationService

        classification_service = ClassificationService(
            db=session, use_ml=True, confidence_threshold=0.3
        )

        classification_result = classification_service.classify_resource(
            resource_id=resource_id, use_ml=True
        )

        logger.info(
            f"ML classification completed for resource {resource_id}: "
            f"{len(classification_result.get('classifications', []))} classifications"
        )
    except Exception as e:
        logger.warning(f"ML classification failed for resource {resource_id}: {e}")


def _compute_quality_scores(session: Session, resource_id) -> None:
    """
    Compute quality scores for resource (modifier).

    Args:
        session: Database session
        resource_id: Resource ID
    """
    try:
        from ...services.quality_service import QualityService

        quality_service = QualityService(db=session)
        quality_result = quality_service.compute_quality(resource_id)

        # quality_result is a QualityScore domain object
        logger.info(
            f"Quality assessment completed for resource {resource_id}: "
            f"overall={quality_result.overall_score():.2f}"
        )
    except Exception as e:
        logger.warning(f"Quality assessment failed for resource {resource_id}: {e}")


def _evaluate_summarization(session: Session, resource_id, summary: str) -> None:
    """
    Evaluate summarization quality (modifier).

    Args:
        session: Database session
        resource_id: Resource ID
        summary: Generated summary
    """
    if not summary or not summary.strip():
        return

    try:
        from ...services.summarization_evaluator import SummarizationEvaluator

        summarization_evaluator = SummarizationEvaluator(db=session)
        summary_result = summarization_evaluator.evaluate_summary(
            resource_id=resource_id, use_g_eval=False
        )

        logger.info(
            f"Summarization evaluation completed for resource {resource_id}: "
            f"overall={summary_result.get('overall', 0.0):.2f}"
        )
    except Exception as e:
        logger.warning(
            f"Summarization evaluation failed for resource {resource_id}: {e}"
        )


def _extract_citations(session: Session, resource_id: str, content_type: str) -> None:
    """
    Extract citations from resource content (modifier).

    Args:
        session: Database session
        resource_id: Resource ID
        content_type: Content type
    """
    try:
        content_type_lower = content_type.lower()
        if any(ct in content_type_lower for ct in ["html", "pdf", "markdown"]):
            from ...services.citation_service import CitationService

            citation_service = CitationService(session)
            citation_service.extract_citations(resource_id)
            citation_service.resolve_internal_citations()
            logger.info(f"Citations extracted for resource {resource_id}")
    except Exception as e:
        logger.warning(f"Citation extraction failed for resource {resource_id}: {e}")


def process_ingestion(
    resource_id: str,
    archive_root: Path | str | None = None,
    ai: Optional[AICore] = None,
    engine_url: Optional[str] = None,
) -> None:
    """
    Background ingestion job (modifier, returns None). Opens its own DB session.

    Steps: fetch, extract, AI summarize/tag, authority normalize, classify, quality, archive, persist.

    Args:
        resource_id: Resource ID to ingest
        archive_root: Optional archive root directory
        ai: Optional AI core instance
        engine_url: Optional database engine URL
    """
    session: Optional[Session] = None
    increment_active_ingestions()
    start_time = datetime.now(timezone.utc)

    logger.info(
        f"[INGESTION START] Resource {resource_id} - Starting background ingestion"
    )

    # Emit ingestion.started event
    event_bus.emit(
        SystemEvent.INGESTION_STARTED.value,
        {"resource_id": resource_id, "started_at": start_time.isoformat()},
        priority=EventPriority.NORMAL,
    )

    try:
        # Setup database session
        if engine_url:
            engine = create_engine(engine_url, echo=False)
            local_session_factory = sessionmaker(
                autocommit=False, autoflush=False, bind=engine
            )
            session = local_session_factory()
        else:
            # Import SessionLocal here to ensure it's initialized
            from ...shared.database import SessionLocal as _SessionLocal

            if _SessionLocal is None:
                logger.error("SessionLocal is None - database not initialized")
                return
            session = _SessionLocal()

        try:
            Base.metadata.create_all(bind=session.get_bind())
        except Exception:
            pass

        # Query: Get resource
        try:
            import uuid as uuid_module

            resource_uuid = uuid_module.UUID(resource_id)
        except (ValueError, TypeError):
            logger.error(f"Invalid UUID format for resource_id: {resource_id}")
            return

        resource = (
            session.query(db_models.Resource)
            .filter(db_models.Resource.id == resource_uuid)
            .first()
        )
        if not resource:
            logger.warning(f"Resource not found: {resource_id}")
            return

        # Modifier: Mark ingestion started
        logger.info(f"[INGESTION] {resource_id} - Marking as started")
        _mark_ingestion_started(session, resource)

        target_url = resource.source or ""

        # Query: Fetch and extract content with error handling
        logger.info(f"[INGESTION] {resource_id} - Fetching content from {target_url}")
        try:
            fetched, extracted, text_clean = _fetch_and_extract_content(target_url)
        except Exception as fetch_error:
            # Mark resource as failed with error details
            logger.error(
                f"[INGESTION ERROR] {resource_id} - Failed to fetch URL: {fetch_error}"
            )
            resource.ingestion_status = "error"
            resource.ingestion_error = f"Failed to fetch URL: {str(fetch_error)}. Please verify the URL is correct or upload the content as a PDF."
            resource.ingestion_completed_at = datetime.now(timezone.utc)
            session.commit()

            # Emit error event
            event_bus.emit(
                SystemEvent.INGESTION_FAILED.value,
                {
                    "resource_id": resource_id,
                    "error": str(fetch_error),
                    "error_type": "URL_FETCH_FAILED",
                    "message": "URL could not be fetched. Please verify the URL or upload as PDF.",
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                },
                priority=EventPriority.HIGH,
            )
            return

        # Validate content was actually fetched
        if not text_clean or len(text_clean) < 50:
            logger.error(
                f"[INGESTION ERROR] {resource_id} - Insufficient content fetched ({len(text_clean)} chars)"
            )
            resource.ingestion_status = "error"
            resource.ingestion_error = "URL returned insufficient content. The page may be empty, require authentication, or block automated access. Please verify the URL or upload as PDF."
            resource.ingestion_completed_at = datetime.now(timezone.utc)
            session.commit()

            event_bus.emit(
                SystemEvent.INGESTION_FAILED.value,
                {
                    "resource_id": resource_id,
                    "error": "Insufficient content",
                    "error_type": "INSUFFICIENT_CONTENT",
                    "message": "URL returned insufficient content. Please verify or upload as PDF.",
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                },
                priority=EventPriority.HIGH,
            )
            return

        logger.info(
            f"[INGESTION] {resource_id} - Fetched {len(text_clean)} chars of content"
        )

        # Resolve AI core
        if ai is not None:
            ai_core = ai
        else:
            try:
                import sys as _sys

                _mod = _sys.modules.get(__name__)
                AICoreClass = getattr(_mod, "AICore") if _mod is not None else AICore
            except Exception:  # pragma: no cover
                AICoreClass = AICore
            ai_core = AICoreClass()

        # Query: Generate AI content
        logger.info(f"[INGESTION] {resource_id} - Generating AI summary and tags")
        summary, tags_raw = _generate_ai_content(ai_core, text_clean)
        logger.info(
            f"[INGESTION] {resource_id} - Generated summary ({len(summary)} chars) and {len(tags_raw)} tags"
        )

        # Query: Normalize tags
        from ...modules.authority.service import AuthorityControl

        logger.info(f"[INGESTION] {resource_id} - Normalizing tags")
        authority = AuthorityControl(session)
        normalized_tags = authority.normalize_subjects(tags_raw)
        logger.info(
            f"[INGESTION] {resource_id} - Normalized to {len(normalized_tags)} tags"
        )

        # Taxonomy/classification module has been removed (single-tenant optimization).
        # classification_code is left as None; the field remains on the model for
        # any future lightweight tagging.
        extracted_title = extracted.get("title") or ""
        if resource.title == "Untitled" and extracted_title:
            title_final = extracted_title
        else:
            title_final = resource.title or extracted_title or "Untitled"
        description_final = resource.description or summary or None
        classification_code = None

        # Modifier: Archive content
        meta = {
            "source_url": fetched.get("url"),
            "status": fetched.get("status"),
            "extracted_title": extracted.get("title"),
            "readability": readability_scores(text_clean),
            "content_type": fetched.get("content_type"),
        }
        root_path = archive_root or ARCHIVE_ROOT
        root_path = root_path if isinstance(root_path, Path) else Path(str(root_path))

        try:
            root_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Archive root ready: {root_path}")
        except Exception as mkdir_exc:
            logger.error(f"Failed to create archive root {root_path}: {str(mkdir_exc)}")

        html_for_archive = fetched.get("html") or ""
        archive_info = ce.archive_local(
            fetched.get("url", target_url),
            html_for_archive,
            text_clean,
            meta,
            root_path,
        )
        logger.info(f"Content archived to {archive_info.get('archive_path')}")

        # Modifier: Generate embeddings
        _generate_embeddings(
            ai_core, resource, session, title_final, description_final, normalized_tags
        )

        # Modifier: Chunk resource content (optional, controlled by configuration)
        # Chunking failures should NOT fail the entire ingestion
        try:
            from ...config.settings import get_settings

            settings = get_settings()
            chunk_on_create = getattr(settings, "CHUNK_ON_RESOURCE_CREATE", True)

            if chunk_on_create and text_clean:
                logger.info(
                    f"[INGESTION] {resource_id} - Starting chunking ({len(text_clean)} chars)"
                )

                # Import ChunkingService (defined later in this file)
                # We need to use the class from this module
                try:
                    # Create chunking service with settings from config
                    chunking_strategy = getattr(
                        settings, "CHUNKING_STRATEGY", "semantic"
                    )
                    chunk_size = getattr(settings, "CHUNK_SIZE", 500)
                    chunk_overlap = getattr(settings, "CHUNK_OVERLAP", 50)

                    logger.info(
                        f"Chunking config: strategy={chunking_strategy}, size={chunk_size}, overlap={chunk_overlap}"
                    )

                    chunking_service = ChunkingService(
                        db=session,
                        strategy=chunking_strategy,
                        chunk_size=chunk_size,
                        overlap=chunk_overlap,
                        parser_type="text",
                        embedding_service=ai_core,  # Reuse AI core for embeddings
                    )

                    # Prepare chunk metadata with page boundaries for PDFs
                    base_chunk_metadata = {"source": "ingestion_pipeline"}
                    if is_pdf and extracted.get("page_boundaries"):
                        base_chunk_metadata["page_boundaries"] = extracted.get(
                            "page_boundaries"
                        )
                        logger.info(
                            f"Including {len(extracted.get('page_boundaries', []))} page boundaries in chunk metadata"
                        )

                    # Chunk the content
                    chunks = chunking_service.chunk_resource(
                        resource_id=str(resource.id),
                        content=text_clean,
                        chunk_metadata=base_chunk_metadata,
                    )
                    logger.info(
                        f"[INGESTION] {resource_id} - Successfully chunked: {len(chunks)} chunks created"
                    )
                except Exception as chunk_error:
                    # Log error but don't fail ingestion - chunking is optional
                    logger.error(
                        f"Chunking failed for resource {resource_id}: {chunk_error}",
                        exc_info=True,
                    )
                    # Continue with ingestion even if chunking fails
                    logger.warning(
                        f"Resource {resource_id} will be created without chunks - "
                        "RAG functionality may be limited for this resource"
                    )
        except Exception as config_error:
            # If configuration check fails, skip chunking but don't fail ingestion
            logger.error(
                f"Chunking configuration check failed: {config_error}", exc_info=True
            )
            logger.warning(
                f"Skipping chunking for resource {resource_id} due to configuration error"
            )

        # Modifier: Perform ML classification
        _perform_ml_classification(session, resource.id)

        # Query: Compute legacy quality score (simple heuristic)
        # Use a basic quality score calculation based on metadata completeness
        quality_score = 0.0
        if title_final and title_final != "Untitled":
            quality_score += 0.2
        if description_final:
            quality_score += 0.2
        if normalized_tags:
            quality_score += 0.2
        if resource.creator:
            quality_score += 0.1
        if resource.language:
            quality_score += 0.1
        if len(text_clean) > 100:
            quality_score += 0.2
        quality = quality_score

        # Modifier: Persist resource updates
        resource.title = title_final
        resource.description = description_final
        resource.subject = normalized_tags
        resource.classification_code = classification_code
        resource.identifier = archive_info.get("archive_path")
        resource.source = resource.source or fetched.get("url")
        resource.quality_score = float(quality)
        resource.date_modified = resource.date_modified or datetime.now(timezone.utc)
        resource.format = fetched.get("content_type")

        # Store PDF structured metadata in existing scholarly fields
        if is_pdf and extracted.get("structured_metadata"):
            pdf_metadata = extracted.get("structured_metadata", {})

            # Store title if not already set and available in PDF metadata
            if pdf_metadata.get("title") and (
                not resource.title or resource.title == "Untitled"
            ):
                resource.title = pdf_metadata["title"]
                logger.info(
                    f"Set resource title from PDF metadata: {pdf_metadata['title']}"
                )

            # Store authors in the authors field
            if pdf_metadata.get("authors"):
                resource.authors = pdf_metadata["authors"]
                logger.info(
                    f"Set resource authors from PDF metadata: {pdf_metadata['authors']}"
                )

            # Store abstract in description if not already set
            if pdf_metadata.get("abstract") and not resource.description:
                resource.description = pdf_metadata["abstract"]
                logger.info(f"Set resource description from PDF abstract")

            # Store subject/keywords if available
            if pdf_metadata.get("keywords"):
                keywords = (
                    pdf_metadata["keywords"].split(",")
                    if isinstance(pdf_metadata["keywords"], str)
                    else []
                )
                keywords = [k.strip() for k in keywords if k.strip()]
                if keywords:
                    # Merge with existing tags
                    existing_tags = set(resource.subject or [])
                    existing_tags.update(keywords)
                    resource.subject = list(existing_tags)
                    logger.info(f"Added {len(keywords)} keywords from PDF metadata")

        session.add(resource)

        # Modifier: Mark ingestion completed BEFORE commit
        _mark_ingestion_completed(session, resource)

        # Commit the main resource data
        session.commit()
        logger.info(f"Resource {resource_id} data committed successfully")

        # Post-processing steps (these run after main commit, failures won't rollback resource)
        # Modifier: Compute quality scores
        try:
            _compute_quality_scores(session, resource.id)
        except Exception as e:
            logger.warning(f"Quality computation failed (non-fatal): {e}")

        # Modifier: Evaluate summarization
        try:
            _evaluate_summarization(session, resource.id, summary)
        except Exception as e:
            logger.warning(f"Summarization evaluation failed (non-fatal): {e}")

        # Modifier: Extract citations
        try:
            _extract_citations(
                session, str(resource.id), fetched.get("content_type", "")
            )
        except Exception as e:
            logger.warning(f"Citation extraction failed (non-fatal): {e}")

        # Track successful ingestion
        track_ingestion_success()

        # Calculate duration
        end_time = datetime.now(timezone.utc)
        duration_seconds = (end_time - start_time).total_seconds()

        logger.info(f"Ingestion completed successfully for resource {resource_id}")

        # Emit ingestion.completed event
        event_bus.emit(
            SystemEvent.INGESTION_COMPLETED.value,
            {
                "resource_id": resource_id,
                "duration_seconds": duration_seconds,
                "success": True,
                "completed_at": end_time.isoformat(),
            },
            priority=EventPriority.NORMAL,
        )

    except Exception as exc:  # pragma: no cover - error path
        logger.error(
            f"Ingestion failed for resource {resource_id}: {type(exc).__name__}: {str(exc)}",
            exc_info=True,
        )

        # Calculate duration
        end_time = datetime.now(timezone.utc)
        duration_seconds = (end_time - start_time).total_seconds()

        # Emit ingestion.failed event
        event_bus.emit(
            SystemEvent.INGESTION_FAILED.value,
            {
                "resource_id": resource_id,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "duration_seconds": duration_seconds,
                "success": False,
                "failed_at": end_time.isoformat(),
            },
            priority=EventPriority.HIGH,
        )

        if session is not None:
            try:
                import uuid as uuid_module

                try:
                    resource_uuid = uuid_module.UUID(resource_id)
                    resource = (
                        session.query(db_models.Resource)
                        .filter(db_models.Resource.id == resource_uuid)
                        .first()
                    )
                except (ValueError, TypeError):
                    resource = None

                if resource is not None:
                    _mark_ingestion_failed(session, resource, str(exc))
                    track_ingestion_failure(type(exc).__name__)
            except Exception as commit_exc:
                logger.error(
                    f"Failed to update resource status for {resource_id}: {str(commit_exc)}"
                )
    finally:
        decrement_active_ingestions()
        if session is not None:
            session.close()


def get_resource(db: Session, resource_id) -> Optional[db_models.Resource]:
    """
    Query for a resource by ID (pure query, no side effects).

    Args:
        db: Database session
        resource_id: Resource ID (UUID or string)

    Returns:
        Resource if found, None otherwise
    """
    try:
        Base.metadata.create_all(bind=db.get_bind())
    except Exception:
        pass

    # Convert string resource_id to UUID if needed
    if isinstance(resource_id, str):
        try:
            import uuid as uuid_module

            resource_uuid = uuid_module.UUID(resource_id)
        except (ValueError, TypeError):
            return None
    else:
        resource_uuid = resource_id

    result = db.execute(
        select(db_models.Resource).filter(db_models.Resource.id == resource_uuid)
    )
    return result.scalar_one_or_none()


def _apply_resource_filters(query, filters: ResourceFilters):
    """
    Apply filters to resource query (pure query helper).

    Args:
        query: SQLAlchemy query
        filters: Resource filters

    Returns:
        Filtered query
    """
    if not filters:
        return query

    if filters.q:
        q_val = f"%{filters.q.lower()}%"
        query = query.filter(
            or_(
                func.lower(db_models.Resource.title).like(q_val),
                func.lower(db_models.Resource.description).like(q_val),
            )
        )

    if filters.classification_code:
        query = query.filter(
            db_models.Resource.classification_code == filters.classification_code
        )

    if filters.type:
        query = query.filter(db_models.Resource.type == filters.type)

    if filters.language:
        query = query.filter(db_models.Resource.language == filters.language)

    if filters.read_status:
        query = query.filter(db_models.Resource.read_status == filters.read_status)

    if filters.min_quality is not None:
        query = query.filter(
            db_models.Resource.quality_score >= float(filters.min_quality)
        )

    if filters.created_from:
        query = query.filter(db_models.Resource.created_at >= filters.created_from)
    if filters.created_to:
        query = query.filter(db_models.Resource.created_at <= filters.created_to)
    if filters.updated_from:
        query = query.filter(db_models.Resource.updated_at >= filters.updated_from)
    if filters.updated_to:
        query = query.filter(db_models.Resource.updated_at <= filters.updated_to)

    # Fallback subject matching on serialized JSON text (portable across SQLite/Postgres)
    if filters.subject_any:
        ser = func.lower(cast(db_models.Resource.subject, String))
        ors = [ser.like(f"%{term.lower()}%") for term in filters.subject_any]
        if ors:
            query = query.filter(or_(*ors))

    if filters.subject_all:
        ser_all = func.lower(cast(db_models.Resource.subject, String))
        for term in filters.subject_all:
            query = query.filter(ser_all.like(f"%{term.lower()}%"))

    return query


def list_resources(
    db: Session,
    filters: ResourceFilters,
    page: PageParams,
    sort: SortParams,
) -> Tuple[List[db_models.Resource], int]:
    """
    Query for list of resources with filtering, pagination, and sorting (pure query).

    Args:
        db: Database session
        filters: Resource filters
        page: Pagination parameters
        sort: Sort parameters

    Returns:
        Tuple of (resources, total_count)
    """
    try:
        Base.metadata.create_all(bind=db.get_bind())
    except Exception:
        pass

    query = select(db_models.Resource)
    query = _apply_resource_filters(query, filters)

    # Total before pagination
    count_query = select(func.count()).select_from(query.subquery())
    total_result = db.execute(count_query)
    total = total_result.scalar()

    # Sorting guard
    sort_map = {
        "created_at": db_models.Resource.created_at,
        "updated_at": db_models.Resource.updated_at,
        "quality_score": db_models.Resource.quality_score,
        "title": db_models.Resource.title,
    }
    sort_col = sort_map.get(sort.sort_by)
    if sort_col is None:
        # This should be prevented by Pydantic Literal, but double-guard anyway
        sort_col = db_models.Resource.created_at

    order = asc(sort_col) if sort.sort_dir == "asc" else desc(sort_col)
    query = query.order_by(order)

    query = query.offset(page.offset).limit(page.limit)
    result = db.execute(query)
    items = result.scalars().all()
    return items, total


def _apply_resource_updates(
    resource: db_models.Resource, updates: Dict[str, Any], authority
) -> Tuple[bool, bool, bool]:
    """
    Apply updates to resource fields (modifier helper).

    Args:
        resource: Resource to update
        updates: Dictionary of field updates
        authority: Authority control service

    Returns:
        Tuple of (embedding_fields_changed, quality_fields_changed, content_changed)
    """
    embedding_fields_changed = False
    embedding_affecting_fields = {"title", "description", "subject"}

    quality_fields_changed = False
    quality_affecting_fields = {
        "title",
        "description",
        "subject",
        "content",
        "creator",
        "publisher",
        "date_created",
        "publication_year",
        "doi",
        "pmid",
        "arxiv_id",
        "journal",
        "affiliations",
        "funding_sources",
    }

    content_changed = False
    content_fields = {
        "content",
        "identifier",
    }  # identifier is the archive path with content

    # Track if quality_score was explicitly set (manual override)
    quality_score_manually_set = "quality_score" in updates

    for key, value in updates.items():
        if key == "subject" and isinstance(value, list):
            setattr(resource, key, authority.normalize_subjects(value))
            embedding_fields_changed = True
            # Only trigger recomputation if quality_score wasn't manually set
            if not quality_score_manually_set:
                quality_fields_changed = True
        elif key == "creator":
            setattr(resource, key, authority.normalize_creator(value))
            # Only trigger recomputation if quality_score wasn't manually set
            if not quality_score_manually_set:
                quality_fields_changed = True
        elif key == "publisher":
            setattr(resource, key, authority.normalize_publisher(value))
            # Only trigger recomputation if quality_score wasn't manually set
            if not quality_score_manually_set:
                quality_fields_changed = True
        elif key == "quality_score":
            # Handle QualityScore domain object or float
            if hasattr(value, "overall_score"):
                # It's a QualityScore domain object
                setattr(resource, key, value.overall_score())
            elif hasattr(value, "to_dict"):
                # It has a to_dict method, extract overall_score
                setattr(resource, key, value.to_dict().get("overall_score", 0.0))
            else:
                # It's already a float or numeric value
                setattr(resource, key, float(value))
            # Don't trigger recomputation when quality_score is manually set
        else:
            setattr(resource, key, value)
            if key in embedding_affecting_fields:
                embedding_fields_changed = True
            if key in quality_affecting_fields and not quality_score_manually_set:
                quality_fields_changed = True
            if key in content_fields:
                content_changed = True

    return embedding_fields_changed, quality_fields_changed, content_changed


def _regenerate_embeddings(db: Session, resource: db_models.Resource) -> None:
    """
    Regenerate dense and sparse embeddings for resource (modifier).

    Args:
        db: Database session
        resource: Resource to regenerate embeddings for
    """
    # Regenerate dense embedding
    try:
        from ...shared.embeddings import create_composite_text, EmbeddingGenerator

        composite_text = create_composite_text(resource)
        if composite_text.strip():
            embedding_gen = EmbeddingGenerator()
            embedding = embedding_gen.generate_embedding(composite_text)
            if embedding:
                resource.embedding = embedding
                logger.info(f"Regenerated dense embedding for resource {resource.id}")
    except Exception as e:
        logger.warning(f"Dense embedding regeneration failed for {resource.id}: {e}")

    # Regenerate sparse embedding
    try:
        from ..search.sparse_embeddings import SparseEmbeddingService

        sparse_service = SparseEmbeddingService(db, model_name="BAAI/bge-m3")

        text_parts = []
        if resource.title:
            text_parts.append(resource.title)
        if resource.description:
            text_parts.append(resource.description)
        if resource.subject:
            subjects_text = " ".join(resource.subject)
            if subjects_text.strip():
                text_parts.append(f"Keywords: {subjects_text}")

        composite_text = " ".join(text_parts)

        if not composite_text.strip():
            resource.sparse_embedding = None
            resource.sparse_embedding_model = None
            resource.sparse_embedding_updated_at = datetime.now(timezone.utc)
        else:
            sparse_vec = sparse_service.generate_sparse_embedding(composite_text)
            if sparse_vec:
                resource.sparse_embedding = json.dumps(sparse_vec)
                resource.sparse_embedding_model = "BAAI/bge-m3"
                resource.sparse_embedding_updated_at = datetime.now(timezone.utc)
                logger.info(f"Regenerated sparse embedding for resource {resource.id}")
            else:
                resource.sparse_embedding = None
                resource.sparse_embedding_model = None
                resource.sparse_embedding_updated_at = None
    except Exception as e:
        logger.warning(f"Sparse embedding regeneration failed for {resource.id}: {e}")
        resource.sparse_embedding = None
        resource.sparse_embedding_model = None
        resource.sparse_embedding_updated_at = None


def _recompute_quality(db: Session, resource_id) -> None:
    """
    Recompute quality score for resource (modifier).

    Args:
        db: Database session
        resource_id: Resource ID
    """
    try:
        from ...services.quality_service import QualityService

        quality_service = QualityService(db=db)
        quality_result = quality_service.compute_quality(resource_id)

        # quality_result is a QualityScore domain object
        logger.info(
            f"Recomputed quality for resource {resource_id}: "
            f"overall={quality_result.overall_score():.2f}"
        )
    except Exception as e:
        logger.warning(f"Quality recomputation failed for resource {resource_id}: {e}")


def update_resource(
    db: Session, resource_id, payload: ResourceUpdate
) -> db_models.Resource:
    """
    Update a resource with new data.

    Args:
        db: Database session
        resource_id: Resource ID
        payload: Update data

    Returns:
        Updated resource

    Raises:
        ValueError: If resource not found
    """
    try:
        Base.metadata.create_all(bind=db.get_bind())
    except Exception:
        pass

    # Query: Get resource
    resource = get_resource(db, resource_id)
    if not resource:
        raise ValueError("Resource not found")

    updates = payload.model_dump(exclude_unset=True)

    # Protect immutable/system-managed fields
    for key in ["id", "created_at", "updated_at"]:
        updates.pop(key, None)

    logger.info(f"Updating resource {resource_id} with {len(updates)} field(s)")

    # Track which fields changed
    changed_fields = list(updates.keys())

    # Modifier: Apply updates
    from ...modules.authority.service import AuthorityControl

    authority = AuthorityControl(db)
    embedding_changed, quality_changed, content_changed = _apply_resource_updates(
        resource, updates, authority
    )

    # Modifier: Regenerate embeddings if needed
    if embedding_changed:
        _regenerate_embeddings(db, resource)

    # Modifier: Update timestamp
    resource.updated_at = datetime.now(timezone.utc)

    # Modifier: Persist changes
    db.add(resource)
    db.commit()
    db.refresh(resource)

    logger.info(f"Successfully updated resource {resource_id}")

    # Emit resource.updated event
    event_bus.emit(
        SystemEvent.RESOURCE_UPDATED.value,
        {"resource_id": str(resource.id), "changed_fields": changed_fields},
        priority=EventPriority.HIGH,
    )

    # Emit specific change events
    if content_changed:
        event_bus.emit(
            SystemEvent.RESOURCE_CONTENT_CHANGED.value,
            {"resource_id": str(resource.id), "changed_fields": changed_fields},
            priority=EventPriority.HIGH,
        )

    # Metadata changed if quality fields changed but not content
    metadata_fields = {
        "title",
        "description",
        "subject",
        "creator",
        "publisher",
        "date_created",
        "publication_year",
        "doi",
        "pmid",
        "arxiv_id",
        "journal",
        "affiliations",
        "funding_sources",
        "language",
        "type",
    }
    metadata_changed = any(field in metadata_fields for field in changed_fields)

    if metadata_changed and not content_changed:
        event_bus.emit(
            SystemEvent.RESOURCE_METADATA_CHANGED.value,
            {"resource_id": str(resource.id), "changed_fields": changed_fields},
            priority=EventPriority.NORMAL,
        )

    # Modifier: Recompute quality if needed (after commit)
    if quality_changed:
        _recompute_quality(db, resource_id)

    return resource


def _delete_resource_annotations(db: Session, resource_id) -> None:
    """
    Delete annotations associated with a resource (modifier).

    Args:
        db: Database session
        resource_id: Resource ID
    """
    try:
        from ...database.models import Annotation

        # Convert resource_id to UUID if needed
        if isinstance(resource_id, str):
            try:
                import uuid as uuid_module

                resource_uuid = uuid_module.UUID(resource_id)
            except (ValueError, TypeError):
                resource_uuid = resource_id
        else:
            resource_uuid = resource_id

        # Delete annotations associated with this resource
        annotation_count = (
            db.query(Annotation)
            .filter(Annotation.resource_id == resource_uuid)
            .delete()
        )
        if annotation_count > 0:
            logger.info(
                f"Deleted {annotation_count} annotations for resource {resource_id}"
            )
    except Exception as e:
        # Log but don't fail if annotation deletion fails
        # The CASCADE constraint will handle it at the database level
        logger.warning(
            f"Could not explicitly delete annotations for resource {resource_id}: {e}"
        )


def delete_resource(db: Session, resource_id) -> None:
    """
    Delete a resource and its associated data (modifier, returns None).

    Args:
        db: Database session
        resource_id: Resource ID

    Raises:
        ValueError: If resource not found
    """
    try:
        Base.metadata.create_all(bind=db.get_bind())
    except Exception:
        pass

    # Query: Get resource
    resource = get_resource(db, resource_id)
    if not resource:
        raise ValueError("Resource not found")

    logger.info(f"Deleting resource {resource_id}")

    # Store resource info for event
    resource_info = {"resource_id": str(resource.id), "title": resource.title}

    # Modifier: Delete associated annotations
    _delete_resource_annotations(db, resource_id)

    # Modifier: Delete resource
    db.delete(resource)
    db.commit()

    logger.info(f"Successfully deleted resource {resource_id}")

    # Emit resource.deleted event
    event_bus.emit(
        SystemEvent.RESOURCE_DELETED.value, resource_info, priority=EventPriority.HIGH
    )


# ============================================================================
# CHUNKING SERVICE (Advanced RAG)
# ============================================================================


class ChunkingService:
    """
    Service for document chunking with multiple strategies.

    Supports semantic chunking (sentence boundaries) and fixed-size chunking
    with configurable chunk size and overlap. Architecture designed to support
    future AST-based chunking strategies (e.g., Tree-Sitter) without breaking
    the API.

    Args:
        db: Database session for storing chunks
        strategy: Chunking strategy ("semantic" or "fixed")
        chunk_size: Target chunk size (tokens for semantic, characters for fixed)
        overlap: Overlap size between chunks (tokens or characters)
        parser_type: Parser type for future extensibility
            - "text" (default): Standard text chunking
            - "code_python", "code_javascript", "code_java", etc.: Future AST chunking
        embedding_service: Optional embedding service for generating chunk embeddings

    Example:
        >>> service = ChunkingService(
        ...     db=session,
        ...     strategy="semantic",
        ...     chunk_size=500,
        ...     overlap=50,
        ...     parser_type="text"
        ... )
        >>> chunks = service.semantic_chunk(resource_id, content)
    """

    def __init__(
        self,
        db: Session,
        strategy: str = "semantic",
        chunk_size: int = 500,
        overlap: int = 50,
        parser_type: str = "text",
        embedding_service: Optional[Any] = None,
    ):
        """
        Initialize ChunkingService with configuration parameters.

        Args:
            db: Database session
            strategy: Chunking strategy ("semantic" or "fixed")
            chunk_size: Target chunk size (tokens for semantic, characters for fixed)
            overlap: Overlap size between chunks
            parser_type: Parser type ("text", "code_python", "code_javascript", etc.)
            embedding_service: Optional embedding service instance
        """
        self.db = db
        self.strategy = strategy
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.parser_type = parser_type
        self.embedding_service = embedding_service

        logger.info(
            f"Initialized ChunkingService: strategy={strategy}, "
            f"chunk_size={chunk_size}, overlap={overlap}, parser_type={parser_type}"
        )

    def semantic_chunk(
        self,
        resource_id: str,
        content: str,
        chunk_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Chunk content using semantic boundaries (sentence splitting).

        Splits text on sentence boundaries using spaCy or NLTK, targeting
        the configured chunk_size with overlap between chunks.

        Args:
            resource_id: Resource ID for the chunks
            content: Text content to chunk
            chunk_metadata: Optional metadata to attach to chunks (e.g., page numbers)

        Returns:
            List of chunk dictionaries with keys:
                - content: Chunk text
                - chunk_index: Sequential index
                - chunk_metadata: Metadata dict

        Example:
            >>> chunks = service.semantic_chunk(
            ...     resource_id="123",
            ...     content="First sentence. Second sentence. Third sentence.",
            ...     chunk_metadata={"page": 1}
            ... )
        """
        if not content or not content.strip():
            logger.warning(f"Empty content provided for resource {resource_id}")
            return []

        logger.info(
            f"Semantic chunking content for resource {resource_id}, length={len(content)}"
        )

        # Split into sentences using simple regex (NLTK can hang during download)
        import re

        # Split on sentence endings followed by whitespace
        # This handles most common cases: . ! ?
        sentences = re.split(r"(?<=[.!?])\s+", content)

        # Filter out empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            logger.warning(f"No sentences found in content for resource {resource_id}")
            return []

        logger.info(f"Split content into {len(sentences)} sentences")

        # Build chunks by combining sentences up to chunk_size
        chunks = []
        current_chunk = []
        current_length = 0
        chunk_index = 0
        overlap_sentences = []

        for sentence in sentences:
            sentence_length = len(sentence.split())  # Word count approximation

            # If adding this sentence would exceed chunk_size, finalize current chunk
            if (
                current_length > 0
                and current_length + sentence_length > self.chunk_size
            ):
                # Finalize current chunk
                chunk_text = " ".join(current_chunk)
                chunk_dict = {
                    "content": chunk_text,
                    "chunk_index": chunk_index,
                    "chunk_metadata": chunk_metadata or {},
                }
                chunks.append(chunk_dict)
                chunk_index += 1

                # Calculate overlap: keep last N sentences for next chunk
                overlap_length = 0
                overlap_sentences = []
                for sent in reversed(current_chunk):
                    sent_len = len(sent.split())
                    if overlap_length + sent_len <= self.overlap:
                        overlap_sentences.insert(0, sent)
                        overlap_length += sent_len
                    else:
                        break

                # Start new chunk with overlap
                current_chunk = overlap_sentences.copy()
                current_length = overlap_length

            # Add sentence to current chunk
            current_chunk.append(sentence)
            current_length += sentence_length

        # Add final chunk if any content remains
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunk_dict = {
                "content": chunk_text,
                "chunk_index": chunk_index,
                "chunk_metadata": chunk_metadata or {},
            }
            chunks.append(chunk_dict)

        logger.info(f"Created {len(chunks)} semantic chunks for resource {resource_id}")
        return chunks

    def fixed_chunk(
        self,
        resource_id: str,
        content: str,
        chunk_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Chunk content using fixed character-based splitting.

        Splits text at fixed character count with overlap, avoiding mid-word breaks
        by splitting on whitespace boundaries.

        Args:
            resource_id: Resource ID for the chunks
            content: Text content to chunk
            chunk_metadata: Optional metadata to attach to chunks (e.g., page numbers)

        Returns:
            List of chunk dictionaries with keys:
                - content: Chunk text
                - chunk_index: Sequential index
                - chunk_metadata: Metadata dict

        Example:
            >>> chunks = service.fixed_chunk(
            ...     resource_id="123",
            ...     content="Long text content...",
            ...     chunk_metadata={"page": 1}
            ... )
        """
        if not content or not content.strip():
            logger.warning(f"Empty content provided for resource {resource_id}")
            return []

        logger.info(
            f"Fixed-size chunking content for resource {resource_id}, length={len(content)}"
        )

        chunks = []
        chunk_index = 0
        start_pos = 0
        content_length = len(content)

        while start_pos < content_length:
            # Calculate end position for this chunk
            end_pos = min(start_pos + self.chunk_size, content_length)

            # If not at the end, try to break on whitespace to avoid mid-word splits
            if end_pos < content_length:
                # Look for the last whitespace before end_pos
                chunk_text = content[start_pos:end_pos]
                last_space = chunk_text.rfind(" ")
                last_newline = chunk_text.rfind("\n")
                last_break = max(last_space, last_newline)

                if last_break > 0:
                    # Adjust end_pos to the last whitespace (but don't include the whitespace itself)
                    end_pos = start_pos + last_break

            # Extract chunk (don't strip to preserve content)
            chunk_text = content[start_pos:end_pos]

            # Only strip for storage if it's not empty after stripping
            chunk_text_stripped = chunk_text.strip()

            if chunk_text_stripped:  # Only add non-empty chunks
                chunk_dict = {
                    "content": chunk_text_stripped,  # Store stripped version
                    "chunk_index": chunk_index,
                    "chunk_metadata": chunk_metadata or {},
                }
                chunks.append(chunk_dict)
                chunk_index += 1

            # Move start position forward, accounting for overlap
            # For fixed-size chunking, overlap is in characters
            if end_pos < content_length:
                # Calculate new start based on actual end position (not stripped)
                new_start = end_pos - self.overlap
                # Ensure we always make forward progress (critical to avoid infinite loop)
                if new_start <= start_pos:
                    new_start = start_pos + 1
                start_pos = new_start
            else:
                # We've reached the end
                break

        logger.info(
            f"Created {len(chunks)} fixed-size chunks for resource {resource_id}"
        )
        return chunks

    def store_chunks(
        self, resource_id: str, chunks: List[Dict[str, Any]], commit: bool = True
    ) -> List[db_models.DocumentChunk]:
        """
        Store chunks to database and generate embeddings.

        Saves chunks and their embeddings in a single transaction. If embedding
        generation fails, the error is logged and the chunk is stored without an embedding.

        Args:
            resource_id: Resource ID for the chunks
            chunks: List of chunk dictionaries from semantic_chunk() or fixed_chunk()
            commit: Whether to commit the transaction (default: True). Set to False
                   when calling from within a larger transaction.

        Returns:
            List of created DocumentChunk model instances

        Raises:
            Exception: If storage or embedding generation fails

        Example:
            >>> chunks = service.semantic_chunk(resource_id, content)
            >>> stored_chunks = service.store_chunks(resource_id, chunks)
        """
        if not chunks:
            logger.warning(f"No chunks to store for resource {resource_id}")
            return []

        logger.info(f"Storing {len(chunks)} chunks for resource {resource_id}")

        try:
            # Convert resource_id to UUID
            import uuid as uuid_module

            try:
                resource_uuid = uuid_module.UUID(resource_id)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid resource_id format: {resource_id}")

            # Verify resource exists
            resource = (
                self.db.query(db_models.Resource)
                .filter(db_models.Resource.id == resource_uuid)
                .first()
            )
            if not resource:
                raise ValueError(f"Resource not found: {resource_id}")

            # Get or create embedding service
            if self.embedding_service is None:
                from ...shared.embeddings import EmbeddingGenerator

                embedding_gen = EmbeddingGenerator()
            else:
                embedding_gen = self.embedding_service

            stored_chunks = []

            # STEP 1: Generate all embeddings first (fail fast if embedding service fails)
            chunk_data_with_embeddings = []
            for chunk_dict in chunks:
                content = chunk_dict["content"]
                chunk_index = chunk_dict["chunk_index"]
                chunk_metadata = chunk_dict.get("chunk_metadata", {}).copy()

                # Generate embedding for chunk (optimized but still required for RAG)
                if self.embedding_service is not None:
                    try:
                        embedding = embedding_gen.generate_embedding(content)
                        if embedding:
                            chunk_metadata["embedding_generated"] = True
                            # Store embedding vector in metadata for now
                            # TODO: Add dedicated embedding column to DocumentChunk model
                            chunk_metadata["embedding_vector"] = (
                                embedding.tolist()
                                if hasattr(embedding, "tolist")
                                else list(embedding)
                            )
                        else:
                            chunk_metadata["embedding_generated"] = False
                    except Exception as e:
                        # Re-raise embedding errors to ensure transaction integrity
                        logger.error(
                            f"Embedding generation failed for chunk {chunk_index}: {e}"
                        )
                        raise
                else:
                    chunk_metadata["embedding_generated"] = False

                chunk_data_with_embeddings.append(
                    {
                        "content": content,
                        "chunk_index": chunk_index,
                        "chunk_metadata": chunk_metadata,
                    }
                )

            # STEP 2: Create all chunk records (only after all embeddings succeed)
            for chunk_data in chunk_data_with_embeddings:
                chunk_record = db_models.DocumentChunk(
                    resource_id=resource_uuid,
                    content=chunk_data["content"],
                    chunk_index=chunk_data["chunk_index"],
                    embedding_id=None,  # Not using separate embedding table yet
                    chunk_metadata=chunk_data["chunk_metadata"],
                    created_at=datetime.now(timezone.utc),
                )
                stored_chunks.append(chunk_record)

            # STEP 3: Bulk insert all chunks at once
            if stored_chunks:
                self.db.bulk_save_objects(stored_chunks)
                # Commit transaction (if requested)
                if commit:
                    self.db.commit()
                else:
                    # Flush to make objects available in current transaction
                    self.db.flush()

            # Verify chunks were actually stored
            chunk_count = (
                self.db.query(db_models.DocumentChunk)
                .filter(db_models.DocumentChunk.resource_id == resource_uuid)
                .count()
            )

            logger.info(
                f"Successfully stored {len(stored_chunks)} chunks for resource {resource_id} "
                f"(verified {chunk_count} chunks in database)"
            )

            if chunk_count != len(stored_chunks):
                logger.warning(
                    f"Chunk count mismatch: stored {len(stored_chunks)} but found {chunk_count} in database"
                )

            return stored_chunks

        except Exception as e:
            # Rollback on any error (only if we were managing the transaction)
            logger.error(
                f"Failed to store chunks for resource {resource_id}: {e}", exc_info=True
            )
            if commit:
                self.db.rollback()
            raise

    def chunk_resource(
        self,
        resource_id: str,
        content: str,
        chunk_metadata: Optional[Dict[str, Any]] = None,
        file_path: Optional[str] = None,
    ) -> List[db_models.DocumentChunk]:
        """
        Chunk a resource and store chunks with event emission.

        This is the main entry point for chunking a resource. It:
        1. Detects if content is code and selects appropriate strategy
        2. Chunks the content using the selected strategy
        3. Stores chunks and generates embeddings
        4. Emits success or failure events

        Args:
            resource_id: Resource ID to chunk
            content: Text content to chunk
            chunk_metadata: Optional metadata to attach to chunks
            file_path: Optional file path for code language detection

        Returns:
            List of created DocumentChunk model instances

        Raises:
            Exception: If chunking or storage fails

        Example:
            >>> service = ChunkingService(db, strategy="semantic")
            >>> chunks = service.chunk_resource(
            ...     resource_id="123",
            ...     content="Document content...",
            ...     chunk_metadata={"page": 1}
            ... )
        """
        try:
            logger.info(
                f"Starting chunking for resource {resource_id} with strategy={self.strategy}"
            )

            # Check if this is a code file and use AST-based chunking
            if file_path:
                from .logic.chunking import (
                    detect_language_from_extension,
                    CodeChunkingStrategy,
                )

                language = detect_language_from_extension(file_path)

                if language:
                    # Use AST-based code chunking
                    logger.info(
                        f"Detected code file ({language}), using AST-based chunking"
                    )
                    code_strategy = CodeChunkingStrategy(
                        language=language,
                        chunk_size=self.chunk_size,
                        overlap=self.overlap,
                    )

                    # Convert resource_id to UUID
                    import uuid as uuid_module

                    try:
                        resource_uuid = uuid_module.UUID(resource_id)
                    except (ValueError, TypeError):
                        raise ValueError(f"Invalid resource_id format: {resource_id}")

                    # Chunk using code strategy (returns DocumentChunk objects directly)
                    stored_chunks = code_strategy.chunk(
                        content, resource_uuid, file_path
                    )

                    # Store chunks to database
                    for chunk in stored_chunks:
                        self.db.add(chunk)
                    self.db.commit()

                    # Emit success event
                    event_bus.emit(
                        "resource.chunked",
                        {
                            "resource_id": resource_id,
                            "chunk_count": len(stored_chunks),
                            "strategy": "ast_code",
                            "language": language,
                            "chunk_size": self.chunk_size,
                            "overlap": self.overlap,
                        },
                        priority=EventPriority.NORMAL,
                    )

                    logger.info(
                        f"Successfully chunked code resource {resource_id}: {len(stored_chunks)} chunks"
                    )
                    return stored_chunks

            # Fall back to text-based chunking strategies
            if self.strategy == "semantic":
                chunk_dicts = self.semantic_chunk(resource_id, content, chunk_metadata)
            elif self.strategy == "fixed":
                chunk_dicts = self.fixed_chunk(resource_id, content, chunk_metadata)
            else:
                raise ValueError(f"Unknown chunking strategy: {self.strategy}")

            # Store chunks
            stored_chunks = self.store_chunks(resource_id, chunk_dicts)

            # Emit success event
            event_bus.emit(
                "resource.chunked",
                {
                    "resource_id": resource_id,
                    "chunk_count": len(stored_chunks),
                    "strategy": self.strategy,
                    "chunk_size": self.chunk_size,
                    "overlap": self.overlap,
                },
                priority=EventPriority.NORMAL,
            )

            logger.info(
                f"Successfully chunked resource {resource_id}: {len(stored_chunks)} chunks"
            )
            return stored_chunks

        except Exception as e:
            # Emit failure event
            event_bus.emit(
                "resource.chunking_failed",
                {
                    "resource_id": resource_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "strategy": self.strategy,
                },
                priority=EventPriority.HIGH,
            )

            logger.error(
                f"Chunking failed for resource {resource_id}: {e}", exc_info=True
            )
            raise


# ============================================================================
# Auto-Linking Service
# ============================================================================


class AutoLinkingService:
    """
    Service for automatically linking PDF chunks to code chunks based on semantic similarity.

    Uses existing embedding infrastructure to compute cosine similarity between chunks
    and creates bidirectional links when similarity exceeds threshold (default 0.7).

    Attributes:
        db: Database session
        embedding_generator: EmbeddingGenerator instance from shared.embeddings
        similarity_threshold: Minimum similarity score for creating links (default 0.7)
    """

    def __init__(
        self,
        db: Session,
        embedding_generator: Optional[Any] = None,
        similarity_threshold: float = 0.7,
    ):
        """
        Initialize auto-linking service.

        Args:
            db: Database session
            embedding_generator: Optional EmbeddingGenerator instance
            similarity_threshold: Minimum similarity for creating links (0.0-1.0)
        """
        self.db = db
        self.similarity_threshold = similarity_threshold

        # Use existing EmbeddingGenerator from shared kernel
        if embedding_generator is None:
            from ...shared.embeddings import EmbeddingGenerator

            self.embedding_generator = EmbeddingGenerator()
        else:
            self.embedding_generator = embedding_generator

    def _compute_cosine_similarity(
        self, embedding1: List[float], embedding2: List[float]
    ) -> float:
        """
        Compute cosine similarity between two embedding vectors.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0.0-1.0)
        """
        import numpy as np

        # Convert to numpy arrays
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)

        # Compute cosine similarity
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = dot_product / (norm1 * norm2)
        return float(similarity)

    def _get_chunk_embedding(
        self, chunk: db_models.DocumentChunk
    ) -> Optional[List[float]]:
        """
        Get embedding for a chunk from metadata or generate if missing.

        Args:
            chunk: DocumentChunk instance

        Returns:
            Embedding vector as list of floats, or None if unavailable
        """
        # Check if embedding exists in chunk metadata
        if chunk.chunk_metadata and "embedding_vector" in chunk.chunk_metadata:
            return chunk.chunk_metadata["embedding_vector"]

        # Generate embedding if missing
        try:
            embedding = self.embedding_generator.generate_embedding(chunk.content)
            if embedding:
                # Store in metadata for future use
                if chunk.chunk_metadata is None:
                    chunk.chunk_metadata = {}
                chunk.chunk_metadata["embedding_vector"] = embedding
                chunk.chunk_metadata["embedding_generated"] = True
                self.db.add(chunk)
                self.db.commit()
                return embedding
        except Exception as e:
            logger.warning(f"Failed to generate embedding for chunk {chunk.id}: {e}")

        return None

    def _create_link(
        self,
        source_chunk_id: uuid.UUID,
        target_chunk_id: uuid.UUID,
        similarity_score: float,
        link_type: str,
    ) -> db_models.ChunkLink:
        """
        Create a chunk link in the database.

        Args:
            source_chunk_id: Source chunk ID
            target_chunk_id: Target chunk ID
            similarity_score: Similarity score
            link_type: Link type ("pdf_to_code", "code_to_pdf", "bidirectional")

        Returns:
            Created ChunkLink instance
        """
        link = db_models.ChunkLink(
            source_chunk_id=source_chunk_id,
            target_chunk_id=target_chunk_id,
            similarity_score=similarity_score,
            link_type=link_type,
        )
        self.db.add(link)
        return link

    async def link_pdf_to_code(
        self, pdf_resource_id: str, similarity_threshold: Optional[float] = None
    ) -> List[db_models.ChunkLink]:
        """
        Link PDF chunks to code chunks based on semantic similarity.

        Computes cosine similarity between all PDF chunks and existing code chunks,
        creating bidirectional links when similarity exceeds threshold.

        Args:
            pdf_resource_id: PDF resource ID
            similarity_threshold: Optional override for similarity threshold

        Returns:
            List of created ChunkLink instances
        """
        threshold = similarity_threshold or self.similarity_threshold
        created_links = []

        try:
            # Convert resource_id to UUID
            import uuid as uuid_module

            try:
                resource_uuid = uuid_module.UUID(pdf_resource_id)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid resource_id format: {pdf_resource_id}")

            # Get PDF resource
            pdf_resource = (
                self.db.query(db_models.Resource)
                .filter(db_models.Resource.id == resource_uuid)
                .first()
            )

            if not pdf_resource:
                logger.warning(f"PDF resource not found: {pdf_resource_id}")
                return []

            # Get all chunks for PDF resource
            pdf_chunks = (
                self.db.query(db_models.DocumentChunk)
                .filter(db_models.DocumentChunk.resource_id == resource_uuid)
                .all()
            )

            if not pdf_chunks:
                logger.info(f"No chunks found for PDF resource: {pdf_resource_id}")
                return []

            # Get all code chunks (chunks from resources with code-related formats)
            # For now, we'll get all chunks from other resources
            # In production, this would filter by resource type/format
            code_chunks = (
                self.db.query(db_models.DocumentChunk)
                .filter(db_models.DocumentChunk.resource_id != resource_uuid)
                .all()
            )

            if not code_chunks:
                logger.info("No code chunks found for linking")
                return []

            logger.info(
                f"Linking {len(pdf_chunks)} PDF chunks to {len(code_chunks)} code chunks"
            )

            # Compute similarities and create links
            for pdf_chunk in pdf_chunks:
                pdf_embedding = self._get_chunk_embedding(pdf_chunk)
                if not pdf_embedding:
                    continue

                for code_chunk in code_chunks:
                    code_embedding = self._get_chunk_embedding(code_chunk)
                    if not code_embedding:
                        continue

                    # Compute similarity
                    similarity = self._compute_cosine_similarity(
                        pdf_embedding, code_embedding
                    )

                    # Create link if above threshold
                    if similarity >= threshold:
                        # Create bidirectional links
                        link1 = self._create_link(
                            pdf_chunk.id, code_chunk.id, similarity, "pdf_to_code"
                        )
                        link2 = self._create_link(
                            code_chunk.id, pdf_chunk.id, similarity, "code_to_pdf"
                        )
                        created_links.extend([link1, link2])

            # Commit all links
            self.db.commit()

            logger.info(
                f"Created {len(created_links)} links for PDF resource {pdf_resource_id}"
            )

            # Emit chunk.linked event
            event_bus.emit(
                "chunk.linked",
                {
                    "resource_id": pdf_resource_id,
                    "link_count": len(created_links),
                    "threshold": threshold,
                },
                priority=EventPriority.NORMAL,
            )

            return created_links

        except Exception as e:
            logger.error(
                f"Auto-linking failed for PDF {pdf_resource_id}: {e}", exc_info=True
            )
            self.db.rollback()
            raise

    async def link_code_to_pdfs(
        self, code_resource_id: str, similarity_threshold: Optional[float] = None
    ) -> List[db_models.ChunkLink]:
        """
        Link code chunks to PDF chunks based on semantic similarity.

        Computes cosine similarity between all code chunks and existing PDF chunks,
        creating bidirectional links when similarity exceeds threshold.

        Args:
            code_resource_id: Code resource ID
            similarity_threshold: Optional override for similarity threshold

        Returns:
            List of created ChunkLink instances
        """
        threshold = similarity_threshold or self.similarity_threshold
        created_links = []

        try:
            # Convert resource_id to UUID
            import uuid as uuid_module

            try:
                resource_uuid = uuid_module.UUID(code_resource_id)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid resource_id format: {code_resource_id}")

            # Get code resource
            code_resource = (
                self.db.query(db_models.Resource)
                .filter(db_models.Resource.id == resource_uuid)
                .first()
            )

            if not code_resource:
                logger.warning(f"Code resource not found: {code_resource_id}")
                return []

            # Get all chunks for code resource
            code_chunks = (
                self.db.query(db_models.DocumentChunk)
                .filter(db_models.DocumentChunk.resource_id == resource_uuid)
                .all()
            )

            if not code_chunks:
                logger.info(f"No chunks found for code resource: {code_resource_id}")
                return []

            # Get all PDF chunks (chunks from resources with PDF format)
            # For now, we'll get all chunks from other resources
            # In production, this would filter by resource type/format
            pdf_chunks = (
                self.db.query(db_models.DocumentChunk)
                .filter(db_models.DocumentChunk.resource_id != resource_uuid)
                .all()
            )

            if not pdf_chunks:
                logger.info("No PDF chunks found for linking")
                return []

            logger.info(
                f"Linking {len(code_chunks)} code chunks to {len(pdf_chunks)} PDF chunks"
            )

            # Compute similarities and create links
            for code_chunk in code_chunks:
                code_embedding = self._get_chunk_embedding(code_chunk)
                if not code_embedding:
                    continue

                for pdf_chunk in pdf_chunks:
                    pdf_embedding = self._get_chunk_embedding(pdf_chunk)
                    if not pdf_embedding:
                        continue

                    # Compute similarity
                    similarity = self._compute_cosine_similarity(
                        code_embedding, pdf_embedding
                    )

                    # Create link if above threshold
                    if similarity >= threshold:
                        # Create bidirectional links
                        link1 = self._create_link(
                            code_chunk.id, pdf_chunk.id, similarity, "code_to_pdf"
                        )
                        link2 = self._create_link(
                            pdf_chunk.id, code_chunk.id, similarity, "pdf_to_code"
                        )
                        created_links.extend([link1, link2])

            # Commit all links
            self.db.commit()

            logger.info(
                f"Created {len(created_links)} links for code resource {code_resource_id}"
            )

            # Emit chunk.linked event
            event_bus.emit(
                "chunk.linked",
                {
                    "resource_id": code_resource_id,
                    "link_count": len(created_links),
                    "threshold": threshold,
                },
                priority=EventPriority.NORMAL,
            )

            return created_links

        except Exception as e:
            logger.error(
                f"Auto-linking failed for code {code_resource_id}: {e}", exc_info=True
            )
            self.db.rollback()
            raise
