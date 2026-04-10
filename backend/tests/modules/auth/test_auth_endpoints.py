"""Integration tests for authentication endpoints.

Tests cover:
- Login with valid/invalid credentials
- Token refresh
- Logout
- OAuth2 flows (with mocked providers)
- User info endpoint
- Rate limit status endpoint
"""

import pytest
import pytest_asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import status
from sqlalchemy import select

from app.database.models import User
from app.modules.auth.model import OAuthAccount
from app.shared.security import get_password_hash


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def test_user(async_db_session):
    """Create a test user for authentication tests."""
    user = User(
        id=uuid.uuid4(),
        username="testuser",
        email="test@example.com",
        hashed_password=get_password_hash("testpassword123"),
        tier="free",
        is_active=True,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def premium_user(async_db_session):
    """Create a premium tier test user."""
    user = User(
        id=uuid.uuid4(),
        username="premiumuser",
        email="premium@example.com",
        hashed_password=get_password_hash("premiumpass123"),
        tier="premium",
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
        username="inactiveuser",
        email="inactive@example.com",
        hashed_password=get_password_hash("inactivepass123"),
        tier="free",
        is_active=False,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)
    return user


# ============================================================================
# Login Endpoint Tests
# ============================================================================


@pytest.mark.asyncio
async def test_login_with_valid_credentials(async_client, test_user):
    """Test login with valid username and password."""
    response = await async_client.post(
        "/api/auth/login", data={"username": "testuser", "password": "testpassword123"}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 0
    assert len(data["refresh_token"]) > 0


@pytest.mark.asyncio
async def test_login_with_email(async_client, test_user):
    """Test login with email instead of username."""
    response = await async_client.post(
        "/api/auth/login",
        data={"username": "test@example.com", "password": "testpassword123"},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_with_invalid_password(async_client, test_user):
    """Test login with incorrect password."""
    response = await async_client.post(
        "/api/auth/login", data={"username": "testuser", "password": "wrongpassword"}
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_login_with_nonexistent_user(async_client):
    """Test login with username that doesn't exist."""
    response = await async_client.post(
        "/api/auth/login", data={"username": "nonexistent", "password": "somepassword"}
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_login_with_inactive_user(async_client, inactive_user):
    """Test login with inactive user account."""
    response = await async_client.post(
        "/api/auth/login",
        data={"username": "inactiveuser", "password": "inactivepass123"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# Token Refresh Tests
# ============================================================================


@pytest.mark.asyncio
async def test_token_refresh_with_valid_token(async_client, test_user):
    """Test refreshing access token with valid refresh token."""
    # First login to get tokens
    login_response = await async_client.post(
        "/api/auth/login", data={"username": "testuser", "password": "testpassword123"}
    )

    refresh_token = login_response.json()["refresh_token"]

    # Refresh the token
    response = await async_client.post(
        "/api/auth/refresh", json={"refresh_token": refresh_token}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["refresh_token"] == refresh_token  # Same refresh token returned


@pytest.mark.asyncio
async def test_token_refresh_with_invalid_token(async_client):
    """Test token refresh with invalid refresh token."""
    response = await async_client.post(
        "/api/auth/refresh", json={"refresh_token": "invalid.token.here"}
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_token_refresh_with_access_token(async_client, test_user):
    """Test token refresh with access token (should fail)."""
    # Login to get access token
    login_response = await async_client.post(
        "/api/auth/login", data={"username": "testuser", "password": "testpassword123"}
    )

    access_token = login_response.json()["access_token"]

    # Try to refresh with access token (wrong type)
    response = await async_client.post(
        "/api/auth/refresh", json={"refresh_token": access_token}
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# Logout Tests
# ============================================================================


@pytest.mark.asyncio
async def test_logout_with_valid_token(async_client, test_user):
    """Test logout with valid access token."""
    # Login first
    login_response = await async_client.post(
        "/api/auth/login", data={"username": "testuser", "password": "testpassword123"}
    )

    access_token = login_response.json()["access_token"]

    # Logout
    response = await async_client.post(
        "/api/auth/logout", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == status.HTTP_200_OK
    assert "message" in response.json()


@pytest.mark.asyncio
async def test_logout_without_token(async_client):
    """Test logout without authentication token."""
    response = await async_client.post("/api/auth/logout")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# OAuth2 Google Tests (Mocked)
# ============================================================================


@pytest.mark.asyncio
async def test_google_login_initiation(async_client, test_settings):
    """Test initiating Google OAuth2 flow."""
    from app.shared.oauth2 import GoogleOAuth2Provider

    mock_provider_instance = AsyncMock(spec=GoogleOAuth2Provider)
    mock_provider_instance.get_authorization_url.return_value = (
        "https://accounts.google.com/o/oauth2/v2/auth?client_id=test"
    )

    with patch(
        "app.modules.auth.router.get_google_provider",
        return_value=mock_provider_instance,
    ):
        response = await async_client.get("/api/auth/google")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "authorization_url" in data
    assert "state" in data
    assert "accounts.google.com" in data["authorization_url"]


@pytest.mark.asyncio
async def test_google_login_not_configured(async_client, test_settings):
    """Test Google OAuth2 when not configured."""
    test_settings.GOOGLE_CLIENT_ID = None
    test_settings.GOOGLE_CLIENT_SECRET = None

    response = await async_client.get("/api/auth/google")

    assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED


@pytest.mark.asyncio
async def test_google_callback_success(async_client, async_db_session, test_settings):
    """Test successful Google OAuth2 callback."""
    mock_token_data = {"access_token": "mock_google_token"}
    mock_user_info = {
        "id": "google123",
        "email": "google@example.com",
        "name": "Google User",
    }

    mock_provider_instance = AsyncMock()
    mock_provider_instance.exchange_code_for_token.return_value = mock_token_data
    mock_provider_instance.get_user_info.return_value = mock_user_info

    with patch(
        "app.modules.auth.router.get_google_provider",
        return_value=mock_provider_instance,
    ):
        response = await async_client.get(
            "/api/auth/google/callback",
            params={"code": "test_code", "state": "test_state"},
        )

    assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
    location = response.headers["location"]

    # Tokens should NOT be in URL (security improvement)
    assert "access_token=" not in location
    assert "refresh_token=" not in location
    assert location == "http://localhost:5173/auth/callback"

    # Verify cookies are set (httpx doesn't expose cookie attributes,
    # but we can verify the cookies are present)
    cookies = response.cookies
    assert "access_token" in cookies
    assert "refresh_token" in cookies
    # Cookie values should be non-empty JWT tokens
    assert len(cookies["access_token"]) > 100  # JWT tokens are long
    assert len(cookies["refresh_token"]) > 100

    # Verify user was created
    stmt = select(User).where(User.email == "google@example.com")
    result = await async_db_session.execute(stmt)
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.username == "Google User"


# ============================================================================
# OAuth2 GitHub Tests (Mocked)
# ============================================================================


@pytest.mark.asyncio
async def test_github_login_initiation(async_client, test_settings):
    """Test initiating GitHub OAuth2 flow."""
    from app.shared.oauth2 import GitHubOAuth2Provider

    mock_provider_instance = AsyncMock(spec=GitHubOAuth2Provider)
    mock_provider_instance.get_authorization_url.return_value = (
        "https://github.com/login/oauth/authorize?client_id=test"
    )

    with patch(
        "app.modules.auth.router.get_github_provider",
        return_value=mock_provider_instance,
    ):
        response = await async_client.get("/api/auth/github")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "authorization_url" in data
    assert "state" in data
    assert "github.com" in data["authorization_url"]


@pytest.mark.asyncio
async def test_github_login_not_configured(async_client, test_settings):
    """Test GitHub OAuth2 when not configured."""
    test_settings.GITHUB_CLIENT_ID = None
    test_settings.GITHUB_CLIENT_SECRET = None

    response = await async_client.get("/api/auth/github")

    assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED


@pytest.mark.asyncio
async def test_github_callback_success(async_client, async_db_session, test_settings):
    """Test successful GitHub OAuth2 callback."""
    mock_token_data = {"access_token": "mock_github_token"}
    mock_user_info = {"id": 12345, "login": "githubuser", "email": "github@example.com"}

    mock_provider_instance = AsyncMock()
    mock_provider_instance.exchange_code_for_token.return_value = mock_token_data
    mock_provider_instance.get_user_info.return_value = mock_user_info

    with patch(
        "app.modules.auth.router.get_github_provider",
        return_value=mock_provider_instance,
    ):
        response = await async_client.get(
            "/api/auth/github/callback",
            params={"code": "test_code", "state": "test_state"},
        )

    assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
    location = response.headers["location"]

    # Tokens should NOT be in URL (security improvement)
    assert "access_token=" not in location
    assert "refresh_token=" not in location
    assert location == "http://localhost:5173/auth/callback"

    # Verify cookies are set (httpx doesn't expose cookie attributes,
    # but we can verify the cookies are present)
    cookies = response.cookies
    assert "access_token" in cookies
    assert "refresh_token" in cookies
    # Cookie values should be non-empty JWT tokens
    assert len(cookies["access_token"]) > 100  # JWT tokens are long
    assert len(cookies["refresh_token"]) > 100

    # Verify user was created
    stmt = select(User).where(User.email == "github@example.com")
    result = await async_db_session.execute(stmt)
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.username == "githubuser"


# ============================================================================
# User Info Endpoint Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_current_user_info(async_client, test_user):
    """Test getting current user information."""
    # Login first
    login_response = await async_client.post(
        "/api/auth/login", data={"username": "testuser", "password": "testpassword123"}
    )

    access_token = login_response.json()["access_token"]

    # Get user info
    response = await async_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["id"] == str(test_user.id)
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"
    assert data["tier"] == "free"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_get_user_info_without_auth(async_client):
    """Test getting user info without authentication."""
    response = await async_client.get("/api/auth/me")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# Rate Limit Status Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_rate_limit_status_free_tier(async_client, test_user):
    """Test getting rate limit status for free tier user."""
    # Login first
    login_response = await async_client.post(
        "/api/auth/login", data={"username": "testuser", "password": "testpassword123"}
    )

    access_token = login_response.json()["access_token"]

    # Get rate limit status
    response = await async_client.get(
        "/api/auth/rate-limit", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "limit" in data
    assert "remaining" in data
    assert "reset" in data
    assert data["tier"] == "free"
    assert data["limit"] > 0  # Free tier has limits


@pytest.mark.asyncio
async def test_get_rate_limit_status_premium_tier(async_client, premium_user):
    """Test getting rate limit status for premium tier user."""
    # Login first
    login_response = await async_client.post(
        "/api/auth/login",
        data={"username": "premiumuser", "password": "premiumpass123"},
    )

    access_token = login_response.json()["access_token"]

    # Get rate limit status
    response = await async_client.get(
        "/api/auth/rate-limit", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["tier"] == "premium"
    assert data["limit"] > 0  # Premium tier has higher limits


@pytest.mark.asyncio
async def test_get_rate_limit_without_auth(async_client):
    """Test getting rate limit status without authentication."""
    response = await async_client.get("/api/auth/rate-limit")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# OAuth Account Linking Tests
# ============================================================================


@pytest.mark.asyncio
async def test_oauth_account_linking_to_existing_user(
    async_client, test_user, async_db_session
):
    """Test linking OAuth account to existing user with same email."""
    mock_token_data = {"access_token": "mock_token"}
    mock_user_info = {
        "id": "google456",
        "email": "test@example.com",  # Same email as test_user
        "name": "Test User",
    }

    with (
        patch("app.modules.auth.service.get_settings") as mock_settings,
        patch("app.modules.auth.router.get_google_provider") as mock_provider,
    ):
        mock_settings.return_value.GOOGLE_CLIENT_ID = "test_client_id"
        mock_settings.return_value.GOOGLE_CLIENT_SECRET.get_secret_value.return_value = "test_secret"

        mock_provider_instance = AsyncMock()
        mock_provider_instance.exchange_code_for_token.return_value = mock_token_data
        mock_provider_instance.get_user_info.return_value = mock_user_info
        mock_provider.return_value = mock_provider_instance

        response = await async_client.get(
            "/api/auth/google/callback",
            params={"code": "test_code", "state": "test_state"},
        )

        assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT

        # Verify OAuth account was linked to existing user
        stmt = select(OAuthAccount).where(
            (OAuthAccount.provider == "google")
            & (OAuthAccount.provider_user_id == "google456")
        )
        result = await async_db_session.execute(stmt)
        oauth_account = result.scalar_one_or_none()

        assert oauth_account is not None
        assert oauth_account.user_id == test_user.id
