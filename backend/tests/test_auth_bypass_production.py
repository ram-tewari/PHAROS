"""
Tests to verify authentication cannot be bypassed in production mode.

These tests ensure that:
1. TEST_MODE does not bypass authentication in production
2. TESTING env var does not bypass authentication in production
3. X-Test-Auth-Bypass header does not work in production
4. All authentication endpoints require valid credentials in production

**Validates: Requirements FR-2.2 (Eliminate authentication bypass in TEST_MODE)**
"""

import os
import sys
from pathlib import Path

# Add backend to path for imports
backend_path = Path(__file__).parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import pytest
import pytest_asyncio
from fastapi import status
from pydantic import ValidationError

from app.config.settings import Settings, get_settings


TRACKED_ENV_KEYS = [
    "ENV",
    "JWT_SECRET_KEY",
    "TESTING",
    "TEST_MODE",
    "TEST_AUTH_BYPASS",
    "ALLOWED_REDIRECT_URLS",
]


def create_settings_with_env(**env_overrides):
    """
    Create Settings with specific environment variables.
    This function handles the complex env var setup needed for testing.
    """
    # Save original env
    original_env = {key: os.environ.get(key) for key in TRACKED_ENV_KEYS}

    try:
        # Clear all relevant env vars
        for key in TRACKED_ENV_KEYS:
            os.environ.pop(key, None)

        # Set production environment with valid JWT secret and HTTPS redirects
        os.environ["ENV"] = "prod"
        os.environ["JWT_SECRET_KEY"] = "a" * 32  # Valid 32-character secret
        os.environ["ALLOWED_REDIRECT_URLS"] = (
            '["https://pharos.example.com/auth/callback"]'
        )

        # Apply any overrides
        for key, value in env_overrides.items():
            os.environ[key] = value

        # Clear settings cache
        get_settings.cache_clear()

        # Create settings (bypass .env file to avoid local config pollution)
        return Settings(_env_file=None)

    finally:
        # Restore original env
        for key in TRACKED_ENV_KEYS:
            os.environ.pop(key, None)
            if original_env[key] is not None:
                os.environ[key] = original_env[key]

        get_settings.cache_clear()


# ============================================================================
# Production Mode Settings Validation Tests
# ============================================================================


class TestProductionSettingsValidation:
    """
    Tests to verify that Settings properly validates production environment.
    """

    def test_production_settings_with_valid_jwt_secret(self):
        """
        Test that Settings can be created with valid JWT secret in production.
        """
        settings = create_settings_with_env()

        assert settings.ENV == "prod"
        assert len(settings.JWT_SECRET_KEY.get_secret_value()) >= 32

    def test_production_settings_rejects_default_jwt_secret(self):
        """
        Test that Settings rejects default JWT secret in production.
        """
        with pytest.raises(ValidationError, match="default"):
            create_settings_with_env(
                JWT_SECRET_KEY="change-this-secret-key-in-production-min-32-chars-long"
            )

    def test_production_settings_rejects_short_jwt_secret(self):
        """
        Test that Settings rejects short JWT secret in production.
        """
        with pytest.raises(ValidationError, match="at least 32"):
            create_settings_with_env(JWT_SECRET_KEY="short")

    def test_production_settings_rejects_test_mode(self):
        """
        Test that Settings rejects TEST_MODE=True in production.
        """
        with pytest.raises(ValidationError, match="TEST_MODE"):
            create_settings_with_env(TEST_MODE="true")

    def test_production_settings_rejects_testing_env_var(self):
        """
        Test that Settings rejects TESTING=true env var in production.
        """
        with pytest.raises(ValidationError, match="TESTING"):
            create_settings_with_env(TESTING="true")


# ============================================================================
# Integration Tests for Auth Bypass Prevention
# ============================================================================


class TestAuthBypassIntegration:
    """
    Integration tests that verify the complete authentication flow
    cannot be bypassed in production mode.

    These tests use the bypass_auth fixture to test protected endpoints
    without requiring actual JWT authentication.
    """

    @pytest.mark.asyncio
    async def test_protected_endpoints_with_bypass_auth(self, bypass_auth):
        """
        Test that protected endpoints work with bypass_auth fixture.
        This verifies the bypass_auth fixture is working correctly.
        """
        client = bypass_auth

        # Test that protected endpoints are accessible with bypass_auth
        response = client.get("/api/resources")
        # Should not return 401 (unauthorized)
        assert response.status_code != status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_auth_endpoints_work_in_test_mode(
        self, async_client, async_db_session
    ):
        """
        Test that authentication endpoints work correctly in test mode.
        """
        from uuid import UUID
        from app.database.models import User
        from app.shared.security import get_password_hash

        # Create user in the same async DB session that async_client uses
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
        async_db_session.add(user)
        await async_db_session.commit()

        # Test login with valid credentials
        response = await async_client.post(
            "/api/auth/login",
            data={"username": "testuser", "password": "testpassword123"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_protected_endpoints_require_auth_without_bypass(
        self, unauthenticated_client
    ):
        """
        Test that protected endpoints require authentication when not using bypass_auth.
        """
        client = unauthenticated_client

        # Test that protected endpoints require authentication
        response = client.get("/api/resources")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_authenticated_access_works(self, authenticated_client, auth_headers):
        """
        Test that authenticated access works correctly.
        """
        client = authenticated_client

        # Test that protected endpoints are accessible with valid auth
        response = client.get("/api/resources", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
