"""
PDF Ingestion Module - FastAPI Router

API endpoints for PDF upload, annotation, and GraphRAG search.
"""

import logging
from typing import List
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.database import get_db
from ...shared.embeddings import EmbeddingService
from .service import PDFIngestionService, PDFExtractionError
from .schema import (
    PDFUploadRequest,
    PDFUploadResponse,
    PDFAnnotationRequest,
    PDFAnnotationResponse,
    GraphTraversalRequest,
    GraphTraversalResponse,
    PDFChunkResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resources/pdf", tags=["PDF Ingestion"])


def get_pdf_service(db: AsyncSession = Depends(get_db)) -> PDFIngestionService:
    """Dependency injection for PDF ingestion service."""
    embedding_service = EmbeddingService()
    return PDFIngestionService(db=db, embedding_service=embedding_service)


@router.post("/ingest", response_model=PDFUploadResponse, status_code=status.HTTP_201_CREATED)
async def ingest_pdf(
    file: UploadFile = File(..., description="PDF file to upload"),
    title: str = Form(..., description="Document title"),
    description: str = Form(None, description="Optional description"),
    authors: str = Form(None, description="Comma-separated authors"),
    publication_year: int = Form(None, description="Year of publication"),
    doi: str = Form(None, description="Digital Object Identifier"),
    tags: str = Form(None, description="Comma-separated tags"),
    service: PDFIngestionService = Depends(get_pdf_service),
):
    """
    Upload and ingest a PDF file.

    Extracts text, equations, tables, and creates searchable chunks.
    Generates embeddings for semantic search.

    **Process:**
    1. Validate PDF file
    2. Extract text with academic fidelity
    3. Detect equations, tables, figures
    4. Create chunks with page/coordinate metadata
    5. Generate embeddings for each chunk
    6. Store in database and emit events

    **Returns:**
    - resource_id: UUID of created resource
    - chunks: List of extracted chunks with metadata
    - status: Ingestion status
    """
    # Validate file type
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported",
        )

    # Parse tags
    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    try:
        # Ingest PDF
        result = await service.ingest_pdf(
            file=file.file,
            title=title,
            description=description,
            authors=authors,
            publication_year=publication_year,
            doi=doi,
            tags=tag_list,
        )

        # Convert chunks to response schema
        chunk_responses = [
            PDFChunkResponse(
                chunk_id=chunk["chunk_id"],
                chunk_index=chunk["chunk_index"],
                content=chunk["content"],
                page_number=chunk.get("page_number"),
                coordinates=chunk.get("coordinates"),
                chunk_type=chunk.get("chunk_type", "text"),
            )
            for chunk in result["chunks"]
        ]

        return PDFUploadResponse(
            resource_id=result["resource_id"],
            title=result["title"],
            status=result["status"],
            total_pages=result.get("total_pages"),
            total_chunks=result["total_chunks"],
            chunks=chunk_responses,
            message=f"PDF ingested successfully: {result['total_chunks']} chunks created",
        )

    except PDFExtractionError as e:
        logger.error(f"PDF extraction failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to extract PDF content: {str(e)}",
        )
    except Exception as e:
        logger.error(f"PDF ingestion failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error during PDF ingestion: {str(e)}",
        )


@router.post("/annotate", response_model=PDFAnnotationResponse, status_code=status.HTTP_201_CREATED)
async def annotate_pdf_chunk(
    request: PDFAnnotationRequest,
    service: PDFIngestionService = Depends(get_pdf_service),
):
    """
    Annotate a PDF chunk with conceptual tags.

    Creates annotation and links to knowledge graph, connecting PDF concepts
    to related code chunks.

    **Process:**
    1. Create annotation record
    2. Extract concept entities from tags
    3. Find related code chunks via semantic search
    4. Create graph relationships (PDF ↔ Code)
    5. Return annotation with graph link count

    **Example:**
    ```json
    {
      "chunk_id": "uuid",
      "concept_tags": ["OAuth", "Security", "Authentication"],
      "note": "Always whitelist redirect URIs",
      "color": "#FFFF00"
    }
    ```

    **Returns:**
    - annotation_id: UUID of created annotation
    - graph_links_created: Number of graph edges created
    - linked_code_chunks: IDs of linked code chunks
    """
    try:
        result = await service.annotate_chunk(
            chunk_id=request.chunk_id,
            concept_tags=request.concept_tags,
            note=request.note,
            color=request.color,
            user_id="system",  # TODO: Get from auth context
        )

        return PDFAnnotationResponse(
            annotation_id=result["annotation_id"],
            chunk_id=result["chunk_id"],
            concept_tags=result["concept_tags"],
            note=result["note"],
            color=result["color"],
            created_at=result["created_at"],
            graph_links_created=result["graph_links_created"],
            linked_code_chunks=result["linked_code_chunks"],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Annotation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create annotation: {str(e)}",
        )


@router.post("/search/graph", response_model=GraphTraversalResponse)
async def graph_traversal_search(
    request: GraphTraversalRequest,
    service: PDFIngestionService = Depends(get_pdf_service),
):
    """
    Perform GraphRAG traversal search across PDF and code chunks.

    Searches knowledge graph to find related content across PDFs and codebase.
    Uses graph relationships to discover connections beyond keyword matching.

    **Process:**
    1. Generate query embedding
    2. Find seed entities matching query
    3. Traverse graph relationships (up to max_hops)
    4. Collect PDF and code chunks along paths
    5. Rank by relevance and graph distance
    6. Return unified results with annotations

    **Example Query:**
    ```json
    {
      "query": "auth implementation",
      "max_hops": 2,
      "include_pdf": true,
      "include_code": true,
      "limit": 10
    }
    ```

    **Returns:**
    - results: List of chunks (PDF + code) with relevance scores
    - Each result includes:
      - chunk content or semantic summary
      - concept tags from annotations
      - graph distance from query
      - file path (code) or page number (PDF)
    """
    try:
        result = await service.graph_traversal_search(
            query=request.query,
            max_hops=request.max_hops,
            include_pdf=request.include_pdf,
            include_code=request.include_code,
            limit=request.limit,
        )

        return GraphTraversalResponse(**result)

    except Exception as e:
        logger.error(f"Graph traversal search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph search failed: {str(e)}",
        )
