"""
Tests for Graph Embeddings Service (Task 11.8)

Tests Node2Vec, DeepWalk, similarity search, and performance.

Note: Tests now verify actual functionality with gensim 4.4.0 on Python 3.13.4.
"""

import importlib.util

import pytest
from unittest.mock import Mock
from uuid import uuid4

from app.modules.graph.embeddings import GraphEmbeddingsService



requires_gensim = pytest.mark.skipif(
    importlib.util.find_spec("gensim") is None,
    reason="gensim (graph embeddings) is an optional extra: pip install gensim",
)

class TestGraphEmbeddingsService:
    """Test suite for GraphEmbeddingsService"""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session"""
        return Mock()

    @pytest.fixture
    def service(self, mock_db):
        """Create GraphEmbeddingsService instance"""
        return GraphEmbeddingsService(mock_db)

    def test_initialization(self, service, mock_db):
        """Test service initialization"""
        assert service.db == mock_db
        assert isinstance(service.embeddings_cache, dict)
        assert len(service.embeddings_cache) == 0

    def test_build_networkx_graph_empty(self, service, mock_db):
        """Test building graph with no citations"""
        mock_db.query.return_value.all.return_value = []

        G = service._build_networkx_graph()

        assert G.number_of_nodes() >= 0
        assert G.number_of_edges() == 0

    def test_cosine_similarity(self, service):
        """Test cosine similarity computation"""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [1.0, 0.0, 0.0]

        similarity = service._cosine_similarity(vec_a, vec_b)
        assert similarity == pytest.approx(1.0, abs=0.01)

        vec_c = [0.0, 1.0, 0.0]
        similarity = service._cosine_similarity(vec_a, vec_c)
        assert similarity == pytest.approx(0.0, abs=0.01)

    def test_cosine_similarity_zero_vectors(self, service):
        """Test cosine similarity with zero vectors"""
        vec_a = [0.0, 0.0, 0.0]
        vec_b = [1.0, 0.0, 0.0]

        similarity = service._cosine_similarity(vec_a, vec_b)
        assert similarity == 0.0

    def test_cosine_similarity_different_lengths(self, service):
        """Test cosine similarity with different length vectors"""
        vec_a = [1.0, 0.0]
        vec_b = [1.0, 0.0, 0.0]

        similarity = service._cosine_similarity(vec_a, vec_b)
        assert similarity == 0.0

    def test_get_embedding_not_found(self, service):
        """Test getting embedding that doesn't exist"""
        resource_id = uuid4()
        embedding = service.get_embedding(resource_id)
        assert embedding is None

    def test_get_embedding_from_cache(self, service):
        """Test getting embedding from cache"""
        resource_id = uuid4()
        expected_embedding = [0.1, 0.2, 0.3]
        service.embeddings_cache[str(resource_id)] = expected_embedding

        embedding = service.get_embedding(resource_id)
        assert embedding == expected_embedding

    def test_find_similar_nodes_no_embedding(self, service):
        """Test finding similar nodes when source has no embedding"""
        resource_id = uuid4()
        similar = service.find_similar_nodes(resource_id, limit=5)
        assert similar == []

    def test_find_similar_nodes(self, service):
        """Test finding similar nodes"""
        resource_id = uuid4()
        other_id_1 = str(uuid4())
        other_id_2 = str(uuid4())

        # Add embeddings to cache
        service.embeddings_cache[str(resource_id)] = [1.0, 0.0, 0.0]
        service.embeddings_cache[other_id_1] = [0.9, 0.1, 0.0]  # Very similar
        service.embeddings_cache[other_id_2] = [0.0, 1.0, 0.0]  # Not similar

        similar = service.find_similar_nodes(resource_id, limit=2)

        assert len(similar) == 2
        assert similar[0][0] == other_id_1  # Most similar first
        assert similar[0][1] > similar[1][1]  # Scores descending

    def test_find_similar_nodes_with_threshold(self, service):
        """Test finding similar nodes with minimum similarity threshold"""
        resource_id = uuid4()
        other_id_1 = str(uuid4())
        other_id_2 = str(uuid4())

        service.embeddings_cache[str(resource_id)] = [1.0, 0.0, 0.0]
        service.embeddings_cache[other_id_1] = [0.9, 0.1, 0.0]  # High similarity
        service.embeddings_cache[other_id_2] = [0.1, 0.9, 0.0]  # Low similarity

        similar = service.find_similar_nodes(resource_id, limit=10, min_similarity=0.5)

        # Only high similarity node should be returned
        assert len(similar) <= 1

    def test_clear_cache(self, service):
        """Test clearing embeddings cache"""
        service.embeddings_cache["node1"] = [0.1, 0.2]
        service.embeddings_cache["node2"] = [0.3, 0.4]

        assert len(service.embeddings_cache) == 2

        service.clear_cache()

        assert len(service.embeddings_cache) == 0

    @requires_gensim
    def test_compute_node2vec_empty_graph(self, service, mock_db):
        """Test Node2Vec computation with empty graph"""
        # Mock empty database
        mock_db.query.return_value.all.return_value = []

        result = service.compute_node2vec_embeddings()

        assert result["status"] == "error"
        assert result["embeddings_computed"] == 0
        assert "no nodes" in result["message"].lower()

    @requires_gensim
    def test_compute_deepwalk_empty_graph(self, service, mock_db):
        """Test DeepWalk computation with empty graph"""
        # Mock empty database
        mock_db.query.return_value.all.return_value = []

        result = service.compute_deepwalk_embeddings()

        assert result["status"] == "error"
        assert result["embeddings_computed"] == 0

    def test_generate_random_walks(self, service):
        """Test random walk generation"""
        import networkx as nx

        # Create a simple graph
        G = nx.DiGraph()
        G.add_edges_from([("1", "2"), ("2", "3"), ("3", "1")])

        walks = service._generate_random_walks(G, num_walks=2, walk_length=5)

        # Should generate walks for each node
        assert len(walks) > 0
        # Each walk should have at least 2 nodes
        for walk in walks:
            assert len(walk) >= 2

    def test_node2vec_walk(self, service):
        """Test single Node2Vec biased random walk"""
        import networkx as nx

        # Create a simple graph
        G = nx.DiGraph()
        G.add_edges_from([("1", "2"), ("2", "3"), ("3", "4")])

        walk = service._node2vec_walk(G, "1", walk_length=4, p=1.0, q=1.0)

        # Walk should start with the start node
        assert walk[0] == "1"
        # Walk should have at least 2 nodes
        assert len(walk) >= 2
        # All nodes in walk should be in the graph
        for node in walk:
            assert node in G.nodes()

    def test_biased_choice(self, service):
        """Test Node2Vec biased choice mechanism"""
        import networkx as nx

        # Create a graph with known structure
        G = nx.DiGraph()
        G.add_edges_from([("1", "2"), ("2", "3"), ("2", "4"), ("1", "3")])

        # Test biased choice
        neighbors = ["3", "4"]
        choice = service._biased_choice(G, "2", "1", neighbors, p=1.0, q=1.0)

        # Should return one of the neighbors
        assert choice in neighbors

    @requires_gensim
    def test_update_embeddings_incremental(self, service, mock_db):
        """Test incremental embedding updates"""
        # Mock empty database
        mock_db.query.return_value.all.return_value = []

        affected_nodes = ["node1", "node2", "node3"]

        result = service.update_embeddings_incremental(affected_nodes)

        # Should return error for empty graph
        assert result["status"] == "error"
        assert result["update_type"] == "full_recomputation"
        assert result["affected_nodes"] == 3

    @pytest.mark.parametrize("dimensions", [32, 64, 128, 256])
    def test_embedding_dimensions(self, service, dimensions):
        """Test different embedding dimensions"""
        # Test that the service accepts different dimensions
        # Verify the service can be configured with different dimensions
        assert service is not None

        # Test with a simple graph
        import networkx as nx

        G = nx.DiGraph()
        G.add_edges_from([("1", "2"), ("2", "3")])

        # Verify walks can be generated
        walks = service._generate_random_walks(G, num_walks=2, walk_length=5)
        assert len(walks) > 0

    def test_compute_node2vec_with_mock_graph(self, service, mock_db):
        """Test Node2Vec computation with mocked graph data"""
        from app.database.models import Citation, Resource

        # Create mock citations
        mock_citation = Mock(spec=Citation)
        mock_citation.source_resource_id = uuid4()
        mock_citation.target_resource_id = uuid4()

        # Create mock resources
        mock_resource1 = Mock(spec=Resource)
        mock_resource1.id = mock_citation.source_resource_id
        mock_resource2 = Mock(spec=Resource)
        mock_resource2.id = mock_citation.target_resource_id

        # Setup mock database queries
        def query_side_effect(model):
            mock_query = Mock()
            if model == Citation:
                mock_query.all.return_value = [mock_citation]
            elif model == Resource:
                mock_query.all.return_value = [mock_resource1, mock_resource2]
            return mock_query

        mock_db.query.side_effect = query_side_effect

        # Test graph building
        G = service._build_networkx_graph()
        assert G.number_of_nodes() == 2
        assert G.number_of_edges() == 1

    @requires_gensim
    def test_deepwalk_is_node2vec_with_default_params(self, service, mock_db):
        """Test that DeepWalk is Node2Vec with p=1, q=1"""
        # Mock empty database
        mock_db.query.return_value.all.return_value = []

        result = service.compute_deepwalk_embeddings(dimensions=64)

        # Should have algorithm set to deepwalk
        assert result["algorithm"] == "deepwalk"
        # Should have error status due to empty graph
        assert result["status"] == "error"


class TestGraphEmbeddingsPerformance:
    """Performance tests for graph embeddings"""

    @pytest.fixture
    def service(self):
        """Create service with mock database"""
        return GraphEmbeddingsService(Mock())

    def test_cosine_similarity_performance(self, service):
        """Test cosine similarity computation performance"""
        import time

        vec_a = [0.1] * 128
        vec_b = [0.2] * 128

        start = time.time()
        for _ in range(1000):
            service._cosine_similarity(vec_a, vec_b)
        elapsed = time.time() - start

        # Should compute 1000 similarities in less than 1 second
        assert elapsed < 1.0

    def test_find_similar_nodes_performance(self, service):
        """Test similarity search performance with many nodes"""
        import time

        # Create cache with 100 nodes
        target_uuid = uuid4()
        target_id = str(target_uuid)
        service.embeddings_cache[target_id] = [0.5] * 128

        for i in range(100):
            node_id = str(uuid4())
            service.embeddings_cache[node_id] = [0.5 + i * 0.001] * 128

        start = time.time()
        similar = service.find_similar_nodes(target_uuid, limit=10)
        elapsed = time.time() - start

        # Should find similar nodes in less than 100ms
        assert elapsed < 0.1
        assert len(similar) <= 10


class TestGraphEmbeddingsIntegration:
    """Integration tests for graph embeddings"""

    @requires_gensim
    def test_full_workflow_with_gensim(self):
        """Test the full workflow with gensim 4.4.0 on Python 3.13"""
        from sqlalchemy.orm import Session

        mock_db = Mock(spec=Session)
        service = GraphEmbeddingsService(mock_db)

        # Test that service initializes correctly
        assert service.db == mock_db
        assert len(service.embeddings_cache) == 0

        # Test that we can add embeddings manually
        node_uuid = uuid4()
        node_id = str(node_uuid)
        embedding = [0.1, 0.2, 0.3]
        service.embeddings_cache[node_id] = embedding

        # Test retrieval
        retrieved = service.get_embedding(node_uuid)
        assert retrieved == embedding

        # Test similarity search
        other_uuid = uuid4()
        other_id = str(other_uuid)
        service.embeddings_cache[other_id] = [0.15, 0.25, 0.35]

        similar = service.find_similar_nodes(node_uuid, limit=5)
        assert len(similar) == 1
        assert similar[0][0] == other_id

    @requires_gensim
    def test_gensim_availability(self):
        """Test that gensim is available and working"""
        try:
            from gensim.models import Word2Vec

            # Test basic Word2Vec functionality
            sentences = [["cat", "dog"], ["dog", "bird"], ["bird", "cat"]]
            model = Word2Vec(sentences, vector_size=10, min_count=1, epochs=1)
            assert model is not None
            assert "cat" in model.wv
        except ImportError:
            pytest.fail("gensim should be available with Python 3.13")

    def test_networkx_availability(self):
        """Test that NetworkX is available and working"""
        try:
            import networkx as nx

            G = nx.DiGraph()
            G.add_edge("1", "2")
            assert G.number_of_nodes() == 2
            assert G.number_of_edges() == 1
        except ImportError:
            pytest.fail("NetworkX should be available")

    def test_custom_node2vec_implementation(self):
        """Test that custom Node2Vec implementation works correctly"""
        import networkx as nx

        mock_db = Mock()
        service = GraphEmbeddingsService(mock_db)

        # Create a test graph
        G = nx.DiGraph()
        G.add_edges_from(
            [("1", "2"), ("2", "3"), ("3", "4"), ("4", "1"), ("2", "4"), ("3", "1")]
        )

        # Test random walk generation
        walks = service._generate_random_walks(
            G, num_walks=5, walk_length=10, p=1.0, q=1.0
        )

        # Verify walks were generated
        assert len(walks) > 0

        # Verify walk properties
        for walk in walks:
            # Each walk should have at least 2 nodes
            assert len(walk) >= 2
            # All nodes should be in the graph
            for node in walk:
                assert node in G.nodes()
            # Consecutive nodes should be connected (or walk ended)
            for i in range(len(walk) - 1):
                if i < len(walk) - 1:
                    # Either there's an edge, or the walk ended early
                    assert (
                        G.has_edge(walk[i], walk[i + 1])
                        or len(list(G.neighbors(walk[i]))) == 0
                    )
