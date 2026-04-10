"""
Anti-Gaslighting Test Suite - Fresh Fixtures

IMPORTANT: This file is built from scratch with NO imports from legacy test code.
All fixtures are self-contained and independent.
"""

# Set TESTING environment variable BEFORE importing app
# This prevents the app from initializing its own database connection
import os

os.environ["TESTING"] = "true"

import logging
import sys
from pathlib import Path
import pytest
import pytest_asyncio
from typing import Generator
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient

# Add deployment directory to Python path for worker module imports
deployment_dir = Path(__file__).parent.parent / "deployment"
if str(deployment_dir) not in sys.path:
    sys.path.insert(0, str(deployment_dir))

logger = logging.getLogger(__name__)

# Direct imports from application code only
from app.shared.database import Base
from app.shared.event_bus import event_bus

# Import create_app instead of app to avoid module-level initialization
from app import create_app

# Import all models to register them with SQLAlchemy
# This ensures all tables are created in test database
from app.database.models import (  # noqa: F401
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
    RecommendationFeedback,
    TaxonomyNode,
    ResourceTaxonomy,
    AuthoritySubject,
    AuthorityCreator,
    AuthorityPublisher,
    User,
    ClassificationCode,
    ModelVersion,
    ABTestExperiment,
    PlanningSession,
)
from app.modules.auth.model import OAuthAccount  # noqa: F401


# ============================================================================
# Database Fixtures (Fresh Implementation)
# ============================================================================


@pytest.fixture(scope="function")
def db_engine():
    """
    Create a fresh in-memory SQLite engine for each test.

    This fixture is function-scoped to ensure complete isolation.
    Uses StaticPool to ensure all connections share the same in-memory database.
    """
    from sqlalchemy.pool import StaticPool
    from sqlalchemy import event

    # Use StaticPool to ensure all connections use the same in-memory database
    # This is critical for testing with dependency injection
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # All connections share the same database
        echo=False,
    )

    # Enable foreign key constraints for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create all tables
    Base.metadata.create_all(bind=engine)

    yield engine

    # Drop all tables after test
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """
    Create a fresh database session for each test.

    Provides complete isolation - each test gets its own session
    with a fresh database state.
    """
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_engine,
        expire_on_commit=False,  # Prevent lazy loading errors after commit
    )

    session = TestingSessionLocal()

    # Explicitly ensure all tables exist before yielding session
    # This is critical for in-memory SQLite databases
    Base.metadata.create_all(bind=db_engine)

    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest_asyncio.fixture(scope="function")
async def async_db_engine():
    """
    Create an async SQLite engine for auth tests.

    Uses aiosqlite for async database operations.
    """
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool

    # Create async engine with aiosqlite
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_db_session(async_db_engine):
    """
    Create an async database session for auth tests.

    Auth module uses async SQLAlchemy operations.
    """
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker

    AsyncSessionLocal = sessionmaker(
        async_db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def async_client(async_db_session):
    """
    Create an AsyncClient with async database session for integration tests.

    This provides a true async HTTP client for testing async endpoints.
    Uses httpx.AsyncClient with ASGITransport.

    In test mode, modules are not auto-registered. Tests that need specific
    modules should register them manually using app.include_router().
    """
    from httpx import AsyncClient, ASGITransport
    from app.shared.database import get_db, get_sync_db
    from fastapi import APIRouter

    # Create app instance for testing (database already initialized by fixture)
    app = create_app()

    # Note: Modules are now auto-registered in create_app(), no need to manually register

    async def override_get_async_db():
        try:
            yield async_db_session
        finally:
            pass

    def override_get_sync_db():
        try:
            # For sync endpoints, we need to provide a sync session
            # This is a workaround - ideally all endpoints should be async
            yield async_db_session
        finally:
            pass

    # Override both database dependencies
    app.dependency_overrides[get_db] = override_get_async_db
    app.dependency_overrides[get_sync_db] = override_get_sync_db

    # Create AsyncClient with ASGITransport
    # Pass Origin header so CSRF middleware allows state-changing requests.
    # The httpx AsyncClient base_url is http://test, so Origin must match.
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test"},
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ============================================================================
# Settings Fixture (Phase 17 - Real Settings for Tests)
# ============================================================================


@pytest.fixture(scope="function")
def test_settings():
    """
    Provide real Settings instance with test values.

    This fixture replaces all Settings mocking with real Settings instances
    configured via environment variables. This ensures tests work with actual
    Settings behavior rather than mocked objects.

    Returns:
        Settings instance configured for testing
    """
    import os
    from app.config.settings import Settings

    # Store original environment
    original_env = {}
    test_env_vars = {
        "TEST_MODE": "true",
        "JWT_SECRET_KEY": "test-secret-key-for-testing-only-min-32-chars",
        "JWT_ALGORITHM": "HS256",
        "JWT_ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "JWT_REFRESH_TOKEN_EXPIRE_DAYS": "7",
        "DATABASE_URL": "sqlite:///:memory:",
        "POSTGRES_SERVER": "localhost",
        "POSTGRES_USER": "test_user",
        "POSTGRES_PASSWORD": "test_password",
        "POSTGRES_DB": "test_db",
        "POSTGRES_PORT": "5432",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "RATE_LIMIT_FREE_TIER": "100",
        "RATE_LIMIT_PREMIUM_TIER": "1000",
        "RATE_LIMIT_ADMIN_TIER": "10000",
        "CHUNK_ON_RESOURCE_CREATE": "false",
        "GRAPH_EXTRACTION_ENABLED": "true",
        "SYNTHETIC_QUESTIONS_ENABLED": "false",
        "DEFAULT_RETRIEVAL_STRATEGY": "parent-child",
        "ENV": "dev",
        "MODE": "CLOUD",
        "QUEUE_SIZE": "10",
        "TASK_TTL": "86400",
        "WORKER_POLL_INTERVAL": "2",
    }

    # Set test environment variables
    for key, value in test_env_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    # Clear the settings cache to force reload
    from app.config.settings import get_settings

    get_settings.cache_clear()

    # Create settings instance - bypass validation for tests
    settings = Settings()

    yield settings

    # Restore original environment
    for key, value in original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    # Clear cache again to restore original settings
    get_settings.cache_clear()


@pytest.fixture(scope="function", autouse=True)
def override_get_settings(test_settings):
    """
    Override get_settings dependency with test settings.

    This autouse fixture ensures all tests use the test_settings instance
    when calling get_settings(). It clears the cache and sets up the override
    before each test, and cleans up after each test.
    """
    from app.config.settings import get_settings, Settings

    # Clear cache to ensure fresh settings
    get_settings.cache_clear()

    # Store original function
    original_get_settings = get_settings

    # Create a wrapper that returns test_settings
    def _get_test_settings() -> Settings:
        return test_settings

    # We can't directly override lru_cache, but we can patch the module
    import app.config.settings as settings_module

    original_cached = settings_module.get_settings

    # Replace with our test version
    settings_module.get_settings = _get_test_settings

    yield test_settings

    # Restore original
    settings_module.get_settings = original_cached
    get_settings.cache_clear()


@pytest.fixture(scope="function")
def mock_redis():
    """
    Mock Redis client for rate limiting tests.

    Returns a MagicMock that simulates Redis operations.
    """
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.get.return_value = None
    mock_client.incr.return_value = 1
    mock_client.expire.return_value = True
    mock_client.ttl.return_value = 60
    mock_client.pipeline.return_value = mock_client
    mock_client.execute.return_value = [1, True]
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None

    return mock_client


# ============================================================================
# Authentication Fixtures (Phase 17)
# ============================================================================


@pytest.fixture(scope="function")
def test_user(db_session: Session) -> User:
    """
    Create a test user for authentication.

    This user is created before the test client is initialized,
    ensuring it exists when authentication dependencies are called.

    Uses a fixed UUID that matches the one returned by _get_current_user_id()
    in the recommendation router.
    """
    from uuid import UUID
    from app.shared.security import get_password_hash

    # Use the same fixed UUID as _get_current_user_id returns
    user = User(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        email="test@example.com",
        username="testuser",
        hashed_password=get_password_hash("testpassword123"),
        full_name="Test User",
        role="user",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_token(test_user: User) -> str:
    """
    Generate a valid JWT access token for the test user.

    Returns:
        Valid JWT token string that can be used in Authorization headers
    """
    from app.shared.security import create_access_token

    token = create_access_token(
        data={
            "username": test_user.username,
            "user_id": str(test_user.id),
        }
    )
    return token


@pytest.fixture(scope="function")
def auth_headers(auth_token: str) -> dict:
    """
    Generate authentication headers with Bearer token.

    Returns:
        Dict with Authorization header ready to use in requests
    """
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="function")
def bypass_auth(db_session: Session, test_user: User) -> TestClient:
    """
    Fixture to bypass authentication in tests via dependency override.

    This fixture creates a TestClient with authentication bypassed,
    allowing tests to access protected endpoints without JWT tokens.

    Usage:
        def test_protected_endpoint(bypass_auth):
            response = bypass_auth.get("/protected-endpoint")
            assert response.status_code == 200

    Note: This fixture should be used when you need to test protected
    endpoints without providing valid JWT tokens. For testing actual
    authentication flows, use authenticated_client instead.

    This fixture:
    - Creates a test app with dependency overrides
    - Overrides get_current_user to return a mock user
    - Overrides module-specific auth dependencies (_get_current_user_id)
    - Returns a TestClient ready for use in tests
    """
    from app.shared.security import get_current_user, TokenData
    from app.shared.database import get_sync_db, get_db

    # Create app instance for testing
    app = create_app()

    def override_get_sync_db():
        try:
            yield db_session
        finally:
            pass

    async def override_get_async_db():
        try:
            yield db_session
        finally:
            pass

    async def mock_get_current_user(token: str = None) -> TokenData:
        """Mock get_current_user that returns test user without token validation."""
        return TokenData(
            user_id=str(test_user.id),
            username=test_user.username,
            scopes=[],
            tier="free",
        )

    # Override dependencies
    app.dependency_overrides[get_sync_db] = override_get_sync_db
    app.dependency_overrides[get_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = mock_get_current_user

    # Also override module-specific auth dependencies
    try:
        from app.modules.recommendations.router import _get_current_user_id

        app.dependency_overrides[_get_current_user_id] = lambda db=None: test_user.id
    except ImportError:
        pass

    try:
        from app.modules.annotations.router import (
            _get_current_user_id as annotations_get_user,
        )

        app.dependency_overrides[annotations_get_user] = lambda: str(test_user.id)
    except ImportError:
        pass

    # Create and return the test client
    # Pass X-Test-Auth-Bypass header so the auth middleware allows the request
    # through to the dependency-overridden handlers.
    # Pass Origin header so the CSRF middleware allows state-changing requests.
    with TestClient(
        app,
        headers={
            "X-Test-Auth-Bypass": "true",
            "Origin": "http://testserver",
        },
    ) as test_client:
        yield test_client

    # Cleanup
    app.dependency_overrides.clear()


# ============================================================================
# FastAPI TestClient Fixture (Fresh Implementation)
# ============================================================================


@pytest.fixture(scope="function")
def client(db_session: Session, test_user: User) -> Generator[TestClient, None, None]:
    """
    Create a TestClient with database dependency override.

    Overrides the app's get_db dependency to use our test session.
    Also overrides authentication to use the test_user.

    NOTE: This client bypasses authentication middleware for convenience.
    Use authenticated_client if you need to test with actual JWT tokens.

    In test mode, modules are not auto-registered. Tests that need specific
    modules should register them manually using app.include_router().
    """
    from app.shared.database import get_sync_db, get_db

    # Create app instance for testing
    app = create_app()

    # Note: Modules are now auto-registered in create_app(), no need to manually register

    def override_get_sync_db():
        try:
            yield db_session
        finally:
            pass

    async def override_get_async_db():
        try:
            yield db_session
        finally:
            pass

    # Override both sync and async database dependencies
    app.dependency_overrides[get_sync_db] = override_get_sync_db
    app.dependency_overrides[get_db] = override_get_async_db

    # Override authentication dependencies for modules that need it
    try:
        from app.modules.recommendations.router import _get_current_user_id

        # Capture the user ID value to avoid lazy loading issues
        user_id_value = test_user.id
        app.dependency_overrides[_get_current_user_id] = lambda db=None: user_id_value
    except ImportError:
        pass

    try:
        from app.modules.annotations.router import (
            _get_current_user_id as annotations_get_user,
        )

        app.dependency_overrides[annotations_get_user] = lambda: str(test_user.id)
    except ImportError:
        pass

    # Pass X-Test-Auth-Bypass header so the auth middleware allows requests
    # through to the dependency-overridden handlers. This matches the behavior
    # of the bypass_auth fixture and is required because the auth middleware
    # runs before dependency injection.
    # Pass Origin header so the CSRF middleware allows state-changing requests.
    with TestClient(
        app,
        headers={
            "X-Test-Auth-Bypass": "true",
            "Origin": "http://testserver",
        },
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def authenticated_client(
    db_session: Session, test_user: User, auth_headers: dict
) -> Generator[TestClient, None, None]:
    """
    Create a TestClient that uses actual JWT authentication.

    This client does NOT bypass authentication middleware.
    Use this when you need to test authentication flows.

    Usage:
        def test_with_auth(authenticated_client, auth_headers):
            response = authenticated_client.get("/protected", headers=auth_headers)
            assert response.status_code == 200
    """
    from app.shared.database import get_sync_db, get_db

    # Create app instance for testing
    app = create_app()

    def override_get_sync_db():
        try:
            yield db_session
        finally:
            pass

    async def override_get_async_db():
        try:
            yield db_session
        finally:
            pass

    # Only override database dependencies, not authentication
    app.dependency_overrides[get_sync_db] = override_get_sync_db
    app.dependency_overrides[get_db] = override_get_async_db

    # Pass Origin header so CSRF middleware allows state-changing requests.
    with TestClient(app, headers={"Origin": "http://testserver"}) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def unauthenticated_client(db_session: Session) -> Generator[TestClient, None, None]:
    """
    Create a TestClient without any authentication.

    Use this when testing endpoints that should work without authentication
    or when testing authentication error handling.
    """
    from app.shared.database import get_sync_db, get_db

    # Create app instance for testing
    app = create_app()

    def override_get_sync_db():
        try:
            yield db_session
        finally:
            pass

    async def override_get_async_db():
        try:
            yield db_session
        finally:
            pass

    # Only override database dependencies
    app.dependency_overrides[get_sync_db] = override_get_sync_db
    app.dependency_overrides[get_db] = override_get_async_db

    # Pass Origin header so CSRF middleware allows state-changing requests.
    with TestClient(app, headers={"Origin": "http://testserver"}) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ============================================================================
# Event Bus Fixtures (Fresh Implementation)
# ============================================================================


@pytest.fixture(scope="function")
def mock_event_bus():
    """
    Create a mock/spy for the event bus emit method.

    This allows tests to verify that events are emitted without
    actually triggering event handlers.

    Usage:
        def test_resource_creation(client, mock_event_bus):
            response = client.post("/resources", json={...})

            # Verify event was emitted
            mock_event_bus.assert_called_with(
                "resource.created",
                {"resource_id": "...", ...}
            )
    """
    original_emit = event_bus.emit
    mock_emit = MagicMock(wraps=original_emit)

    # Track emitted events for tests that need to inspect them
    emitted_events = []

    def track_emit(event_name, data, **kwargs):
        # Create a simple event object
        class Event:
            def __init__(self, name, data):
                self.name = name
                self.data = data

        emitted_events.append(Event(event_name, data))
        return original_emit(event_name, data, **kwargs)

    mock_emit.side_effect = track_emit
    mock_emit.emitted_events = emitted_events

    with patch.object(event_bus, "emit", mock_emit):
        yield mock_emit


@pytest.fixture(scope="function")
def clean_event_bus():
    """
    Provide a clean event bus state for each test.

    Clears all handlers and history before and after the test.
    """
    # Clear before test
    event_bus.clear_handlers()
    event_bus.clear_history()
    event_bus.reset_metrics()

    yield event_bus

    # Clear after test
    event_bus.clear_handlers()
    event_bus.clear_history()
    event_bus.reset_metrics()


# ============================================================================
# Test User Fixture
# ============================================================================
# ML Inference Mocking Fixtures (Task 2.1)
# ============================================================================


@pytest.fixture(scope="session")
def mock_ml_inference():
    """
    Mock ML model inference for all tests.

    Mocks:
        - sentence_transformers.SentenceTransformer.encode
        - transformers.pipeline.__call__

    Returns:
        Dict with mock objects for test customization
    """
    # Create mock objects without importing the actual modules
    mock_encoder = MagicMock()
    mock_encoder.encode.return_value = [[0.1, 0.2, 0.3]]  # Default embedding

    mock_pipe = MagicMock()
    mock_pipe.return_value = [{"label": "LABEL_0", "score": 0.95}]

    # Return mocks that can be used to patch in individual tests
    return {"sentence_transformer": mock_encoder, "pipeline": mock_pipe}


# ============================================================================
# Test Data Factory Fixtures (Fresh Implementation)
# ============================================================================


@pytest.fixture(scope="function")
def create_test_resource(db_session: Session):
    """
    Factory fixture for creating test resources.

    Returns a function that creates resources with sensible defaults.

    Note: The embedding field is stored as Text in the database, so we
    serialize list embeddings to JSON strings for SQLite compatibility.
    """
    import json

    def _create_resource(**kwargs):
        defaults = {
            "title": "Test Resource",
            "description": "A test resource for unit testing",
            "source": "https://example.com/test",
            "ingestion_status": "pending",
            "quality_score": 0.0,
        }
        defaults.update(kwargs)

        # Serialize embedding to JSON string if it's a list
        # Resource.embedding column is Text type, not JSON
        if "embedding" in defaults and isinstance(defaults["embedding"], list):
            defaults["embedding"] = json.dumps(defaults["embedding"])

        resource = Resource(**defaults)
        db_session.add(resource)
        db_session.commit()
        db_session.refresh(resource)

        return resource

    return _create_resource


@pytest.fixture(scope="function")
def create_test_category(db_session: Session):
    """
    Factory fixture for creating test taxonomy categories.

    Returns a function that creates and returns a TaxonomyNode instance.
    """

    def _create_category(name: str = "Test Category", parent_id=None, **kwargs):
        defaults = {
            "name": name,
            "slug": name.lower().replace(" ", "-"),
            "parent_id": parent_id,
            "level": 0,
            "path": f"/{name.lower().replace(' ', '-')}",
            "is_leaf": True,
            "allow_resources": True,
        }
        defaults.update(kwargs)

        category = TaxonomyNode(**defaults)
        db_session.add(category)
        db_session.commit()
        db_session.refresh(category)

        return category

    return _create_category


@pytest.fixture(scope="function")
def create_test_collection(db_session: Session):
    """
    Factory fixture for creating test collections.

    Returns a function that creates and returns a Collection instance.
    """

    def _create_collection(
        name: str = "Test Collection",
        description: str = None,
        owner_id: str = "test_user",
        **kwargs,
    ):
        defaults = {
            "name": name,
            "description": description,
            "owner_id": owner_id,
            "visibility": "private",
        }
        defaults.update(kwargs)

        collection = Collection(**defaults)
        db_session.add(collection)
        db_session.commit()
        db_session.refresh(collection)

        return collection

    return _create_collection


@pytest.fixture(scope="function")
def create_test_annotation(db_session: Session, create_test_resource):
    """
    Factory fixture for creating test annotations.

    Returns a function that creates and returns an Annotation instance.
    """

    def _create_annotation(
        resource_id=None,
        user_id: str = "test_user",
        highlighted_text: str = "Test annotation",
        start_offset: int = 0,
        end_offset: int = 10,
        **kwargs,
    ):
        # Create a test resource if resource_id not provided
        if resource_id is None:
            resource = create_test_resource()
            resource_id = resource.id

        defaults = {
            "resource_id": resource_id,
            "user_id": user_id,
            "highlighted_text": highlighted_text,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "color": "#FFFF00",
        }
        defaults.update(kwargs)

        annotation = Annotation(**defaults)
        db_session.add(annotation)
        db_session.commit()
        db_session.refresh(annotation)

        return annotation

    return _create_annotation


@pytest.fixture(scope="function")
def mock_embedding_service(mock_ml_inference):
    """
    Mock embedding service that uses mock_ml_inference.

    Returns:
        Mock embedding service with generate_embedding method
    """
    mock_service = MagicMock()
    mock_service.generate_embedding.return_value = [0.1, 0.2, 0.3]
    return mock_service


# ============================================================================
# Cleanup Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def cleanup_after_test(db_session: Session):
    """
    Automatic cleanup after each test.

    This runs after every test to ensure clean state.
    """
    yield

    # Rollback any uncommitted changes
    db_session.rollback()


# ============================================================================
# Celery Fixtures (For Task Testing)
# ============================================================================


@pytest.fixture(scope="function")
def celery_eager_mode():
    """
    Configure Celery to run tasks synchronously (eager mode) for testing.

    In eager mode, tasks execute immediately in the same process,
    making them easier to test without requiring a running worker.
    """
    from app.tasks.celery_app import celery_app

    # Store original configuration
    original_always_eager = celery_app.conf.task_always_eager
    original_eager_propagates = celery_app.conf.task_eager_propagates
    original_result_backend = celery_app.conf.result_backend

    # Enable eager mode and disable result backend
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    celery_app.conf.result_backend = None  # Disable Redis backend for testing

    yield celery_app

    # Restore original configuration
    celery_app.conf.task_always_eager = original_always_eager
    celery_app.conf.task_eager_propagates = original_eager_propagates
    celery_app.conf.result_backend = original_result_backend
