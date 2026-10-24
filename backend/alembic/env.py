"""Alembic environment.

Run from ``backend/``::

    alembic -c config/alembic.ini upgrade head

The database URL comes from ``DATABASE_URL`` (via app settings) and is
normalised to the psycopg2 / sqlite sync drivers by
``app.shared.db_url.normalize_database_url`` — the same function the
application uses, so migrations always hit the database the app uses.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

# Make `app` importable no matter where alembic is invoked from.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import app.database.models  # noqa: F401, E402  (populates Base.metadata)
from app.config.settings import get_settings  # noqa: E402
from app.shared.database import Base  # noqa: E402
from app.shared.db_url import normalize_database_url  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _include_object(object_, name, type_, reflected, compare_to):
    """Skip schema objects declared ``.ddl_if(dialect=...)`` for another dialect.

    Autogenerate ignores ``ddl_if``; without this, ``alembic check`` on SQLite
    would demand the PostgreSQL-only HNSW / GIN indexes.
    """
    ddl_if = getattr(object_, "_ddl_if", None)
    if ddl_if is not None and ddl_if.dialect is not None:
        return ddl_if.dialect == context.get_context().dialect.name
    return True


def _database_url() -> str:
    return normalize_database_url(get_settings().get_database_url(), async_driver=False)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:  # supplied by tests
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(
            connection=conn,
            target_metadata=target_metadata,
            # SQLite cannot ALTER most things in place; batch mode recreates
            # tables when needed. No-op on PostgreSQL.
            render_as_batch=True,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
