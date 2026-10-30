"""Migrations: clean upgrade, downgrade, and no drift between models and migrations."""

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from tests.codeintel.conftest import BACKEND_DIR, PG_URL


def _cfg(conn):
    cfg = Config(str(BACKEND_DIR / "config" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["connection"] = conn
    return cfg


@pytest.fixture(params=["sqlite", "postgresql"])
def blank_engine(request, tmp_path):
    if request.param == "sqlite":
        eng = create_engine(f"sqlite:///{tmp_path / 'migrate.db'}")
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


def test_upgrade_downgrade_upgrade_from_scratch(blank_engine):
    with blank_engine.begin() as conn:
        command.upgrade(_cfg(conn), "head")
    tables = set(inspect(blank_engine).get_table_names())
    assert {"repositories", "resources", "document_chunks", "code_edges", "ingestion_jobs", "learning_jobs",
            "memory_items", "memory_skills", "repo_briefs", "memory_ledger"} <= tables

    with blank_engine.begin() as conn:
        command.downgrade(_cfg(conn), "base")
    assert set(inspect(blank_engine).get_table_names()) <= {"alembic_version"}

    with blank_engine.begin() as conn:
        command.upgrade(_cfg(conn), "head")
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0004_learning"


def test_models_match_migrations(blank_engine):
    """`alembic check`: the ORM and the migration chain describe the same schema."""
    with blank_engine.begin() as conn:
        command.upgrade(_cfg(conn), "head")
        command.check(_cfg(conn))


def test_postgres_has_vector_and_fulltext_indexes(blank_engine):
    if blank_engine.dialect.name != "postgresql":
        pytest.skip("pgvector / GIN indexes are PostgreSQL-only")
    with blank_engine.begin() as conn:
        command.upgrade(_cfg(conn), "head")
        rows = dict(conn.execute(text(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename IN ('document_chunks', 'resources')"
        )).all())
        coltype = conn.execute(text(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = 'document_chunks'::regclass AND attname = 'embedding'"
        )).scalar_one()
    assert coltype == "vector(768)"
    assert "hnsw" in rows["idx_chunks_embedding_hnsw"]
    assert "hnsw" in rows["idx_resources_embedding_hnsw"]
    assert "gin" in rows["idx_chunks_search_text_fts"] and "to_tsvector" in rows["idx_chunks_search_text_fts"]
