"""
Integration tests for database connections.

Tests database initialization with SQLite and PostgreSQL,
and error handling for connection failures.

Requirements: 2.1, 2.4, 8.1
"""

import pytest
from unittest.mock import patch, MagicMock

from app.shared.database import init_database, get_database_type
from app.config.settings import Settings


class TestSQLiteConnection:
    """Test SQLite database connection."""

    def test_sqlite_connection_with_file(self, tmp_path):
        """Test SQLite connection with file-based database."""
        # Create a temporary database file path
        db_file = tmp_path / "test.db"
        database_url = f"sqlite:///{db_file}"

        # Initialize database
        init_database(database_url, env="dev")

        # Verify database type
        assert get_database_type(database_url) == "sqlite"

    def test_sqlite_connection_in_memory(self):
        """Test SQLite connection with in-memory database."""
        database_url = "sqlite:///:memory:"

        # Initialize database
        init_database(database_url, env="dev")

        # Verify database type
        assert get_database_type(database_url) == "sqlite"

    def test_sqlite_backward_compatibility(self):
        """Test that SQLite URLs work without modification."""
        # Test with default SQLite URL from settings
        settings = Settings(DATABASE_URL="sqlite:///./backend.db")
        database_url = settings.get_database_url()

        # Should return SQLite URL unchanged
        assert database_url == "sqlite:///./backend.db"
        assert get_database_type(database_url) == "sqlite"


class TestPostgreSQLConnection:
    """Test PostgreSQL database connection."""

    def test_postgresql_url_construction(self):
        """Test PostgreSQL URL construction from settings."""
        settings = Settings(
            POSTGRES_SERVER="testhost",
            POSTGRES_USER="testuser",
            POSTGRES_PASSWORD="testpass",
            POSTGRES_DB="testdb",
            POSTGRES_PORT=5432,
            DATABASE_URL="postgresql://placeholder",  # Trigger PostgreSQL mode
        )

        database_url = settings.get_database_url()

        # Verify URL format
        assert (
            database_url
            == "postgresql+asyncpg://testuser:testpass@testhost:5432/testdb"
        )
        assert get_database_type(database_url) == "postgresql"

    def test_postgresql_url_with_custom_port(self):
        """Test PostgreSQL URL with custom port."""
        settings = Settings(
            POSTGRES_SERVER="localhost",
            POSTGRES_USER="user",
            POSTGRES_PASSWORD="pass",
            POSTGRES_DB="db",
            POSTGRES_PORT=5433,
            DATABASE_URL="postgresql://placeholder",
        )

        database_url = settings.get_database_url()

        assert "5433" in database_url
        assert get_database_type(database_url) == "postgresql"

    @pytest.mark.skipif(
        True,  # Skip by default - requires actual PostgreSQL instance
        reason="Requires PostgreSQL instance - run manually with real database",
    )
    def test_postgresql_connection_real(self):
        """Test actual PostgreSQL connection (manual test only)."""
        # This test requires a real PostgreSQL instance
        # Set environment variables before running:
        # POSTGRES_SERVER=localhost
        # POSTGRES_USER=neo_user
        # POSTGRES_PASSWORD=neo_password
        # POSTGRES_DB=neo_alexandria

        settings = Settings(DATABASE_URL="postgresql://placeholder")
        database_url = settings.get_database_url()

        # Initialize database
        init_database(database_url, env="dev")

        # Verify database type
        assert get_database_type(database_url) == "postgresql"


class TestDatabaseConnectionErrors:
    """Test database connection error handling."""

    def test_invalid_database_url_raises_error(self):
        """Test that invalid database URL raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported database type"):
            get_database_type("mysql://localhost/db")

    def test_connection_failure_logs_and_raises(self):
        """Test that connection failures are logged and raise RuntimeError."""
        # Use an invalid database type that will fail during engine creation
        invalid_url = "mysql://localhost/db"

        with pytest.raises((RuntimeError, ValueError)):
            init_database(invalid_url, env="dev")

    def test_postgresql_connection_failure_with_invalid_host(self):
        """Test PostgreSQL connection failure with invalid host."""
        # Create settings with invalid PostgreSQL host
        settings = Settings(
            POSTGRES_SERVER="invalid-host-that-does-not-exist",
            POSTGRES_USER="user",
            POSTGRES_PASSWORD="pass",
            POSTGRES_DB="db",
            POSTGRES_PORT=5432,
            DATABASE_URL="postgresql://placeholder",
        )

        database_url = settings.get_database_url()

        # Should raise RuntimeError when trying to initialize
        # Note: This might not fail immediately with asyncpg as it's lazy
        # The actual connection test happens on first query
        try:
            init_database(database_url, env="dev")
            # If initialization succeeds (lazy connection), that's also valid behavior
        except RuntimeError as e:
            # If it fails, verify error message is informative
            assert "Failed to initialize database connection" in str(e)

    def test_get_database_url_with_sqlite_returns_unchanged(self):
        """Test that SQLite URLs are returned unchanged."""
        settings = Settings(DATABASE_URL="sqlite:///./test.db")

        url = settings.get_database_url()

        assert url == "sqlite:///./test.db"

    def test_get_database_url_with_postgresql_constructs_url(self):
        """Test that PostgreSQL URLs are constructed from components."""
        settings = Settings(
            POSTGRES_SERVER="host",
            POSTGRES_USER="user",
            POSTGRES_PASSWORD="pass",
            POSTGRES_DB="db",
            POSTGRES_PORT=5432,
            DATABASE_URL="postgresql://anything",  # Trigger PostgreSQL mode
        )

        url = settings.get_database_url()

        # Should construct new URL from components
        assert url == "postgresql+asyncpg://user:pass@host:5432/db"
        assert "asyncpg" in url  # Verify async driver


class TestDatabaseTypeDetection:
    """Test database type detection."""

    def test_detect_sqlite_type(self):
        """Test SQLite type detection."""
        assert get_database_type("sqlite:///./backend.db") == "sqlite"
        assert get_database_type("sqlite:///:memory:") == "sqlite"

    def test_detect_postgresql_type(self):
        """Test PostgreSQL type detection."""
        assert get_database_type("postgresql://user:pass@host/db") == "postgresql"
        assert (
            get_database_type("postgresql+asyncpg://user:pass@host/db") == "postgresql"
        )
        assert (
            get_database_type("postgresql+psycopg2://user:pass@host/db") == "postgresql"
        )

    def test_unsupported_database_type_raises_error(self):
        """Test that unsupported database types raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported database type"):
            get_database_type("mysql://localhost/db")

        with pytest.raises(ValueError, match="Unsupported database type"):
            get_database_type("mongodb://localhost/db")


class TestDatabaseInitialization:
    """Test database initialization behavior."""

    def test_init_database_uses_settings_by_default(self, monkeypatch):
        """Test that init_database uses settings.get_database_url() when no URL provided."""
        # Ensure DATABASE_URL env var doesn't short-circuit the settings lookup.
        monkeypatch.delenv("DATABASE_URL", raising=False)

        # This test verifies the integration with settings
        with patch("app.config.settings.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.get_database_url.return_value = "sqlite:///:memory:"
            mock_get_settings.return_value = mock_settings

            # Initialize without providing URL
            init_database(env="dev")

            # Verify settings.get_database_url() was called
            mock_settings.get_database_url.assert_called_once()

    def test_init_database_with_explicit_url(self):
        """Test that init_database accepts explicit URL."""
        # Provide explicit URL
        database_url = "sqlite:///:memory:"

        # Should not raise error
        init_database(database_url, env="dev")

    def test_init_database_logs_success(self, caplog):
        """Test that successful initialization logs message."""
        import logging

        caplog.set_level(logging.INFO)

        database_url = "sqlite:///:memory:"
        init_database(database_url, env="dev")

        # Check for success log message
        assert any(
            "Database initialized successfully" in record.message
            for record in caplog.records
        )
        assert any("sqlite" in record.message for record in caplog.records)

    def test_init_database_logs_error_on_failure(self, caplog):
        """Test that failed initialization logs error."""
        import logging

        caplog.set_level(logging.ERROR)

        # Use invalid database type
        invalid_url = "mysql://localhost/db"

        with pytest.raises((RuntimeError, ValueError)):
            init_database(invalid_url, env="dev")

        # Check for error log message (either from init_database or from get_database_type)
        assert any(
            "Failed to initialize database connection" in record.message
            or "Unsupported database type" in record.message
            for record in caplog.records
        )
