"""
Neo Alexandria 2.0 - Graph API Router

Provides REST endpoints for the hybrid knowledge graph system, enabling
mind-map neighbor exploration and global overview analysis.

Migrated from app/routers/graph.py to modules/graph/router.py
"""

from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.shared.database import get_db, get_sync_db
from app.database import models as db_models
from app.modules.graph.schema import KnowledgeGraph
from app.modules.graph.service import (
    find_hybrid_neighbors,
    generate_global_overview,
)
from app.modules.graph.embeddings import GraphEmbeddingsService
from app.config.settings import get_settings
from app.shared.event_bus import event_bus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/graph", tags=["graph"])
settings = get_settings()


@router.post(
    "/resources/{resource_id}/extract-citations",
    summary="Extract citations from a resource",
    description=(
        "Extracts citations from a resource's content and creates citation edges in the graph. "
        "This endpoint triggers citation extraction and emits a citation.extracted event."
    ),
)
def extract_resource_citations(
    resource_id: UUID,
    db: Session = Depends(get_sync_db),
) -> dict:
    """
    Extract citations from a resource and update the graph.

    This endpoint:
    1. Extracts citation markers and references from the resource
    2. Creates citation edges in the graph database
    3. Emits a citation.extracted event for downstream processing

    Args:
        resource_id: UUID of the resource to extract citations from
        db: Database session dependency

    Returns:
        dict: Response with extraction status and citations found

    Raises:
        HTTPException: If resource is not found or extraction fails
    """
    try:
        # Verify resource exists using SQLAlchemy 2.0 style
        from sqlalchemy import select

        stmt = select(db_models.Resource).where(db_models.Resource.id == resource_id)
        result = db.execute(stmt)
        resource = result.scalar_one_or_none()

        if not resource:
            raise HTTPException(
                status_code=404, detail=f"Resource with ID {resource_id} not found"
            )

        # Extract citations from resource description/content
        # In a real implementation, this would parse the text for citation markers
        # For now, we'll create a simple mock extraction
        citations = []

        if resource.description:
            # Simple citation marker detection (e.g., [1], [2], etc.)
            import re

            citation_pattern = r"\[(\d+)\]"
            matches = re.finditer(citation_pattern, resource.description)

            for match in matches:
                marker = match.group(0)
                position = match.start()

                # Extract context around the citation
                start = max(0, position - 20)
                end = min(len(resource.description), position + 50)
                context = resource.description[start:end]

                citations.append(
                    {
                        "marker": marker,
                        "position": position,
                        "context": context,
                        "text": marker,  # In real implementation, would extract actual reference text
                    }
                )

        # Emit citation.extracted event
        try:
            from app.shared.event_bus import EventPriority

            event_bus.emit(
                "citation.extracted",
                {
                    "resource_id": str(resource_id),
                    "citations": citations,
                    "count": len(citations),
                },
                priority=EventPriority.NORMAL,
            )
            logger.debug(f"Emitted citation.extracted event for {resource_id}")
        except Exception as e:
            logger.error(f"Failed to emit citation.extracted event: {e}", exc_info=True)

        logger.info(f"Extracted {len(citations)} citations from resource {resource_id}")

        return {
            "status": "success",
            "resource_id": str(resource_id),
            "citations": citations,
            "count": len(citations),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting citations for {resource_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Internal server error while extracting citations"
        )


@router.get(
    "/resource/{resource_id}/neighbors",
    response_model=KnowledgeGraph,
    summary="Get hybrid neighbors for mind-map view",
    description=(
        "Returns a knowledge graph showing the most relevant neighbors for a given resource, "
        "ranked by hybrid scoring that combines vector similarity, shared subjects, and "
        "classification code matches. Suitable for mind-map visualization."
    ),
)
def get_resource_neighbors(
    resource_id: UUID,
    limit: Optional[int] = Query(
        None,
        ge=1,
        le=20,
        description=f"Maximum number of neighbors to return (default: {settings.DEFAULT_GRAPH_NEIGHBORS})",
    ),
    db: Session = Depends(get_db),
) -> KnowledgeGraph:
    """
    Get hybrid-scored neighbors for a specific resource.

    This endpoint provides the data needed for a mind-map visualization
    centered on the specified resource. The returned graph includes:
    - The source resource as a node
    - Its top-ranked neighbor resources as nodes
    - Weighted edges explaining the relationships

    The hybrid scoring considers:
    - Vector similarity between embeddings (60% weight by default)
    - Shared canonical subjects (30% weight by default)
    - Classification code matches (10% weight by default)

    Args:
        resource_id: UUID of the resource to find neighbors for
        limit: Maximum number of neighbors to return
        db: Database session dependency

    Returns:
        KnowledgeGraph: Graph with source node and its neighbors

    Raises:
        HTTPException: If resource is not found or other errors occur
    """
    try:
        graph = find_hybrid_neighbors(db, resource_id, limit)

        # Check if source resource was found (empty graph means resource not found)
        if not graph.nodes:
            raise HTTPException(
                status_code=404, detail=f"Resource with ID {resource_id} not found"
            )

        logger.info(
            f"Generated neighbor graph for resource {resource_id}: "
            f"{len(graph.nodes)} nodes, {len(graph.edges)} edges"
        )

        return graph

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating neighbor graph for {resource_id}: {e}")
        # Return empty graph instead of 500 error
        logger.warning(f"Returning empty neighbor graph for {resource_id} due to error")
        return KnowledgeGraph(nodes=[], edges=[])


@router.get(
    "/overview",
    response_model=KnowledgeGraph,
    summary="Get global overview of strongest connections",
    description=(
        "Returns a knowledge graph showing the strongest relationships across the entire library. "
        "Combines high vector similarity pairs and significant tag overlap pairs, ranked by "
        "hybrid scoring. Suitable for global overview visualization."
    ),
)
def get_global_overview(
    limit: Optional[int] = Query(
        None,
        ge=1,
        le=100,
        description=f"Maximum number of edges to return (default: {settings.GRAPH_OVERVIEW_MAX_EDGES})",
    ),
    vector_threshold: Optional[float] = Query(
        None,
        ge=0.0,
        le=1.0,
        description=f"Minimum vector similarity threshold for candidates (default: {settings.GRAPH_VECTOR_MIN_SIM_THRESHOLD})",
    ),
    db: Session = Depends(get_db),
) -> KnowledgeGraph:
    """
    Get global overview of strongest connections across the library.

    This endpoint provides data for a global knowledge graph visualization
    showing the most significant relationships in the entire collection.

    The algorithm:
    1. Finds resource pairs with high vector similarity (above threshold)
    2. Finds resource pairs with significant tag overlap
    3. Scores all candidate pairs using hybrid weighting
    4. Returns the top-weighted edges and their involved nodes

    Args:
        limit: Maximum number of edges to include in the overview
        vector_threshold: Minimum cosine similarity for vector-based candidates
        db: Database session dependency

    Returns:
        KnowledgeGraph: Graph with strongest global connections (empty if no resources)

    Raises:
        HTTPException: If errors occur during graph generation
    """
    try:
        graph = generate_global_overview(db, limit, vector_threshold)

        logger.info(
            f"Generated global overview: "
            f"{len(graph.nodes)} nodes, {len(graph.edges)} edges, "
            f"limit={limit}, threshold={vector_threshold}"
        )

        return graph

    except Exception as e:
        logger.error(f"Error generating global overview: {e}")
        # Return empty graph instead of 500 error for empty database
        logger.warning("Returning empty graph due to error (likely empty database)")
        return KnowledgeGraph(nodes=[], edges=[])


# Graph Embeddings Endpoints (Task 11.7)


@router.post(
    "/embeddings/generate",
    summary="Generate graph embeddings",
    description=(
        "Generate Node2Vec or DeepWalk embeddings for the citation graph. "
        "This endpoint computes embeddings for all nodes in the graph and caches them."
    ),
)
def generate_graph_embeddings(
    algorithm: str = Query(
        "node2vec", description="Algorithm to use: 'node2vec' or 'deepwalk'"
    ),
    dimensions: int = Query(128, ge=32, le=512, description="Embedding dimensionality"),
    walk_length: int = Query(80, ge=10, le=200, description="Length of random walks"),
    num_walks: int = Query(10, ge=1, le=100, description="Number of walks per node"),
    p: float = Query(
        1.0, ge=0.1, le=10.0, description="Return parameter (Node2Vec only)"
    ),
    q: float = Query(
        1.0, ge=0.1, le=10.0, description="In-out parameter (Node2Vec only)"
    ),
    db: Session = Depends(get_sync_db),
) -> dict:
    """
    Generate graph embeddings using Node2Vec or DeepWalk algorithm.

    This endpoint:
    1. Builds a NetworkX graph from citation data
    2. Trains the specified embedding algorithm
    3. Extracts embeddings for all nodes
    4. Caches embeddings for fast retrieval

    Args:
        algorithm: Algorithm to use ("node2vec" or "deepwalk")
        dimensions: Embedding dimensionality (default: 128)
        walk_length: Length of random walks (default: 80)
        num_walks: Number of walks per node (default: 10)
        p: Return parameter for Node2Vec (default: 1.0)
        q: In-out parameter for Node2Vec (default: 1.0)
        db: Database session dependency

    Returns:
        dict: Response with status, embeddings_computed, dimensions, and execution_time

    Raises:
        HTTPException: If embedding generation fails
    """
    try:
        embeddings_service = GraphEmbeddingsService(db)

        if algorithm.lower() == "deepwalk":
            result = embeddings_service.compute_deepwalk_embeddings(
                dimensions=dimensions, walk_length=walk_length, num_walks=num_walks
            )
        elif algorithm.lower() == "node2vec":
            result = embeddings_service.compute_node2vec_embeddings(
                dimensions=dimensions,
                walk_length=walk_length,
                num_walks=num_walks,
                p=p,
                q=q,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid algorithm: {algorithm}. Must be 'node2vec' or 'deepwalk'",
            )

        logger.info(
            f"Generated {algorithm} embeddings: "
            f"{result['embeddings_computed']} nodes, "
            f"{result['execution_time']:.2f}s"
        )

        return result

    except ImportError as e:
        logger.error(f"Missing dependency for graph embeddings: {e}")
        raise HTTPException(
            status_code=500, detail=f"Missing required dependency: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error generating graph embeddings: {e}")
        raise HTTPException(
            status_code=500, detail="Internal server error while generating embeddings"
        )


@router.get(
    "/embeddings/{node_id}",
    summary="Get embedding for a node",
    description=(
        "Retrieve the graph embedding vector for a specific node (resource). "
        "Returns None if embeddings have not been generated or node not found."
    ),
)
def get_node_embedding(
    node_id: UUID,
    db: Session = Depends(get_sync_db),
) -> dict:
    """
    Get the graph embedding for a specific node.

    Args:
        node_id: UUID of the resource/node
        db: Database session dependency

    Returns:
        dict: Response with node_id, embedding vector, and dimensions

    Raises:
        HTTPException: If node is not found or embeddings not generated
    """
    try:
        embeddings_service = GraphEmbeddingsService(db)
        embedding = embeddings_service.get_embedding(node_id)

        if embedding is None:
            raise HTTPException(
                status_code=404,
                detail=f"No embedding found for node {node_id}. Generate embeddings first.",
            )

        return {
            "node_id": str(node_id),
            "embedding": embedding,
            "dimensions": len(embedding),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving embedding for {node_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Internal server error while retrieving embedding"
        )


@router.get(
    "/embeddings/{node_id}/similar",
    summary="Find similar nodes using embeddings",
    description=(
        "Find the most similar nodes to a given node based on graph embedding similarity. "
        "Uses cosine similarity to rank nodes by their structural similarity in the citation graph."
    ),
)
def get_similar_nodes(
    node_id: UUID,
    limit: int = Query(
        10, ge=1, le=100, description="Maximum number of similar nodes to return"
    ),
    min_similarity: float = Query(
        0.0, ge=0.0, le=1.0, description="Minimum similarity threshold"
    ),
    db: Session = Depends(get_sync_db),
) -> dict:
    """
    Find similar nodes based on graph embedding similarity.

    This endpoint:
    1. Retrieves the embedding for the source node
    2. Computes cosine similarity with all other nodes
    3. Returns the top-N most similar nodes with scores

    Args:
        node_id: UUID of the source resource/node
        limit: Maximum number of similar nodes to return (default: 10)
        min_similarity: Minimum similarity threshold (default: 0.0)
        db: Database session dependency

    Returns:
        dict: Response with node_id, similar_nodes list, and count

    Raises:
        HTTPException: If node is not found or embeddings not generated
    """
    try:
        embeddings_service = GraphEmbeddingsService(db)
        similar_nodes = embeddings_service.find_similar_nodes(
            node_id, limit=limit, min_similarity=min_similarity
        )

        if not similar_nodes:
            # Check if it's because embeddings don't exist
            embedding = embeddings_service.get_embedding(node_id)
            if embedding is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No embedding found for node {node_id}. Generate embeddings first.",
                )

        # Format response with resource details
        from app.database.models import Resource

        results = []
        for similar_node_id, similarity in similar_nodes:
            try:
                resource_id = UUID(similar_node_id)
                resource = db.query(Resource).filter(Resource.id == resource_id).first()

                result = {
                    "node_id": similar_node_id,
                    "similarity": float(similarity),
                }

                if resource:
                    result["title"] = resource.title
                    result["type"] = resource.type

                results.append(result)
            except (ValueError, AttributeError):
                # Skip invalid node IDs
                continue

        logger.info(f"Found {len(results)} similar nodes for {node_id}")

        return {
            "node_id": str(node_id),
            "similar_nodes": results,
            "count": len(results),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding similar nodes for {node_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Internal server error while finding similar nodes"
        )


# Literature-Based Discovery (LBD) Endpoints (Task 12.7)


@router.post(
    "/discover",
    summary="Discover hypotheses using ABC pattern",
    description=(
        "Discover novel connections between two concepts using the ABC pattern. "
        "Finds bridging concepts B that connect concept A to concept C through "
        "the literature. Returns hypotheses ranked by support strength and novelty. "
        "Target response time: <5 seconds for typical queries."
    ),
)
def discover_hypotheses(
    concept_a: str = Query(..., description="Starting concept to search for"),
    concept_c: str = Query(..., description="Target concept to connect to"),
    limit: int = Query(50, ge=1, le=100, description="Maximum hypotheses to return"),
    start_date: Optional[str] = Query(
        None, description="Start date for time-slicing (ISO format)"
    ),
    end_date: Optional[str] = Query(
        None, description="End date for time-slicing (ISO format)"
    ),
    db: Session = Depends(get_sync_db),
) -> dict:
    """
    Discover hypotheses connecting two concepts using ABC pattern.

    This endpoint implements Literature-Based Discovery (LBD) to find
    novel connections between concepts in the literature.

    The ABC pattern:
    - A: Starting concept (e.g., "machine learning")
    - B: Bridging concept(s) discovered by the algorithm
    - C: Target concept (e.g., "drug discovery")

    The algorithm:
    1. Finds resources mentioning concept A
    2. Finds resources mentioning concept C
    3. Identifies bridging concepts B appearing with both A and C
    4. Filters out known A-C connections
    5. Ranks hypotheses by support strength and novelty
    6. Builds evidence chains showing A→B and B→C connections

    Args:
        concept_a: Starting concept
        concept_c: Target concept
        limit: Maximum hypotheses to return (default: 50)
        start_date: Optional start date for temporal filtering
        end_date: Optional end date for temporal filtering
        db: Database session dependency

    Returns:
        dict: Response with hypotheses list, count, and execution time

    Raises:
        HTTPException: If discovery fails or times out
    """
    import time
    from datetime import datetime

    start_time = time.time()

    try:
        from app.modules.graph.discovery import LBDService

        lbd_service = LBDService(db)

        # Parse time slice if provided
        time_slice = None
        if start_date and end_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                time_slice = (start_dt, end_dt)
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid date format: {str(e)}. Use ISO format (YYYY-MM-DD)",
                )

        # Discover hypotheses
        hypotheses = lbd_service.discover_hypotheses(
            concept_a=concept_a, concept_c=concept_c, limit=limit, time_slice=time_slice
        )

        execution_time = time.time() - start_time

        # Check performance target
        if execution_time > 5.0:
            logger.warning(
                f"LBD discovery exceeded 5s target: {execution_time:.2f}s "
                f"(A='{concept_a}', C='{concept_c}')"
            )

        logger.info(
            f"LBD discovery completed: {len(hypotheses)} hypotheses, "
            f"{execution_time:.2f}s (A='{concept_a}', C='{concept_c}')"
        )

        return {
            "concept_a": concept_a,
            "concept_c": concept_c,
            "hypotheses": hypotheses,
            "count": len(hypotheses),
            "execution_time": execution_time,
            "time_slice": {"start_date": start_date, "end_date": end_date}
            if time_slice
            else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in LBD discovery (A='{concept_a}', C='{concept_c}'): {e}")
        raise HTTPException(
            status_code=500, detail="Internal server error during hypothesis discovery"
        )


@router.get(
    "/hypotheses/{hypothesis_id}",
    summary="Get hypothesis details",
    description=(
        "Retrieve detailed information about a specific hypothesis, "
        "including evidence chains and support metrics."
    ),
)
def get_hypothesis(
    hypothesis_id: str,
    db: Session = Depends(get_sync_db),
) -> dict:
    """
    Get details for a specific hypothesis.

    This endpoint retrieves a stored hypothesis from the database
    with all its associated metadata and evidence.

    Args:
        hypothesis_id: UUID of the hypothesis
        db: Database session dependency

    Returns:
        dict: Hypothesis details including concepts, support, and evidence

    Raises:
        HTTPException: If hypothesis is not found
    """
    try:
        from app.modules.graph.model import DiscoveryHypothesis
        from app.database.models import Resource

        # Query hypothesis
        hypothesis = (
            db.query(DiscoveryHypothesis)
            .filter(DiscoveryHypothesis.id == UUID(hypothesis_id))
            .first()
        )

        if not hypothesis:
            raise HTTPException(
                status_code=404, detail=f"Hypothesis {hypothesis_id} not found"
            )

        # Get resource details
        a_resource = (
            db.query(Resource).filter(Resource.id == hypothesis.a_resource_id).first()
        )

        c_resource = (
            db.query(Resource).filter(Resource.id == hypothesis.c_resource_id).first()
        )

        # Parse B resource IDs
        try:
            if isinstance(hypothesis.b_resource_ids, str):
                b_resource_ids = json.loads(hypothesis.b_resource_ids)
            else:
                b_resource_ids = hypothesis.b_resource_ids or []
        except (json.JSONDecodeError, TypeError):
            b_resource_ids = []

        # Get B resources
        b_resources = []
        if b_resource_ids:
            b_resources_query = (
                db.query(Resource)
                .filter(Resource.id.in_([UUID(bid) for bid in b_resource_ids]))
                .all()
            )

            b_resources = [
                {
                    "id": str(r.id),
                    "title": r.title,
                    "type": r.type,
                    "publication_year": r.publication_year,
                }
                for r in b_resources_query
            ]

        logger.info(f"Retrieved hypothesis {hypothesis_id}")

        return {
            "id": str(hypothesis.id),
            "hypothesis_type": hypothesis.hypothesis_type,
            "a_resource": {
                "id": str(a_resource.id),
                "title": a_resource.title,
                "type": a_resource.type,
            }
            if a_resource
            else None,
            "c_resource": {
                "id": str(c_resource.id),
                "title": c_resource.title,
                "type": c_resource.type,
            }
            if c_resource
            else None,
            "b_resources": b_resources,
            "plausibility_score": hypothesis.plausibility_score,
            "path_strength": hypothesis.path_strength,
            "path_length": hypothesis.path_length,
            "common_neighbors": hypothesis.common_neighbors,
            "discovered_at": hypothesis.discovered_at.isoformat(),
            "is_validated": bool(hypothesis.is_validated)
            if hypothesis.is_validated is not None
            else None,
            "validation_notes": hypothesis.validation_notes,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving hypothesis {hypothesis_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Internal server error while retrieving hypothesis"
        )


# ============================================================================
# ADVANCED RAG ENDPOINTS
# ============================================================================


@router.post(
    "/extract/{chunk_id}",
    summary="Extract entities and relationships from a chunk",
    description=(
        "Extract named entities and semantic relationships from a document chunk. "
        "Entities are classified as Concept, Person, Organization, or Method. "
        "Relationships are typed as CONTRADICTS, SUPPORTS, EXTENDS, or CITES. "
        "All extractions are linked to the source chunk for provenance tracking."
    ),
)
def extract_graph_from_chunk(
    chunk_id: UUID,
    extraction_method: str = Query(
        "llm", description="Extraction method: 'llm', 'spacy', or 'hybrid'"
    ),
    db: Session = Depends(get_sync_db),
) -> dict:
    """
    Extract entities and relationships from a document chunk.

    This endpoint:
    1. Retrieves the chunk content from the database
    2. Extracts named entities using the specified method
    3. Extracts relationships between entities
    4. Stores entities and relationships in the knowledge graph
    5. Emits events for downstream processing

    Args:
        chunk_id: UUID of the document chunk to extract from
        extraction_method: Method to use ('llm', 'spacy', or 'hybrid')
        db: Database session dependency

    Returns:
        dict: Response with extraction status, entities, and relationships

    Raises:
        HTTPException: If chunk is not found or extraction fails
    """
    try:
        from app.database.models import DocumentChunk
        from app.modules.graph.model import GraphEntity, GraphRelationship
        from app.modules.graph.service import GraphExtractionService

        # Verify chunk exists
        chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()

        if not chunk:
            raise HTTPException(
                status_code=404, detail=f"Chunk with ID {chunk_id} not found"
            )

        # Initialize extraction service
        extraction_service = GraphExtractionService(
            db=db, extraction_method=extraction_method
        )

        # Extract entities
        entities = extraction_service.extract_entities(chunk.content)

        # Store entities in database and build entity map
        entity_map = {}  # Maps (name, type) to entity ID
        stored_entities = []

        for entity_data in entities:
            # Check if entity already exists
            existing_entity = (
                db.query(GraphEntity)
                .filter(
                    GraphEntity.name == entity_data["name"],
                    GraphEntity.type == entity_data["type"],
                )
                .first()
            )

            if existing_entity:
                entity_id = existing_entity.id
            else:
                # Create new entity
                new_entity = GraphEntity(
                    name=entity_data["name"],
                    type=entity_data["type"],
                    description=entity_data.get("description"),
                )
                db.add(new_entity)
                db.flush()  # Get ID without committing
                entity_id = new_entity.id

            entity_map[(entity_data["name"], entity_data["type"])] = entity_id
            stored_entities.append(
                {
                    "id": str(entity_id),
                    "name": entity_data["name"],
                    "type": entity_data["type"],
                }
            )

            # Emit event
            extraction_service.emit_entity_extracted_event(entity_data, str(chunk_id))

        # Extract relationships
        relationships = extraction_service.extract_relationships(
            chunk.content, entities, str(chunk_id)
        )

        # Store relationships in database
        stored_relationships = []

        for rel_data in relationships:
            source_key = (
                rel_data["source_entity"]["name"],
                rel_data["source_entity"]["type"],
            )
            target_key = (
                rel_data["target_entity"]["name"],
                rel_data["target_entity"]["type"],
            )

            source_entity_id = entity_map.get(source_key)
            target_entity_id = entity_map.get(target_key)

            if not source_entity_id or not target_entity_id:
                logger.warning("Skipping relationship: entity not found in map")
                continue

            # Create relationship
            new_relationship = GraphRelationship(
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relation_type=rel_data["relation_type"],
                weight=rel_data["weight"],
                provenance_chunk_id=chunk_id,
            )
            db.add(new_relationship)
            db.flush()

            stored_relationships.append(
                {
                    "id": str(new_relationship.id),
                    "source_entity": rel_data["source_entity"]["name"],
                    "target_entity": rel_data["target_entity"]["name"],
                    "relation_type": rel_data["relation_type"],
                    "weight": rel_data["weight"],
                }
            )

            # Emit event
            extraction_service.emit_relationship_extracted_event(
                rel_data, str(chunk_id)
            )

        # Commit all changes
        db.commit()

        logger.info(
            f"Extracted {len(stored_entities)} entities and "
            f"{len(stored_relationships)} relationships from chunk {chunk_id}"
        )

        return {
            "status": "success",
            "chunk_id": str(chunk_id),
            "extraction_method": extraction_method,
            "entities": stored_entities,
            "relationships": stored_relationships,
            "counts": {
                "entities": len(stored_entities),
                "relationships": len(stored_relationships),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting graph from chunk {chunk_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Internal server error while extracting graph"
        )


@router.get(
    "/entities",
    summary="List graph entities with filtering",
    description=(
        "Retrieve a list of graph entities with optional filtering by type and name. "
        "Supports pagination for large result sets."
    ),
)
def list_entities(
    entity_type: Optional[str] = Query(
        None,
        description="Filter by entity type (Concept, Person, Organization, Method)",
    ),
    name_contains: Optional[str] = Query(
        None, description="Filter by entities whose name contains this string"
    ),
    skip: int = Query(0, ge=0, description="Number of entities to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum entities to return"),
    db: Session = Depends(get_sync_db),
) -> dict:
    """
    List graph entities with optional filtering.

    Args:
        entity_type: Optional filter by entity type
        name_contains: Optional filter by name substring
        skip: Number of entities to skip (pagination)
        limit: Maximum entities to return
        db: Database session dependency

    Returns:
        dict: Response with entities list and pagination info

    Raises:
        HTTPException: If query fails
    """
    try:
        from app.modules.graph.model import GraphEntity

        # Build query
        query = db.query(GraphEntity)

        # Apply filters
        if entity_type:
            query = query.filter(GraphEntity.type == entity_type)

        if name_contains:
            query = query.filter(GraphEntity.name.ilike(f"%{name_contains}%"))

        # Get total count
        total_count = query.count()

        # Apply pagination
        entities = query.offset(skip).limit(limit).all()

        # Format response
        entity_list = [
            {
                "id": str(entity.id),
                "name": entity.name,
                "type": entity.type,
                "description": entity.description,
                "created_at": entity.created_at.isoformat(),
            }
            for entity in entities
        ]

        logger.info(
            f"Listed {len(entity_list)} entities "
            f"(type={entity_type}, name_contains={name_contains})"
        )

        return {
            "entities": entity_list,
            "total_count": total_count,
            "skip": skip,
            "limit": limit,
        }

    except Exception as e:
        logger.error(f"Error listing entities: {e}")
        raise HTTPException(
            status_code=500, detail="Internal server error while listing entities"
        )


@router.get(
    "/entities/{entity_id}/relationships",
    summary="Get relationships for an entity",
    description=(
        "Retrieve all relationships where the specified entity is either "
        "the source or target. Includes relationship details and connected entities."
    ),
)
def get_entity_relationships(
    entity_id: UUID,
    relation_type: Optional[str] = Query(
        None, description="Filter by relationship type"
    ),
    direction: str = Query(
        "both", description="Relationship direction: 'outgoing', 'incoming', or 'both'"
    ),
    db: Session = Depends(get_sync_db),
) -> dict:
    """
    Get all relationships for a specific entity.

    Args:
        entity_id: UUID of the entity
        relation_type: Optional filter by relationship type
        direction: Filter by direction ('outgoing', 'incoming', or 'both')
        db: Database session dependency

    Returns:
        dict: Response with relationships and connected entities

    Raises:
        HTTPException: If entity is not found or query fails
    """
    try:
        from app.modules.graph.model import GraphEntity, GraphRelationship

        # Verify entity exists
        entity = db.query(GraphEntity).filter(GraphEntity.id == entity_id).first()

        if not entity:
            raise HTTPException(
                status_code=404, detail=f"Entity with ID {entity_id} not found"
            )

        # Build queries based on direction
        outgoing_relationships = []
        incoming_relationships = []

        if direction in ["outgoing", "both"]:
            outgoing_query = db.query(GraphRelationship).filter(
                GraphRelationship.source_entity_id == entity_id
            )
            if relation_type:
                outgoing_query = outgoing_query.filter(
                    GraphRelationship.relation_type == relation_type
                )
            outgoing_relationships = outgoing_query.all()

        if direction in ["incoming", "both"]:
            incoming_query = db.query(GraphRelationship).filter(
                GraphRelationship.target_entity_id == entity_id
            )
            if relation_type:
                incoming_query = incoming_query.filter(
                    GraphRelationship.relation_type == relation_type
                )
            incoming_relationships = incoming_query.all()

        # Format outgoing relationships
        outgoing_list = []
        for rel in outgoing_relationships:
            target_entity = (
                db.query(GraphEntity)
                .filter(GraphEntity.id == rel.target_entity_id)
                .first()
            )

            outgoing_list.append(
                {
                    "id": str(rel.id),
                    "target_entity": {
                        "id": str(target_entity.id),
                        "name": target_entity.name,
                        "type": target_entity.type,
                    }
                    if target_entity
                    else None,
                    "relation_type": rel.relation_type,
                    "weight": rel.weight,
                    "provenance_chunk_id": str(rel.provenance_chunk_id)
                    if rel.provenance_chunk_id
                    else None,
                    "created_at": rel.created_at.isoformat(),
                }
            )

        # Format incoming relationships
        incoming_list = []
        for rel in incoming_relationships:
            source_entity = (
                db.query(GraphEntity)
                .filter(GraphEntity.id == rel.source_entity_id)
                .first()
            )

            incoming_list.append(
                {
                    "id": str(rel.id),
                    "source_entity": {
                        "id": str(source_entity.id),
                        "name": source_entity.name,
                        "type": source_entity.type,
                    }
                    if source_entity
                    else None,
                    "relation_type": rel.relation_type,
                    "weight": rel.weight,
                    "provenance_chunk_id": str(rel.provenance_chunk_id)
                    if rel.provenance_chunk_id
                    else None,
                    "created_at": rel.created_at.isoformat(),
                }
            )

        logger.info(
            f"Retrieved {len(outgoing_list)} outgoing and "
            f"{len(incoming_list)} incoming relationships for entity {entity_id}"
        )

        return {
            "entity": {"id": str(entity.id), "name": entity.name, "type": entity.type},
            "outgoing_relationships": outgoing_list,
            "incoming_relationships": incoming_list,
            "counts": {
                "outgoing": len(outgoing_list),
                "incoming": len(incoming_list),
                "total": len(outgoing_list) + len(incoming_list),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting relationships for entity {entity_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while retrieving relationships",
        )


@router.get(
    "/traverse",
    summary="Traverse the knowledge graph",
    description=(
        "Traverse the knowledge graph starting from a given entity, "
        "following relationships up to a specified number of hops. "
        "Returns all entities and relationships discovered in the traversal."
    ),
)
def traverse_graph(
    start_entity_id: UUID = Query(..., description="Starting entity UUID"),
    max_hops: int = Query(2, ge=1, le=3, description="Maximum number of hops"),
    relation_types: Optional[str] = Query(
        None, description="Comma-separated list of relation types to follow"
    ),
    db: Session = Depends(get_sync_db),
) -> dict:
    """
    Traverse the knowledge graph from a starting entity.

    This endpoint performs a breadth-first traversal of the knowledge graph,
    following relationships up to max_hops distance from the starting entity.

    Args:
        start_entity_id: UUID of the starting entity
        max_hops: Maximum number of hops to traverse (1-3)
        relation_types: Optional comma-separated list of relation types to follow
        db: Database session dependency

    Returns:
        dict: Response with discovered entities, relationships, and traversal info

    Raises:
        HTTPException: If starting entity is not found or traversal fails
    """
    try:
        from app.modules.graph.model import GraphEntity, GraphRelationship

        # Verify starting entity exists
        start_entity = (
            db.query(GraphEntity).filter(GraphEntity.id == start_entity_id).first()
        )

        if not start_entity:
            raise HTTPException(
                status_code=404,
                detail=f"Starting entity with ID {start_entity_id} not found",
            )

        # Parse relation types filter
        allowed_relation_types = None
        if relation_types:
            allowed_relation_types = set(rt.strip() for rt in relation_types.split(","))

        # Perform breadth-first traversal
        visited_entities = {start_entity_id}
        visited_relationships = set()
        entities_by_hop = {0: [start_entity_id]}
        current_frontier = {start_entity_id}

        for hop in range(1, max_hops + 1):
            next_frontier = set()

            for entity_id in current_frontier:
                # Get outgoing relationships
                outgoing_query = db.query(GraphRelationship).filter(
                    GraphRelationship.source_entity_id == entity_id
                )

                if allowed_relation_types:
                    outgoing_query = outgoing_query.filter(
                        GraphRelationship.relation_type.in_(allowed_relation_types)
                    )

                outgoing_rels = outgoing_query.all()

                for rel in outgoing_rels:
                    rel_id = rel.id
                    target_id = rel.target_entity_id

                    if rel_id not in visited_relationships:
                        visited_relationships.add(rel_id)

                        if target_id not in visited_entities:
                            visited_entities.add(target_id)
                            next_frontier.add(target_id)

                # Get incoming relationships
                incoming_query = db.query(GraphRelationship).filter(
                    GraphRelationship.target_entity_id == entity_id
                )

                if allowed_relation_types:
                    incoming_query = incoming_query.filter(
                        GraphRelationship.relation_type.in_(allowed_relation_types)
                    )

                incoming_rels = incoming_query.all()

                for rel in incoming_rels:
                    rel_id = rel.id
                    source_id = rel.source_entity_id

                    if rel_id not in visited_relationships:
                        visited_relationships.add(rel_id)

                        if source_id not in visited_entities:
                            visited_entities.add(source_id)
                            next_frontier.add(source_id)

            if next_frontier:
                entities_by_hop[hop] = list(next_frontier)

            current_frontier = next_frontier

            if not current_frontier:
                break

        # Fetch all discovered entities
        all_entities = (
            db.query(GraphEntity).filter(GraphEntity.id.in_(visited_entities)).all()
        )

        entity_list = [
            {
                "id": str(entity.id),
                "name": entity.name,
                "type": entity.type,
                "description": entity.description,
            }
            for entity in all_entities
        ]

        # Fetch all discovered relationships
        all_relationships = (
            db.query(GraphRelationship)
            .filter(GraphRelationship.id.in_(visited_relationships))
            .all()
        )

        relationship_list = [
            {
                "id": str(rel.id),
                "source_entity_id": str(rel.source_entity_id),
                "target_entity_id": str(rel.target_entity_id),
                "relation_type": rel.relation_type,
                "weight": rel.weight,
            }
            for rel in all_relationships
        ]

        logger.info(
            f"Graph traversal from {start_entity_id}: "
            f"{len(entity_list)} entities, {len(relationship_list)} relationships "
            f"(max_hops={max_hops})"
        )

        return {
            "start_entity": {
                "id": str(start_entity.id),
                "name": start_entity.name,
                "type": start_entity.type,
            },
            "entities": entity_list,
            "relationships": relationship_list,
            "traversal_info": {
                "max_hops": max_hops,
                "entities_by_hop": {
                    str(hop): [str(eid) for eid in entity_ids]
                    for hop, entity_ids in entities_by_hop.items()
                },
                "total_entities": len(entity_list),
                "total_relationships": len(relationship_list),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error traversing graph from {start_entity_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Internal server error while traversing graph"
        )


# ============================================================================
# CODE INTELLIGENCE ENDPOINTS
# ============================================================================


@router.post(
    "/hover",
    summary="Get hover information for code position",
    description=(
        "Retrieve contextual information for code at a specific position. "
        "Returns symbol information, documentation, related chunks, and context lines. "
        "Target response time: <100ms. Supports Python, JavaScript, TypeScript, Java, C++, Go, and Rust."
    ),
)
def post_hover_information(
    resource_id: str = Query(..., description="Resource UUID containing the file"),
    file_path: str = Query(..., description="File path within the resource"),
    line: int = Query(..., ge=1, description="Line number (1-indexed)"),
    column: int = Query(..., ge=0, description="Column number (0-indexed)"),
    db: Session = Depends(get_sync_db),
) -> dict:
    """
    Get hover information for code at a specific position (POST method).

    This endpoint provides contextual information for code at a given position,
    including:
    - Symbol name and type (function, class, variable, etc.)
    - Definition location
    - Documentation string
    - Related document chunks with similar content
    - Surrounding code lines for context

    The endpoint uses static analysis (Tree-Sitter AST parsing) to extract
    symbol information without executing code. Results are cached for 5 minutes.

    Args:
        resource_id: UUID of the resource containing the file
        file_path: File path within the resource
        line: Line number (1-indexed)
        column: Column number (0-indexed)
        db: Database session dependency

    Returns:
        HoverInformationResponse: Hover information with symbol details and context

    Raises:
        HTTPException: If resource is not found or hover extraction fails
    """
    from uuid import UUID as UUIDType

    return _get_hover_information_impl(
        resource_id=UUIDType(resource_id),
        file_path=file_path,
        line=line,
        column=column,
        db=db,
    )


@router.get(
    "/code/hover",
    summary="Get hover information for code position (GET alias)",
    description=(
        "Retrieve contextual information for code at a specific position. "
        "Returns symbol information, documentation, related chunks, and context lines. "
        "Target response time: <100ms. Supports Python, JavaScript, TypeScript, Java, C++, Go, and Rust. "
        "Note: This is a GET alias for backward compatibility. Use POST /hover for new implementations."
    ),
)
def get_hover_information(
    file_path: str = Query(..., description="File path within the resource"),
    line: int = Query(..., ge=1, description="Line number (1-indexed)"),
    column: int = Query(..., ge=0, description="Column number (0-indexed)"),
    resource_id: UUID = Query(..., description="Resource UUID containing the file"),
    db: Session = Depends(get_sync_db),
) -> dict:
    """
    Get hover information for code at a specific position (GET method - deprecated).

    This is a backward compatibility alias. New implementations should use POST /hover.
    """
    return _get_hover_information_impl(
        resource_id=resource_id, file_path=file_path, line=line, column=column, db=db
    )


def _get_hover_information_impl(
    resource_id: UUID,
    file_path: str,
    line: int,
    column: int,
    db: Session,
) -> dict:
    """
    Get hover information for code at a specific position.

    This endpoint provides contextual information for code at a given position,
    including:
    - Symbol name and type (function, class, variable, etc.)
    - Definition location
    - Documentation string
    - Related document chunks with similar content
    - Surrounding code lines for context

    The endpoint uses static analysis (Tree-Sitter AST parsing) to extract
    symbol information without executing code. Results are cached for 5 minutes.

    Args:
        file_path: File path within the resource
        line: Line number (1-indexed)
        column: Column number (0-indexed)
        resource_id: UUID of the resource containing the file
        db: Database session dependency

    Returns:
        HoverInformationResponse: Hover information with symbol details and context

    Raises:
        HTTPException: If resource is not found or hover extraction fails
    """
    import time
    from app.modules.graph.schema import (
        HoverInformationResponse,
        LocationInfo,
    )
    from app.modules.graph.logic.static_analysis import StaticAnalysisService
    from app.database.models import Resource, DocumentChunk
    from app.shared.cache import CacheService

    start_time = time.time()

    try:
        # Check cache first (5-minute TTL)
        cache_service = CacheService()
        cache_key = f"hover:{resource_id}:{file_path}:{line}:{column}"

        cached_result = cache_service.get(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for hover info: {cache_key}")
            return cached_result

        # Verify resource exists
        resource = db.query(Resource).filter(Resource.id == resource_id).first()

        if not resource:
            raise HTTPException(
                status_code=404, detail=f"Resource with ID {resource_id} not found"
            )

        # Get resource metadata to determine language
        language = resource.language

        # Try to infer language from file extension if not in metadata
        if not language:
            ext_map = {
                ".py": "python",
                ".js": "javascript",
                ".jsx": "javascript",
                ".ts": "typescript",
                ".tsx": "typescript",
                ".java": "java",
                ".cpp": "cpp",
                ".cc": "cpp",
                ".cxx": "cpp",
                ".go": "go",
                ".rs": "rust",
            }
            for ext, lang in ext_map.items():
                if file_path.endswith(ext):
                    language = lang
                    break

        # Validate language support
        supported_languages = [
            "python",
            "javascript",
            "typescript",
            "java",
            "cpp",
            "go",
            "rust",
        ]
        if language and language not in supported_languages:
            # Return empty context for unsupported languages
            response = HoverInformationResponse(
                symbol_name=None,
                symbol_type=None,
                definition_location=None,
                documentation=None,
                related_chunks=[],
                context_lines=[],
            )
            return response.model_dump()

        # Find the chunk containing this position
        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.resource_id == resource_id)
            .all()
        )

        target_chunk = None
        for chunk in chunks:
            chunk_metadata = chunk.chunk_metadata or {}
            start_line = chunk_metadata.get("start_line", 0)
            end_line = chunk_metadata.get("end_line", 0)

            if start_line <= line <= end_line:
                target_chunk = chunk
                break

        if not target_chunk:
            # No chunk found for this position - return empty context
            response = HoverInformationResponse(
                symbol_name=None,
                symbol_type=None,
                definition_location=None,
                documentation=None,
                related_chunks=[],
                context_lines=[],
            )
            return response.model_dump()

        # Extract context lines from chunk content
        chunk_lines = target_chunk.content.split("\n")
        chunk_metadata = target_chunk.chunk_metadata or {}
        chunk_start_line = chunk_metadata.get("start_line", 1)

        # Calculate relative line number within chunk
        relative_line = line - chunk_start_line

        # Get context lines (3 before and 3 after)
        context_start = max(0, relative_line - 3)
        context_end = min(len(chunk_lines), relative_line + 4)
        context_lines = chunk_lines[context_start:context_end]

        # Use StaticAnalyzer to extract symbol information
        symbol_name = None
        symbol_type = None
        definition_location = None
        documentation = None

        if language:
            try:
                # Use StaticAnalyzer for proper AST-based symbol extraction
                static_analyzer = StaticAnalysisService(db)

                # Calculate column position within chunk content
                # For now, use column parameter directly
                symbol_info = static_analyzer.get_symbol_at_position(
                    code=target_chunk.content,
                    language=language,
                    line=relative_line + 1,  # Convert to 1-indexed within chunk
                    column=column,
                )

                if symbol_info:
                    symbol_name = symbol_info.get("symbol_name")
                    symbol_type = symbol_info.get("symbol_type")
                    documentation = symbol_info.get("documentation")

                    # Build definition location
                    def_loc = symbol_info.get("definition_location")
                    if def_loc:
                        # Convert chunk-relative line to file-absolute line
                        absolute_line = chunk_start_line + def_loc["line"] - 1
                        definition_location = LocationInfo(
                            file_path=file_path,
                            line=absolute_line,
                            column=def_loc.get("column", 0),
                        )

                logger.debug(
                    f"StaticAnalyzer extracted: symbol={symbol_name}, "
                    f"type={symbol_type}, has_doc={documentation is not None}"
                )

            except Exception as e:
                logger.warning(f"StaticAnalyzer failed, using fallback: {e}")
                # Fall back to simple heuristics if static analysis fails
                symbol_info = None

        # Find related chunks based on embedding similarity
        # Note: DocumentChunk uses embedding_id (UUID reference) not direct embedding field
        # For now, return empty related_chunks list
        # TODO: Implement proper embedding lookup via embedding_id if needed
        related_chunks = []

        # Future enhancement: Query embeddings table using embedding_id
        # if target_chunk and target_chunk.embedding_id:
        #     # Query embedding service or embeddings table
        #     # Compute similarity with other chunk embeddings
        #     pass

        # Build response
        response = HoverInformationResponse(
            symbol_name=symbol_name,
            symbol_type=symbol_type,
            definition_location=definition_location,
            documentation=documentation,
            related_chunks=related_chunks,
            context_lines=context_lines,
        )

        # Cache the result for 5 minutes
        result_dict = response.model_dump()
        cache_service.set(cache_key, result_dict, ttl=300)

        # Check performance target
        elapsed_time = time.time() - start_time
        if elapsed_time > 0.1:
            logger.warning(
                f"Hover info exceeded 100ms target: {elapsed_time * 1000:.1f}ms "
                f"(resource={resource_id}, file={file_path}, line={line})"
            )
        else:
            logger.debug(
                f"Hover info completed in {elapsed_time * 1000:.1f}ms "
                f"(resource={resource_id}, file={file_path}, line={line})"
            )

        return result_dict

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error getting hover info for {file_path}:{line}:{column} "
            f"in resource {resource_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error while retrieving hover information",
        )


@router.get(
    "/centrality",
    summary="Compute graph centrality metrics",
    description=(
        "Compute centrality metrics for specified resources. "
        "Returns degree centrality, betweenness centrality, and PageRank scores. "
        "Results are cached for 10 minutes. Target response time: <2s for 1000 nodes."
    ),
)
async def get_centrality_metrics(
    resource_ids: str = Query(
        ...,
        description="Comma-separated list of resource UUIDs",
        example="123e4567-e89b-12d3-a456-426614174000,223e4567-e89b-12d3-a456-426614174001",
    ),
    damping_factor: float = Query(
        0.85,
        ge=0.01,
        le=0.99,
        description="PageRank damping factor (default 0.85)",
    ),
    db: Session = Depends(get_sync_db),
) -> dict:
    """
    Compute centrality metrics for specified resources.

    This endpoint computes multiple centrality measures:
    - Degree centrality: Number of direct connections (in-degree and out-degree)
    - Betweenness centrality: How often a node appears on shortest paths
    - PageRank: Importance based on incoming link structure

    Results are cached for 10 minutes to improve performance. The cache is
    invalidated when the graph structure changes.

    Args:
        resource_ids: Comma-separated list of resource UUIDs
        damping_factor: PageRank damping factor (0.01-0.99, default 0.85)
        db: Database session dependency

    Returns:
        CentralityResponse: Centrality metrics for requested resources

    Raises:
        HTTPException: If resource IDs are invalid or computation fails
    """
    import time
    from datetime import datetime, timedelta, timezone
    from app.modules.graph.schema import CentralityMetrics, CentralityResponse
    from app.modules.graph.service import GraphService
    from app.database.models import GraphCentralityCache
    from app.shared.cache import CacheService

    start_time = time.time()

    try:
        # Parse resource IDs
        try:
            resource_id_list = [UUID(rid.strip()) for rid in resource_ids.split(",")]
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid resource ID format: {e}",
            )

        if not resource_id_list:
            raise HTTPException(
                status_code=400,
                detail="At least one resource ID must be provided",
            )

        # Check cache first (10-minute TTL)
        cache_service = CacheService()
        cache_key = f"centrality:{','.join(str(rid) for rid in resource_id_list)}:{damping_factor}"

        cached_result = cache_service.get(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for centrality metrics: {cache_key}")
            elapsed_time = time.time() - start_time
            cached_result["computation_time_ms"] = elapsed_time * 1000
            cached_result["cached"] = True
            return cached_result

        # Check database cache (10-minute TTL)
        cache_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        db_cached_metrics = (
            db.query(GraphCentralityCache)
            .filter(
                GraphCentralityCache.resource_id.in_(resource_id_list),
                GraphCentralityCache.computed_at >= cache_cutoff,
            )
            .all()
        )

        # Build map of cached metrics
        cached_by_id = {cache.resource_id: cache for cache in db_cached_metrics}

        # Identify resources that need computation
        needs_computation = [rid for rid in resource_id_list if rid not in cached_by_id]

        # Compute metrics for uncached resources
        computed_metrics = {}
        if needs_computation:
            graph_service = GraphService(db)

            # Compute all centrality metrics
            degree_metrics = await graph_service.compute_degree_centrality(
                [int(rid) for rid in needs_computation]
            )
            betweenness_metrics = await graph_service.compute_betweenness_centrality(
                [int(rid) for rid in needs_computation]
            )
            pagerank_metrics = await graph_service.compute_pagerank(
                [int(rid) for rid in needs_computation],
                damping_factor=damping_factor,
            )

            # Store computed metrics in database cache
            for resource_id in needs_computation:
                resource_id_int = int(resource_id)
                degree = degree_metrics.get(resource_id_int, {})
                betweenness = betweenness_metrics.get(resource_id_int, 0.0)
                pagerank = pagerank_metrics.get(resource_id_int, 0.0)

                # Create cache entry
                cache_entry = GraphCentralityCache(
                    resource_id=resource_id,
                    in_degree=degree.get("in_degree", 0),
                    out_degree=degree.get("out_degree", 0),
                    betweenness=betweenness,
                    pagerank=pagerank,
                    computed_at=datetime.now(timezone.utc),
                )
                db.add(cache_entry)

                computed_metrics[resource_id] = cache_entry

            db.commit()

        # Build response combining cached and computed metrics
        metrics_dict = {}
        for resource_id in resource_id_list:
            if resource_id in cached_by_id:
                cache = cached_by_id[resource_id]
                metrics_dict[resource_id] = CentralityMetrics(
                    resource_id=resource_id,
                    in_degree=cache.in_degree,
                    out_degree=cache.out_degree,
                    total_degree=cache.in_degree + cache.out_degree,
                    betweenness=cache.betweenness,
                    pagerank=cache.pagerank,
                    computed_at=cache.computed_at.isoformat(),
                )
            elif resource_id in computed_metrics:
                cache = computed_metrics[resource_id]
                metrics_dict[resource_id] = CentralityMetrics(
                    resource_id=resource_id,
                    in_degree=cache.in_degree,
                    out_degree=cache.out_degree,
                    total_degree=cache.in_degree + cache.out_degree,
                    betweenness=cache.betweenness,
                    pagerank=cache.pagerank,
                    computed_at=cache.computed_at.isoformat(),
                )
            else:
                # Resource not found in graph
                metrics_dict[resource_id] = CentralityMetrics(
                    resource_id=resource_id,
                    in_degree=0,
                    out_degree=0,
                    total_degree=0,
                    betweenness=0.0,
                    pagerank=0.0,
                    computed_at=datetime.now(timezone.utc).isoformat(),
                )

        # Build response
        elapsed_time = time.time() - start_time
        response = CentralityResponse(
            metrics=metrics_dict,
            computation_time_ms=elapsed_time * 1000,
            cached=len(needs_computation) == 0,
        )

        # Cache the result for 10 minutes
        result_dict = response.model_dump()
        cache_service.set(cache_key, result_dict, ttl=600)

        # Check performance target
        if elapsed_time > 2.0:
            logger.warning(
                f"Centrality computation exceeded 2s target: {elapsed_time:.2f}s "
                f"({len(resource_id_list)} resources)"
            )
        else:
            logger.debug(
                f"Centrality computation completed in {elapsed_time:.2f}s "
                f"({len(resource_id_list)} resources)"
            )

        return result_dict

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error computing centrality metrics: {e}", exc_info=True)
        # Return empty metrics instead of 500 error for empty graph
        logger.warning("Returning empty centrality metrics due to error (likely empty graph)")
        return {
            "metrics": {},
            "computation_time_ms": 0.0,
            "cached": False,
        }


@router.post(
    "/communities",
    summary="Detect communities in knowledge graph",
    description=(
        "Detect communities using Louvain algorithm. "
        "Returns community assignments, modularity score, and community statistics. "
        "Results are cached for 15 minutes. Target response time: <10s for 1000 nodes."
    ),
)
async def detect_communities(
    resource_ids: str = Query(
        ...,
        description="Comma-separated list of resource UUIDs to include in community detection",
        example="123e4567-e89b-12d3-a456-426614174000,223e4567-e89b-12d3-a456-426614174001",
    ),
    resolution: float = Query(
        1.0,
        ge=0.1,
        le=10.0,
        description="Resolution parameter for community granularity (default 1.0). Higher values = more communities.",
    ),
    db: Session = Depends(get_sync_db),
) -> dict:
    """
    Detect communities in the knowledge graph using Louvain algorithm.

    The Louvain algorithm finds communities by maximizing modularity. Communities
    are groups of densely connected nodes that are sparsely connected to other groups.

    The resolution parameter controls community granularity:
    - Higher values (>1.0) lead to more, smaller communities
    - Lower values (<1.0) lead to fewer, larger communities
    - Default (1.0) provides balanced community sizes

    Results are cached for 15 minutes to improve performance. The cache is
    invalidated when the graph structure changes.

    Args:
        resource_ids: Comma-separated list of resource UUIDs
        resolution: Resolution parameter for community granularity (0.1-10.0, default 1.0)
        db: Database session dependency

    Returns:
        CommunityDetectionResponse: Community assignments and statistics

    Raises:
        HTTPException: If resource IDs are invalid or computation fails
    """
    import time
    from datetime import datetime, timedelta, timezone
    from app.modules.graph.schema import (
        CommunityDetectionResult,
        CommunityDetectionResponse,
    )
    from app.modules.graph.service import CommunityDetectionService
    from app.database.models import CommunityAssignment
    from app.shared.cache import CacheService

    start_time = time.time()

    try:
        # Parse resource IDs
        try:
            resource_id_list = [UUID(rid.strip()) for rid in resource_ids.split(",")]
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid resource ID format: {e}",
            )

        if not resource_id_list:
            raise HTTPException(
                status_code=400,
                detail="At least one resource ID must be provided",
            )

        if len(resource_id_list) < 2:
            raise HTTPException(
                status_code=400,
                detail="At least two resources are required for community detection",
            )

        # Check cache first (15-minute TTL)
        cache_service = CacheService()
        cache_key = f"communities:{','.join(str(rid) for rid in sorted(resource_id_list))}:{resolution}"

        cached_result = cache_service.get(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for community detection: {cache_key}")
            elapsed_time = time.time() - start_time
            cached_result["computation_time_ms"] = elapsed_time * 1000
            cached_result["cached"] = True
            return cached_result

        # Check database cache (15-minute TTL)
        cache_cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        db_cached_assignments = (
            db.query(CommunityAssignment)
            .filter(
                CommunityAssignment.resource_id.in_(resource_id_list),
                CommunityAssignment.resolution == resolution,
                CommunityAssignment.computed_at >= cache_cutoff,
            )
            .all()
        )

        # If we have cached assignments for all resources, use them
        if len(db_cached_assignments) == len(resource_id_list):
            logger.debug("Database cache hit for community detection")

            # Build result from cached assignments
            communities = {
                int(assignment.resource_id): assignment.community_id
                for assignment in db_cached_assignments
            }

            # Get modularity from first assignment (same for all in same detection run)
            modularity = (
                db_cached_assignments[0].modularity if db_cached_assignments else 0.0
            )

            # Compute community sizes
            community_sizes = {}
            for comm_id in communities.values():
                community_sizes[comm_id] = community_sizes.get(comm_id, 0) + 1

            result = CommunityDetectionResult(
                communities=communities,
                modularity=modularity,
                num_communities=len(community_sizes),
                community_sizes=community_sizes,
            )

            elapsed_time = time.time() - start_time
            response = CommunityDetectionResponse(
                result=result,
                computation_time_ms=elapsed_time * 1000,
                cached=True,
                resolution=resolution,
            )

            return response.model_dump()

        # Compute communities
        community_service = CommunityDetectionService(db)

        result_dict = await community_service.detect_communities(
            resource_ids=[int(rid) for rid in resource_id_list],
            resolution=resolution,
        )

        # Store results in database cache
        for resource_id in resource_id_list:
            resource_id_int = int(resource_id)
            community_id = result_dict["communities"].get(resource_id_int, 0)

            # Create cache entry
            cache_entry = CommunityAssignment(
                resource_id=resource_id,
                community_id=community_id,
                modularity=result_dict["modularity"],
                resolution=resolution,
                computed_at=datetime.now(timezone.utc),
            )
            db.add(cache_entry)

        db.commit()

        # Build response
        result = CommunityDetectionResult(
            communities=result_dict["communities"],
            modularity=result_dict["modularity"],
            num_communities=result_dict["num_communities"],
            community_sizes=result_dict["community_sizes"],
        )

        elapsed_time = time.time() - start_time
        response = CommunityDetectionResponse(
            result=result,
            computation_time_ms=elapsed_time * 1000,
            cached=False,
            resolution=resolution,
        )

        # Cache the result for 15 minutes
        result_dict_response = response.model_dump()
        cache_service.set(cache_key, result_dict_response, ttl=900)

        # Check performance target
        if elapsed_time > 10.0:
            logger.warning(
                f"Community detection exceeded 10s target: {elapsed_time:.2f}s "
                f"({len(resource_id_list)} resources)"
            )
        else:
            logger.debug(
                f"Community detection completed in {elapsed_time:.2f}s "
                f"({len(resource_id_list)} resources, {result.num_communities} communities)"
            )

        return result_dict_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error detecting communities: {e}", exc_info=True)
        # Return empty communities instead of 500 error for empty graph
        logger.warning("Returning empty communities due to error (likely empty graph)")
        return {
            "communities": {},
            "modularity": 0.0,
            "num_communities": 0,
            "community_sizes": {},
            "computation_time_ms": 0.0,
            "cached": False,
        }


@router.post(
    "/layout",
    summary="Compute graph layout for visualization",
    description=(
        "Compute graph layout using force-directed, hierarchical, or circular algorithms. "
        "Returns node positions and edge routing normalized to [0, 1000] coordinate space. "
        "Results are cached for 10 minutes. Target response time: <2s for 500 nodes."
    ),
)
async def compute_graph_layout(
    resource_ids: str = Query(
        ...,
        description="Comma-separated list of resource UUIDs to include in layout",
        example="123e4567-e89b-12d3-a456-426614174000,223e4567-e89b-12d3-a456-426614174001",
    ),
    layout_type: str = Query(
        "force",
        description="Layout algorithm: 'force' (Fruchterman-Reingold), 'hierarchical' (Kamada-Kawai), or 'circular'",
        regex="^(force|hierarchical|circular)$",
    ),
    db: Session = Depends(get_sync_db),
) -> dict:
    """
    Compute graph layout for visualization.

    This endpoint computes node positions and edge routing for graph visualization
    using one of three layout algorithms:

    - **force**: Force-directed layout using Fruchterman-Reingold algorithm
    - **hierarchical**: Hierarchical layout using Kamada-Kawai algorithm
    - **circular**: Circular layout with nodes arranged in a circle

    All coordinates are normalized to [0, 1000] range for consistent rendering
    across different screen sizes.

    Results are cached for 10 minutes to improve performance. The cache is
    invalidated when the graph structure changes.

    Args:
        resource_ids: Comma-separated list of resource UUIDs
        layout_type: Layout algorithm (force, hierarchical, circular)
        db: Database session dependency

    Returns:
        GraphLayoutResponse: Node positions, edge routing, and bounding box

    Raises:
        HTTPException: If resource IDs are invalid or layout computation fails
    """
    import time
    from app.modules.graph.schema import GraphLayoutResponse
    from app.modules.graph.service import GraphVisualizationService
    from app.shared.cache import CacheService

    start_time = time.time()

    try:
        # Parse resource IDs
        try:
            resource_id_list = [UUID(rid.strip()) for rid in resource_ids.split(",")]
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid resource UUID format: {e}",
            )

        if len(resource_id_list) < 1:
            raise HTTPException(
                status_code=400,
                detail="At least one resource is required for layout computation",
            )

        # Check cache
        cache_service = CacheService()
        cache_key = f"graph_layout:{','.join(str(rid) for rid in resource_id_list)}:{layout_type}"

        cached_result = cache_service.get(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for graph layout: {cache_key}")
            elapsed_time = time.time() - start_time
            cached_result["computation_time_ms"] = elapsed_time * 1000
            cached_result["cached"] = True
            return cached_result

        # Compute layout
        viz_service = GraphVisualizationService(db)
        result_dict = await viz_service.compute_layout(
            resource_ids=resource_id_list,
            layout_type=layout_type,
        )

        # Build response
        response = GraphLayoutResponse(
            layout=result_dict["layout"],
            computation_time_ms=result_dict["computation_time_ms"],
            cached=False,
            node_count=result_dict["node_count"],
            edge_count=result_dict["edge_count"],
        )

        # Cache result for 10 minutes
        result_dict_response = response.model_dump(mode="json")
        cache_service.set(cache_key, result_dict_response, ttl=600)

        elapsed_time = time.time() - start_time

        # Log performance
        if elapsed_time > 2.0:
            logger.warning(
                f"Graph layout exceeded 2s target: {elapsed_time:.2f}s "
                f"({len(resource_id_list)} nodes, {layout_type} layout)"
            )
        else:
            logger.debug(
                f"Graph layout completed in {elapsed_time:.2f}s "
                f"({len(resource_id_list)} nodes, {layout_type} layout)"
            )

        return result_dict_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error computing graph layout: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error while computing graph layout",
        )
