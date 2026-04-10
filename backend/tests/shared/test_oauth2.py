"""Unit tests for OAuth2 provider integration.

Tests OAuth2 authorization code flow for Google and GitHub providers
with mocked HTTP responses.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException

from app.shared.oauth2 import OAuth2Provider, GoogleOAuth2Provider, GitHubOAuth2Provider


class TestOAuth2Provider:
    """Test OAuth2Provider base class."""

    def test_base_class_initialization(self):
        """Test OAuth2Provider can be initialized with credentials."""
        provider = OAuth2Provider(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_uri="http://localhost:8000/callback",
        )

        assert provider.client_id == "test_client_id"
        assert provider.client_secret == "test_client_secret"
        assert provider.redirect_uri == "http://localhost:8000/callback"

    @pytest.mark.asyncio
    async def test_base_class_methods_not_implemented(self):
        """Test base class methods raise NotImplementedError."""
        provider = OAuth2Provider(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_uri="http://localhost:8000/callback",
        )

        with pytest.raises(NotImplementedError):
            await provider.get_authorization_url("test_state")

        with pytest.raises(NotImplementedError):
            await provider.exchange_code_for_token("test_code")

        with pytest.raises(NotImplementedError):
            await provider.get_user_info("test_token")


class TestGoogleOAuth2Provider:
    """Test GoogleOAuth2Provider implementation."""

    def test_initialization(self):
        """Test GoogleOAuth2Provider initialization."""
        provider = GoogleOAuth2Provider(
            client_id="google_client_id",
            client_secret="google_client_secret",
            redirect_uri="http://localhost:8000/auth/google/callback",
        )

        assert provider.client_id == "google_client_id"
        assert provider.client_secret == "google_client_secret"
        assert provider.redirect_uri == "http://localhost:8000/auth/google/callback"
        assert provider.AUTH_URL == "https://accounts.google.com/o/oauth2/v2/auth"
        assert provider.TOKEN_URL == "https://oauth2.googleapis.com/token"
        assert provider.USER_INFO_URL == "https://www.googleapis.com/oauth2/v2/userinfo"

    @pytest.mark.asyncio
    async def test_get_authorization_url(self):
        """Test Google authorization URL generation."""
        provider = GoogleOAuth2Provider(
            client_id="google_client_id",
            client_secret="google_client_secret",
            redirect_uri="http://localhost:8000/auth/google/callback",
        )

        state = "random_state_token"
        auth_url = await provider.get_authorization_url(state)

        # Verify URL structure
        from urllib.parse import parse_qs, urlsplit

        assert auth_url.startswith(provider.AUTH_URL)
        params = parse_qs(urlsplit(auth_url).query)
        assert params["client_id"] == ["google_client_id"]
        assert params["redirect_uri"] == [
            "http://localhost:8000/auth/google/callback"
        ]
        assert params["response_type"] == ["code"]
        assert params["scope"] == ["openid email profile"]
        assert params["state"] == [state]
        assert params["access_type"] == ["offline"]
        assert params["prompt"] == ["consent"]

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_success(self):
        """Test successful Google code-to-token exchange."""
        provider = GoogleOAuth2Provider(
            client_id="google_client_id",
            client_secret="google_client_secret",
            redirect_uri="http://localhost:8000/auth/google/callback",
        )

        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "google_access_token",
            "refresh_token": "google_refresh_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            token_data = await provider.exchange_code_for_token("auth_code")

            assert token_data["access_token"] == "google_access_token"
            assert token_data["refresh_token"] == "google_refresh_token"
            assert token_data["expires_in"] == 3600

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_failure(self):
        """Test failed Google code-to-token exchange."""
        provider = GoogleOAuth2Provider(
            client_id="google_client_id",
            client_secret="google_client_secret",
            redirect_uri="http://localhost:8000/auth/google/callback",
        )

        # Mock failed HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid authorization code"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(HTTPException) as exc_info:
                await provider.exchange_code_for_token("invalid_code")

            assert exc_info.value.status_code == 400
            assert "Failed to exchange code for token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_user_info_success(self):
        """Test successful Google user info retrieval."""
        provider = GoogleOAuth2Provider(
            client_id="google_client_id",
            client_secret="google_client_secret",
            redirect_uri="http://localhost:8000/auth/google/callback",
        )

        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "google_user_123",
            "email": "user@example.com",
            "name": "Test User",
            "picture": "https://example.com/photo.jpg",
            "verified_email": True,
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            user_info = await provider.get_user_info("access_token")

            assert user_info["id"] == "google_user_123"
            assert user_info["email"] == "user@example.com"
            assert user_info["name"] == "Test User"
            assert user_info["verified_email"] is True

    @pytest.mark.asyncio
    async def test_get_user_info_failure(self):
        """Test failed Google user info retrieval."""
        provider = GoogleOAuth2Provider(
            client_id="google_client_id",
            client_secret="google_client_secret",
            redirect_uri="http://localhost:8000/auth/google/callback",
        )

        # Mock failed HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid access token"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(HTTPException) as exc_info:
                await provider.get_user_info("invalid_token")

            assert exc_info.value.status_code == 400
            assert "Failed to get user info" in exc_info.value.detail


class TestGitHubOAuth2Provider:
    """Test GitHubOAuth2Provider implementation."""

    def test_initialization(self):
        """Test GitHubOAuth2Provider initialization."""
        provider = GitHubOAuth2Provider(
            client_id="github_client_id",
            client_secret="github_client_secret",
            redirect_uri="http://localhost:8000/auth/github/callback",
        )

        assert provider.client_id == "github_client_id"
        assert provider.client_secret == "github_client_secret"
        assert provider.redirect_uri == "http://localhost:8000/auth/github/callback"
        assert provider.AUTH_URL == "https://github.com/login/oauth/authorize"
        assert provider.TOKEN_URL == "https://github.com/login/oauth/access_token"
        assert provider.USER_INFO_URL == "https://api.github.com/user"

    @pytest.mark.asyncio
    async def test_get_authorization_url(self):
        """Test GitHub authorization URL generation."""
        provider = GitHubOAuth2Provider(
            client_id="github_client_id",
            client_secret="github_client_secret",
            redirect_uri="http://localhost:8000/auth/github/callback",
        )

        state = "random_state_token"
        auth_url = await provider.get_authorization_url(state)

        # Verify URL structure
        from urllib.parse import parse_qs, urlsplit

        assert auth_url.startswith(provider.AUTH_URL)
        params = parse_qs(urlsplit(auth_url).query)
        assert params["client_id"] == ["github_client_id"]
        assert params["redirect_uri"] == [
            "http://localhost:8000/auth/github/callback"
        ]
        assert params["scope"] == ["user:email"]
        assert params["state"] == [state]

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_success(self):
        """Test successful GitHub code-to-token exchange."""
        provider = GitHubOAuth2Provider(
            client_id="github_client_id",
            client_secret="github_client_secret",
            redirect_uri="http://localhost:8000/auth/github/callback",
        )

        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "github_access_token",
            "token_type": "bearer",
            "scope": "user:email",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            token_data = await provider.exchange_code_for_token("auth_code")

            assert token_data["access_token"] == "github_access_token"
            assert token_data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_with_error(self):
        """Test GitHub code-to-token exchange with error response."""
        provider = GitHubOAuth2Provider(
            client_id="github_client_id",
            client_secret="github_client_secret",
            redirect_uri="http://localhost:8000/auth/github/callback",
        )

        # Mock error response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "error": "bad_verification_code",
            "error_description": "The code passed is incorrect or expired.",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(HTTPException) as exc_info:
                await provider.exchange_code_for_token("invalid_code")

            assert exc_info.value.status_code == 400
            assert "GitHub OAuth2 error" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_exchange_code_for_token_failure(self):
        """Test failed GitHub code-to-token exchange."""
        provider = GitHubOAuth2Provider(
            client_id="github_client_id",
            client_secret="github_client_secret",
            redirect_uri="http://localhost:8000/auth/github/callback",
        )

        # Mock failed HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(HTTPException) as exc_info:
                await provider.exchange_code_for_token("invalid_code")

            assert exc_info.value.status_code == 400
            assert "Failed to exchange code for token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_user_info_success_with_public_email(self):
        """Test successful GitHub user info retrieval with public email."""
        provider = GitHubOAuth2Provider(
            client_id="github_client_id",
            client_secret="github_client_secret",
            redirect_uri="http://localhost:8000/auth/github/callback",
        )

        # Mock successful HTTP response with public email
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 12345,
            "login": "testuser",
            "email": "user@example.com",
            "name": "Test User",
            "avatar_url": "https://avatars.githubusercontent.com/u/12345",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            user_info = await provider.get_user_info("access_token")

            assert user_info["id"] == 12345
            assert user_info["login"] == "testuser"
            assert user_info["email"] == "user@example.com"
            assert user_info["name"] == "Test User"

    @pytest.mark.asyncio
    async def test_get_user_info_success_with_private_email(self):
        """Test successful GitHub user info retrieval with private email."""
        provider = GitHubOAuth2Provider(
            client_id="github_client_id",
            client_secret="github_client_secret",
            redirect_uri="http://localhost:8000/auth/github/callback",
        )

        # Mock profile response without email
        mock_profile_response = MagicMock()
        mock_profile_response.status_code = 200
        mock_profile_response.json.return_value = {
            "id": 12345,
            "login": "testuser",
            "email": None,
            "name": "Test User",
        }

        # Mock emails response
        mock_email_response = MagicMock()
        mock_email_response.status_code = 200
        mock_email_response.json.return_value = [
            {"email": "secondary@example.com", "primary": False, "verified": True},
            {"email": "primary@example.com", "primary": True, "verified": True},
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(
                side_effect=[mock_profile_response, mock_email_response]
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            user_info = await provider.get_user_info("access_token")

            assert user_info["id"] == 12345
            assert user_info["login"] == "testuser"
            assert user_info["email"] == "primary@example.com"

    @pytest.mark.asyncio
    async def test_get_user_info_failure(self):
        """Test failed GitHub user info retrieval."""
        provider = GitHubOAuth2Provider(
            client_id="github_client_id",
            client_secret="github_client_secret",
            redirect_uri="http://localhost:8000/auth/github/callback",
        )

        # Mock failed HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Bad credentials"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(HTTPException) as exc_info:
                await provider.get_user_info("invalid_token")

            assert exc_info.value.status_code == 400
            assert "Failed to get user info" in exc_info.value.detail
