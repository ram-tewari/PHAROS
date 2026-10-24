"""Database URL normalisation.

Every component that opens a database connection (the API, the workers,
Alembic, scripts) goes through :func:`normalize_database_url` so that driver
selection is explicit and identical everywhere.

Why this exists: SQLAlchemy 2.1 changed the default driver for a bare
``postgresql://`` URL from psycopg2 to psycopg 3. Neon hands out bare
``postgresql://`` URLs, so relying on the default silently picks a driver that
is not installed. We always pin the driver: psycopg2 for sync, asyncpg for
async.

asyncpg does not understand libpq query parameters such as ``sslmode`` or
``channel_binding``; they are stripped from async URLs and translated into
the ``ssl`` connect argument by :func:`asyncpg_ssl_mode`.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_PG_SCHEMES = {
    "postgres",
    "postgresql",
    "postgresql+psycopg2",
    "postgresql+psycopg",
    "postgresql+asyncpg",
}
_SQLITE_SCHEMES = {"sqlite", "sqlite+pysqlite", "sqlite+aiosqlite"}

# libpq parameters asyncpg rejects as unknown keyword arguments.
_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding", "sslrootcert", "options"}


def database_kind(url: str) -> str:
    """Return ``"postgresql"`` or ``"sqlite"`` for a database URL."""
    scheme = urlsplit(url).scheme.lower()
    if scheme in _PG_SCHEMES:
        return "postgresql"
    if scheme in _SQLITE_SCHEMES:
        return "sqlite"
    raise ValueError(f"Unsupported database URL scheme: {scheme!r}")


def normalize_database_url(url: str, *, async_driver: bool) -> str:
    """Return ``url`` with an explicit, installed driver.

    >>> normalize_database_url("postgresql://u:p@h/db", async_driver=False)
    'postgresql+psycopg2://u:p@h/db'
    >>> normalize_database_url("postgres://u:p@h/db?sslmode=require", async_driver=True)
    'postgresql+asyncpg://u:p@h/db'
    >>> normalize_database_url("sqlite:///./x.db", async_driver=True)
    'sqlite+aiosqlite:///./x.db'
    """
    kind = database_kind(url)
    # Replace the scheme textually: urlunsplit() would drop the "//" of
    # authority-less URLs such as sqlite:///:memory:.
    rest = url.split("://", 1)[1]
    if kind == "sqlite":
        return ("sqlite+aiosqlite" if async_driver else "sqlite") + "://" + rest

    scheme = "postgresql+asyncpg" if async_driver else "postgresql+psycopg2"
    if async_driver and "?" in rest:
        base, query = rest.split("?", 1)
        kept = [(k, v) for k, v in parse_qsl(query) if k not in _LIBPQ_ONLY_PARAMS]
        rest = base + ("?" + urlencode(kept) if kept else "")
    return scheme + "://" + rest


def asyncpg_ssl_mode(url: str) -> str | None:
    """Translate a libpq ``sslmode`` query parameter into asyncpg's ``ssl`` value.

    Returns None when the URL does not specify one.
    """
    params = dict(parse_qsl(urlsplit(url).query))
    mode = params.get("sslmode")
    if mode is None:
        return None
    # asyncpg accepts the libpq names directly for these modes.
    if mode in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
        return mode
    raise ValueError(f"Unsupported sslmode {mode!r}")


def redact_database_url(url: str) -> str:
    """Return ``url`` with any password replaced, safe for logs and errors."""
    parts = urlsplit(url)
    if parts.password is None:
        return url
    netloc = parts.netloc.replace(f":{parts.password}@", ":***@", 1)
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
