"""Migration 0005: the new memory_items columns arrive with defaults and leave without touching old rows."""

import uuid

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from tests.codeintel.conftest import BACKEND_DIR, PG_URL

NEW = {"predicate", "holdout", "strength", "served", "complied", "helped"}


def _cfg(conn):
    cfg = Config(str(BACKEND_DIR / "config" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["connection"] = conn
    return cfg


@pytest.fixture(params=["sqlite", "postgresql"])
def blank(request, tmp_path):
    if request.param == "sqlite":
        eng = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    else:
        if not PG_URL:
            pytest.skip("PHAROS_TEST_DATABASE_URL not set")
        from app.shared.db_url import normalize_database_url

        eng = create_engine(normalize_database_url(PG_URL, async_driver=False))
        with eng.begin() as c:
            c.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
    yield eng
    eng.dispose()


def _columns(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("memory_items")}


def test_upgrade_keeps_existing_items_and_downgrade_removes_only_the_new_columns(blank):
    with blank.begin() as conn:
        command.upgrade(_cfg(conn), "0004_learning")
    assert not NEW & _columns(blank)
    repo_id, item_id = uuid.uuid4(), uuid.uuid4()
    hexed = (repo_id.hex, item_id.hex) if blank.dialect.name == "sqlite" else (str(repo_id), str(item_id))
    with blank.begin() as conn:
        conn.execute(text("INSERT INTO repositories (id, url, name, metadata, total_files, total_lines, source_type, "
                          "index_status) VALUES (:id, 'https://example.com/o/r', 'r', '{}', 0, 0, 'git', 'ready')"),
                     {"id": hexed[0]})
        conn.execute(text("INSERT INTO memory_items (id, repository_id, key, kind, title, body, evidence, support, "
                          "confidence, source, tier, status, learned_at_commit) VALUES (:id, :repo, 'naming/x', "
                          "'convention', 't', 'b', '[]', 1, 1.0, 'code', 'L1', 'active', 'c')"),
                     {"id": hexed[1], "repo": hexed[0]})
    with blank.begin() as conn:
        command.upgrade(_cfg(conn), "head")
        row = conn.execute(text("SELECT predicate, holdout, strength, served, complied, helped, status "
                                "FROM memory_items")).one()
    assert NEW <= _columns(blank)
    assert tuple(row) == (None, None, None, 0, 0, 0, "active")
    with blank.begin() as conn:
        command.downgrade(_cfg(conn), "0004_learning")
        assert conn.execute(text("SELECT key, status FROM memory_items")).one() == ("naming/x", "active")
    assert not NEW & _columns(blank)
