"""Process-level wiring shared by the API, the worker and the CLI."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from ..config.settings import get_settings
from ..shared import database
from .git_source import RepoRef, parse_repo_spec


def ensure_database() -> None:
    if database.SessionLocal is None:
        settings = get_settings()
        database.init_database(settings.get_database_url(), settings.ENV)


@contextmanager
def session_scope() -> Iterator[Session]:
    ensure_database()
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def secret(value) -> str | None:
    return value.get_secret_value() if value is not None else None


def job_ref(repo_url: str) -> RepoRef:
    """Rebuild a RepoRef for a stored job.

    Local (``file://``) jobs can only have been created by the CLI — the API
    validates with ``allow_local=False`` — so allowing them here does not let
    API callers reach the worker's filesystem.
    """
    settings = get_settings()
    return parse_repo_spec(repo_url, allowed_hosts=settings.CODEINTEL_ALLOWED_GIT_HOSTS, allow_local=True)


def run_options() -> dict:
    s = get_settings()
    return {
        "max_file_bytes": s.CODEINTEL_MAX_FILE_BYTES,
        "max_files": s.CODEINTEL_MAX_FILES,
        "clone_timeout": s.CODEINTEL_CLONE_TIMEOUT_SECONDS,
        "clone_token": secret(s.GIT_CLONE_TOKEN),
    }
