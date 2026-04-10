"""
Neo Alexandria 2.0 - Hybrid Knowledge Graph Service

Implements hybrid graph scoring that fuses vector similarity, shared canonical
subjects, and classification code matches to build a knowledge graph suitable
for mind map visualization and global overview analysis.

Related files:
- app/schemas/graph.py: Pydantic models for graph data structures
- app/config/settings.py: Graph configuration and weights
- app/database/models.py: Resource model with embeddings and metadata
- app/routers/graph.py: API endpoints using this service
"""

from __future__ import annotations

import logging
from typing import List, Optional, Set, Tuple
from uuid import UUID

# Import numpy with fallback for vector operations
try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.database import models as db_models
from app.modules.graph.schema import (
    GraphEdge,
    GraphEdgeDetails,
    GraphNode,
    KnowledgeGraph,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class NeighborCollection:
    """
    Encapsulates a collection of graph neighbors with validation and accessor methods.

    This class provides controlled access to neighbor data, ensuring that
    neighbors are properly validated and sorted before being accessed.
    """

    def __init__(self):
        """Initialize an empty neighbor collection."""
        self._neighbors: List[dict] = []

    def add_neighbor(self, neighbor: dict) -> None:
        """
        Add a neighbor to the collection with validation.

        Args:
            neighbor: Dictionary containing neighbor information

        Raises:
            ValueError: If neighbor data is invalid
        """
        # Validate required fields
        required_fields = ["resource_id", "hops", "path", "edge_types", "total_weight"]
        for field in required_fields:
            if field not in neighbor:
                raise ValueError(f"Neighbor missing required field: {field}")

        # Validate data types
        if not isinstance(neighbor["resource_id"], str):
            raise ValueError("resource_id must be a string")
        if not isinstance(neighbor["hops"], int) or neighbor["hops"] < 1:
            raise ValueError("hops must be a positive integer")
        if not isinstance(neighbor["path"], list) or len(neighbor["path"]) < 2:
            raise ValueError("path must be a list with at least 2 elements")
        if (
            not isinstance(neighbor["edge_types"], list)
            or len(neighbor["edge_types"]) < 1
        ):
            raise ValueError("edge_types must be a non-empty list")
        if not isinstance(neighbor["total_weight"], (int, float)):
            raise ValueError("total_weight must be a number")

        # Validate optional fields if present
        if "quality" in neighbor:
            if not isinstance(neighbor["quality"], (int, float)) or not (
                0 <= neighbor["quality"] <= 1
            ):
                raise ValueError("quality must be a number between 0 and 1")

        if "score" in neighbor:
            if not isinstance(neighbor["score"], (int, float)):
                raise ValueError("score must be a number")

        self._neighbors.append(neighbor)

    def remove_neighbor(self, resource_id: str) -> bool:
        """
        Remove a neighbor by resource ID.

        Args:
            resource_id: ID of the resource to remove

        Returns:
            bool: True if neighbor was removed, False if not found
        """
        original_length = len(self._neighbors)
        self._neighbors = [
            n for n in self._neighbors if n["resource_id"] != resource_id
        ]
        return len(self._neighbors) < original_length

    def get_neighbors(self) -> List[dict]:
        """
        Get a copy of all neighbors.

        Returns:
            List of neighbor dictionaries (copy to prevent external modification)
        """
        return self._neighbors.copy()

    def sort_by_weight(self, reverse: bool = True) -> None:
        """
        Sort neighbors by total_weight.

        Args:
            reverse: If True, sort in descending order (highest weight first)
        """
        self._neighbors.sort(key=lambda x: x.get("total_weight", 0), reverse=reverse)

    def apply_limit(self, limit: int) -> None:
        """
        Limit the number of neighbors in the collection.

        Args:
            limit: Maximum number of neighbors to keep

        Raises:
            ValueError: If limit is not positive
        """
        if limit < 1:
            raise ValueError("Limit must be a positive integer")
        self._neighbors = self._neighbors[:limit]

    def filter_by_min_weight(self, min_weight: float) -> None:
        """
        Filter neighbors by minimum weight threshold.

        Args:
            min_weight: Minimum total_weight threshold
        """
        self._neighbors = [
            n for n in self._neighbors if n.get("total_weight", 0) >= min_weight
        ]

    def filter_by_edge_types(self, edge_types: List[str]) -> None:
        """
        Filter neighbors by edge types.

        Args:
            edge_types: List of allowed edge types
        """
        if not edge_types:
            return

        filtered = []
        for neighbor in self._neighbors:
            neighbor_edge_types = neighbor.get("edge_types", [])
            # Keep neighbor if any of its edge types match the filter
            if any(et in edge_types for et in neighbor_edge_types):
                filtered.append(neighbor)

        self._neighbors = filtered

    def __len__(self) -> int:
        """Return the number of neighbors in the collection."""
        return len(self._neighbors)

    def __iter__(self):
        """Iterate over neighbors (returns copies to prevent modification)."""
        return iter(self._neighbors.copy())

    def is_empty(self) -> bool:
        """Check if the collection is empty."""
        return len(self._neighbors) == 0


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Compute cosine similarity between two vectors using NumPy.

    Formula: cos(θ) = (a · b) / (||a|| * ||b||)

    Args:
        vec_a: First vector as list of floats
        vec_b: Second vector as list of floats

    Returns:
        float: Cosine similarity in range [-1, 1], or 0.0 for zero vectors
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    if np is None:
        # Fallback to manual computation if numpy is not available
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        similarity = dot_product / (norm_a * norm_b)
        return max(-1.0, min(1.0, similarity))

    try:
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)

        # Check for zero vectors
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        # Compute cosine similarity
        dot_product = np.dot(a, b)
        similarity = dot_product / (norm_a * norm_b)

        # Ensure result is in valid range due to floating point precision
        return float(np.clip(similarity, -1.0, 1.0))

    except Exception as e:
        logger.warning(f"Error computing cosine similarity: {e}")
        return 0.0


def compute_tag_overlap_score(
    subjects_a: List[str], subjects_b: List[str]
) -> Tuple[float, List[str]]:
    """
    Compute shared canonical subjects score using diminishing returns heuristic.

    Score formula: min(1.0, 0.5 + (num_shared - 1) * 0.1)
    This gives:
    - 1 shared subject: 0.5
    - 2 shared subjects: 0.6
    - 3 shared subjects: 0.7
    - 6+ shared subjects: 1.0 (capped)

    Args:
        subjects_a: List of canonical subjects for first resource
        subjects_b: List of canonical subjects for second resource

    Returns:
        Tuple of (score, shared_subjects_list)
    """
    if not subjects_a or not subjects_b:
        return 0.0, []

    # Convert to sets for intersection, preserving case sensitivity
    set_a = set(subjects_a)
    set_b = set(subjects_b)
    shared = set_a.intersection(set_b)

    if not shared:
        return 0.0, []

    num_shared = len(shared)
    score = min(1.0, 0.5 + (num_shared - 1) * 0.1)
    shared_list = sorted(list(shared))  # Sort for consistent output

    return score, shared_list


def compute_classification_match_score(
    code_a: Optional[str], code_b: Optional[str]
) -> float:
    """
    Compute binary classification code match score.

    Args:
        code_a: Classification code for first resource
        code_b: Classification code for second resource

    Returns:
        float: 1.0 if codes match and are not None, else 0.0
    """
    if code_a is None or code_b is None:
        return 0.0
    return 1.0 if code_a == code_b else 0.0


def compute_hybrid_weight(
    vector_score: float,
    tag_score: float,
    classification_score: float,
    vector_weight: float = None,
    tag_weight: float = None,
    classification_weight: float = None,
) -> float:
    """
    Compute hybrid weight by fusing vector, tag, and classification scores.

    Normalizes vector score to [0,1] range by clamping negative values to 0,
    then combines all scores using weighted sum.

    Args:
        vector_score: Cosine similarity score in [-1, 1]
        tag_score: Tag overlap score in [0, 1]
        classification_score: Classification match score in {0, 1}
        vector_weight: Weight for vector component (uses settings default if None)
        tag_weight: Weight for tag component (uses settings default if None)
        classification_weight: Weight for classification component (uses settings default if None)

    Returns:
        float: Combined hybrid weight in [0, 1]
    """
    # Use settings defaults if weights not provided
    if vector_weight is None:
        vector_weight = settings.GRAPH_WEIGHT_VECTOR
    if tag_weight is None:
        tag_weight = settings.GRAPH_WEIGHT_TAGS
    if classification_weight is None:
        classification_weight = settings.GRAPH_WEIGHT_CLASSIFICATION

    # Normalize vector score to [0, 1] range by clamping negative values
    normalized_vector_score = max(0.0, vector_score)

    # Compute weighted sum
    hybrid_weight = (
        vector_weight * normalized_vector_score
        + tag_weight * tag_score
        + classification_weight * classification_score
    )

    # Ensure result is in [0, 1] range
    return max(0.0, min(1.0, hybrid_weight))


def _gather_vector_candidates(
    db: Session,
    source_resource: db_models.Resource,
    limit: int,
) -> Set[UUID]:
    """
    Gather candidate resources based on vector similarity.

    Args:
        db: Database session
        source_resource: Source resource with embedding
        limit: Maximum number of candidates to gather

    Returns:
        Set of candidate resource IDs
    """
    candidate_ids: Set[UUID] = set()

    if source_resource.embedding:
        vector_candidates = (
            db.query(db_models.Resource)
            .filter(
                db_models.Resource.id != source_resource.id,
                db_models.Resource.embedding.isnot(None),
                func.json_array_length(db_models.Resource.embedding) > 0,
            )
            .limit(limit * 2)
            .all()
        )

        for candidate in vector_candidates:
            if candidate.embedding:
                candidate_ids.add(candidate.id)

    return candidate_ids


def _gather_subject_candidates(
    db: Session,
    source_resource: db_models.Resource,
) -> Set[UUID]:
    """
    Gather candidate resources based on shared subjects.

    Args:
        db: Database session
        source_resource: Source resource with subjects

    Returns:
        Set of candidate resource IDs
    """
    candidate_ids: Set[UUID] = set()

    if source_resource.subject:
        subject_conditions = []
        for subject in source_resource.subject:
            subject_conditions.append(
                func.lower(
                    func.cast(db_models.Resource.subject, db_models.String)
                ).like(f"%{subject.lower()}%")
            )

        if subject_conditions:
            shared_subject_candidates = (
                db.query(db_models.Resource)
                .filter(
                    db_models.Resource.id != source_resource.id,
                    or_(*subject_conditions),
                )
                .all()
            )

            for candidate in shared_subject_candidates:
                candidate_ids.add(candidate.id)

    return candidate_ids


def _gather_classification_candidates(
    db: Session,
    source_resource: db_models.Resource,
) -> Set[UUID]:
    """
    Gather candidate resources based on classification code match.

    Args:
        db: Database session
        source_resource: Source resource with classification code

    Returns:
        Set of candidate resource IDs
    """
    candidate_ids: Set[UUID] = set()

    if source_resource.classification_code:
        classification_candidates = (
            db.query(db_models.Resource)
            .filter(
                db_models.Resource.id != source_resource.id,
                db_models.Resource.classification_code
                == source_resource.classification_code,
            )
            .all()
        )

        for candidate in classification_candidates:
            candidate_ids.add(candidate.id)

    return candidate_ids


def _score_candidate(
    source_resource: db_models.Resource,
    candidate: db_models.Resource,
) -> Tuple[float, GraphEdgeDetails]:
    """
    Score a single candidate resource against the source.

    Computes vector similarity, tag overlap, and classification match scores,
    then combines them into a hybrid weight.

    Args:
        source_resource: Source resource
        candidate: Candidate resource to score

    Returns:
        Tuple of (hybrid_weight, edge_details)
    """
    # Vector similarity score
    vector_score = 0.0
    if source_resource.embedding and candidate.embedding:
        vector_score = cosine_similarity(source_resource.embedding, candidate.embedding)

    # Tag overlap score
    tag_score, shared_subjects = compute_tag_overlap_score(
        source_resource.subject or [], candidate.subject or []
    )

    # Classification match score
    classification_score = compute_classification_match_score(
        source_resource.classification_code, candidate.classification_code
    )

    # Compute hybrid weight
    hybrid_weight = compute_hybrid_weight(vector_score, tag_score, classification_score)

    # Determine primary connection type
    if classification_score > 0:
        connection_type = "classification"
    elif tag_score > 0:
        connection_type = "topical"
    else:
        connection_type = "semantic"

    # Create edge details
    edge_details = GraphEdgeDetails(
        connection_type=connection_type,
        vector_similarity=vector_score if vector_score > 0 else None,
        shared_subjects=shared_subjects,
    )

    return hybrid_weight, edge_details


def _build_knowledge_graph_from_scored_candidates(
    source_resource: db_models.Resource,
    scored_candidates: List[Tuple[db_models.Resource, float, GraphEdgeDetails]],
) -> KnowledgeGraph:
    """
    Build knowledge graph from scored candidates.

    Args:
        source_resource: Source resource
        scored_candidates: List of (candidate, weight, details) tuples

    Returns:
        KnowledgeGraph with nodes and edges
    """
    nodes = [
        GraphNode(
            id=source_resource.id,
            title=source_resource.title,
            type=source_resource.type,
            classification_code=source_resource.classification_code,
        )
    ]

    edges = []

    for candidate, weight, details in scored_candidates:
        candidate_node = GraphNode(
            id=candidate.id,
            title=candidate.title,
            type=candidate.type,
            classification_code=candidate.classification_code,
        )
        nodes.append(candidate_node)

        edge = GraphEdge(
            source=source_resource.id,
            target=candidate.id,
            weight=weight,
            details=details,
        )
        edges.append(edge)

    return KnowledgeGraph(nodes=nodes, edges=edges)


def find_hybrid_neighbors(
    db: Session,
    source_resource_id: UUID,
    limit: Optional[int] = None,
) -> KnowledgeGraph:
    """
    Find hybrid-scored neighbors for a given resource.

    Gathers candidates from vector similarity, shared subjects, and classification
    matches, then scores and ranks them using the hybrid weighting scheme.

    Args:
        db: Database session
        source_resource_id: UUID of the source resource
        limit: Maximum number of neighbors to return (uses setting default if None)

    Returns:
        KnowledgeGraph: Graph with source node and its top neighbors
    """
    if limit is None:
        limit = settings.DEFAULT_GRAPH_NEIGHBORS

    # Load source resource
    source_resource = (
        db.query(db_models.Resource)
        .filter(db_models.Resource.id == source_resource_id)
        .first()
    )

    if not source_resource:
        return KnowledgeGraph(nodes=[], edges=[])

    # Gather candidates from multiple sources
    candidate_ids: Set[UUID] = set()
    candidate_ids.update(_gather_vector_candidates(db, source_resource, limit))
    candidate_ids.update(_gather_subject_candidates(db, source_resource))
    candidate_ids.update(_gather_classification_candidates(db, source_resource))

    # Return early if no candidates found
    if not candidate_ids:
        source_node = GraphNode(
            id=source_resource.id,
            title=source_resource.title,
            type=source_resource.type,
            classification_code=source_resource.classification_code,
        )
        return KnowledgeGraph(nodes=[source_node], edges=[])

    # Load all candidates
    candidates = (
        db.query(db_models.Resource)
        .filter(db_models.Resource.id.in_(candidate_ids))
        .all()
    )

    # Score all candidates
    scored_candidates: List[Tuple[db_models.Resource, float, GraphEdgeDetails]] = []
    for candidate in candidates:
        hybrid_weight, edge_details = _score_candidate(source_resource, candidate)
        scored_candidates.append((candidate, hybrid_weight, edge_details))

    # Sort by hybrid weight (descending) and take top limit
    scored_candidates.sort(key=lambda x: x[1], reverse=True)
    top_candidates = scored_candidates[:limit]

    # Build and return knowledge graph
    return _build_knowledge_graph_from_scored_candidates(
        source_resource, top_candidates
    )


def _find_high_vector_similarity_pairs(
    resources: List[db_models.Resource],
    vector_threshold: float,
) -> Set[Tuple[UUID, UUID]]:
    """
    Find resource pairs with high vector similarity.

    Args:
        resources: List of resources to compare
        vector_threshold: Minimum similarity threshold

    Returns:
        Set of resource ID pairs (ordered with smaller UUID first)
    """
    candidate_pairs: Set[Tuple[UUID, UUID]] = set()

    for i, res_a in enumerate(resources):
        if not res_a.embedding:
            continue

        for j, res_b in enumerate(resources[i + 1 :], i + 1):
            if not res_b.embedding:
                continue

            vector_sim = cosine_similarity(res_a.embedding, res_b.embedding)
            if vector_sim >= vector_threshold:
                pair = (
                    (res_a.id, res_b.id)
                    if res_a.id < res_b.id
                    else (res_b.id, res_a.id)
                )
                candidate_pairs.add(pair)

    return candidate_pairs


def _find_high_tag_overlap_pairs(
    resources: List[db_models.Resource],
    limit: int,
) -> Set[Tuple[UUID, UUID]]:
    """
    Find resource pairs with high tag overlap.

    Args:
        resources: List of resources to compare
        limit: Maximum number of pairs to return

    Returns:
        Set of resource ID pairs (ordered with smaller UUID first)
    """
    tag_pairs: List[Tuple[Tuple[UUID, UUID], int]] = []

    for i, res_a in enumerate(resources):
        if not res_a.subject:
            continue

        for j, res_b in enumerate(resources[i + 1 :], i + 1):
            if not res_b.subject:
                continue

            _, shared_subjects = compute_tag_overlap_score(res_a.subject, res_b.subject)
            if shared_subjects:
                pair = (
                    (res_a.id, res_b.id)
                    if res_a.id < res_b.id
                    else (res_b.id, res_a.id)
                )
                tag_pairs.append((pair, len(shared_subjects)))

    # Sort by shared count and take top limit
    tag_pairs.sort(key=lambda x: x[1], reverse=True)
    top_tag_pairs = tag_pairs[:limit]

    return {pair for pair, _ in top_tag_pairs}


def _score_resource_pair(
    res_a: db_models.Resource,
    res_b: db_models.Resource,
) -> Tuple[float, GraphEdgeDetails]:
    """
    Score a pair of resources for global overview.

    Args:
        res_a: First resource
        res_b: Second resource

    Returns:
        Tuple of (hybrid_weight, edge_details)
    """
    # Vector similarity score
    vector_score = 0.0
    if res_a.embedding and res_b.embedding:
        vector_score = cosine_similarity(res_a.embedding, res_b.embedding)

    # Tag overlap score
    tag_score, shared_subjects = compute_tag_overlap_score(
        res_a.subject or [], res_b.subject or []
    )

    # Classification match score
    classification_score = compute_classification_match_score(
        res_a.classification_code, res_b.classification_code
    )

    # Compute hybrid weight
    hybrid_weight = compute_hybrid_weight(vector_score, tag_score, classification_score)

    # Determine primary connection type
    if classification_score > 0:
        connection_type = "classification"
    elif tag_score > 0:
        connection_type = "topical"
    else:
        connection_type = "semantic"

    # Create edge details
    edge_details = GraphEdgeDetails(
        connection_type=connection_type,
        vector_similarity=vector_score if vector_score > 0 else None,
        shared_subjects=shared_subjects,
    )

    return hybrid_weight, edge_details


def _build_global_graph_from_pairs(
    scored_pairs: List[Tuple[Tuple[UUID, UUID], float, GraphEdgeDetails]],
    resources_by_id: dict,
) -> KnowledgeGraph:
    """
    Build knowledge graph from scored resource pairs.

    Args:
        scored_pairs: List of (pair, weight, details) tuples
        resources_by_id: Dictionary mapping resource IDs to resources

    Returns:
        KnowledgeGraph with nodes and edges
    """
    involved_node_ids = set()
    edges = []

    for pair, weight, details in scored_pairs:
        source_id, target_id = pair
        involved_node_ids.add(source_id)
        involved_node_ids.add(target_id)

        edge = GraphEdge(
            source=source_id,
            target=target_id,
            weight=weight,
            details=details,
        )
        edges.append(edge)

    # Create nodes for all involved resources
    nodes = []
    for res_id in involved_node_ids:
        res = resources_by_id.get(res_id)
        if res:
            node = GraphNode(
                id=res.id,
                title=res.title,
                type=res.type,
                classification_code=res.classification_code,
            )
            nodes.append(node)

    return KnowledgeGraph(nodes=nodes, edges=edges)


def generate_global_overview(
    db: Session,
    limit: Optional[int] = None,
    vector_threshold: Optional[float] = None,
) -> KnowledgeGraph:
    """
    Generate global overview of strongest connections across the library.

    Finds the most significant relationships by combining high vector similarity
    pairs and high tag overlap pairs, then selecting the top hybrid-weighted edges.

    Args:
        db: Database session
        limit: Maximum number of edges to return (uses setting default if None)
        vector_threshold: Minimum vector similarity for candidate pairs

    Returns:
        KnowledgeGraph: Graph with strongest global connections
    """
    if limit is None:
        limit = settings.GRAPH_OVERVIEW_MAX_EDGES
    if vector_threshold is None:
        vector_threshold = settings.GRAPH_VECTOR_MIN_SIM_THRESHOLD

    # Load all resources with embeddings and subjects
    resources = (
        db.query(db_models.Resource)
        .filter(
            or_(
                db_models.Resource.embedding.isnot(None),
                func.json_array_length(db_models.Resource.subject) > 0,
            )
        )
        .all()
    )

    if len(resources) < 2:
        return KnowledgeGraph(nodes=[], edges=[])

    # Gather candidate pairs from multiple sources
    candidate_pairs: Set[Tuple[UUID, UUID]] = set()
    candidate_pairs.update(
        _find_high_vector_similarity_pairs(resources, vector_threshold)
    )
    candidate_pairs.update(_find_high_tag_overlap_pairs(resources, limit))

    # Score all candidate pairs
    resources_by_id = {res.id: res for res in resources}
    scored_pairs: List[Tuple[Tuple[UUID, UUID], float, GraphEdgeDetails]] = []

    for pair in candidate_pairs:
        res_a_id, res_b_id = pair
        res_a = resources_by_id.get(res_a_id)
        res_b = resources_by_id.get(res_b_id)

        if not res_a or not res_b:
            continue

        hybrid_weight, edge_details = _score_resource_pair(res_a, res_b)

        # Skip pairs with very low weights
        if hybrid_weight < 0.1:
            continue

        scored_pairs.append((pair, hybrid_weight, edge_details))

    # Sort by hybrid weight and take top limit
    scored_pairs.sort(key=lambda x: x[1], reverse=True)
    top_pairs = scored_pairs[:limit]

    # Build and return knowledge graph
    return _build_global_graph_from_pairs(top_pairs, resources_by_id)


class GraphService:
    """Service for multi-layer graph construction and neighbor discovery."""

    def __init__(self, db: Session):
        self.db = db
        self._graph_cache = None
        self._cache_timestamp = None

    def _has_cached_graph(self) -> bool:
        """
        Check if a cached graph exists.

        Returns:
            bool: True if graph cache is available
        """
        return self._graph_cache is not None

    def _get_cached_graph(self):
        """
        Get the cached graph.

        Returns:
            NetworkX graph or dict-based graph structure

        Raises:
            ValueError: If no cached graph exists
        """
        if not self._has_cached_graph():
            raise ValueError(
                "No cached graph available. Call build_multilayer_graph() first."
            )
        return self._graph_cache

    def _set_cached_graph(self, graph) -> None:
        """
        Set the cached graph and update timestamp.

        Args:
            graph: NetworkX graph or dict-based graph structure to cache
        """
        self._graph_cache = graph
        from datetime import datetime, timezone

        self._cache_timestamp = datetime.now(timezone.utc)

    def _clear_cache(self) -> None:
        """Clear the graph cache and timestamp."""
        self._graph_cache = None
        self._cache_timestamp = None

    def get_cache_timestamp(self):
        """
        Get the timestamp of the cached graph.

        Returns:
            datetime or None: Timestamp when graph was cached, or None if no cache
        """
        return self._cache_timestamp

    def build_multilayer_graph(self, refresh_cache: bool = False):
        """
        Build multi-layer graph with citation, coauthorship, subject, and temporal edges.

        Args:
            refresh_cache: If True, rebuild graph even if cache exists

        Returns:
            NetworkX MultiGraph object or dict-based graph structure
        """
        try:
            import networkx as nx
        except ImportError:
            # Return a simple dict-based graph structure if networkx not available
            return {"nodes": [], "edges": []}

        # Check cache
        if not refresh_cache and self._has_cached_graph():
            return self._get_cached_graph()

        G = nx.MultiGraph()

        # Add all resources as nodes
        from app.database.models import Resource, Citation, GraphEdge

        resources = self.db.query(Resource).all()

        for resource in resources:
            G.add_node(
                str(resource.id),
                title=resource.title,
                type=resource.type,
                quality_overall=resource.quality_overall
                if hasattr(resource, "quality_overall")
                else 0.5,
            )

        # Add citation edges from Citation table
        citations = (
            self.db.query(Citation)
            .filter(Citation.target_resource_id.isnot(None))
            .all()
        )

        for citation in citations:
            G.add_edge(
                str(citation.source_resource_id),
                str(citation.target_resource_id),
                edge_type="citation",
                weight=1.0,
                key="citation",
            )

        # Add edges from GraphEdge table
        graph_edges = self.db.query(GraphEdge).all()
        for edge in graph_edges:
            G.add_edge(
                str(edge.source_id),
                str(edge.target_id),
                edge_type=edge.edge_type,
                weight=edge.weight,
                key=edge.edge_type,
            )

        # Cache the graph using accessor method
        self._set_cached_graph(G)

        return G

    def _get_one_hop_neighbors(
        self,
        G,
        resource_id: str,
        edge_types: Optional[List[str]],
        min_weight: float,
    ) -> NeighborCollection:
        """
        Get direct (1-hop) neighbors from graph.

        Args:
            G: NetworkX graph
            resource_id: Source resource ID
            edge_types: Filter by edge types
            min_weight: Minimum edge weight threshold

        Returns:
            NeighborCollection containing neighbor data
        """
        collection = NeighborCollection()

        for neighbor in G.neighbors(resource_id):
            edge_data = G.get_edge_data(resource_id, neighbor)

            for key, data in edge_data.items():
                edge_type = data.get("edge_type", "unknown")
                weight = data.get("weight", 1.0)

                # Apply filters
                if edge_types and edge_type not in edge_types:
                    continue
                if weight < min_weight:
                    continue

                # Get neighbor node data for quality score
                neighbor_node_data = G.nodes.get(neighbor, {})
                quality = neighbor_node_data.get("quality_overall", 0.5)

                neighbor_data = {
                    "resource_id": neighbor,
                    "hops": 1,
                    "distance": 1,  # Alias for hops for backward compatibility
                    "path": [resource_id, neighbor],
                    "edge_types": [edge_type],
                    "total_weight": weight,
                    "path_strength": weight,  # For 1-hop, path_strength equals weight
                    "edge_type": edge_type,
                    "weight": weight,
                    "intermediate": None,  # No intermediate node for 1-hop
                    "quality": quality,
                    "novelty": 0.5,  # Default novelty score
                    "score": weight * quality,  # Combined score
                }
                collection.add_neighbor(neighbor_data)

        return collection

    def _get_two_hop_neighbors(
        self,
        G,
        resource_id: str,
        edge_types: Optional[List[str]],
        min_weight: float,
    ) -> NeighborCollection:
        """
        Get 2-hop neighbors from graph.

        Args:
            G: NetworkX graph
            resource_id: Source resource ID
            edge_types: Filter by edge types
            min_weight: Minimum edge weight threshold

        Returns:
            NeighborCollection containing neighbor data
        """
        collection = NeighborCollection()
        visited = {resource_id}

        for neighbor1 in G.neighbors(resource_id):
            if neighbor1 in visited:
                continue

            edge_data_1 = G.get_edge_data(resource_id, neighbor1)

            for key1, data1 in edge_data_1.items():
                edge_type_1 = data1.get("edge_type", "unknown")
                weight_1 = data1.get("weight", 1.0)

                if edge_types and edge_type_1 not in edge_types:
                    continue
                if weight_1 < min_weight:
                    continue

                # Explore second hop
                for neighbor2 in G.neighbors(neighbor1):
                    if neighbor2 == resource_id or neighbor2 in visited:
                        continue

                    edge_data_2 = G.get_edge_data(neighbor1, neighbor2)

                    for key2, data2 in edge_data_2.items():
                        edge_type_2 = data2.get("edge_type", "unknown")
                        weight_2 = data2.get("weight", 1.0)

                        if edge_types and edge_type_2 not in edge_types:
                            continue
                        if weight_2 < min_weight:
                            continue

                        total_weight = weight_1 * weight_2

                        # Get neighbor node data for quality score
                        neighbor_node_data = G.nodes.get(neighbor2, {})
                        quality = neighbor_node_data.get("quality_overall", 0.5)

                        neighbor_data = {
                            "resource_id": neighbor2,
                            "hops": 2,
                            "distance": 2,  # Alias for hops for backward compatibility
                            "path": [resource_id, neighbor1, neighbor2],
                            "edge_types": [edge_type_1, edge_type_2],
                            "total_weight": total_weight,
                            "path_strength": total_weight,  # Product of edge weights
                            "intermediate_nodes": [neighbor1],
                            "intermediate": neighbor1,  # Single intermediate for 2-hop
                            "quality": quality,
                            "novelty": 0.5,  # Default novelty score
                            "score": total_weight * quality,  # Combined score
                        }
                        collection.add_neighbor(neighbor_data)

        return collection

    def get_neighbors_multihop(
        self,
        resource_id: str,
        hops: int = 1,
        edge_types: Optional[List[str]] = None,
        min_weight: float = 0.0,
        limit: Optional[int] = None,
    ) -> List[dict]:
        """
        Get multi-hop neighbors with filtering and ranking.

        Args:
            resource_id: Source resource ID
            hops: Number of hops (1 or 2)
            edge_types: Filter by edge types (e.g., ['citation', 'coauthorship'])
            min_weight: Minimum edge weight threshold
            limit: Maximum number of neighbors to return

        Returns:
            List of neighbor dictionaries with paths and scores
        """
        G = self.build_multilayer_graph()

        if not G.has_node(resource_id):
            return []

        # Get neighbors based on hop count using encapsulated collection
        if hops == 1:
            collection = self._get_one_hop_neighbors(
                G, resource_id, edge_types, min_weight
            )
        elif hops == 2:
            collection = self._get_two_hop_neighbors(
                G, resource_id, edge_types, min_weight
            )
        else:
            collection = NeighborCollection()

        # Sort by total_weight descending
        collection.sort_by_weight(reverse=True)

        # Apply limit
        if limit:
            collection.apply_limit(limit)

        return collection.get_neighbors()

    async def compute_degree_centrality(
        self, resource_ids: List[int]
    ) -> dict[int, dict]:
        """
        Compute degree centrality for specified resources.

        Degree centrality measures the number of direct connections a node has.
        Returns both in-degree (incoming edges) and out-degree (outgoing edges).

        Args:
            resource_ids: List of resource IDs to compute centrality for

        Returns:
            Dictionary mapping resource_id to centrality metrics:
            {
                resource_id: {
                    "in_degree": int,
                    "out_degree": int,
                    "total_degree": int
                }
            }
        """
        try:
            import networkx as nx
        except ImportError:
            logger.error("NetworkX not installed, cannot compute centrality")
            return {}

        # Build graph
        G = self.build_multilayer_graph()

        # Convert to directed graph for in/out degree calculation
        DG = nx.DiGraph()
        for u, v, data in G.edges(data=True):
            DG.add_edge(u, v, **data)

        results = {}
        for resource_id in resource_ids:
            resource_id_str = str(resource_id)
            if not DG.has_node(resource_id_str):
                results[resource_id] = {
                    "in_degree": 0,
                    "out_degree": 0,
                    "total_degree": 0,
                }
                continue

            in_degree = DG.in_degree(resource_id_str)
            out_degree = DG.out_degree(resource_id_str)

            results[resource_id] = {
                "in_degree": in_degree,
                "out_degree": out_degree,
                "total_degree": in_degree + out_degree,
            }

        return results

    async def compute_betweenness_centrality(
        self, resource_ids: List[int]
    ) -> dict[int, float]:
        """
        Compute betweenness centrality for specified resources.

        Betweenness centrality measures how often a node appears on shortest
        paths between other nodes. High betweenness indicates a node that
        bridges different parts of the graph.

        Args:
            resource_ids: List of resource IDs to compute centrality for

        Returns:
            Dictionary mapping resource_id to betweenness centrality score (0-1)
        """
        try:
            import networkx as nx
        except ImportError:
            logger.error("NetworkX not installed, cannot compute centrality")
            return {}

        # Build graph
        G = self.build_multilayer_graph()

        # Compute betweenness centrality for all nodes
        betweenness = nx.betweenness_centrality(G, weight="weight")

        # Extract results for requested resources
        results = {}
        for resource_id in resource_ids:
            resource_id_str = str(resource_id)
            results[resource_id] = betweenness.get(resource_id_str, 0.0)

        return results

    async def compute_pagerank(
        self, resource_ids: List[int], damping_factor: float = 0.85
    ) -> dict[int, float]:
        """
        Compute PageRank centrality for specified resources.

        PageRank measures the importance of nodes based on the structure of
        incoming links. Originally developed for ranking web pages, it's
        useful for identifying influential nodes in citation networks.

        Args:
            resource_ids: List of resource IDs to compute centrality for
            damping_factor: Probability of following a link (default 0.85)

        Returns:
            Dictionary mapping resource_id to PageRank score
        """
        try:
            import networkx as nx
        except ImportError:
            logger.error("NetworkX not installed, cannot compute centrality")
            return {}

        # Validate damping factor
        if not 0 < damping_factor < 1:
            logger.warning(
                f"Invalid damping factor {damping_factor}, using default 0.85"
            )
            damping_factor = 0.85

        # Build graph
        G = self.build_multilayer_graph()

        # Convert to directed graph for PageRank
        DG = nx.DiGraph()
        for u, v, data in G.edges(data=True):
            weight = data.get("weight", 1.0)
            DG.add_edge(u, v, weight=weight)

        # Compute PageRank for all nodes
        try:
            pagerank = nx.pagerank(DG, alpha=damping_factor, weight="weight")
        except Exception as e:
            logger.error(f"Error computing PageRank: {e}")
            return {resource_id: 0.0 for resource_id in resource_ids}

        # Extract results for requested resources
        results = {}
        for resource_id in resource_ids:
            resource_id_str = str(resource_id)
            results[resource_id] = pagerank.get(resource_id_str, 0.0)

        return results


class CommunityDetectionService:
    """
    Service for detecting communities in knowledge graphs using Louvain algorithm.

    Communities are clusters of densely connected nodes that are sparsely connected
    to other clusters. This service helps identify thematic groups in the knowledge graph.
    """

    def __init__(self, db: Session):
        """
        Initialize the community detection service.

        Args:
            db: Database session
        """
        self.db = db
        logger.info("CommunityDetectionService initialized")

    async def detect_communities(
        self, resource_ids: List[int], resolution: float = 1.0
    ) -> dict:
        """
        Detect communities in the graph using Louvain algorithm.

        The Louvain algorithm is a greedy optimization method that maximizes
        modularity to find communities. Higher resolution values lead to more
        (smaller) communities, while lower values lead to fewer (larger) communities.

        Args:
            resource_ids: List of resource IDs to include in community detection
            resolution: Resolution parameter for community granularity (default 1.0)
                       Higher values = more communities, lower values = fewer communities

        Returns:
            Dictionary with:
            {
                "communities": {resource_id: community_id, ...},
                "modularity": float,
                "num_communities": int,
                "community_sizes": {community_id: size, ...}
            }
        """
        try:
            import networkx as nx
            import community as community_louvain
        except ImportError as e:
            logger.error(f"Required library not installed: {e}")
            logger.error("Install with: pip install python-louvain")
            return {
                "communities": {},
                "modularity": 0.0,
                "num_communities": 0,
                "community_sizes": {},
            }

        # Build a fresh graph with only the requested resources
        # This avoids cache issues and ensures we have the latest data
        from app.database.models import Resource, GraphEdge
        import uuid

        # Convert resource_ids to UUID objects
        resource_uuids = []
        for rid in resource_ids:
            if isinstance(rid, uuid.UUID):
                resource_uuids.append(rid)
            elif isinstance(rid, str):
                try:
                    resource_uuids.append(uuid.UUID(rid))
                except ValueError:
                    logger.warning(f"Invalid UUID string: {rid}")
                    continue
            elif isinstance(rid, int):
                # For backwards compatibility with tests that pass ints
                # We'll just skip these since UUIDs can't be converted from ints
                logger.warning(f"Cannot convert integer {rid} to UUID, skipping")
                continue
            else:
                logger.warning(f"Unknown resource ID type: {type(rid)}")
                continue

        if len(resource_uuids) < 2:
            logger.warning(
                f"Not enough valid resource UUIDs: {len(resource_uuids)} of {len(resource_ids)} requested"
            )
            return {
                "communities": {},
                "modularity": 0.0,
                "num_communities": 0,
                "community_sizes": {},
            }

        # Query requested resources to ensure they exist
        resources = (
            self.db.query(Resource).filter(Resource.id.in_(resource_uuids)).all()
        )

        if len(resources) < 2:
            logger.warning(
                f"Not enough resources found in database: {len(resources)} of {len(resource_ids)} requested"
            )
            return {
                "communities": {rid: 0 for rid in resource_ids},
                "modularity": 0.0,
                "num_communities": 1 if resources else 0,
                "community_sizes": {0: len(resources)} if resources else {},
            }

        # Create graph with requested resources
        G = nx.MultiGraph()
        resource_id_strs = [str(r.id) for r in resources]

        # Add nodes
        for resource in resources:
            G.add_node(
                str(resource.id),
                title=resource.title,
                type=resource.type,
            )

        # Add edges between requested resources
        edges = (
            self.db.query(GraphEdge)
            .filter(
                GraphEdge.source_id.in_(resource_id_strs),
                GraphEdge.target_id.in_(resource_id_strs),
            )
            .all()
        )

        for edge in edges:
            G.add_edge(
                str(edge.source_id),
                str(edge.target_id),
                edge_type=edge.edge_type,
                weight=edge.weight,
            )

        if len(G.nodes()) < 2:
            logger.warning(f"Not enough nodes in subgraph: {len(G.nodes())}")
            return {
                "communities": {n: 0 for n in G.nodes()},
                "modularity": 0.0,
                "num_communities": 1 if G.nodes() else 0,
                "community_sizes": {0: len(G.nodes())} if G.nodes() else {},
            }

        # Convert to simple graph (Louvain requires undirected, no multi-edges)
        simple_graph = nx.Graph()
        for u, v, data in G.edges(data=True):
            weight = data.get("weight", 1.0)
            if simple_graph.has_edge(u, v):
                # Combine weights for multi-edges
                simple_graph[u][v]["weight"] += weight
            else:
                simple_graph.add_edge(u, v, weight=weight)

        # Add isolated nodes
        for node in G.nodes():
            if node not in simple_graph:
                simple_graph.add_node(node)

        # Run Louvain community detection
        try:
            partition = community_louvain.best_partition(
                simple_graph, weight="weight", resolution=resolution
            )

            # Compute modularity
            modularity = community_louvain.modularity(
                partition, simple_graph, weight="weight"
            )
        except Exception as e:
            logger.error(f"Error in Louvain algorithm: {e}")
            # Return single community as fallback
            return {
                "communities": {n: 0 for n in G.nodes()},
                "modularity": 0.0,
                "num_communities": 1,
                "community_sizes": {0: len(G.nodes())},
            }

        # Convert partition - keep node IDs as strings (matching graph node format)
        communities = {node: comm_id for node, comm_id in partition.items()}

        # Compute community sizes
        community_sizes = {}
        for comm_id in communities.values():
            community_sizes[comm_id] = community_sizes.get(comm_id, 0) + 1

        num_communities = len(community_sizes)

        logger.info(
            f"Detected {num_communities} communities with modularity {modularity:.3f} "
            f"(resolution={resolution})"
        )

        return {
            "communities": communities,
            "modularity": modularity,
            "num_communities": num_communities,
            "community_sizes": community_sizes,
        }


# Graph Extraction Service for Advanced RAG
class GraphExtractionService:
    """
    Service for extracting entities and relationships from document chunks.

    Supports multiple extraction methods:
    - llm: Use LLM for entity and relationship extraction
    - spacy: Use spaCy NER for entity extraction
    - hybrid: Combine LLM and spaCy approaches

    Extracted entities and relationships are stored in the knowledge graph
    with provenance links back to source chunks.
    """

    def __init__(self, db: Session, ai_service=None, extraction_method: str = "llm"):
        """
        Initialize the graph extraction service.

        Args:
            db: Database session
            ai_service: AI service for LLM-based extraction (optional)
            extraction_method: Extraction method ("llm", "spacy", or "hybrid")
        """
        self.db = db
        self.ai_service = ai_service
        self.extraction_method = extraction_method

        # Entity type mapping for classification
        self.entity_types = ["Concept", "Person", "Organization", "Method"]

        # Relation type mapping
        self.relation_types = ["CONTRADICTS", "SUPPORTS", "EXTENDS", "CITES"]

        logger.info(
            f"GraphExtractionService initialized with method: {extraction_method}"
        )

    def extract_entities(self, chunk_content: str) -> List[dict]:
        """
        Extract named entities from chunk content.

        Uses the configured extraction method to identify entities and classify
        their types (Concept, Person, Organization, Method).

        Args:
            chunk_content: Text content to extract entities from

        Returns:
            List of entity dictionaries with 'name', 'type', and 'description' keys
        """
        if not chunk_content or not chunk_content.strip():
            return []

        if self.extraction_method == "llm":
            return self._extract_entities_llm(chunk_content)
        elif self.extraction_method == "spacy":
            return self._extract_entities_spacy(chunk_content)
        elif self.extraction_method == "hybrid":
            # Combine both methods and deduplicate
            llm_entities = self._extract_entities_llm(chunk_content)
            spacy_entities = self._extract_entities_spacy(chunk_content)
            return self._deduplicate_entities(llm_entities + spacy_entities)
        else:
            logger.warning(f"Unknown extraction method: {self.extraction_method}")
            return []

    def _extract_entities_llm(self, text: str) -> List[dict]:
        """
        Extract entities using LLM-based classification.

        Args:
            text: Text to extract entities from

        Returns:
            List of entity dictionaries
        """
        entities = []

        # Use AI service if available
        if self.ai_service:
            try:
                # Use zero-shot classification to identify entity types
                for entity_type in self.entity_types:
                    # Simple heuristic: look for capitalized phrases
                    # In production, this would use proper NER or LLM prompting
                    words = text.split()
                    for i, word in enumerate(words):
                        if word and word[0].isupper() and len(word) > 2:
                            # Check if it's a potential entity
                            entity_name = word.strip(".,;:!?")
                            if entity_name and len(entity_name) > 2:
                                entities.append(
                                    {
                                        "name": entity_name,
                                        "type": entity_type,
                                        "description": f"Extracted from text as {entity_type}",
                                    }
                                )
            except Exception as e:
                logger.error(f"Error in LLM entity extraction: {e}")

        return self._deduplicate_entities(entities)

    def _extract_entities_spacy(self, text: str) -> List[dict]:
        """
        Extract entities using spaCy NER.

        Args:
            text: Text to extract entities from

        Returns:
            List of entity dictionaries
        """
        entities = []

        try:
            import spacy

            # Try to load spaCy model
            try:
                nlp = spacy.load("en_core_web_sm")
            except OSError:
                # Model not installed, return empty list
                logger.warning("spaCy model 'en_core_web_sm' not installed")
                return []

            doc = nlp(text)

            for ent in doc.ents:
                # Map spaCy entity types to our types
                entity_type = self._map_spacy_entity_type(ent.label_)

                entities.append(
                    {
                        "name": ent.text,
                        "type": entity_type,
                        "description": f"Extracted as {ent.label_} entity",
                    }
                )

        except ImportError:
            logger.warning("spaCy not installed, skipping spaCy extraction")
        except Exception as e:
            logger.error(f"Error in spaCy entity extraction: {e}")

        return entities

    def _map_spacy_entity_type(self, spacy_label: str) -> str:
        """
        Map spaCy entity labels to our entity types.

        Args:
            spacy_label: spaCy entity label (e.g., "PERSON", "ORG")

        Returns:
            Mapped entity type
        """
        mapping = {
            "PERSON": "Person",
            "ORG": "Organization",
            "GPE": "Organization",  # Geopolitical entity
            "PRODUCT": "Concept",
            "EVENT": "Concept",
            "WORK_OF_ART": "Concept",
            "LAW": "Concept",
            "LANGUAGE": "Concept",
            "NORP": "Organization",  # Nationalities or religious/political groups
        }

        return mapping.get(spacy_label, "Concept")

    def _deduplicate_entities(self, entities: List[dict]) -> List[dict]:
        """
        Deduplicate entities by name and type.

        Args:
            entities: List of entity dictionaries

        Returns:
            Deduplicated list of entities
        """
        seen = set()
        deduplicated = []

        for entity in entities:
            key = (entity["name"].lower(), entity["type"])
            if key not in seen:
                seen.add(key)
                deduplicated.append(entity)

        return deduplicated

    def extract_relationships(
        self, chunk_content: str, entities: List[dict], chunk_id: Optional[str] = None
    ) -> List[dict]:
        """
        Extract relationships between entities within a chunk.

        Args:
            chunk_content: Text content containing entities
            entities: List of extracted entities
            chunk_id: ID of the source chunk for provenance

        Returns:
            List of relationship dictionaries with 'source_entity', 'target_entity',
            'relation_type', 'weight', and 'provenance_chunk_id' keys
        """
        if not entities or len(entities) < 2:
            return []

        relationships = []

        # Extract relationships based on method
        if self.extraction_method in ["llm", "hybrid"]:
            relationships.extend(
                self._extract_relationships_heuristic(chunk_content, entities, chunk_id)
            )

        return relationships

    def _extract_relationships_heuristic(
        self, text: str, entities: List[dict], chunk_id: Optional[str] = None
    ) -> List[dict]:
        """
        Extract relationships using heuristic rules.

        This is a simplified implementation. In production, this would use:
        - Dependency parsing to find syntactic relationships
        - LLM prompting to identify semantic relationships
        - Pattern matching for specific relationship types

        Args:
            text: Text content
            entities: List of entities
            chunk_id: Source chunk ID

        Returns:
            List of relationship dictionaries
        """
        relationships = []
        text_lower = text.lower()

        # Check all entity pairs
        for i, source_entity in enumerate(entities):
            for target_entity in entities[i + 1 :]:
                # Skip if same entity
                if source_entity["name"] == target_entity["name"]:
                    continue

                # Determine relationship type based on text patterns
                relation_type, weight = self._infer_relationship_type(
                    text_lower,
                    source_entity["name"].lower(),
                    target_entity["name"].lower(),
                )

                if relation_type:
                    relationships.append(
                        {
                            "source_entity": source_entity,
                            "target_entity": target_entity,
                            "relation_type": relation_type,
                            "weight": weight,
                            "provenance_chunk_id": chunk_id,
                        }
                    )

        return relationships

    def _infer_relationship_type(
        self, text: str, source_name: str, target_name: str
    ) -> tuple[Optional[str], float]:
        """
        Infer relationship type between two entities based on text patterns.

        Args:
            text: Text content (lowercase)
            source_name: Source entity name (lowercase)
            target_name: Target entity name (lowercase)

        Returns:
            Tuple of (relation_type, confidence_weight)
        """
        # Find positions of entities in text
        source_pos = text.find(source_name)
        target_pos = text.find(target_name)

        if source_pos == -1 or target_pos == -1:
            return None, 0.0

        # Get text between entities
        if source_pos < target_pos:
            between_text = text[source_pos + len(source_name) : target_pos]
        else:
            between_text = text[target_pos + len(target_name) : source_pos]

        # Pattern matching for relationship types
        if any(
            word in between_text
            for word in ["contradicts", "disagrees", "opposes", "refutes"]
        ):
            return "CONTRADICTS", 0.8

        if any(
            word in between_text
            for word in ["supports", "agrees", "confirms", "validates"]
        ):
            return "SUPPORTS", 0.8

        if any(
            word in between_text
            for word in ["extends", "builds on", "expands", "develops"]
        ):
            return "EXTENDS", 0.7

        if any(
            word in between_text
            for word in ["cites", "references", "mentions", "according to"]
        ):
            return "CITES", 0.9

        # Default: if entities appear in same chunk, assume weak support relationship
        return "SUPPORTS", 0.3

    def emit_entity_extracted_event(self, entity: dict, chunk_id: str) -> None:
        """
        Emit event when an entity is extracted.

        Args:
            entity: Entity dictionary with name, type, description
            chunk_id: Source chunk ID
        """
        try:
            from app.events.event_system import EventEmitter, EventPriority

            emitter = EventEmitter()
            emitter.emit(
                "graph.entity_extracted",
                {
                    "entity_name": entity["name"],
                    "entity_type": entity["type"],
                    "entity_description": entity.get("description"),
                    "chunk_id": chunk_id,
                },
                priority=EventPriority.NORMAL,
            )

            logger.debug(
                f"Emitted graph.entity_extracted event for entity: {entity['name']}"
            )

        except Exception as e:
            logger.error(f"Error emitting entity extracted event: {e}")

    def emit_relationship_extracted_event(
        self, relationship: dict, chunk_id: str
    ) -> None:
        """
        Emit event when a relationship is extracted.

        Args:
            relationship: Relationship dictionary
            chunk_id: Source chunk ID
        """
        try:
            from app.events.event_system import EventEmitter, EventPriority

            emitter = EventEmitter()
            emitter.emit(
                "graph.relationship_extracted",
                {
                    "source_entity": relationship["source_entity"]["name"],
                    "target_entity": relationship["target_entity"]["name"],
                    "relation_type": relationship["relation_type"],
                    "weight": relationship["weight"],
                    "chunk_id": chunk_id,
                },
                priority=EventPriority.NORMAL,
            )

            logger.debug(
                f"Emitted graph.relationship_extracted event: "
                f"{relationship['source_entity']['name']} -> "
                f"{relationship['relation_type']} -> "
                f"{relationship['target_entity']['name']}"
            )

        except Exception as e:
            logger.error(f"Error emitting relationship extracted event: {e}")

    async def extract_from_resource(self, resource, db: Session) -> List:
        """
        Extract relationships from a resource based on its type.

        For code resources (PRACTICE with code file extensions), uses static
        analysis to extract code relationships (IMPORTS, DEFINES, CALLS).

        For other resources, uses semantic extraction for academic relationships.

        Args:
            resource: Resource to extract relationships from
            db: Database session

        Returns:
            List of GraphRelationship objects
        """
        if self._is_code_resource(resource):
            return await self._extract_code_relationships(resource, db)
        else:
            # Existing semantic extraction for academic content
            return await self._extract_semantic_relationships(resource, db)

    def _is_code_resource(self, resource) -> bool:
        """
        Check if a resource is a code file.

        Args:
            resource: Resource to check

        Returns:
            True if resource is a code file
        """
        # Check resource metadata for classification
        metadata = resource.metadata or {}
        classification = metadata.get("classification", "")

        if classification == "PRACTICE":
            # Check file extension
            file_path = metadata.get("path", resource.title)
            code_extensions = [
                ".py",
                ".js",
                ".ts",
                ".jsx",
                ".tsx",
                ".rs",
                ".go",
                ".java",
                ".cpp",
                ".c",
                ".rb",
                ".php",
                ".swift",
                ".kt",
            ]

            return any(file_path.endswith(ext) for ext in code_extensions)

        return False

    async def _extract_code_relationships(self, resource, db: Session) -> List:
        """
        Extract code relationships using static analysis.

        Args:
            resource: Code resource to analyze
            db: Database session

        Returns:
            List of GraphRelationship objects
        """
        from app.modules.graph.logic.static_analysis import StaticAnalysisService
        from app.database.models import DocumentChunk, GraphEntity, GraphRelationship

        relationships = []

        try:
            # Get all chunks for this resource
            chunks = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.resource_id == resource.id)
                .all()
            )

            if not chunks:
                logger.info(f"No chunks found for resource {resource.id}")
                return relationships

            # Create static analysis service
            static_analysis = StaticAnalysisService(db)

            # Analyze each chunk
            for chunk in chunks:
                try:
                    # Extract relationships from chunk
                    chunk_relationships = await static_analysis.analyze_code_chunk(
                        chunk, resource
                    )

                    # Create GraphEntity and GraphRelationship entries
                    for rel_data in chunk_relationships:
                        # Create or get source entity
                        source_symbol = rel_data.get("source_file", resource.title)
                        source_entity = (
                            db.query(GraphEntity)
                            .filter(
                                GraphEntity.name == source_symbol,
                                GraphEntity.type == "CodeFile",
                            )
                            .first()
                        )

                        if not source_entity:
                            source_entity = GraphEntity(
                                name=source_symbol,
                                type="CodeFile",
                                description=f"Code file: {source_symbol}",
                            )
                            db.add(source_entity)
                            db.flush()

                        # Create or get target entity
                        target_symbol = rel_data.get("target_symbol", "unknown")
                        target_entity = (
                            db.query(GraphEntity)
                            .filter(
                                GraphEntity.name == target_symbol,
                                GraphEntity.type == "CodeSymbol",
                            )
                            .first()
                        )

                        if not target_entity:
                            target_entity = GraphEntity(
                                name=target_symbol,
                                type="CodeSymbol",
                                description=f"Code symbol: {target_symbol}",
                            )
                            db.add(target_entity)
                            db.flush()

                        # Create relationship
                        relationship = GraphRelationship(
                            source_entity_id=source_entity.id,
                            target_entity_id=target_entity.id,
                            relation_type=rel_data["type"],
                            weight=rel_data.get("metadata", {}).get("confidence", 1.0),
                            provenance_chunk_id=chunk.id,
                            relationship_metadata=rel_data.get("metadata", {}),
                        )

                        db.add(relationship)
                        relationships.append(relationship)

                        logger.debug(
                            f"Created {rel_data['type']} relationship: "
                            f"{source_symbol} -> {target_symbol}"
                        )

                except Exception as e:
                    logger.error(f"Error analyzing chunk {chunk.id}: {e}")
                    continue

            # Commit all relationships
            db.commit()

            logger.info(
                f"Extracted {len(relationships)} code relationships "
                f"from resource {resource.id}"
            )

        except Exception as e:
            logger.error(f"Error extracting code relationships: {e}")
            db.rollback()

        return relationships

    async def _extract_semantic_relationships(self, resource, db: Session) -> List:
        """
        Extract semantic relationships for academic content.

        This is the existing extraction logic for non-code resources.

        Args:
            resource: Resource to extract relationships from
            db: Database session

        Returns:
            List of GraphRelationship objects
        """
        # Placeholder for existing semantic extraction logic
        # This would use the existing entity and relationship extraction
        # for academic content (CONTRADICTS, SUPPORTS, EXTENDS, CITES)
        return []


class GraphVisualizationService:
    """
    Service for computing graph layouts for visualization.

    Provides multiple layout algorithms:
    - Force-directed (Fruchterman-Reingold)
    - Hierarchical (Kamada-Kawai)
    - Circular

    All layouts normalize coordinates to [0, 1000] range for consistent rendering.
    """

    def __init__(self, db: Session):
        """
        Initialize the graph visualization service.

        Args:
            db: Database session
        """
        self.db = db
        self.graph_service = GraphService(db)

    async def compute_layout(
        self, resource_ids: List[UUID], layout_type: str = "force", **layout_params
    ) -> dict:
        """
        Compute graph layout for visualization.

        Args:
            resource_ids: List of resource UUIDs to include in layout
            layout_type: Layout algorithm ("force", "hierarchical", "circular")
            **layout_params: Additional parameters for layout algorithm

        Returns:
            Dictionary with layout result containing:
            - nodes: Dict mapping resource_id to (x, y) position
            - edges: List of edge routing information
            - bounds: Bounding box (min/max x/y)
            - layout_type: Algorithm used

        Raises:
            ValueError: If layout_type is invalid or resource_ids is empty
        """
        import time
        import networkx as nx
        from app.modules.graph.schema import (
            NodePosition,
            EdgeRouting,
            BoundingBox,
            GraphLayoutResult,
        )

        start_time = time.time()

        # Validate inputs
        if not resource_ids:
            raise ValueError("resource_ids cannot be empty")

        valid_layouts = {"force", "hierarchical", "circular"}
        if layout_type not in valid_layouts:
            raise ValueError(
                f"Invalid layout_type '{layout_type}'. Must be one of: {valid_layouts}"
            )

        # Build NetworkX graph from resource IDs
        G = nx.DiGraph()

        # Add nodes
        for resource_id in resource_ids:
            G.add_node(str(resource_id))

        # Query edges between these resources
        edges = (
            self.db.query(db_models.GraphEdge)
            .filter(
                db_models.GraphEdge.source_id.in_(resource_ids),
                db_models.GraphEdge.target_id.in_(resource_ids),
            )
            .all()
        )

        # Add edges to graph
        for edge in edges:
            G.add_edge(str(edge.source_id), str(edge.target_id), weight=edge.weight)

        # Compute layout based on type
        if layout_type == "force":
            # Fruchterman-Reingold force-directed layout
            k = layout_params.get("k", None)  # Optimal distance between nodes
            iterations = layout_params.get("iterations", 50)
            pos = nx.spring_layout(G, k=k, iterations=iterations, seed=42)

        elif layout_type == "hierarchical":
            # Kamada-Kawai hierarchical layout
            pos = nx.kamada_kawai_layout(G)

        elif layout_type == "circular":
            # Circular layout
            pos = nx.circular_layout(G)

        # Normalize coordinates to [0, 1000] range
        if pos:
            # Get min/max coordinates
            x_coords = [p[0] for p in pos.values()]
            y_coords = [p[1] for p in pos.values()]

            min_x, max_x = min(x_coords), max(x_coords)
            min_y, max_y = min(y_coords), max(y_coords)

            # Special case: single node - place at center
            if len(pos) == 1:
                node_id = list(pos.keys())[0]
                normalized_pos = {UUID(node_id): NodePosition(x=500.0, y=500.0)}
            else:
                # Avoid division by zero
                x_range = max_x - min_x if max_x != min_x else 1.0
                y_range = max_y - min_y if max_y != min_y else 1.0

                # Normalize to [0, 1000]
                normalized_pos = {}
                for node_id, (x, y) in pos.items():
                    norm_x = ((x - min_x) / x_range) * 1000
                    norm_y = ((y - min_y) / y_range) * 1000
                    normalized_pos[UUID(node_id)] = NodePosition(x=norm_x, y=norm_y)
        else:
            # Empty graph - single node at center
            normalized_pos = {resource_ids[0]: NodePosition(x=500.0, y=500.0)}
            min_x, max_x = 0.0, 1000.0
            min_y, max_y = 0.0, 1000.0

        # Build edge routing list
        edge_routing = []
        for edge in edges:
            edge_routing.append(
                EdgeRouting(
                    source=edge.source_id, target=edge.target_id, weight=edge.weight
                )
            )

        # Create bounding box
        bounds = BoundingBox(min_x=0.0, max_x=1000.0, min_y=0.0, max_y=1000.0)

        # Build result
        result = GraphLayoutResult(
            nodes=normalized_pos,
            edges=edge_routing,
            bounds=bounds,
            layout_type=layout_type,
        )

        computation_time = (time.time() - start_time) * 1000  # Convert to ms

        return {
            "layout": result,
            "computation_time_ms": computation_time,
            "node_count": len(normalized_pos),
            "edge_count": len(edge_routing),
        }
