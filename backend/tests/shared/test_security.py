"""Unit tests for JWT authentication and security utilities."""

import pytest
from datetime import timedelta
from unittest.mock import AsyncMock, patch
from jose import JWTError

from app.shared.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_token_type,
    is_token_revoked,
    revoke_token,
    TokenData,
)
from app.config.settings import get_settings


class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_password_hash_creates_hash(self):
        """Test that password hashing creates a non-empty hash."""
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert hashed is not None
        assert len(hashed) > 0
        assert hashed != password  # Hash should be different from password

    def test_password_verification_success(self):
        """Test that correct password verifies successfully."""
        password = "my_secure_password"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_password_verification_failure(self):
        """Test that incorrect password fails verification."""
        password = "correct_password"
        wrong_password = "wrong_password"
        hashed = get_password_hash(password)

        assert verify_password(wrong_password, hashed) is False

    def test_different_passwords_create_different_hashes(self):
        """Test that same password creates different hashes (salt)."""
        password = "same_password"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        # Hashes should be different due to salt
        assert hash1 != hash2
        # But both should verify correctly
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestTokenCreation:
    """Test JWT token creation."""

    def test_create_access_token_with_valid_data(self):
        """Test creating access token with valid user data."""
        data = {
            "user_id": 1,
            "username": "testuser",
            "tier": "free",
            "scopes": ["read"],
        }
        token = create_access_token(data)

        assert token is not None
        assert len(token) > 0
        assert isinstance(token, str)

    def test_create_access_token_with_custom_expiration(self):
        """Test creating access token with custom expiration."""
        data = {"user_id": 1, "username": "testuser"}
        expires_delta = timedelta(minutes=15)
        token = create_access_token(data, expires_delta=expires_delta)

        assert token is not None
        payload = decode_token(token)
        assert "exp" in payload

    def test_create_refresh_token_with_valid_data(self):
        """Test creating refresh token with valid user data."""
        data = {"user_id": 1, "username": "testuser"}
        token = create_refresh_token(data)

        assert token is not None
        assert len(token) > 0
        assert isinstance(token, str)

    def test_access_token_has_correct_type(self):
        """Test that access token has type 'access'."""
        data = {"user_id": 1, "username": "testuser"}
        token = create_access_token(data)
        payload = decode_token(token)

        assert payload["type"] == "access"

    def test_refresh_token_has_correct_type(self):
        """Test that refresh token has type 'refresh'."""
        data = {"user_id": 1, "username": "testuser"}
        token = create_refresh_token(data)
        payload = decode_token(token)

        assert payload["type"] == "refresh"


class TestTokenValidation:
    """Test JWT token validation."""

    def test_decode_valid_token(self):
        """Test decoding a valid token."""
        data = {"user_id": 123, "username": "testuser", "tier": "premium"}
        token = create_access_token(data)
        payload = decode_token(token)

        assert payload["user_id"] == 123
        assert payload["username"] == "testuser"
        assert payload["tier"] == "premium"
        assert payload["type"] == "access"

    def test_decode_invalid_token_raises_error(self):
        """Test that decoding invalid token raises JWTError."""
        invalid_token = "invalid.token.here"

        with pytest.raises(JWTError):
            decode_token(invalid_token)

    def test_decode_expired_token_raises_error(self):
        """Test that decoding expired token raises JWTError."""
        data = {"user_id": 1, "username": "testuser"}
        # Create token with negative expiration (already expired)
        token = create_access_token(data, expires_delta=timedelta(seconds=-1))

        with pytest.raises(JWTError):
            decode_token(token)

    def test_validate_token_type_access(self):
        """Test validating access token type."""
        token = create_access_token({"user_id": 1, "username": "test"})
        payload = decode_token(token)

        assert validate_token_type(payload, "access") is True
        assert validate_token_type(payload, "refresh") is False

    def test_validate_token_type_refresh(self):
        """Test validating refresh token type."""
        token = create_refresh_token({"user_id": 1, "username": "test"})
        payload = decode_token(token)

        assert validate_token_type(payload, "refresh") is True
        assert validate_token_type(payload, "access") is False

    def test_token_with_invalid_signature_fails(self):
        """Test that token with invalid signature fails validation."""
        # Create a token
        token = create_access_token({"user_id": 1, "username": "test"})

        # Tamper with the signature portion (after the last dot)
        parts = token.rsplit(".", 1)
        # Reverse the signature to ensure it's invalid
        tampered_sig = parts[1][::-1] if parts[1][::-1] != parts[1] else parts[1] + "X"
        tampered_token = parts[0] + "." + tampered_sig

        with pytest.raises(JWTError):
            decode_token(tampered_token)


class TestTokenRevocation:
    """Test token revocation system.

    Uses a mock cache to avoid requiring a running Redis instance.
    """

    @pytest.fixture(autouse=True)
    def mock_cache(self):
        """Mock the cache module used by token revocation."""
        self._store = {}

        class FakeCache:
            def __init__(self, store):
                self._store = store

            def get(self, key):
                return self._store.get(key)

            def set(self, key, value, ttl=None):
                self._store[key] = value

        fake = FakeCache(self._store)
        with (
            patch("app.shared.security.cache", fake, create=True),
            patch.dict("sys.modules", {}),
        ):
            # Patch at the point of import inside revoke_token / is_token_revoked
            import app.shared.cache as cache_mod

            original = getattr(cache_mod, "cache", None)
            cache_mod.cache = fake
            yield fake
            if original is not None:
                cache_mod.cache = original

    @pytest.mark.asyncio
    async def test_token_not_revoked_initially(self):
        """Test that new token is not revoked."""
        token = create_access_token({"user_id": 1, "username": "test"})

        is_revoked = await is_token_revoked(token)
        assert is_revoked is False

    @pytest.mark.asyncio
    async def test_revoke_token_marks_as_revoked(self):
        """Test that revoking token marks it as revoked."""
        token = create_access_token({"user_id": 1, "username": "test"})

        await revoke_token(token)

        is_revoked = await is_token_revoked(token)
        assert is_revoked is True

    @pytest.mark.asyncio
    async def test_revoke_token_with_custom_ttl(self):
        """Test revoking token with custom TTL."""
        token = create_access_token({"user_id": 1, "username": "test"})

        await revoke_token(token, ttl=3600)

        is_revoked = await is_token_revoked(token)
        assert is_revoked is True

    @pytest.mark.asyncio
    async def test_different_tokens_revoked_independently(self):
        """Test that revoking one token doesn't affect others."""
        token1 = create_access_token({"user_id": 1, "username": "user1"})
        token2 = create_access_token({"user_id": 2, "username": "user2"})

        await revoke_token(token1)

        assert await is_token_revoked(token1) is True
        assert await is_token_revoked(token2) is False


class TestModeConfiguration:
    """Test TEST_MODE configuration setting.

    Note: TEST_MODE is a configuration setting but does NOT bypass authentication.
    Authentication bypass in tests is handled via the bypass_auth fixture in conftest.py.
    """

    def test_test_mode_setting_exists(self):
        """Test that TEST_MODE setting exists in settings."""
        settings = get_settings()
        # Verify the setting exists
        assert hasattr(settings, "TEST_MODE")
        assert isinstance(settings.TEST_MODE, bool)


class TestTokenData:
    """Test TokenData model."""

    def test_token_data_creation(self):
        """Test creating TokenData instance."""
        token_data = TokenData(
            user_id="123", username="testuser", scopes=["read", "write"], tier="premium"
        )

        assert token_data.user_id == "123"
        assert token_data.username == "testuser"
        assert token_data.scopes == ["read", "write"]
        assert token_data.tier == "premium"

    def test_token_data_defaults(self):
        """Test TokenData default values."""
        token_data = TokenData(user_id="1", username="test")

        assert token_data.scopes == []
        assert token_data.tier == "free"


class TestIntegrationScenarios:
    """Test complete authentication scenarios."""

    @pytest.fixture(autouse=True)
    def mock_cache(self):
        """Mock the cache module used by token revocation."""
        self._store = {}

        class FakeCache:
            def __init__(self, store):
                self._store = store

            def get(self, key):
                return self._store.get(key)

            def set(self, key, value, ttl=None):
                self._store[key] = value

        fake = FakeCache(self._store)
        import app.shared.cache as cache_mod

        original = getattr(cache_mod, "cache", None)
        cache_mod.cache = fake
        yield fake
        if original is not None:
            cache_mod.cache = original

    @pytest.mark.asyncio
    async def test_complete_authentication_flow(self):
        """Test complete authentication flow from token creation to validation."""
        user_data = {
            "user_id": 456,
            "username": "integration_user",
            "tier": "premium",
            "scopes": ["read", "write", "admin"],
        }

        access_token = create_access_token(user_data)
        assert access_token is not None

        assert await is_token_revoked(access_token) is False

        payload = decode_token(access_token)
        assert payload["user_id"] == 456
        assert payload["username"] == "integration_user"
        assert validate_token_type(payload, "access") is True

        await revoke_token(access_token)

        assert await is_token_revoked(access_token) is True

    @pytest.mark.asyncio
    async def test_refresh_token_flow(self):
        """Test refresh token creation and validation."""
        user_data = {"user_id": 789, "username": "refresh_user"}
        refresh_token = create_refresh_token(user_data)

        payload = decode_token(refresh_token)
        assert payload["user_id"] == 789
        assert payload["username"] == "refresh_user"
        assert validate_token_type(payload, "refresh") is True
        assert validate_token_type(payload, "access") is False

        await revoke_token(refresh_token)
        assert await is_token_revoked(refresh_token) is True
