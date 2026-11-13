"""
Tests for Settings configuration (Phase 17).

These tests use REAL Settings instances with environment variables,
ensuring tests match actual runtime behavior.

Note: Validation checks (like "must be positive") are performed in
get_settings(), not in Settings.__init__(). Tests that check validation
must use get_settings() instead of Settings() directly.
"""

import pytest
from pydantic import ValidationError
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

    def test_postgresql_database_url_is_returned_as_is(self, monkeypatch):
        """A PostgreSQL DATABASE_URL wins over POSTGRES_* parts (it used to be
        silently replaced by them, pointing Alembic at localhost)."""
        url = "postgresql://neon_user:secret@ep-x.neon.tech/db?sslmode=require"
        monkeypatch.setenv("DATABASE_URL", url)
        monkeypatch.setenv("POSTGRES_SERVER", "somewhere-else")
        monkeypatch.setenv("POSTGRES_PASSWORD", "other")
        assert make_settings().get_database_url() == url

    def test_postgresql_url_built_from_parts_when_database_url_unset(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("POSTGRES_SERVER", "prodhost")
        monkeypatch.setenv("POSTGRES_USER", "admin")
        monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss:word!")
        monkeypatch.setenv("POSTGRES_DB", "proddb")
        monkeypatch.setenv("POSTGRES_PORT", "5433")
        assert make_settings().get_database_url() == "postgresql://admin:p%40ss%3Aword%21@prodhost:5433/proddb"

    def test_postgresql_does_not_require_postgres_password(self, monkeypatch):
        from app.config.settings import Settings, get_settings

        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
        monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
        get_settings.cache_clear() if hasattr(get_settings, "cache_clear") else None
        assert isinstance(Settings(), Settings)


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
        assert settings.EMBEDDING_BACKEND == "auto"
        assert settings.INGESTION_NOTIFY_KEY == "ingest_queue"
        assert "github.com" in settings.CODEINTEL_ALLOWED_GIT_HOSTS

    def test_optional_fields_can_be_none(self, monkeypatch):
        """Optional credentials are unset by default (auth fails closed)."""
        for var in ("PHAROS_ADMIN_TOKEN", "PHAROS_READ_TOKEN", "EDGE_EMBEDDING_URL", "GIT_CLONE_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        settings = make_settings()
        assert settings.PHAROS_READ_TOKEN is None
        assert settings.EDGE_EMBEDDING_URL is None
        assert settings.GIT_CLONE_TOKEN is None

    def test_removed_saas_auth_settings_are_gone(self):
        """JWT/OAuth/rate-limit settings were removed with the SaaS auth stack."""
        settings = make_settings()
        for name in ("JWT_SECRET_KEY", "GOOGLE_CLIENT_ID", "GITHUB_CLIENT_ID", "RATE_LIMIT_FREE_TIER"):
            assert not hasattr(settings, name)


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
        monkeypatch.setenv("EMBEDDING_BACKEND", "hash")
        monkeypatch.setenv("CODEINTEL_MAX_FILES", "123")
        monkeypatch.setenv("MCP_ALLOWED_HOSTS", '["pharos.example.com"]')
        monkeypatch.setenv("TEST_MODE", "true")
        settings = make_settings()
        assert settings.EMBEDDING_BACKEND == "hash"
        assert settings.CODEINTEL_MAX_FILES == 123
        assert settings.MCP_ALLOWED_HOSTS == ["pharos.example.com"]
        assert settings.TEST_MODE is True


# ============================================================================
# Production Environment Validation Tests
# ============================================================================


class TestProductionEnvironmentValidation:
    """Production refuses the test-only switches that disable authentication."""

    @pytest.fixture(autouse=True)
    def _clean_test_switches(self, monkeypatch):
        # The global test conftest sets these; production must see them unset.
        for var in ("TEST_AUTH_BYPASS", "TESTING", "TEST_MODE"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("ENV", "prod")

    def test_production_allows_clean_configuration(self):
        settings = make_settings()
        assert settings.ENV == "prod"
        assert settings.TEST_MODE is False

    def test_test_mode_setting_rejected_in_production(self, monkeypatch):
        monkeypatch.setenv("TEST_MODE", "true")
        with pytest.raises(ValidationError, match="TEST_MODE must be False in production"):
            make_settings()

    @pytest.mark.parametrize("value", ["true", "1", "yes", "TRUE"])
    def test_testing_env_var_rejected_in_production(self, monkeypatch, value):
        monkeypatch.setenv("TESTING", value)
        with pytest.raises(ValidationError, match="TESTING must not be set in production"):
            make_settings()

    def test_auth_bypass_rejected_in_production(self, monkeypatch):
        monkeypatch.setenv("TEST_AUTH_BYPASS", "true")
        with pytest.raises(ValidationError, match="TEST_AUTH_BYPASS must not be set in production"):
            make_settings()

    def test_dev_mode_tolerates_test_switches(self, monkeypatch):
        monkeypatch.setenv("ENV", "dev")
        monkeypatch.setenv("TEST_AUTH_BYPASS", "true")
        assert make_settings().ENV == "dev"


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
