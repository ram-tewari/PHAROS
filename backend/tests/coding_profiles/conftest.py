"""
Self-contained fixtures for coding profiles tests.
Avoids the root conftest which has stale imports.
"""

import os
os.environ["TESTING"] = "true"

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.shared.database import Base, get_sync_db, get_db
from app import create_app
from app.database.models import (  # noqa: F401 — register all tables
    CodingProfile,
    ProposedRule,
    RuleStatus,
    User,
    Resource,
    Collection,
    CollectionResource,
    Annotation,
    Citation,
    GraphEdge,
    GraphEmbedding,
    DiscoveryHypothesis,
    UserProfile,
    UserInteraction,
    AuthoritySubject,
    AuthorityCreator,
    AuthorityPublisher,
    ClassificationCode,
    ModelVersion,
    ABTestExperiment,
    PlanningSession,
    DeveloperProfileRecord,
)


@pytest.fixture(scope="function")
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    @event.listens_for(eng, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture(scope="function")
def db(engine) -> Session:
    factory = sessionmaker(
        autocommit=False, autoflush=False, bind=engine, expire_on_commit=False,
    )
    session = factory()
    Base.metadata.create_all(bind=engine)
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def seed_user(db: Session) -> User:
    from uuid import UUID

    user = User(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        email="test@example.com",
        username="testuser",
        hashed_password="fakehash_for_testing",
        full_name="Test User",
        role="user",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture(scope="function")
def client(db: Session, seed_user: User) -> TestClient:
    """
    Create a minimal FastAPI app with just the patterns router.

    Uses a lightweight app to avoid broken middleware/auth imports that
    exist in the main app during the ongoing pharos-ronin integration.
    """
    from fastapi import FastAPI
    from app.modules.patterns.router import patterns_router

    app = FastAPI()
    app.include_router(patterns_router)

    def override_sync():
        try:
            yield db
        finally:
            pass

    async def override_async():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_sync_db] = override_sync
    app.dependency_overrides[get_db] = override_async

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
