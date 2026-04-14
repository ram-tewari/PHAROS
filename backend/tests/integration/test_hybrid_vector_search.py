"""Fast unit tests for hybrid vector search using mocks only.

These tests intentionally avoid real database setup, pgvector extension,
and transformer model downloads. They validate query-building contracts,
score fusion logic, and fallback SPLADE behavior.
"""

import os
import sys
import types
import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

os.environ.setdefault("TESTING", "true")
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _install_sqlalchemy_stubs() -> None:
    if "sqlalchemy" not in sys.modules:
        sqlalchemy_stub = types.ModuleType("sqlalchemy")

        def _text(sql: str):
            return types.SimpleNamespace(text=sql)

        sqlalchemy_stub.text = _text
        sys.modules["sqlalchemy"] = sqlalchemy_stub

    if "sqlalchemy.orm" not in sys.modules:
        orm_stub = types.ModuleType("sqlalchemy.orm")
        orm_stub.Session = object
        sys.modules["sqlalchemy.orm"] = orm_stub


_install_sqlalchemy_stubs()


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module: {module_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_vector_module = _load_module(
    "vector_search_real",
    BACKEND_ROOT / "app" / "modules" / "search" / "vector_search_real.py",
)
_sparse_module = _load_module(
    "sparse_embeddings_real",
    BACKEND_ROOT / "app" / "modules" / "search" / "sparse_embeddings_real.py",
)

RealVectorSearchService = _vector_module.RealVectorSearchService
RealSPLADEService = _sparse_module.RealSPLADEService


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


def _sql_text(statement) -> str:
    return statement.text if hasattr(statement, "text") else str(statement)


def test_dense_vector_search_uses_parameterized_query_and_returns_rows():
    db = Mock()
    db.execute.return_value = _FakeResult([("a", 0.05), ("b", 0.17)])

    service = RealVectorSearchService(db)
    rows = service.dense_vector_search(
        query_embedding=[0.1, 0.2, 0.3],
        top_k=2,
        distance_metric="cosine",
        filters={"resource_type": "code", "min_quality_score": 0.8},
    )

    assert rows == [("a", 0.05), ("b", 0.17)]
    assert db.execute.call_count == 1

    statement, params = db.execute.call_args[0]
    sql = _sql_text(statement)

    assert "embedding <=> :embedding::vector" in sql
    assert "type = :resource_type" in sql
    assert "quality_score >= :min_quality_score" in sql
    assert "LIMIT :top_k" in sql

    assert params["embedding"].startswith("[")
    assert params["resource_type"] == "code"
    assert params["min_quality_score"] == 0.8
    assert params["top_k"] == 2


def test_dense_vector_search_rejects_unknown_metric():
    service = RealVectorSearchService(Mock())

    with pytest.raises(ValueError, match="Unknown distance metric"):
        service.dense_vector_search(query_embedding=[0.1], distance_metric="bad")


def test_sparse_vector_search_returns_empty_for_empty_query():
    db = Mock()
    service = RealVectorSearchService(db)

    result = service.sparse_vector_search(query_sparse_embedding={}, top_k=10)

    assert result == []
    db.execute.assert_not_called()


def test_sparse_vector_search_uses_parameterized_query_and_filters():
    db = Mock()
    db.execute.return_value = _FakeResult([("x", 1.5), ("y", 0.4)])

    service = RealVectorSearchService(db)
    rows = service.sparse_vector_search(
        query_sparse_embedding={1: 0.8, 2: 0.4},
        top_k=3,
        filters={"resource_type": "doc", "min_quality_score": 0.6},
    )

    assert rows == [("x", 1.5), ("y", 0.4)]

    statement, params = db.execute.call_args[0]
    sql = _sql_text(statement)

    assert "jsonb_each_text(:query_sparse_json::jsonb)" in sql
    assert "r.type = :resource_type" in sql
    assert "r.quality_score >= :min_quality_score" in sql
    assert "LIMIT :top_k" in sql

    assert params["query_sparse_json"].startswith("{")
    assert params["resource_type"] == "doc"
    assert params["min_quality_score"] == 0.6
    assert params["top_k"] == 3


def test_chunk_dense_vector_search_places_join_before_where():
    db = Mock()
    db.execute.return_value = _FakeResult([("chunk-1", 0.02)])

    service = RealVectorSearchService(db)
    rows = service.chunk_dense_vector_search(
        query_embedding=[0.1, 0.2],
        top_k=5,
        distance_metric="l2",
        filters={"resource_type": "code", "min_quality_score": 0.7},
    )

    assert rows == [("chunk-1", 0.02)]

    statement, params = db.execute.call_args[0]
    sql = _sql_text(statement)

    assert "FROM document_chunks dc" in sql
    assert "JOIN resources r ON dc.resource_id = r.id" in sql
    assert sql.index("JOIN resources r ON dc.resource_id = r.id") < sql.index("WHERE")
    assert sql.count("WHERE") == 1
    assert "dc.embedding IS NOT NULL" in sql
    assert "r.type = :resource_type" in sql
    assert "r.quality_score >= :min_quality_score" in sql
    assert "LIMIT :top_k" in sql

    assert params["resource_type"] == "code"
    assert params["min_quality_score"] == 0.7
    assert params["top_k"] == 5


def test_hybrid_vector_search_combines_dense_and_sparse_scores():
    service = RealVectorSearchService(Mock())

    with patch.object(service, "dense_vector_search", return_value=[("a", 0.1), ("b", 0.5)]):
        with patch.object(
            service,
            "sparse_vector_search",
            return_value=[("b", 3.0), ("c", 1.5)],
        ):
            result = service.hybrid_vector_search(
                query_dense_embedding=[0.1, 0.2],
                query_sparse_embedding={1: 1.0},
                top_k=3,
                dense_weight=0.6,
                sparse_weight=0.4,
            )

    # a = 0.6 * 0.9 = 0.54
    # b = 0.6 * 0.5 + 0.4 * 1.0 = 0.7
    # c = 0.4 * 0.5 = 0.2
    assert [item[0] for item in result] == ["b", "a", "c"]
    assert pytest.approx(result[0][1], 0.0001) == 0.7


def test_rrf_scores_match_reference_formula():
    service = RealVectorSearchService(Mock())

    list_1 = [("id1", 0.9), ("id2", 0.8), ("id3", 0.7)]
    list_2 = [("id2", 0.95), ("id1", 0.85), ("id4", 0.75)]
    list_3 = [("id3", 0.92), ("id4", 0.88), ("id1", 0.82)]

    fused = service.reciprocal_rank_fusion([list_1, list_2, list_3], k=60, top_k=4)

    assert len(fused) == 4
    id1_score = next(score for resource_id, score in fused if resource_id == "id1")
    expected = 1 / (60 + 1) + 1 / (60 + 2) + 1 / (60 + 3)
    assert pytest.approx(id1_score, 0.000001) == expected


def test_generate_embedding_returns_empty_for_blank_text():
    service = RealSPLADEService(Mock())

    assert service.generate_embedding("") == {}
    assert service.generate_embedding("   ") == {}


def test_generate_embedding_uses_fallback_when_model_unavailable():
    service = RealSPLADEService(Mock())

    with patch.object(_sparse_module, "SPLADE_AVAILABLE", False):
        sparse_vec = service.generate_embedding("authentication oauth security token")

    assert sparse_vec
    for token_id, weight in sparse_vec.items():
        assert isinstance(token_id, int)
        assert isinstance(weight, float)
        assert 0.0 <= weight <= 1.0


def test_batch_generate_embeddings_calls_single_generate_path():
    service = RealSPLADEService(Mock())

    with patch.object(service, "generate_embedding", side_effect=[{1: 0.1}, {2: 0.2}, {3: 0.3}]) as mocked:
        result = service.batch_generate_embeddings(["a", "b", "c"], batch_size=2)

    assert result == [{1: 0.1}, {2: 0.2}, {3: 0.3}]
    assert mocked.call_count == 3


def test_decode_tokens_returns_empty_when_tokenizer_unavailable():
    service = RealSPLADEService(Mock())

    with patch.object(service, "_load_model"):
        service.tokenizer = None
        result = service.decode_tokens({1: 0.8}, top_k=1)

    assert result == []
