"""Fixtures for the code-intelligence test suite.

Database-backed tests run against SQLite always and against PostgreSQL +
pgvector when ``PHAROS_TEST_DATABASE_URL`` points at a scratch database
(CI provides one). The PostgreSQL schema is built with the real Alembic
migrations, so those tests also prove the migrations work from scratch.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

FIXTURE_REPO = Path(__file__).resolve().parents[1] / "fixtures" / "tinyshop"
BACKEND_DIR = Path(__file__).resolve().parents[2]
PG_URL = os.getenv("PHAROS_TEST_DATABASE_URL")


def _git(cwd: Path, *args: str) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


class FixtureRepo:
    """A throwaway git repository seeded with the tinyshop fixture."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def commit(self, message: str = "change") -> str:
        _git(self.path, "add", "-A")
        _git(self.path, "commit", "-q", "--allow-empty", "-m", message)
        return _git(self.path, "rev-parse", "HEAD").strip()

    def write(self, rel: str, content: str | bytes) -> None:
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")

    def remove(self, rel: str) -> None:
        (self.path / rel).unlink()

    @property
    def head(self) -> str:
        return _git(self.path, "rev-parse", "HEAD").strip()


@pytest.fixture
def fixture_repo(tmp_path) -> FixtureRepo:
    path = tmp_path / "tinyshop"
    shutil.copytree(FIXTURE_REPO, path)
    _git(path, "init", "-q", "-b", "main")
    repo = FixtureRepo(path)
    repo.commit("initial")
    return repo


def _reset_postgres(url: str) -> None:
    from alembic.config import Config

    from alembic import command

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    cfg = Config(str(BACKEND_DIR / "config" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    # Hand Alembic the connection explicitly (env.py supports this): the
    # global conftest patches get_settings() to an in-memory SQLite URL.
    engine = create_engine(url)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    engine.dispose()


@pytest.fixture(params=["sqlite", "postgresql"])
def db_url(request, tmp_path) -> str:
    if request.param == "sqlite":
        return f"sqlite:///{tmp_path / 'pharos-test.db'}"
    if not PG_URL:
        pytest.skip("PHAROS_TEST_DATABASE_URL not set")
    from app.shared.db_url import normalize_database_url

    url = normalize_database_url(PG_URL, async_driver=False)
    _reset_postgres(url)
    return url


@pytest.fixture
def engine(db_url, monkeypatch):
    """Engine + session factory, also installed as the app's global database."""
    from app.database import models
    from app.shared import database

    eng = create_engine(db_url)
    if eng.dialect.name == "sqlite":
        models.Base.metadata.create_all(eng)
    factory = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "sync_engine", eng)
    monkeypatch.setattr(database, "SessionLocal", factory)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as s:
        yield s


@pytest.fixture
def embedder():
    from app.codeintel.embeddings import HashEmbedder

    return HashEmbedder()


@pytest.fixture
def indexed(session, fixture_repo, embedder):
    """The fixture repository indexed once; returns (RepoRef, IndexStats)."""
    from app.codeintel.git_source import parse_repo_spec
    from app.codeintel.indexer import CodeIndexer

    ref = parse_repo_spec(str(fixture_repo.path), allowed_hosts=[], allow_local=True)
    stats = CodeIndexer(session, embedder).index(ref)
    return ref, stats


ADMIN_TOKEN = "a" * 40
READ_TOKEN = "r" * 40


@pytest.fixture
def codeintel_settings(test_settings, monkeypatch):
    """Hash embeddings + github-only allowlist, visible through both the
    patched ``get_settings`` (global conftest) and the environment."""
    from app.codeintel import embeddings

    monkeypatch.setenv("EMBEDDING_BACKEND", "hash")
    monkeypatch.setenv("CODEINTEL_ALLOWED_GIT_HOSTS", '["github.com"]')
    monkeypatch.setattr(test_settings, "EMBEDDING_BACKEND", "hash")
    monkeypatch.setattr(test_settings, "CODEINTEL_ALLOWED_GIT_HOSTS", ["github.com"])
    monkeypatch.setattr(test_settings, "MCP_ALLOWED_HOSTS", ["testserver"])
    # Modules hold whatever get_settings they imported: the original
    # lru-cached function, or a *previous test's* patched closure (the global
    # conftest patches the attribute per test). Point every module at this
    # test's settings.
    import sys

    for module in list(sys.modules.values()):
        if getattr(module, "__name__", "").startswith("app.") and callable(getattr(module, "get_settings", None)):
            monkeypatch.setattr(module, "get_settings", lambda: test_settings, raising=False)
    embeddings.reset_embedder_cache()
    yield test_settings
    embeddings.reset_embedder_cache()


@pytest.fixture
def api(engine, monkeypatch, codeintel_settings):
    """TestClient against the real app, real auth middleware, test database."""
    from fastapi.testclient import TestClient

    from app import create_app
    from app.shared.database import get_sync_db

    monkeypatch.delenv("TEST_AUTH_BYPASS", raising=False)
    monkeypatch.setenv("PHAROS_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("PHAROS_READ_TOKEN", READ_TOKEN)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _db():
        with factory() as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_sync_db] = _db
    with TestClient(app) as client:
        yield client


def auth(token: str = ADMIN_TOKEN) -> dict:
    return {"Authorization": f"Bearer {token}"}
