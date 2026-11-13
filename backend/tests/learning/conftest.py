"""Database fixtures shared with the code-intelligence suite (SQLite always, PostgreSQL when configured)."""

from tests.codeintel.conftest import db_url, engine, session  # noqa: F401 - pytest fixtures
