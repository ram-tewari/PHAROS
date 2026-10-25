"""Legacy parent-child search (``/api/search/advanced``) on its real backend.

The SQL is PostgreSQL + pgvector only; the legacy suite runs on in-memory
SQLite, so its parent-child tests are strict xfails that point here.
"""

import logging
import uuid

import pytest

from app.database.models import DocumentChunk, Resource
from app.modules.search.service import SearchService


def _resource_with_chunks(session, title, direction, n=5):
    vec = [0.0] * 768
    vec[direction] = 1.0
    r = Resource(id=uuid.uuid4(), title=title, type="article", embedding=vec)
    session.add(r)
    session.flush()
    for i in range(n):
        session.add(DocumentChunk(resource_id=r.id, content=f"{title} chunk {i}", chunk_index=i))
    session.commit()
    return r, vec


def test_parent_child_search(session):
    if session.get_bind().dialect.name != "postgresql":
        pytest.skip("parent-child search is PostgreSQL + pgvector only (see test below for SQLite)")
    near, query_vec = _resource_with_chunks(session, "ML Research", 0)
    _resource_with_chunks(session, "Cooking", 1)
    svc = SearchService(session)
    svc._embed_query = lambda q: query_vec

    results = svc.parent_child_search("neural networks", top_k=1, context_window=1)

    assert len(results) == 1
    assert results[0]["parent_resource"].id == near.id
    assert results[0]["chunk"].resource_id == near.id
    assert len(results[0]["surrounding_chunks"]) >= 1
    assert '"ML Research' in svc.parent_child_search_json("neural networks", top_k=1, context_window=1)


def test_parent_child_search_says_why_it_is_empty_on_sqlite(session, caplog):
    if session.get_bind().dialect.name == "postgresql":
        pytest.skip("SQLite behaviour")
    _resource_with_chunks(session, "ML Research", 0)
    with caplog.at_level(logging.WARNING):
        assert SearchService(session).parent_child_search("x") == []
    assert "requires PostgreSQL + pgvector" in caplog.text
