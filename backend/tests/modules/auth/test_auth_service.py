"""Unit tests for authentication service functions.

Tests cover:
- User authentication with username/password
- User retrieval by ID
- OAuth user creation and linking
"""

import pytest
import pytest_asyncio
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import User
from app.modules.auth.model import OAuthAccount
from app.modules.auth.service import (
    authenticate_user,
    get_user_by_id,
    get_or_create_oauth_user,
)
from app.shared.security import get_password_hash
from app.shared.database import Base


# ============================================================================
# Async Database Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def async_engine():
    """Create async SQLite engine for testing."""
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

    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def async_db_session(async_engine):
    """Create async database session for testing."""
    async_session_maker = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def test_user(async_db_session):
    """Create a test user for service tests."""
    user = User(
        id=uuid.uuid4(),
        username="serviceuser",
        email="service@example.com",
        hashed_password=get_password_hash("servicepass123"),
        tier="free",
        is_active=True,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def inactive_user(async_db_session):
    """Create an inactive test user."""
    user = User(
        id=uuid.uuid4(),
        username="inactiveservice",
        email="inactive@service.com",
        hashed_password=get_password_hash("inactivepass123"),
        tier="free",
        is_active=False,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)
    return user


# ============================================================================
# authenticate_user() Tests
# ============================================================================


@pytest.mark.asyncio
async def test_authenticate_user_with_valid_username(async_db_session, test_user):
    """Test authenticating user with valid username and password."""
    result = await authenticate_user(
        db=async_db_session, username="serviceuser", password="servicepass123"
    )

    assert result is not None
    assert result.id == test_user.id
    assert result.username == "serviceuser"
    assert result.email == "service@example.com"


@pytest.mark.asyncio
async def test_authenticate_user_with_valid_email(async_db_session, test_user):
    """Test authenticating user with email instead of username."""
    result = await authenticate_user(
        db=async_db_session, username="service@example.com", password="servicepass123"
    )

    assert result is not None
    assert result.id == test_user.id
    assert result.username == "serviceuser"


@pytest.mark.asyncio
async def test_authenticate_user_with_invalid_password(async_db_session, test_user):
    """Test authentication fails with incorrect password."""
    result = await authenticate_user(
        db=async_db_session, username="serviceuser", password="wrongpassword"
    )

    assert result is None


@pytest.mark.asyncio
async def test_authenticate_user_with_nonexistent_username(async_db_session):
    """Test authentication fails with non-existent username."""
    result = await authenticate_user(
        db=async_db_session, username="nonexistent", password="somepassword"
    )

    assert result is None


@pytest.mark.asyncio
async def test_authenticate_inactive_user(async_db_session, inactive_user):
    """Test authentication fails for inactive user."""
    result = await authenticate_user(
        db=async_db_session, username="inactiveservice", password="inactivepass123"
    )

    assert result is None


# ============================================================================
# get_user_by_id() Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_user_by_id_success(async_db_session, test_user):
    """Test retrieving user by valid ID."""
    result = await get_user_by_id(db=async_db_session, user_id=test_user.id)

    assert result is not None
    assert result.id == test_user.id
    assert result.username == "serviceuser"
    assert result.email == "service@example.com"


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(async_db_session):
    """Test retrieving user with non-existent ID."""
    random_uuid = uuid.uuid4()
    result = await get_user_by_id(db=async_db_session, user_id=random_uuid)

    assert result is None


@pytest.mark.asyncio
async def test_get_user_by_id_returns_inactive_user(async_db_session, inactive_user):
    """Test get_user_by_id returns inactive users (no filtering)."""
    result = await get_user_by_id(db=async_db_session, user_id=inactive_user.id)

    assert result is not None
    assert result.id == inactive_user.id
    # SQLite stores boolean as integer (0 or 1)
    assert result.is_active == 0 or result.is_active is False


# ============================================================================
# get_or_create_oauth_user() Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_new_oauth_user(async_db_session):
    """Test creating new user from OAuth provider data."""
    result = await get_or_create_oauth_user(
        db=async_db_session,
        provider="google",
        provider_user_id="google123",
        email="newuser@gmail.com",
        username="New User",
    )

    assert result is not None
    assert result.username == "New User"
    assert result.email == "newuser@gmail.com"
    assert result.tier == "free"
    # SQLite stores boolean as integer (0 or 1)
    assert result.is_active == 1 or result.is_active is True

    # Verify OAuth account was created
    stmt = select(OAuthAccount).where(
        (OAuthAccount.provider == "google")
        & (OAuthAccount.provider_user_id == "google123")
    )
    oauth_result = await async_db_session.execute(stmt)
    oauth_account = oauth_result.scalar_one_or_none()

    assert oauth_account is not None
    assert oauth_account.user_id == result.id
    assert oauth_account.provider == "google"


@pytest.mark.asyncio
async def test_link_oauth_to_existing_user_by_email(async_db_session, test_user):
    """Test linking OAuth account to existing user with matching email."""
    result = await get_or_create_oauth_user(
        db=async_db_session,
        provider="github",
        provider_user_id="github456",
        email="service@example.com",  # Same as test_user
        username="GitHub User",
    )

    assert result is not None
    assert result.id == test_user.id  # Should return existing user
    assert result.username == "serviceuser"  # Original username preserved

    # Verify OAuth account was linked
    stmt = select(OAuthAccount).where(
        (OAuthAccount.provider == "github")
        & (OAuthAccount.provider_user_id == "github456")
    )
    oauth_result = await async_db_session.execute(stmt)
    oauth_account = oauth_result.scalar_one_or_none()

    assert oauth_account is not None
    assert oauth_account.user_id == test_user.id


@pytest.mark.asyncio
async def test_return_existing_oauth_user(async_db_session, test_user):
    """Test returning existing user when OAuth account already exists."""
    # First, create OAuth account
    oauth_account = OAuthAccount(
        user_id=test_user.id, provider="google", provider_user_id="google789"
    )
    async_db_session.add(oauth_account)
    await async_db_session.commit()
    await async_db_session.refresh(oauth_account)

    # Try to create again with same provider and provider_user_id
    result = await get_or_create_oauth_user(
        db=async_db_session,
        provider="google",
        provider_user_id="google789",
        email="different@email.com",  # Different email
        username="Different Name",  # Different username
    )

    assert result is not None
    assert result.id == test_user.id  # Should return existing user
    assert result.username == "serviceuser"  # Original data preserved
    assert result.email == "service@example.com"  # Original email preserved


@pytest.mark.asyncio
async def test_create_oauth_user_with_github_provider(async_db_session):
    """Test creating user from GitHub OAuth provider."""
    result = await get_or_create_oauth_user(
        db=async_db_session,
        provider="github",
        provider_user_id="12345",
        email="github@example.com",
        username="githubuser",
    )

    assert result is not None
    assert result.username == "githubuser"
    assert result.email == "github@example.com"

    # Verify OAuth account
    stmt = select(OAuthAccount).where(
        (OAuthAccount.provider == "github") & (OAuthAccount.provider_user_id == "12345")
    )
    oauth_result = await async_db_session.execute(stmt)
    oauth_account = oauth_result.scalar_one_or_none()

    assert oauth_account is not None
    assert oauth_account.provider == "github"


@pytest.mark.asyncio
async def test_oauth_user_has_random_password(async_db_session):
    """Test that OAuth users get a random hashed password."""
    result = await get_or_create_oauth_user(
        db=async_db_session,
        provider="google",
        provider_user_id="google999",
        email="oauth@example.com",
        username="OAuth User",
    )

    assert result is not None
    assert result.hashed_password is not None
    assert len(result.hashed_password) > 0
    # Password should be hashed (bcrypt hashes start with $2b$)
    assert result.hashed_password.startswith("$2b$")


@pytest.mark.asyncio
async def test_multiple_oauth_accounts_same_user(async_db_session, test_user):
    """Test linking multiple OAuth providers to same user."""
    # Link Google account
    google_result = await get_or_create_oauth_user(
        db=async_db_session,
        provider="google",
        provider_user_id="google111",
        email="service@example.com",
        username="Google Name",
    )

    assert google_result.id == test_user.id

    # Link GitHub account to same user
    github_result = await get_or_create_oauth_user(
        db=async_db_session,
        provider="github",
        provider_user_id="github222",
        email="service@example.com",
        username="GitHub Name",
    )

    assert github_result.id == test_user.id

    # Verify both OAuth accounts exist
    stmt = select(OAuthAccount).where(OAuthAccount.user_id == test_user.id)
    result = await async_db_session.execute(stmt)
    oauth_accounts = result.scalars().all()

    assert len(oauth_accounts) == 2
    providers = {acc.provider for acc in oauth_accounts}
    assert "google" in providers
    assert "github" in providers
