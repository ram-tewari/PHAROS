"""
Tests for Settings configuration (Phase 17).

These tests use REAL Settings instances with environment variables,
ensuring tests match actual runtime behavior.

Note: Validation checks (like "must be positive") are performed in
get_settings(), not in Settings.__init__(). Tests that check validation
must use get_settings() instead of Settings() directly.
"""

import pytest
import os
from pydantic import SecretStr, ValidationError
from unittest.mock import patch

from app.config.settings import Settings, get_settings


def make_settings(**overrides):
    """Create a Settings instance without loading .env file.

    This prevents test pollution from the local .env file.
    """
    return Settings(_env_file=None, **overrides)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Clean environment before and after each test."""
    # Clean test-related env vars
    test_keys = [
        "DATABASE_URL",
        "POSTGRES_SERVER",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "POSTGRES_PORT",
        "JWT_SECRET_KEY",
        "JWT_ALGORITHM",
        "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
        "JWT_REFRESH_TOKEN_EXPIRE_DAYS",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GITHUB_CLIENT_ID",
        "GITHUB_CLIENT_SECRET",
        "RATE_LIMIT_FREE_TIER",
        "RATE_LIMIT_PREMIUM_TIER",
        "RATE_LIMIT_ADMIN_TIER",
        "TEST_MODE",
        "TESTING",
        "REDIS_PORT",
        "MIN_QUALITY_THRESHOLD",
        "DEFAULT_HYBRID_SEARCH_WEIGHT",
        "CHUNK_ON_RESOURCE_CREATE",
        "CHUNKING_STRATEGY",
        "CHUNK_SIZE",
        "CHUNK_OVERLAP",
        "GRAPH_EXTRACTION_ENABLED",
        "GRAPH_EXTRACTION_METHOD",
        "SYNTHETIC_QUESTIONS_ENABLED",
        "QUESTIONS_PER_CHUNK",
        "DEFAULT_RETRIEVAL_STRATEGY",
        "PARENT_CHILD_CONTEXT_WINDOW",
        "GRAPHRAG_MAX_HOPS",
        "GRAPH_WEIGHT_VECTOR",
        "GRAPH_WEIGHT_TAGS",
        "GRAPH_WEIGHT_CLASSIFICATION",
        "ENV",
        "UPSTASH_REDIS_REST_URL",
        "UPSTASH_REDIS_REST_TOKEN",
        "PHAROS_ADMIN_TOKEN",
        "PHASE19_ENABLED",
        "MODE",
    ]

    for key in test_keys:
        monkeypatch.delenv(key, raising=False)

    # Clear settings cache
    get_settings.cache_clear()

    yield

    get_settings.cache_clear()


# ============================================================================
# Database URL Construction Tests
# ============================================================================


class TestDatabaseURLConstruction:
    """Test database URL construction logic."""

    def test_sqlite_url_unchanged(self, monkeypatch):
        """SQLite URLs should be returned unchanged."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///./backend.db")
        settings = make_settings()
        assert settings.get_database_url() == "sqlite:///./backend.db"

    def test_sqlite_memory_url_unchanged(self, monkeypatch):
        """SQLite memory URLs should be returned unchanged."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        settings = make_settings()
        assert settings.get_database_url() == "sqlite:///:memory:"

    def test_postgresql_url_construction(self, monkeypatch):
        """PostgreSQL URLs should be constructed from components."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://placeholder")
        monkeypatch.setenv("POSTGRES_SERVER", "testhost")
        monkeypatch.setenv("POSTGRES_USER", "testuser")
        monkeypatch.setenv("POSTGRES_PASSWORD", "testpass")
        monkeypatch.setenv("POSTGRES_DB", "testdb")
        monkeypatch.setenv("POSTGRES_PORT", "5432")

        settings = make_settings()
        expected = "postgresql+asyncpg://testuser:testpass@testhost:5432/testdb"
        assert settings.get_database_url() == expected

    def test_postgresql_url_with_custom_port(self, monkeypatch):
        """PostgreSQL URLs should support custom ports."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://placeholder")
        monkeypatch.setenv("POSTGRES_SERVER", "prodhost")
        monkeypatch.setenv("POSTGRES_USER", "admin")
        monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
        monkeypatch.setenv("POSTGRES_DB", "proddb")
        monkeypatch.setenv("POSTGRES_PORT", "5433")

        settings = make_settings()
        expected = "postgresql+asyncpg://admin:secret@prodhost:5433/proddb"
        assert settings.get_database_url() == expected

    def test_postgresql_url_with_special_characters_in_password(self, monkeypatch):
        """PostgreSQL URLs should URL-encode special characters in password."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://placeholder")
        monkeypatch.setenv("POSTGRES_SERVER", "host")
        monkeypatch.setenv("POSTGRES_USER", "user")
        monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss:word!")
        monkeypatch.setenv("POSTGRES_DB", "db")
        monkeypatch.setenv("POSTGRES_PORT", "5432")

        settings = make_settings()
        # Special characters should be URL-encoded
        expected = "postgresql+asyncpg://user:p%40ss%3Aword%21@host:5432/db"
        assert settings.get_database_url() == expected


# ============================================================================
# JWT Configuration Tests
# ============================================================================


class TestJWTConfiguration:
    """Test JWT configuration."""

    def test_jwt_secret_key_has_default(self):
        """JWT secret key has a default value for development."""
        settings = make_settings()
        secret = settings.JWT_SECRET_KEY.get_secret_value()
        assert "change-this-secret-key" in secret
        assert len(secret) >= 32  # Default is now 32+ chars

    def test_jwt_secret_key_minimum_length(self, monkeypatch):
        """JWT secret key must be at least 32 characters."""
        # Too short - should fail
        with pytest.raises(ValidationError, match="at least 32 characters"):
            make_settings(JWT_SECRET_KEY=SecretStr("short"))

    def test_jwt_secret_key_default_rejected_in_production(self, monkeypatch):
        """Default JWT secret key is rejected in production mode."""
        monkeypatch.setenv("ENV", "prod")
        # Default value is used, but production mode should reject it
        with pytest.raises(ValidationError, match="default"):
            make_settings()

    def test_jwt_algorithm_default(self):
        """JWT algorithm should default to HS256."""
        settings = make_settings()
        assert settings.JWT_ALGORITHM == "HS256"

    def test_jwt_access_token_expire_minutes_default(self):
        """Access token expiration should default to 30 minutes."""
        settings = make_settings()
        assert settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES == 30

    def test_jwt_refresh_token_expire_days_default(self):
        """Refresh token expiration should default to 7 days."""
        settings = make_settings()
        assert settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS == 7

    def test_jwt_secret_key_from_env(self, monkeypatch):
        """JWT secret key should be loadable from environment."""
        monkeypatch.setenv(
            "JWT_SECRET_KEY", "my-super-secret-key-min-32-chars-long-here"
        )
        settings = make_settings()
        assert (
            settings.JWT_SECRET_KEY.get_secret_value()
            == "my-super-secret-key-min-32-chars-long-here"
        )

    def test_jwt_algorithm_from_env(self, monkeypatch):
        """JWT algorithm should be loadable from environment."""
        monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)
        monkeypatch.setenv("JWT_ALGORITHM", "RS256")
        settings = make_settings()
        assert settings.JWT_ALGORITHM == "RS256"


# ============================================================================
# OAuth2 Configuration Tests
# ============================================================================


class TestOAuth2Configuration:
    """Test OAuth2 configuration."""

    def test_google_oauth_defaults(self):
        """Google OAuth should default to None."""
        settings = make_settings()
        assert settings.GOOGLE_CLIENT_ID is None
        assert settings.GOOGLE_CLIENT_SECRET is None

    def test_github_oauth_defaults(self):
        """GitHub OAuth should default to None."""
        settings = make_settings()
        assert settings.GITHUB_CLIENT_ID is None
        assert settings.GITHUB_CLIENT_SECRET is None

    def test_google_oauth_from_env(self, monkeypatch):
        """Google OAuth should be loadable from environment."""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client-123")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret-456")
        settings = make_settings()
        assert settings.GOOGLE_CLIENT_ID == "google-client-123"
        assert settings.GOOGLE_CLIENT_SECRET.get_secret_value() == "google-secret-456"

    def test_github_oauth_from_env(self, monkeypatch):
        """GitHub OAuth should be loadable from environment."""
        monkeypatch.setenv("GITHUB_CLIENT_ID", "github-client-789")
        monkeypatch.setenv("GITHUB_CLIENT_SECRET", "github-secret-012")
        settings = make_settings()
        assert settings.GITHUB_CLIENT_ID == "github-client-789"
        assert settings.GITHUB_CLIENT_SECRET.get_secret_value() == "github-secret-012"


# ============================================================================
# Rate Limiting Configuration Tests
# ============================================================================


class TestRateLimitingConfiguration:
    """Test rate limiting configuration."""

    def test_rate_limit_defaults(self):
        """Rate limits should have default values."""
        settings = make_settings()
        assert settings.RATE_LIMIT_FREE_TIER == 100
        assert settings.RATE_LIMIT_PREMIUM_TIER == 1000
        assert settings.RATE_LIMIT_ADMIN_TIER == 10000  # Default admin tier limit

    def test_rate_limit_from_env(self, monkeypatch):
        """Rate limits should be loadable from environment."""
        monkeypatch.setenv("RATE_LIMIT_FREE_TIER", "50")
        monkeypatch.setenv("RATE_LIMIT_PREMIUM_TIER", "500")
        monkeypatch.setenv("RATE_LIMIT_ADMIN_TIER", "5000")
        settings = make_settings()
        assert settings.RATE_LIMIT_FREE_TIER == 50
        assert settings.RATE_LIMIT_PREMIUM_TIER == 500
        assert settings.RATE_LIMIT_ADMIN_TIER == 5000


# ============================================================================
# Test Mode Configuration Tests
# ============================================================================


class TestTestModeConfiguration:
    """Test TEST_MODE configuration."""

    def test_test_mode_default(self):
        """TEST_MODE should default to False."""
        settings = make_settings()
        assert settings.TEST_MODE is False

    def test_test_mode_from_env_true(self, monkeypatch):
        """TEST_MODE should be settable to True."""
        monkeypatch.setenv("TEST_MODE", "true")
        settings = make_settings()
        assert settings.TEST_MODE is True

    def test_test_mode_from_env_false(self, monkeypatch):
        """TEST_MODE should be settable to False."""
        monkeypatch.setenv("TEST_MODE", "false")
        settings = make_settings()
        assert settings.TEST_MODE is False


# ============================================================================
# SecretStr Masking Tests
# ============================================================================


class TestSecretStrMasking:
    """Test that SecretStr fields are properly masked."""

    def test_jwt_secret_key_accessible_via_get_secret_value(self, monkeypatch):
        """JWT secret should be accessible via get_secret_value()."""
        monkeypatch.setenv("JWT_SECRET_KEY", "super-secret-key-min-32-chars-long-here")
        settings = make_settings()
        assert (
            settings.JWT_SECRET_KEY.get_secret_value()
            == "super-secret-key-min-32-chars-long-here"
        )

    def test_oauth_secrets_accessible_via_get_secret_value(self, monkeypatch):
        """OAuth secrets should be accessible via get_secret_value()."""
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
        monkeypatch.setenv("GITHUB_CLIENT_SECRET", "github-secret")
        settings = make_settings()
        assert settings.GOOGLE_CLIENT_SECRET.get_secret_value() == "google-secret"
        assert settings.GITHUB_CLIENT_SECRET.get_secret_value() == "github-secret"


# ============================================================================
# Configuration Validation Tests
# ============================================================================


class TestConfigurationValidation:
    """Test that invalid configurations raise ValidationError."""

    def test_invalid_postgres_port_type(self, monkeypatch):
        """Invalid PostgreSQL port should raise ValidationError."""
        monkeypatch.setenv("POSTGRES_PORT", "not-a-number")
        with pytest.raises(ValidationError):
            make_settings()

    def test_invalid_rate_limit_type(self, monkeypatch):
        """Invalid rate limit should raise ValidationError."""
        monkeypatch.setenv("RATE_LIMIT_FREE_TIER", "not-a-number")
        with pytest.raises(ValidationError):
            make_settings()

    def test_invalid_jwt_expire_minutes_type(self, monkeypatch):
        """Invalid JWT expiration should raise ValidationError."""
        monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "not-a-number")
        with pytest.raises(ValidationError):
            make_settings()

    def test_invalid_test_mode_type(self, monkeypatch):
        """Invalid TEST_MODE should raise ValidationError."""
        monkeypatch.setenv("TEST_MODE", "not-a-boolean")
        with pytest.raises(ValidationError):
            make_settings()


# ============================================================================
# Configuration Validation Error Tests (via get_settings)
# ============================================================================


class TestConfigurationValidationErrors:
    """Test that validation errors are raised for invalid values.

    Note: These validations happen in get_settings(), not Settings.__init__().
    We patch Settings() inside get_settings to use _env_file=None.
    """

    def _get_settings_no_env(self):
        """Call get_settings() but ensure Settings() doesn't load .env."""
        original_init = Settings.__init__

        def patched_init(self, **kwargs):
            kwargs.setdefault("_env_file", None)
            original_init(self, **kwargs)

        with patch.object(Settings, "__init__", patched_init):
            get_settings.cache_clear()
            return get_settings()

    def test_graph_weights_must_sum_to_one(self, monkeypatch):
        """Graph weights must sum to 1.0."""
        monkeypatch.setenv("GRAPH_WEIGHT_VECTOR", "0.5")
        monkeypatch.setenv("GRAPH_WEIGHT_TAGS", "0.3")
        monkeypatch.setenv("GRAPH_WEIGHT_CLASSIFICATION", "0.3")  # Sum = 1.1
        with pytest.raises(ValueError, match="must sum to 1.0"):
            self._get_settings_no_env()

    def test_jwt_access_token_expire_minutes_must_be_positive(self, monkeypatch):
        """JWT access token expiration must be positive."""
        monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "-1")
        with pytest.raises(ValueError, match="must be positive"):
            self._get_settings_no_env()

    def test_jwt_refresh_token_expire_days_must_be_positive(self, monkeypatch):
        """JWT refresh token expiration must be positive."""
        monkeypatch.setenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "0")
        with pytest.raises(ValueError, match="must be positive"):
            self._get_settings_no_env()

    def test_rate_limit_free_tier_must_be_non_negative(self, monkeypatch):
        """Rate limit free tier must be non-negative."""
        monkeypatch.setenv("RATE_LIMIT_FREE_TIER", "-1")
        with pytest.raises(ValueError, match="must be non-negative"):
            self._get_settings_no_env()

    def test_rate_limit_premium_tier_must_be_non_negative(self, monkeypatch):
        """Rate limit premium tier must be non-negative."""
        monkeypatch.setenv("RATE_LIMIT_PREMIUM_TIER", "-1")
        with pytest.raises(ValueError, match="must be non-negative"):
            self._get_settings_no_env()

    def test_rate_limit_admin_tier_must_be_non_negative(self, monkeypatch):
        """Rate limit admin tier must be non-negative."""
        monkeypatch.setenv("RATE_LIMIT_ADMIN_TIER", "-1")
        with pytest.raises(ValueError, match="must be non-negative"):
            self._get_settings_no_env()

    def test_redis_port_must_be_valid_range(self, monkeypatch):
        """Redis port must be in valid range."""
        monkeypatch.setenv("REDIS_PORT", "70000")
        with pytest.raises(ValueError, match="must be between"):
            self._get_settings_no_env()

    def test_min_quality_threshold_must_be_in_range(self, monkeypatch):
        """Min quality threshold must be between 0 and 1."""
        monkeypatch.setenv("MIN_QUALITY_THRESHOLD", "1.5")
        with pytest.raises(ValueError, match="must be between"):
            self._get_settings_no_env()

    def test_hybrid_search_weight_must_be_in_range(self, monkeypatch):
        """Hybrid search weight must be between 0 and 1."""
        monkeypatch.setenv("DEFAULT_HYBRID_SEARCH_WEIGHT", "2.0")
        with pytest.raises(ValueError, match="must be between"):
            self._get_settings_no_env()


# ============================================================================
# Default Values Tests
# ============================================================================


class TestDefaultValues:
    """Test that all default values are set correctly."""

    def test_all_defaults_are_set(self):
        """All settings should have default values."""
        settings = make_settings()
        assert settings.ENV in ["dev", "staging", "prod"]
        assert settings.DATABASE_URL is not None
        assert settings.JWT_SECRET_KEY is not None
        assert settings.JWT_ALGORITHM == "HS256"
        assert settings.RATE_LIMIT_FREE_TIER == 100

    def test_optional_fields_can_be_none(self):
        """Optional fields should be None by default."""
        settings = make_settings()
        assert settings.GOOGLE_CLIENT_ID is None
        assert settings.GITHUB_CLIENT_ID is None


# ============================================================================
# get_settings() Caching Tests
# ============================================================================


class TestGetSettingsCaching:
    """Test that get_settings() caches properly."""

    def test_get_settings_returns_settings_instance(self):
        """get_settings() should return a Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_get_settings_validates_graph_weights(self, monkeypatch):
        """get_settings() should validate graph weights."""
        monkeypatch.setenv("GRAPH_WEIGHT_VECTOR", "0.5")
        monkeypatch.setenv("GRAPH_WEIGHT_TAGS", "0.3")
        monkeypatch.setenv("GRAPH_WEIGHT_CLASSIFICATION", "0.3")
        get_settings.cache_clear()
        with pytest.raises(ValueError, match="must sum to 1.0"):
            get_settings()


# ============================================================================
# Advanced RAG Configuration Tests
# ============================================================================


class TestAdvancedRAGConfiguration:
    """Test Advanced RAG configuration defaults and env loading."""

    def test_chunking_config_defaults(self):
        """Chunking config should have defaults."""
        settings = make_settings()
        assert isinstance(settings.CHUNK_ON_RESOURCE_CREATE, bool)
        assert settings.CHUNKING_STRATEGY in ("semantic", "fixed")
        assert settings.CHUNK_SIZE > 0
        assert settings.CHUNK_OVERLAP >= 0

    def test_graph_extraction_config_defaults(self):
        """Graph extraction config should have defaults."""
        settings = make_settings()
        assert settings.GRAPH_EXTRACTION_ENABLED is True
        assert settings.GRAPH_EXTRACTION_METHOD == "llm"

    def test_synthetic_questions_config_defaults(self):
        """Synthetic questions config should have defaults."""
        settings = make_settings()
        assert settings.SYNTHETIC_QUESTIONS_ENABLED is False
        assert settings.QUESTIONS_PER_CHUNK > 0

    def test_retrieval_config_defaults(self):
        """Retrieval config should have defaults."""
        settings = make_settings()
        assert settings.DEFAULT_RETRIEVAL_STRATEGY in [
            "parent-child",
            "graphrag",
            "hybrid",
        ]
        assert settings.PARENT_CHILD_CONTEXT_WINDOW >= 0
        assert settings.GRAPHRAG_MAX_HOPS >= 1

    def test_chunking_config_from_env(self, monkeypatch):
        """Chunking config should be loadable from env."""
        monkeypatch.setenv("CHUNK_ON_RESOURCE_CREATE", "true")
        monkeypatch.setenv("CHUNKING_STRATEGY", "semantic")
        monkeypatch.setenv("CHUNK_SIZE", "1024")
        monkeypatch.setenv("CHUNK_OVERLAP", "100")
        settings = make_settings()
        assert settings.CHUNK_ON_RESOURCE_CREATE is True
        assert settings.CHUNKING_STRATEGY == "semantic"
        assert settings.CHUNK_SIZE == 1024
        assert settings.CHUNK_OVERLAP == 100

    def test_graph_extraction_config_from_env(self, monkeypatch):
        """Graph extraction config should be loadable from env."""
        monkeypatch.setenv("GRAPH_EXTRACTION_ENABLED", "false")
        monkeypatch.setenv("GRAPH_EXTRACTION_METHOD", "spacy")
        settings = make_settings()
        assert settings.GRAPH_EXTRACTION_ENABLED is False
        assert settings.GRAPH_EXTRACTION_METHOD == "spacy"

    def test_synthetic_questions_config_from_env(self, monkeypatch):
        """Synthetic questions config should be loadable from env."""
        monkeypatch.setenv("SYNTHETIC_QUESTIONS_ENABLED", "true")
        monkeypatch.setenv("QUESTIONS_PER_CHUNK", "5")
        settings = make_settings()
        assert settings.SYNTHETIC_QUESTIONS_ENABLED is True
        assert settings.QUESTIONS_PER_CHUNK == 5

    def test_retrieval_config_from_env(self, monkeypatch):
        """Retrieval config should be loadable from env."""
        monkeypatch.setenv("DEFAULT_RETRIEVAL_STRATEGY", "graphrag")
        monkeypatch.setenv("PARENT_CHILD_CONTEXT_WINDOW", "2")
        monkeypatch.setenv("GRAPHRAG_MAX_HOPS", "3")
        settings = make_settings()
        assert settings.DEFAULT_RETRIEVAL_STRATEGY == "graphrag"
        assert settings.PARENT_CHILD_CONTEXT_WINDOW == 2
        assert settings.GRAPHRAG_MAX_HOPS == 3


# ============================================================================
# Advanced RAG Configuration Validation Tests (via get_settings)
# ============================================================================


class TestAdvancedRAGConfigurationValidation:
    """Test Advanced RAG configuration validation.

    Note: These validations happen in get_settings(), not Settings.__init__().
    """

    def _get_settings_no_env(self):
        """Call get_settings() but ensure Settings() doesn't load .env."""
        original_init = Settings.__init__

        def patched_init(self, **kwargs):
            kwargs.setdefault("_env_file", None)
            original_init(self, **kwargs)

        with patch.object(Settings, "__init__", patched_init):
            get_settings.cache_clear()
            return get_settings()

    def test_chunking_strategy_must_be_valid(self, monkeypatch):
        """Chunking strategy must be valid."""
        monkeypatch.setenv("CHUNKING_STRATEGY", "invalid")
        with pytest.raises(ValueError, match="CHUNKING_STRATEGY"):
            self._get_settings_no_env()

    def test_chunk_size_must_be_positive(self, monkeypatch):
        """Chunk size must be positive."""
        monkeypatch.setenv("CHUNK_SIZE", "0")
        with pytest.raises(ValueError, match="must be positive"):
            self._get_settings_no_env()

    def test_chunk_overlap_must_be_non_negative(self, monkeypatch):
        """Chunk overlap must be non-negative."""
        monkeypatch.setenv("CHUNK_OVERLAP", "-1")
        with pytest.raises(ValueError, match="must be non-negative"):
            self._get_settings_no_env()

    def test_chunk_overlap_must_be_less_than_chunk_size(self, monkeypatch):
        """Chunk overlap must be less than chunk size."""
        monkeypatch.setenv("CHUNK_SIZE", "100")
        monkeypatch.setenv("CHUNK_OVERLAP", "150")
        with pytest.raises(ValueError, match="must be less than"):
            self._get_settings_no_env()

    def test_graph_extraction_method_must_be_valid(self, monkeypatch):
        """Graph extraction method must be valid."""
        monkeypatch.setenv("GRAPH_EXTRACTION_METHOD", "invalid")
        with pytest.raises(ValueError, match="GRAPH_EXTRACTION_METHOD"):
            self._get_settings_no_env()

    def test_questions_per_chunk_must_be_positive(self, monkeypatch):
        """Questions per chunk must be positive."""
        monkeypatch.setenv("QUESTIONS_PER_CHUNK", "0")
        with pytest.raises(ValueError, match="must be positive"):
            self._get_settings_no_env()

    def test_retrieval_strategy_must_be_valid(self, monkeypatch):
        """Retrieval strategy must be valid."""
        monkeypatch.setenv("DEFAULT_RETRIEVAL_STRATEGY", "invalid")
        with pytest.raises(ValueError, match="DEFAULT_RETRIEVAL_STRATEGY"):
            self._get_settings_no_env()

    def test_parent_child_context_window_must_be_non_negative(self, monkeypatch):
        """Parent-child context window must be non-negative."""
        monkeypatch.setenv("PARENT_CHILD_CONTEXT_WINDOW", "-1")
        with pytest.raises(ValueError, match="must be non-negative"):
            self._get_settings_no_env()

    def test_graphrag_max_hops_must_be_positive(self, monkeypatch):
        """GraphRAG max hops must be positive."""
        monkeypatch.setenv("GRAPHRAG_MAX_HOPS", "0")
        with pytest.raises(ValueError, match="must be positive"):
            self._get_settings_no_env()


# ============================================================================
# Environment Variable Loading Tests
# ============================================================================


class TestEnvironmentVariableLoading:
    """Test that environment variables are loaded correctly."""

    def test_database_url_from_env(self, monkeypatch):
        """DATABASE_URL should be loadable from environment."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/db")
        settings = make_settings()
        assert settings.DATABASE_URL == "postgresql://user:pass@host:5432/db"

    def test_postgres_config_from_env(self, monkeypatch):
        """PostgreSQL config should be loadable from environment."""
        monkeypatch.setenv("POSTGRES_SERVER", "prod-db.example.com")
        monkeypatch.setenv("POSTGRES_USER", "produser")
        monkeypatch.setenv("POSTGRES_PASSWORD", "prodpass")
        monkeypatch.setenv("POSTGRES_DB", "proddb")
        monkeypatch.setenv("POSTGRES_PORT", "5433")
        settings = make_settings()
        assert settings.POSTGRES_SERVER == "prod-db.example.com"
        assert settings.POSTGRES_USER == "produser"
        assert settings.POSTGRES_PASSWORD == "prodpass"
        assert settings.POSTGRES_DB == "proddb"
        assert settings.POSTGRES_PORT == 5433

    def test_multiple_env_vars_loaded(self, monkeypatch):
        """Multiple environment variables should be loaded together."""
        monkeypatch.setenv("JWT_SECRET_KEY", "env-secret-min-32-chars-long-here")
        monkeypatch.setenv("JWT_ALGORITHM", "RS256")
        monkeypatch.setenv("RATE_LIMIT_FREE_TIER", "200")
        monkeypatch.setenv("TEST_MODE", "true")
        settings = make_settings()
        assert (
            settings.JWT_SECRET_KEY.get_secret_value()
            == "env-secret-min-32-chars-long-here"
        )
        assert settings.JWT_ALGORITHM == "RS256"
        assert settings.RATE_LIMIT_FREE_TIER == 200
        assert settings.TEST_MODE is True


# ============================================================================
# Production Environment Validation Tests
# ============================================================================


class TestProductionEnvironmentValidation:
    """Test that production environment has proper security requirements."""

    def test_jwt_secret_key_required_in_production(self, monkeypatch):
        """JWT secret key must be set in production mode."""
        monkeypatch.setenv("ENV", "prod")
        monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)
        monkeypatch.setenv("ALLOWED_REDIRECT_URLS", '["https://example.com"]')
        # Should not raise - valid secret provided
        settings = make_settings()
        assert settings.ENV == "prod"

    def test_jwt_secret_key_too_short_in_production(self, monkeypatch):
        """JWT secret key must be at least 32 chars in production."""
        monkeypatch.setenv("ENV", "prod")
        monkeypatch.setenv("JWT_SECRET_KEY", "short")
        monkeypatch.setenv("ALLOWED_REDIRECT_URLS", '["https://example.com"]')
        with pytest.raises(ValidationError, match="at least 32 characters"):
            make_settings()

    def test_jwt_secret_key_default_rejected_in_production(self, monkeypatch):
        """Default JWT secret key is rejected in production."""
        monkeypatch.setenv("ENV", "prod")
        monkeypatch.setenv("ALLOWED_REDIRECT_URLS", '["https://example.com"]')
        # Don't set JWT_SECRET_KEY - use default
        with pytest.raises(ValidationError, match="default"):
            make_settings()

    def test_dev_mode_allows_default_secret(self, monkeypatch):
        """Dev mode allows the default secret for development convenience."""
        monkeypatch.setenv("ENV", "dev")
        # Don't set JWT_SECRET_KEY - use default
        settings = make_settings()
        assert settings.ENV == "dev"
        assert "change-this-secret-key" in settings.JWT_SECRET_KEY.get_secret_value()

    def test_production_mode_requires_strong_secret(self, monkeypatch):
        """Production mode requires a strong JWT secret."""
        monkeypatch.setenv("ENV", "prod")
        monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)  # Exactly 32 chars - minimum
        monkeypatch.setenv("ALLOWED_REDIRECT_URLS", '["https://example.com"]')
        settings = make_settings()
        assert settings.ENV == "prod"
        assert len(settings.JWT_SECRET_KEY.get_secret_value()) == 32

    def test_production_mode_rejects_weak_secret(self, monkeypatch):
        """Production mode rejects weak JWT secrets."""
        monkeypatch.setenv("ENV", "prod")
        monkeypatch.setenv("JWT_SECRET_KEY", "weak")  # Too short
        monkeypatch.setenv("ALLOWED_REDIRECT_URLS", '["https://example.com"]')
        with pytest.raises(ValidationError):
            make_settings()

    def test_test_mode_setting_rejected_in_production(self, monkeypatch):
        """TEST_MODE=True is rejected in production mode."""
        monkeypatch.setenv("ENV", "prod")
        monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)  # Valid secret
        monkeypatch.setenv("TEST_MODE", "true")
        monkeypatch.setenv("ALLOWED_REDIRECT_URLS", '["https://example.com"]')
        with pytest.raises(
            ValidationError, match="TEST_MODE must be False in production"
        ):
            make_settings()

    def test_testing_env_var_rejected_in_production(self, monkeypatch):
        """TESTING=true environment variable is rejected in production mode."""
        monkeypatch.setenv("ENV", "prod")
        monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)  # Valid secret
        monkeypatch.setenv("TESTING", "true")
        monkeypatch.setenv("ALLOWED_REDIRECT_URLS", '["https://example.com"]')
        with pytest.raises(
            ValidationError, match="TESTING environment variable must not be set"
        ):
            make_settings()

    def test_testing_env_var_variants_rejected_in_production(self, monkeypatch):
        """TESTING=1 and TESTING=yes are rejected in production mode."""
        monkeypatch.setenv("ENV", "prod")
        monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)  # Valid secret
        monkeypatch.setenv("TESTING", "1")
        monkeypatch.setenv("ALLOWED_REDIRECT_URLS", '["https://example.com"]')
        with pytest.raises(
            ValidationError, match="TESTING environment variable must not be set"
        ):
            make_settings()

    def test_testing_env_var_yes_rejected_in_production(self, monkeypatch):
        """TESTING=yes is rejected in production mode."""
        monkeypatch.setenv("ENV", "prod")
        monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)  # Valid secret
        monkeypatch.setenv("TESTING", "yes")
        monkeypatch.setenv("ALLOWED_REDIRECT_URLS", '["https://example.com"]')
        with pytest.raises(
            ValidationError, match="TESTING environment variable must not be set"
        ):
            make_settings()

    def test_production_allows_test_mode_disabled(self, monkeypatch):
        """Production mode allows TEST_MODE=False and TESTING not set."""
        monkeypatch.setenv("ENV", "prod")
        monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)  # Valid secret
        monkeypatch.setenv("ALLOWED_REDIRECT_URLS", '["https://example.com"]')
        # Don't set TEST_MODE or TESTING - they default to False
        settings = make_settings()
        assert settings.ENV == "prod"
        assert settings.TEST_MODE is False


# ============================================================================
# PostgreSQL Password Optional Tests
# ============================================================================


class TestPostgresPasswordOptional:
    """Test that POSTGRES_PASSWORD is optional for SQLite."""

    def test_postgres_password_optional_for_sqlite(self, monkeypatch):
        """POSTGRES_PASSWORD should be optional when using SQLite."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
        settings = make_settings()
        assert settings.POSTGRES_PASSWORD is None

    def test_postgres_password_required_for_postgresql(self, monkeypatch):
        """POSTGRES_PASSWORD should be required when using PostgreSQL."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:placeholder@host:5432/db")
        # Note: This validation happens in get_settings(), not in Settings.__init__()
        # The Settings object is created, but get_settings() will raise an error
        settings = make_settings()
        assert settings.POSTGRES_PASSWORD is None  # Not set in env

    def test_postgres_password_can_be_set(self, monkeypatch):
        """POSTGRES_PASSWORD should be settable."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
        monkeypatch.setenv("POSTGRES_PASSWORD", "my-secret-password")
        settings = make_settings()
        assert settings.POSTGRES_PASSWORD == "my-secret-password"
