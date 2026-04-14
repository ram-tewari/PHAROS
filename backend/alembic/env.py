from logging.config import fileConfig
import sys
import os

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Ensure project root is on sys.path so 'backend' package is importable
_alembic_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_dir = os.path.dirname(_alembic_dir)
_project_root = os.path.dirname(_pkg_dir)
for _p in (_project_root, _pkg_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Import our models and settings
from backend.app.config.settings import get_settings  # noqa: E402
from backend.app.database.base import Base  # noqa: E402
import backend.app.database.models  # noqa: F401, E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    # Use settings for database URL
    settings = get_settings()
    url = settings.get_database_url()
    # Convert async URL to sync for Alembic
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://")
    elif url.startswith("sqlite+aiosqlite://"):
        url = url.replace("sqlite+aiosqlite://", "sqlite://")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Check if connection is provided (e.g., from tests)
    connection = config.attributes.get("connection", None)

    if connection is None:
        # Use settings for database URL
        settings = get_settings()
        configuration = config.get_section(config.config_ini_section, {})
        url = settings.get_database_url()
        # Convert async URL to sync for Alembic
        if url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql://")
        elif url.startswith("sqlite+aiosqlite://"):
            url = url.replace("sqlite+aiosqlite://", "sqlite://")
        configuration["sqlalchemy.url"] = url

        connectable = engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                version_table_pk=False,
                # Use longer varchar for version_num to support descriptive migration names
                version_table_schema=None,
            )

            with context.begin_transaction():
                context.run_migrations()
    else:
        # Use provided connection (from tests)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_pk=False,
            version_table_schema=None,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
