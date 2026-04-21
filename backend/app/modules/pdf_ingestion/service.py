"""
PDF Ingestion Module - Service Layer

Business logic for PDF extraction, chunking, and annotation.
Integrates with GraphRAG for conceptual linking.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, BinaryIO, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

# PDF extraction libraries
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

from ...database.models import (
    Resource,
    DocumentChunk,
    Annotation,
    GraphEntity,
    GraphRelationship,
)
# Lazy import embeddings to avoid loading models in CLOUD mode
# from ...shared.embeddings import EmbeddingService

if TYPE_CHECKING:
    from ...shared.embeddings import EmbeddingService
from ...shared.event_bus import event_bus

logger = logging.getLogger(__name__)


class PDFExtractionError(Exception):
    """Raised when PDF extraction fails."""

    pass


class PDFIngestionService:
    """
    Service for PDF ingestion, extraction, and annotation.

    Handles:
    - PDF text extraction with academic fidelity
    - Chunking with page/coordinate preservation
    - Equation and table detection
    - Annotation with conceptual tagging
    - GraphRAG linking between PDF concepts and code
    """

    def __init__(self, db: AsyncSession, embedding_service: "EmbeddingService"):  # type: ignore
        self.db = db
        self.embedding_service = embedding_service

        if not HAS_PYMUPDF:
            logger.warning(
                "PyMuPDF not installed. PDF extraction will be limited. "
                "Install with: pip install PyMuPDF"
            )

    async def ingest_pdf(
        self,
        file: BinaryIO,
        title: str,
        description: Optional[str] = None,
        authors: Optional[str] = None,
        publication_year: Optional[int] = None,
        doi: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest a PDF file: extract text, create chunks, generate embeddings.

        Args:
            file: Binary file object (PDF)
            title: Document title
            description: Optional description
            authors: Comma-separated author names
            publication_year: Year of publication
            doi: Digital Object Identifier
            tags: Initial tags

        Returns:
            Dict with resource_id, chunks, and metadata

        Raises:
            PDFExtractionError: If PDF extraction fails
        """
        if not HAS_PYMUPDF:
            raise PDFExtractionError(
                "PyMuPDF not installed. Cannot extract PDF content."
            )

        logger.info(f"Starting PDF ingestion: {title}")

        # Step 1: Create Resource record
        resource = Resource(
            id=uuid.uuid4(),
            title=title,
            description=description,
            authors=authors,
            publication_year=publication_year,
            doi=doi,
            type="research_paper",
            format="application/pdf",
            subject=tags or [],
            ingestion_status="processing",
            ingestion_started_at=datetime.utcnow(),
        )
        self.db.add(resource)
        await self.db.flush()

        try:
            # Step 2: Extract PDF content
            pdf_data = await self._extract_pdf_content(file)

            # Step 3: Create chunks with embeddings
            chunks = await self._create_chunks(resource.id, pdf_data)

            # Step 4: Update resource metadata
            resource.ingestion_status = "completed"
            resource.ingestion_completed_at = datetime.utcnow()
            resource.equation_count = pdf_data.get("equation_count", 0)
            resource.table_count = pdf_data.get("table_count", 0)
            resource.figure_count = pdf_data.get("figure_count", 0)

            await self.db.commit()

            # Step 5: Emit event for downstream processing
            event_bus.emit(
                "resource.created",
                {
                    "resource_id": str(resource.id),
                    "title": resource.title,
                    "type": "pdf",
                    "chunk_count": len(chunks),
                },
            )

            logger.info(
                f"PDF ingestion completed: {title} ({len(chunks)} chunks created)"
            )

            return {
                "resource_id": resource.id,
                "title": title,
                "status": "completed",
                "total_pages": pdf_data.get("total_pages"),
                "total_chunks": len(chunks),
                "chunks": chunks,
            }

        except Exception as e:
            # Rollback and mark as failed
            resource.ingestion_status = "failed"
            resource.ingestion_error = str(e)
            resource.ingestion_completed_at = datetime.utcnow()
            await self.db.commit()

            logger.error(f"PDF ingestion failed for {title}: {e}", exc_info=True)
            raise PDFExtractionError(f"Failed to ingest PDF: {e}") from e

    async def _extract_pdf_content(self, file: BinaryIO) -> Dict[str, Any]:
        """
        Extract text, equations, tables from PDF using PyMuPDF.

        Args:
            file: Binary PDF file

        Returns:
            Dict with pages, equations, tables, metadata
        """
        # Read file bytes
        pdf_bytes = file.read()

        # Open PDF with PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        pages = []
        equation_count = 0
        table_count = 0
        figure_count = 0

        for page_num in range(len(doc)):
            page = doc[page_num]

            # Extract text blocks with coordinates
            blocks = page.get_text("dict")["blocks"]

            page_data = {
                "page_number": page_num + 1,
                "blocks": [],
            }

            for block in blocks:
                if block["type"] == 0:  # Text block
                    # Extract text from lines
                    text_lines = []
                    for line in block.get("lines", []):
                        line_text = ""
                        for span in line.get("spans", []):
                            line_text += span.get("text", "")
                        text_lines.append(line_text)

                    text = "\n".join(text_lines).strip()

                    if text:
                        # Detect equations (heuristic: contains math symbols)
                        is_equation = self._detect_equation(text)
                        if is_equation:
                            equation_count += 1

                        page_data["blocks"].append(
                            {
                                "type": "equation" if is_equation else "text",
                                "text": text,
                                "bbox": block["bbox"],  # [x0, y0, x1, y1]
                            }
                        )

                elif block["type"] == 1:  # Image block (potential figure/table)
                    figure_count += 1
                    page_data["blocks"].append(
                        {
                            "type": "figure",
                            "bbox": block["bbox"],
                        }
                    )

            # Detect tables (heuristic: look for grid-like structures)
            tables = page.find_tables()
            if tables:
                table_count += len(tables.tables)
                for table in tables.tables:
                    page_data["blocks"].append(
                        {
                            "type": "table",
                            "bbox": table.bbox,
                            "rows": table.row_count,
                            "cols": table.col_count,
                        }
                    )

            pages.append(page_data)

        doc.close()

        return {
            "total_pages": len(pages),
            "pages": pages,
            "equation_count": equation_count,
            "table_count": table_count,
            "figure_count": figure_count,
        }

    def _detect_equation(self, text: str) -> bool:
        """
        Heuristic to detect if text block is an equation.

        Args:
            text: Text content

        Returns:
            True if likely an equation
        """
        math_symbols = ["∫", "∑", "∏", "√", "∂", "∇", "≈", "≠", "≤", "≥", "α", "β", "γ", "θ", "λ", "μ", "σ", "π"]
        math_patterns = ["=", "∈", "⊂", "⊆", "∪", "∩", "×", "÷"]

        # Check for LaTeX-style equations
        if "$" in text or "\\(" in text or "\\[" in text:
            return True

        # Check for math symbols
        symbol_count = sum(1 for symbol in math_symbols if symbol in text)
        if symbol_count >= 2:
            return True

        # Check for pattern density
        pattern_count = sum(1 for pattern in math_patterns if pattern in text)
        if pattern_count >= 3 and len(text) < 200:
            return True

        return False

    async def _create_chunks(
        self, resource_id: uuid.UUID, pdf_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Create document chunks from extracted PDF data.

        Chunks are created per page with semantic boundaries.

        Args:
            resource_id: Parent resource ID
            pdf_data: Extracted PDF data

        Returns:
            List of chunk dictionaries
        """
        chunks = []
        chunk_index = 0

        for page_data in pdf_data["pages"]:
            page_num = page_data["page_number"]

            # Group blocks into semantic chunks (max 512 tokens per chunk)
            current_chunk_text = []
            current_chunk_blocks = []

            for block in page_data["blocks"]:
                block_text = block.get("text", "")

                # Estimate tokens (rough: 1 token ≈ 4 chars)
                current_tokens = sum(len(t) for t in current_chunk_text) // 4
                block_tokens = len(block_text) // 4

                if current_tokens + block_tokens > 512 and current_chunk_text:
                    # Create chunk from accumulated blocks
                    chunk = await self._create_single_chunk(
                        resource_id=resource_id,
                        chunk_index=chunk_index,
                        content="\n\n".join(current_chunk_text),
                        page_number=page_num,
                        blocks=current_chunk_blocks,
                    )
                    chunks.append(chunk)
                    chunk_index += 1

                    # Reset for next chunk
                    current_chunk_text = []
                    current_chunk_blocks = []

                # Add block to current chunk
                if block_text:
                    current_chunk_text.append(block_text)
                    current_chunk_blocks.append(block)

            # Create final chunk for page
            if current_chunk_text:
                chunk = await self._create_single_chunk(
                    resource_id=resource_id,
                    chunk_index=chunk_index,
                    content="\n\n".join(current_chunk_text),
                    page_number=page_num,
                    blocks=current_chunk_blocks,
                )
                chunks.append(chunk)
                chunk_index += 1

        return chunks

    async def _create_single_chunk(
        self,
        resource_id: uuid.UUID,
        chunk_index: int,
        content: str,
        page_number: int,
        blocks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Create a single document chunk with embedding.

        Args:
            resource_id: Parent resource ID
            chunk_index: Sequential chunk index
            content: Chunk text content
            page_number: PDF page number
            blocks: List of text blocks in chunk

        Returns:
            Chunk dictionary
        """
        # Generate embedding
        embedding_vector = await self.embedding_service.generate_embedding(content)

        # Extract coordinates from blocks
        coordinates = None
        if blocks:
            # Use first block's bbox as representative coordinates
            first_bbox = blocks[0].get("bbox")
            if first_bbox:
                coordinates = {
                    "x0": first_bbox[0],
                    "y0": first_bbox[1],
                    "x1": first_bbox[2],
                    "y1": first_bbox[3],
                }

        # Determine chunk type
        chunk_type = "text"
        if any(b.get("type") == "equation" for b in blocks):
            chunk_type = "equation"
        elif any(b.get("type") == "table" for b in blocks):
            chunk_type = "table"

        # Create chunk record
        chunk = DocumentChunk(
            id=uuid.uuid4(),
            resource_id=resource_id,
            content=content,
            chunk_index=chunk_index,
            chunk_metadata={
                "page": page_number,
                "coordinates": coordinates,
                "chunk_type": chunk_type,
                "block_count": len(blocks),
            },
            is_remote=False,  # PDF chunks are inline
        )
        self.db.add(chunk)
        await self.db.flush()

        # Store embedding (would typically go to vector store)
        # For now, we'll emit an event for async embedding storage
        event_bus.emit(
            "resource.chunked",
            {
                "resource_id": str(resource_id),
                "chunk_id": str(chunk.id),
                "chunk_index": chunk_index,
                "embedding": embedding_vector,
            },
        )

        return {
            "chunk_id": chunk.id,
            "chunk_index": chunk_index,
            "content": content,
            "page_number": page_number,
            "coordinates": coordinates,
            "chunk_type": chunk_type,
        }

    async def annotate_chunk(
        self,
        chunk_id: uuid.UUID,
        concept_tags: List[str],
        note: Optional[str] = None,
        color: str = "#FFFF00",
        user_id: str = "system",
    ) -> Dict[str, Any]:
        """
        Annotate a PDF chunk with conceptual tags and link to graph.

        Args:
            chunk_id: ID of chunk to annotate
            concept_tags: List of concept tags (e.g., ["OAuth", "Security"])
            note: Optional annotation note
            color: Highlight color
            user_id: User creating annotation

        Returns:
            Dict with annotation details and graph links created
        """
        # Fetch chunk
        result = await self.db.execute(
            select(DocumentChunk).where(DocumentChunk.id == chunk_id)
        )
        chunk = result.scalar_one_or_none()

        if not chunk:
            raise ValueError(f"Chunk not found: {chunk_id}")

        logger.info(
            f"Annotating chunk {chunk_id} with tags: {concept_tags}"
        )

        # Create annotation record
        annotation = Annotation(
            id=uuid.uuid4(),
            resource_id=chunk.resource_id,
            user_id=user_id,
            start_offset=0,  # Chunk-level annotation
            end_offset=len(chunk.content or ""),
            highlighted_text=chunk.content[:200] if chunk.content else "",
            note=note,
            tags=",".join(concept_tags),
            color=color,
        )
        self.db.add(annotation)
        await self.db.flush()

        # Link to knowledge graph
        linked_chunks = await self._link_to_graph(chunk, concept_tags)

        await self.db.commit()

        # Emit event
        event_bus.emit(
            "annotation.created",
            {
                "annotation_id": str(annotation.id),
                "chunk_id": str(chunk_id),
                "concept_tags": concept_tags,
                "graph_links": len(linked_chunks),
            },
        )

        return {
            "annotation_id": annotation.id,
            "chunk_id": chunk_id,
            "concept_tags": concept_tags,
            "note": note,
            "color": color,
            "created_at": annotation.created_at,
            "graph_links_created": len(linked_chunks),
            "linked_code_chunks": linked_chunks,
        }

    async def _link_to_graph(
        self, pdf_chunk: DocumentChunk, concept_tags: List[str]
    ) -> List[uuid.UUID]:
        """
        Link PDF chunk to knowledge graph based on concept tags.

        Creates graph entities for concepts and relationships to code chunks
        that share the same concepts.

        Args:
            pdf_chunk: PDF chunk to link
            concept_tags: Concept tags for linking

        Returns:
            List of linked code chunk IDs
        """
        linked_chunk_ids = []

        for concept in concept_tags:
            # Create or get graph entity for concept
            entity = await self._get_or_create_entity(concept, "Concept")

            # Create relationship from PDF chunk to concept
            pdf_relationship = GraphRelationship(
                id=uuid.uuid4(),
                source_entity_id=entity.id,
                target_entity_id=entity.id,  # Self-reference for now
                provenance_chunk_id=pdf_chunk.id,
                relation_type="MENTIONS",
                weight=1.0,
                relationship_metadata={
                    "source_type": "pdf",
                    "concept": concept,
                },
            )
            self.db.add(pdf_relationship)

            # Find code chunks with similar concepts
            code_chunks = await self._find_code_chunks_by_concept(concept)

            for code_chunk in code_chunks:
                # Create bidirectional link
                link_relationship = GraphRelationship(
                    id=uuid.uuid4(),
                    source_entity_id=entity.id,
                    target_entity_id=entity.id,
                    provenance_chunk_id=code_chunk.id,
                    relation_type="IMPLEMENTS",
                    weight=0.8,  # Semantic similarity weight
                    relationship_metadata={
                        "pdf_chunk_id": str(pdf_chunk.id),
                        "code_chunk_id": str(code_chunk.id),
                        "concept": concept,
                        "link_type": "pdf_to_code",
                    },
                )
                self.db.add(link_relationship)
                linked_chunk_ids.append(code_chunk.id)

        await self.db.flush()

        logger.info(
            f"Created {len(linked_chunk_ids)} graph links for chunk {pdf_chunk.id}"
        )

        return linked_chunk_ids

    async def _get_or_create_entity(
        self, name: str, entity_type: str
    ) -> GraphEntity:
        """
        Get existing graph entity or create new one.

        Args:
            name: Entity name
            entity_type: Entity type (Concept, Person, etc.)

        Returns:
            GraphEntity instance
        """
        # Check if entity exists
        result = await self.db.execute(
            select(GraphEntity).where(
                and_(GraphEntity.name == name, GraphEntity.type == entity_type)
            )
        )
        entity = result.scalar_one_or_none()

        if not entity:
            # Create new entity
            entity = GraphEntity(
                id=uuid.uuid4(),
                name=name,
                type=entity_type,
                description=f"{entity_type}: {name}",
            )
            self.db.add(entity)
            await self.db.flush()

        return entity

    async def _find_code_chunks_by_concept(
        self, concept: str
    ) -> List[DocumentChunk]:
        """
        Find code chunks that match a concept.

        Uses semantic search on chunk summaries and symbol names.

        Args:
            concept: Concept to search for

        Returns:
            List of matching code chunks
        """
        # Search for code chunks with matching semantic summary or symbol name
        result = await self.db.execute(
            select(DocumentChunk).where(
                and_(
                    DocumentChunk.is_remote,  # Code chunks
                    or_(
                        DocumentChunk.semantic_summary.ilike(f"%{concept}%"),
                        DocumentChunk.symbol_name.ilike(f"%{concept}%"),
                    ),
                )
            ).limit(10)
        )

        return list(result.scalars().all())

    async def graph_traversal_search(
        self,
        query: str,
        max_hops: int = 2,
        include_pdf: bool = True,
        include_code: bool = True,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Perform GraphRAG traversal search across PDF and code chunks.

        Args:
            query: Search query
            max_hops: Maximum graph traversal depth
            include_pdf: Include PDF chunks in results
            include_code: Include code chunks in results
            limit: Maximum results to return

        Returns:
            Dict with search results and metadata
        """
        import time

        start_time = time.time()

        logger.info(f"GraphRAG traversal search: {query} (max_hops={max_hops})")

        # Step 1: Generate query embedding
        await self.embedding_service.generate_embedding(query)

        # Step 2: Find seed entities matching query
        # (Simplified: search for entities with names matching query terms)
        query_terms = query.lower().split()
        seed_entities = []

        for term in query_terms:
            result = await self.db.execute(
                select(GraphEntity).where(GraphEntity.name.ilike(f"%{term}%")).limit(5)
            )
            seed_entities.extend(result.scalars().all())

        if not seed_entities:
            return {
                "query": query,
                "total_results": 0,
                "pdf_results": 0,
                "code_results": 0,
                "results": [],
                "execution_time_ms": (time.time() - start_time) * 1000,
            }

        # Step 3: Traverse graph from seed entities
        visited_chunks = set()
        results = []

        for entity in seed_entities[:3]:  # Limit seed entities
            # Get relationships from this entity
            relationships_result = await self.db.execute(
                select(GraphRelationship)
                .where(
                    or_(
                        GraphRelationship.source_entity_id == entity.id,
                        GraphRelationship.target_entity_id == entity.id,
                    )
                )
                .limit(20)
            )
            relationships = list(relationships_result.scalars().all())

            for rel in relationships:
                if rel.provenance_chunk_id and rel.provenance_chunk_id not in visited_chunks:
                    # Fetch chunk
                    chunk_result = await self.db.execute(
                        select(DocumentChunk).where(
                            DocumentChunk.id == rel.provenance_chunk_id
                        )
                    )
                    chunk = chunk_result.scalar_one_or_none()

                    if chunk:
                        # Filter by type
                        is_code = chunk.is_remote
                        is_pdf = not chunk.is_remote

                        if (include_code and is_code) or (include_pdf and is_pdf):
                            # Fetch annotations for this chunk
                            annotations_result = await self.db.execute(
                                select(Annotation).where(
                                    Annotation.resource_id == chunk.resource_id
                                )
                            )
                            annotations = list(annotations_result.scalars().all())

                            results.append(
                                {
                                    "chunk_id": chunk.id,
                                    "resource_id": chunk.resource_id,
                                    "chunk_type": "code" if is_code else "pdf",
                                    "content": chunk.content,
                                    "semantic_summary": chunk.semantic_summary,
                                    "relevance_score": rel.weight,
                                    "graph_distance": 1,  # Simplified
                                    "concept_tags": [entity.name],
                                    "file_path": chunk.github_uri if is_code else None,
                                    "page_number": chunk.chunk_metadata.get("page") if chunk.chunk_metadata else None,
                                    "annotations": [
                                        {
                                            "id": str(ann.id),
                                            "tags": ann.tags,
                                            "note": ann.note,
                                        }
                                        for ann in annotations
                                    ],
                                }
                            )

                            visited_chunks.add(chunk.id)

                            if len(results) >= limit:
                                break

                if len(results) >= limit:
                    break

        # Sort by relevance
        results.sort(key=lambda x: x["relevance_score"], reverse=True)

        # Calculate stats
        pdf_count = sum(1 for r in results if r["chunk_type"] == "pdf")
        code_count = sum(1 for r in results if r["chunk_type"] == "code")

        execution_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"GraphRAG search completed: {len(results)} results "
            f"({pdf_count} PDF, {code_count} code) in {execution_time_ms:.2f}ms"
        )

        return {
            "query": query,
            "total_results": len(results),
            "pdf_results": pdf_count,
            "code_results": code_count,
            "results": results,
            "execution_time_ms": execution_time_ms,
        }
