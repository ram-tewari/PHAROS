"""Tokenisation, embedding backends and graph resolution (pure units)."""

import math

import pytest

from app.codeintel.embeddings import EmbeddingUnavailable, HashEmbedder, HttpEmbedder, _pad, resolve_backend
from app.codeintel.graph import ChunkNode, build_edges
from app.codeintel.retrieval import is_test_path, symbol_like_terms
from app.codeintel.text import query_terms, split_identifier, tokenize, tsquery_from_terms


def test_identifier_splitting():
    assert split_identifier("parseHTTPResponse") == ["parse", "http", "response"]
    assert split_identifier("parse_http_response") == ["parse", "http", "response"]
    assert split_identifier("utf8Decode") == ["utf8", "decode"]
    assert tokenize("verify_password") == ["verify", "password", "verifypassword"]


def test_query_terms_drop_stopwords_and_dedupe():
    assert query_terms("How does the Auth middleware validate the auth token?") == [
        "auth", "middleware", "validate", "token",
    ]


def test_tsquery_is_injection_safe():
    assert tsquery_from_terms(["auth", "x' | !y", "a&b", "ok"]) == "auth | ok"


def test_symbol_like_terms_only_for_identifier_shaped_words():
    assert "verifypassword" in symbol_like_terms("where is verify_password used")
    assert "tokensigner" in symbol_like_terms("TokenSigner.verify behaviour")
    assert "parcel" not in symbol_like_terms("volumetric weight of a parcel")
    assert symbol_like_terms("parcel") == {"parcel"}


def test_test_path_detection():
    assert is_test_path("tests/test_cart.py")
    assert is_test_path("pkg/foo_test.go")
    assert is_test_path("web/__tests__/a.js")
    assert is_test_path("web/a.spec.ts")
    assert not is_test_path("shop/contest.py")


def test_hash_embedder_is_deterministic_normalised_and_lexical():
    e = HashEmbedder()
    a, b, c = e.embed_documents(["verify user password", "check the password of a user", "render html template"])
    assert len(a) == 768 and math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-9)
    assert e.embed_documents(["verify user password"])[0] == a
    dot = lambda x, y: sum(i * j for i, j in zip(x, y, strict=True))  # noqa: E731
    assert dot(a, b) > dot(a, c)
    assert e.semantic is False and e.model_id == "hash-v1"


def test_padding_preserves_cosine_and_rejects_oversize():
    v = [0.6, 0.8]
    assert _pad(v, 4) == [0.6, 0.8, 0.0, 0.0]
    with pytest.raises(EmbeddingUnavailable):
        _pad([0.0] * 1024, 768)


def test_backend_resolution():
    assert resolve_backend("auto", "CLOUD", None) == "none"
    assert resolve_backend("auto", "CLOUD", "https://edge") == "http"
    assert resolve_backend("auto", "EDGE", None) == "sentence-transformers"
    assert resolve_backend("hash", "CLOUD", None) == "hash"


def test_onnx_batch_size_comes_from_settings():
    from types import SimpleNamespace

    from app.codeintel.embeddings import OnnxEmbedder, get_embedder, reset_embedder_cache

    settings = SimpleNamespace(
        EMBEDDING_BACKEND="onnx", MODE="CLOUD", EDGE_EMBEDDING_URL=None, EDGE_EMBED_TOKEN=None,
        EMBEDDING_MODEL_NAME="unused", EMBEDDING_ONNX_DIR="/models/mini", EMBEDDING_MODEL_ID="mini-onnx",
        EMBEDDING_ONNX_BATCH_SIZE=4,
    )
    reset_embedder_cache()
    try:
        embedder = get_embedder(settings)  # the model loads lazily, so no files are needed
        assert isinstance(embedder, OnnxEmbedder)
        assert embedder.batch_size == 4 and embedder.model_id == "mini-onnx"
    finally:
        reset_embedder_cache()


def test_http_embedder_reports_unreachable_server():
    e = HttpEmbedder("http://127.0.0.1:9", "nomic-ai/nomic-embed-text-v1", timeout=1)
    assert e.model_id == "nomic-ai/nomic-embed-text-v1+prefix"
    with pytest.raises(EmbeddingUnavailable):
        e.embed_query("x")


def _node(i, path, kind, name, qual, parent=None, calls=(), language="python", imports=(), import_map=None):
    return ChunkNode(str(i), path, language, kind, name, qual, parent, list(calls), list(imports), import_map or {})


def test_graph_resolution_rules():
    nodes = [
        _node(1, "pkg/a.py", "module", "a", "pkg.a", imports=["pkg.b", "pkg.b.helper"], import_map={"helper": "pkg.b.helper"}),
        _node(2, "pkg/a.py", "function", "main", "pkg.a.main", "pkg.a", calls=["helper", "local", "print", "dup"]),
        _node(3, "pkg/a.py", "function", "local", "pkg.a.local", "pkg.a"),
        _node(4, "pkg/b.py", "module", "b", "pkg.b"),
        _node(5, "pkg/b.py", "function", "helper", "pkg.b.helper", "pkg.b"),
        _node(6, "pkg/b.py", "function", "dup", "pkg.b.dup", "pkg.b"),
        _node(7, "pkg/c.py", "function", "dup", "pkg.c.dup", "pkg.c"),
    ]
    edges, stats = build_edges(nodes)
    calls = {(e.source_id, e.target_id, e.resolution) for e in edges if e.edge_type == "calls"}
    assert ("2", "5", "imported_file") in calls
    assert ("2", "3", "same_file") in calls
    # "dup" is defined twice and not imported: ambiguous, so not linked.
    assert not any(t in ("6", "7") for _, t, _ in calls)
    assert stats.calls_ambiguous == 1 and stats.calls_unresolved == 1  # print
    contains = {(e.source_id, e.target_id) for e in edges if e.edge_type == "contains"}
    assert ("1", "2") in contains and ("4", "5") in contains
    assert ("1", "4") in {(e.source_id, e.target_id) for e in edges if e.edge_type == "imports"}


def test_graph_js_relative_imports():
    nodes = [
        _node(1, "web/client.js", "module", "client.js", "web.client", language="javascript", imports=["./format", "react"]),
        _node(2, "web/format.js", "module", "format.js", "web.format", language="javascript"),
        _node(3, "web/client.js", "function", "go", "web.client.go", "web.client", calls=["formatPrice"], language="javascript"),
        _node(4, "web/format.js", "function", "formatPrice", "web.format.formatPrice", "web.format", language="javascript"),
    ]
    edges, _ = build_edges(nodes)
    kinds = {(e.source_id, e.target_id, e.edge_type, e.resolution) for e in edges}
    assert ("1", "2", "imports", "imported_file") in kinds
    assert ("3", "4", "calls", "imported_file") in kinds
