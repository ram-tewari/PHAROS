"""Indexing: persistence, incremental re-ingestion, stale data, safety limits."""

from sqlalchemy import func, select

from app.codeintel.embeddings import EmbeddingUnavailable, HashEmbedder
from app.codeintel.git_source import parse_repo_spec
from app.codeintel.indexer import CodeIndexer
from app.database.models import CodeEdge, DocumentChunk, Repository, Resource


def _ref(fixture_repo):
    return parse_repo_spec(str(fixture_repo.path), allowed_hosts=[], allow_local=True)


def _count(session, model, *where):
    return session.execute(select(func.count()).select_from(model).where(*where)).scalar_one()


def test_initial_index_persists_chunks_without_source(session, indexed, fixture_repo):
    ref, stats = indexed
    assert stats.outcome == "indexed"
    assert stats.files_indexed == 16 and stats.files_failed == 0
    assert all(lang.fallback_files == 0 for lang in stats.languages.values())
    assert set(stats.languages) == {"python", "javascript", "typescript", "go", "rust", "c", "cpp", "java"}

    repo = session.execute(select(Repository).where(Repository.url == ref.canonical_url)).scalar_one()
    assert repo.index_status == "ready"
    assert repo.last_commit_sha == fixture_repo.head
    assert repo.source_type == "local"

    chunks = session.execute(select(DocumentChunk).where(DocumentChunk.repository_id == repo.id)).scalars().all()
    assert len(chunks) == stats.chunks_total > 50
    assert all(c.content is None for c in chunks), "hybrid storage: no raw source in the database"
    assert all(c.branch_reference == fixture_repo.head for c in chunks)
    assert all(c.embedding and len(c.embedding) == 768 and c.embedding_model == "hash-v1" for c in chunks)
    assert {c.parser for c in chunks} == {"python-ast", "tree-sitter"}

    verify = next(c for c in chunks if c.symbol_name == "shop.auth.verify_password")
    assert (verify.start_line, verify.end_line) == (20, 24)
    assert verify.ast_node_type == "function"
    assert "Check a plaintext password" in verify.semantic_summary
    assert "verify" in verify.search_text and "password" in verify.search_text

    resource = session.get(Resource, verify.resource_id)
    assert resource.identifier == "shop/auth.py"
    assert resource.content_sha and len(resource.content_sha) == 40
    assert resource.embedding is not None  # file-level mean of chunk vectors


def test_graph_edges_are_built(session, indexed):
    edges = _count(session, CodeEdge, CodeEdge.edge_type == "calls")
    assert edges >= 20
    rows = session.execute(
        select(DocumentChunk.symbol_name)
        .join(CodeEdge, CodeEdge.target_chunk_id == DocumentChunk.id)
        .where(CodeEdge.edge_type == "calls")
    ).scalars().all()
    assert "shop.db.fetch_user" in rows  # called from shop.auth.authenticate (cross-file)


def test_reindexing_same_commit_is_a_noop(session, indexed, fixture_repo, embedder):
    ref, first = indexed
    before = _count(session, DocumentChunk)
    again = CodeIndexer(session, embedder).index(ref)
    assert again.outcome == "unchanged"
    assert _count(session, DocumentChunk) == before
    assert _count(session, Resource, Resource.repository_id.isnot(None)) == first.files_indexed


def test_incremental_reindex_replaces_changed_and_removes_deleted(session, indexed, fixture_repo, embedder):
    ref, first = indexed
    cart = (fixture_repo.path / "shop/cart.py").read_text()
    fixture_repo.write("shop/cart.py", cart.replace("Remove a product from the cart entirely", "Drop a product line"))
    fixture_repo.remove("web/format.js")
    fixture_repo.write("shop/health.py", 'def ping():\n    """Liveness check."""\n    return "pong"\n')
    new_head = fixture_repo.commit("edit")

    stats = CodeIndexer(session, embedder).index(ref)
    assert stats.outcome == "indexed"
    assert (stats.files_indexed, stats.files_deleted, stats.files_unchanged) == (2, 1, 14)

    paths = set(session.execute(select(Resource.identifier).where(Resource.repository_id.isnot(None))).scalars())
    assert "web/format.js" not in paths and "shop/health.py" in paths
    assert len(paths) == 16  # no duplicate rows for re-indexed files

    stale = _count(session, DocumentChunk, DocumentChunk.branch_reference != new_head)
    assert stale == 0, "every chunk must point at the indexed commit"
    summary = session.execute(
        select(DocumentChunk.semantic_summary).where(DocumentChunk.symbol_name == "shop.cart.Cart.remove_item")
    ).scalar_one()
    assert "Drop a product line" in summary
    # Edges pointing at deleted chunks are gone.
    dangling = session.execute(
        select(func.count()).select_from(CodeEdge).outerjoin(
            DocumentChunk, DocumentChunk.id == CodeEdge.target_chunk_id
        ).where(DocumentChunk.id.is_(None))
    ).scalar_one()
    assert dangling == 0


def test_changing_embedding_model_reembeds_everything(session, indexed, fixture_repo):
    ref, first = indexed

    class OtherModel(HashEmbedder):
        model_id = "hash-v1-other"

    stats = CodeIndexer(session, OtherModel()).index(ref)
    assert stats.outcome == "indexed" and stats.files_indexed == first.files_indexed
    models = set(session.execute(select(DocumentChunk.embedding_model)).scalars())
    assert models == {"hash-v1-other"}


def test_safety_limits_and_skip_reasons(session, fixture_repo, embedder):
    fixture_repo.write("vendor/lib.py", "def vendored():\n    pass\n")
    fixture_repo.write("node_modules/x/index.js", "function x() {}\n")
    fixture_repo.write("big/huge.py", "x = 1\n" * 300_000)  # ~1.8 MB
    fixture_repo.write("blob.c", b"int x;\0\0\0binary")
    fixture_repo.write("web/app.min.js", "function a(){}" * 1000)
    fixture_repo.write("web/bundle.js", "var a=" + "1+" * 20000 + "1;")  # minified, no .min suffix
    fixture_repo.write("docs/README.md", "# not code")
    fixture_repo.commit("noise")

    stats = CodeIndexer(session, embedder, max_file_bytes=1_000_000).index(_ref(fixture_repo))
    assert stats.skipped["excluded_path"] == 2
    assert stats.skipped["too_large"] == 1
    assert stats.skipped["binary"] == 1
    assert stats.skipped["excluded_file"] == 1
    assert stats.skipped["minified"] == 1
    assert stats.skipped["not_source"] >= 1
    paths = set(session.execute(select(Resource.identifier).where(Resource.repository_id.isnot(None))).scalars())
    assert not {"vendor/lib.py", "big/huge.py", "blob.c", "web/bundle.js"} & paths


def test_max_files_cap(session, fixture_repo, embedder):
    stats = CodeIndexer(session, embedder, max_files=5).index(_ref(fixture_repo))
    assert stats.files_indexed == 5
    assert stats.skipped["max_files_exceeded"] == 11


def test_fallback_is_visible_in_chunks_and_stats(session, fixture_repo, embedder):
    fixture_repo.write("scripts/deploy.rb", "puts 'deploy'\n")
    fixture_repo.write("shop/broken.py", "def oops(:\n    pass\n")
    fixture_repo.commit("fallbacks")
    stats = CodeIndexer(session, embedder).index(_ref(fixture_repo))
    assert stats.languages["ruby"].fallback_reasons == {"unsupported_language": 1}
    assert stats.languages["python"].fallback_reasons == {"syntax_error": 1}
    chunk = session.execute(
        select(DocumentChunk).where(DocumentChunk.chunk_metadata["path"].as_string() == "shop/broken.py")
    ).scalar_one()
    assert chunk.parser == "line-fallback" and chunk.ast_node_type == "block"
    assert chunk.chunk_metadata["fallback_reason"] == "syntax_error"


def test_failure_keeps_previous_index_searchable(session, indexed, fixture_repo):
    ref, first = indexed
    fixture_repo.write("shop/new.py", "def added():\n    pass\n")
    fixture_repo.commit("new file")

    class Broken(HashEmbedder):
        def embed_documents(self, texts):
            raise RuntimeError("GPU fell off the bus")

    import pytest

    with pytest.raises(EmbeddingUnavailable):
        CodeIndexer(session, Broken()).index(ref, force=True)
    session.rollback()
    repo = session.execute(select(Repository).where(Repository.url == ref.canonical_url)).scalar_one()
    assert repo.index_status == "failed"
    assert repo.last_commit_sha == first.commit_sha  # previous index still referenced
    assert _count(session, DocumentChunk, DocumentChunk.repository_id == repo.id) > 0


def test_interrupted_run_converges_on_retry(session, fixture_repo, embedder, monkeypatch):
    """A crash mid-batch leaves partial state; the next run repairs it."""
    from app.codeintel import indexer as indexer_mod

    ref = _ref(fixture_repo)
    calls = {"n": 0}
    original = indexer_mod.CodeIndexer._index_batch

    def crash_after_first_batch(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ConnectionError("database connection dropped")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(indexer_mod, "FILE_BATCH", 5)
    monkeypatch.setattr(indexer_mod.CodeIndexer, "_index_batch", crash_after_first_batch)
    import pytest

    with pytest.raises(ConnectionError):
        CodeIndexer(session, embedder).index(ref)
    session.rollback()
    assert 0 < _count(session, Resource, Resource.repository_id.isnot(None)) < 16

    monkeypatch.setattr(indexer_mod.CodeIndexer, "_index_batch", original)
    stats = CodeIndexer(session, embedder).index(ref)
    assert stats.outcome == "indexed"
    assert _count(session, Resource, Resource.repository_id.isnot(None)) == 16
    dupes = session.execute(
        select(Resource.identifier, func.count()).where(Resource.repository_id.isnot(None))
        .group_by(Resource.identifier).having(func.count() > 1)
    ).all()
    assert dupes == []
