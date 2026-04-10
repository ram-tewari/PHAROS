"""
Shared database components.

Provides engine, session factory, and Base for all modules.
Extracted from app/database/base.py to serve as shared kernel component.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Session as OrmSession, sessionmaker
from sqlalchemy import create_engine, event, Engine
from sqlalchemy.exc import OperationalError, DBAPIError
from typing import AsyncGenerator, Literal, Callable, TypeVar, ParamSpec, Generator
from functools import wraps
import asyncio
import time
import logging
import os

logger = logging.getLogger(__name__)

# Type variables for generic decorator
P = ParamSpec("P")
T = TypeVar("T")

# Global engine and session factory (initialized by init_database)
async_engine = None
AsyncSessionLocal = None
sync_engine = None
SessionLocal = None

# Default database URL for when settings aren't available
_DEFAULT_DATABASE_URL = "sqlite:///./backend.db"


class Base(DeclarativeBase):
    """
    SQLAlchemy declarative base class.

    All database models inherit from this base class to ensure consistent
    metadata management and table creation across the application.
    """

    pass


def _get_database_url_from_env() -> str:
    """
    Get database URL from environment variable without importing settings.

    This avoids circular imports during module initialization.

    Returns:
        Database URL from DATABASE_URL env var or default
    """
    return os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL)


def get_database_type(
    database_url: str | None = None,
) -> Literal["sqlite", "postgresql"]:
    """
    Detect database type from connection URL.

    Args:
        database_url: Database connection URL. If None, uses DATABASE_URL env var

    Returns:
        Database type: "sqlite" or "postgresql"

    Raises:
        ValueError: If database type is not supported
    """
    if database_url is None:
        # Use environment variable directly to avoid circular import
        database_url = _get_database_url_from_env()

    if database_url.startswith("sqlite"):
        return "sqlite"
    elif database_url.startswith("postgresql"):
        return "postgresql"
    else:
        raise ValueError(f"Unsupported database type in URL: {database_url}")


def create_database_engine(
    database_url: str, is_async: bool = False, env: str = "prod"
) -> Engine:
    """
    Factory function to create database engine with database-specific parameters.

    Args:
        database_url: Database connection URL
        is_async: Whether to create async engine (True) or sync engine (False)
        env: Environment (dev/prod) for echo configuration

    Returns:
        SQLAlchemy Engine configured with database-specific parameters
    """
    db_type = get_database_type(database_url)

    # Convert URL to use appropriate driver
    if is_async:
        # Async: use aiosqlite for SQLite, asyncpg for PostgreSQL
        if database_url.startswith("sqlite:///"):
            database_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace(
                "postgresql://", "postgresql+asyncpg://"
            )
        elif database_url.startswith("postgresql+psycopg2://"):
            database_url = database_url.replace(
                "postgresql+psycopg2://", "postgresql+asyncpg://"
            )
    else:
        # Sync: use default sqlite driver, psycopg2 for PostgreSQL
        if (
            database_url.startswith("postgresql://")
            and "+psycopg2" not in database_url
            and "+asyncpg" not in database_url
        ):
            database_url = database_url.replace(
                "postgresql://", "postgresql+psycopg2://"
            )
        elif database_url.startswith("postgresql+asyncpg://"):
            database_url = database_url.replace(
                "postgresql+asyncpg://", "postgresql+psycopg2://"
            )

    # Common parameters
    common_params = {"echo": True if env == "dev" else False, "echo_pool": True}

    # Database-specific parameters
    if db_type == "postgresql":
        # PostgreSQL-specific connection pool parameters
        engine_params = {
            **common_params,
            "pool_size": 5,  # Reduced for serverless (NeonDB)
            "max_overflow": 10,  # Reduced for serverless (total: 15)
            "pool_recycle": 300,  # Recycle connections after 5 minutes (before NeonDB auto-suspend)
            "pool_pre_ping": True,  # Health check before using connection (critical for NeonDB)
            "pool_timeout": 30,  # Wait up to 30 seconds for connection from pool
            "isolation_level": "READ COMMITTED",  # Transaction isolation level
        }

        # Add connect_args based on driver type
        if is_async:
            # asyncpg uses server_settings instead of options
            engine_params["connect_args"] = {
                "server_settings": {
                    "statement_timeout": "30000",  # 30 seconds timeout for queries
                },
                "timeout": 60,  # Connection timeout (60s to allow NeonDB wake-up)
                "command_timeout": 60,  # Command timeout
            }
        else:
            # psycopg2 uses options parameter
            engine_params["connect_args"] = {
                "options": "-c statement_timeout=30000",  # 30 seconds timeout for queries
                "connect_timeout": 60,  # Connection timeout (60s to allow NeonDB wake-up)
            }
    else:  # sqlite
        # SQLite-specific connection parameters
        engine_params = {
            **common_params,
            "connect_args": {
                "check_same_thread": False,  # Allow multi-threaded access
                "timeout": 30,  # 30 seconds timeout for locks
            },
        }

    # Create engine
    if is_async:
        return create_async_engine(database_url, **engine_params)
    else:
        return create_engine(database_url, **engine_params)


def _is_connection_refused_error(error: Exception) -> bool:
    """
    Check if an exception is a connection refused error (e.g., NeonDB auto-suspend).

    Args:
        error: Exception to check

    Returns:
        bool: True if error is a connection refused error, False otherwise
    """
    error_msg = str(error).lower()

    connection_refused_indicators = [
        "connection refused",
        "could not connect",
        "connection timed out",
        "no connection to the server",
        "server closed the connection",
        "connection reset",
    ]

    return any(indicator in error_msg for indicator in connection_refused_indicators)


def init_database(database_url: str | None = None, env: str = "prod") -> None:
    """
    Initialize database engine and session factory with retry logic for serverless databases.

    Handles NeonDB auto-suspend by retrying connection with exponential backoff.

    Args:
        database_url: Database connection URL. If None, uses DATABASE_URL env var or settings
        env: Environment (dev/prod) for echo configuration

    Raises:
        RuntimeError: If database connection fails after all retries
    """
    global async_engine, AsyncSessionLocal, sync_engine, SessionLocal

    # Get database URL - prefer explicit, then env var, then settings
    if database_url is None:
        database_url = os.environ.get("DATABASE_URL")
        if database_url is None:
            # Only import settings as last resort
            from ..config.settings import get_settings

            database_url = get_settings().get_database_url()

    # Retry configuration for serverless databases (e.g., NeonDB auto-suspend)
    max_retries = 5
    initial_backoff = 2.0  # Start with 2 seconds
    backoff_multiplier = 2.0

    last_error = None
    backoff = initial_backoff

    for attempt in range(max_retries):
        try:
            # Create async engine
            async_engine = create_database_engine(database_url, is_async=True, env=env)

            # Create async sessionmaker
            AsyncSessionLocal = async_sessionmaker(
                async_engine, class_=AsyncSession, expire_on_commit=False
            )

            # Create sync engine for background tasks
            sync_engine = create_database_engine(database_url, is_async=False, env=env)

            # Create sync sessionmaker
            SessionLocal = sessionmaker(
                autocommit=False, autoflush=False, bind=sync_engine
            )

            # Setup event listeners
            _setup_event_listeners()

            db_type = get_database_type(database_url)

            if attempt > 0:
                logger.info(
                    f"Database connection successful after {attempt + 1} attempts: {db_type}"
                )
            else:
                logger.info(f"Database initialized successfully: {db_type}")

            return  # Success!

        except Exception as e:
            last_error = e

            # Check if this is a connection refused error (NeonDB auto-suspend)
            if _is_connection_refused_error(e) and attempt < max_retries - 1:
                logger.warning(
                    f"Database connection refused on attempt {attempt + 1}/{max_retries}. "
                    f"This may be due to serverless database auto-suspend (e.g., NeonDB). "
                    f"Retrying after {backoff:.1f}s to allow database wake-up..."
                )
                time.sleep(backoff)
                backoff *= backoff_multiplier
                continue

            # Not a connection refused error, or out of retries
            if attempt < max_retries - 1:
                logger.warning(
                    f"Database initialization failed on attempt {attempt + 1}/{max_retries}: {str(e)[:200]}. "
                    f"Retrying after {backoff:.1f}s..."
                )
                time.sleep(backoff)
                backoff *= backoff_multiplier
            else:
                # Final attempt failed
                error_msg = (
                    f"Failed to initialize database connection after {max_retries} attempts: {str(e)}\n\n"
                    f"If using NeonDB or another serverless database:\n"
                    f"1. Check that the database is not suspended in your dashboard\n"
                    f"2. Verify the connection string is correct\n"
                    f"3. Ensure SSL mode is set correctly (?sslmode=require)\n"
                    f"4. Check firewall/network settings\n"
                )
                logger.error(error_msg, exc_info=True)
                raise RuntimeError(error_msg) from e


def _setup_event_listeners():
    """Setup database event listeners for monitoring and table creation."""

    # Store query start time in connection context
    @event.listens_for(Engine, "before_cursor_execute")
    def receive_before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        """Record query start time."""
        context._query_start_time = time.time()

    # Log slow queries
    @event.listens_for(Engine, "after_cursor_execute")
    def receive_after_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        """Log slow queries (>1 second)."""
        total_time = time.time() - context._query_start_time

        if total_time > 1.0:
            statement_preview = (
                statement[:200] + "..." if len(statement) > 200 else statement
            )
            logger.warning(
                f"Slow query detected ({total_time:.3f}s): {statement_preview}",
                extra={
                    "query_time": total_time,
                    "statement": statement,
                    "parameters": parameters,
                },
            )

    # Ensure tables exist for in-memory SQLite tests only (runs once per engine)
    _tables_created_for = set()

    @event.listens_for(OrmSession, "before_flush")
    def _ensure_tables_before_flush(session: OrmSession, flush_context, instances):
        """Ensure tables exist before flush (useful for in-memory SQLite tests only)."""
        try:
            bind = session.get_bind()
            if bind is not None:
                engine_id = id(bind)
                if engine_id not in _tables_created_for:
                    url_str = str(bind.url)
                    if ":memory:" in url_str or "mode=memory" in url_str:
                        Base.metadata.create_all(bind=bind)
                    _tables_created_for.add(engine_id)
        except Exception:
            pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async database dependency for FastAPI dependency injection with retry logic.

    Provides an async database session that is automatically created and closed
    for each request. Includes retry logic for serverless database wake-up.

    Yields:
        AsyncSession: SQLAlchemy async database session
    """
    if AsyncSessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    # Retry configuration for session creation (handles NeonDB auto-suspend)
    max_retries = 3
    initial_backoff = 1.0
    backoff_multiplier = 2.0

    last_error = None
    backoff = initial_backoff

    for attempt in range(max_retries):
        try:
            async with AsyncSessionLocal() as session:
                yield session
                return  # Success!

        except (OperationalError, DBAPIError) as e:
            last_error = e

            # Check if this is a connection refused error (NeonDB auto-suspend)
            if _is_connection_refused_error(e) and attempt < max_retries - 1:
                logger.warning(
                    f"Database session creation failed on attempt {attempt + 1}/{max_retries}. "
                    f"Retrying after {backoff:.1f}s (serverless database may be waking up)..."
                )
                await asyncio.sleep(backoff)
                backoff *= backoff_multiplier
                continue

            # Not a connection refused error, or out of retries
            raise

    # If we get here, all retries failed
    if last_error:
        raise last_error


def get_sync_db() -> Generator[OrmSession, None, None]:
    """
    Synchronous database dependency for background tasks.

    Provides a synchronous database session for background processing
    where async context is not available.

    Yields:
        Session: SQLAlchemy synchronous database session
    """
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# Transaction Isolation and Concurrency Handling
# ============================================================================


def is_serialization_error(error: Exception) -> bool:
    """
    Check if an exception is a PostgreSQL serialization error.

    Args:
        error: Exception to check

    Returns:
        bool: True if error is a serialization error, False otherwise
    """
    error_msg = str(error).lower()

    serialization_indicators = [
        "could not serialize access",
        "deadlock detected",
        "serialization failure",
        "40001",  # serialization_failure error code
        "40P01",  # deadlock_detected error code
    ]

    return any(indicator in error_msg for indicator in serialization_indicators)


def retry_on_serialization_error(
    max_retries: int = 3, initial_backoff: float = 0.1, backoff_multiplier: float = 2.0
):
    """
    Decorator to retry database operations on PostgreSQL serialization errors.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_backoff: Initial backoff delay in seconds (default: 0.1)
        backoff_multiplier: Multiplier for exponential backoff (default: 2.0)

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error = None
            backoff = initial_backoff

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (OperationalError, DBAPIError) as e:
                    if is_serialization_error(e) and attempt < max_retries - 1:
                        last_error = e
                        logger.warning(
                            f"Serialization error on attempt {attempt + 1}/{max_retries}, "
                            f"retrying after {backoff:.3f}s: {str(e)[:100]}"
                        )
                        await asyncio.sleep(backoff)
                        backoff *= backoff_multiplier
                        continue
                    raise

            if last_error:
                raise last_error

            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            import time

            last_error = None
            backoff = initial_backoff

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (OperationalError, DBAPIError) as e:
                    if is_serialization_error(e) and attempt < max_retries - 1:
                        last_error = e
                        logger.warning(
                            f"Serialization error on attempt {attempt + 1}/{max_retries}, "
                            f"retrying after {backoff:.3f}s: {str(e)[:100]}"
                        )
                        time.sleep(backoff)
                        backoff *= backoff_multiplier
                        continue
                    raise

            if last_error:
                raise last_error

            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        else:
            return sync_wrapper  # type: ignore

    return decorator


async def with_row_lock(
    session: AsyncSession, model_class, record_id, lock_mode: str = "update"
):
    """
    Acquire a row-level lock on a database record for safe concurrent updates.

    Args:
        session: SQLAlchemy async session
        model_class: SQLAlchemy model class
        record_id: Primary key value of the record to lock
        lock_mode: Lock mode - "update" (default) or "no_key_update"

    Returns:
        The locked database record, or None if not found
    """
    from sqlalchemy import select

    if lock_mode not in ("update", "no_key_update"):
        raise ValueError(f"Unsupported lock_mode: {lock_mode}")

    db_type = get_database_type()

    stmt = select(model_class).where(model_class.id == record_id)

    if db_type == "postgresql":
        if lock_mode == "update":
            stmt = stmt.with_for_update()
        elif lock_mode == "no_key_update":
            stmt = stmt.with_for_update(key_share=False)

    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def with_row_lock_sync(
    session: OrmSession, model_class, record_id, lock_mode: str = "update"
):
    """
    Synchronous version of with_row_lock for background tasks.

    Args:
        session: SQLAlchemy sync session
        model_class: SQLAlchemy model class
        record_id: Primary key value of the record to lock
        lock_mode: Lock mode - "update" (default) or "no_key_update"

    Returns:
        The locked database record, or None if not found
    """
    from sqlalchemy import select

    if lock_mode not in ("update", "no_key_update"):
        raise ValueError(f"Unsupported lock_mode: {lock_mode}")

    db_type = get_database_type()

    stmt = select(model_class).where(model_class.id == record_id)

    if db_type == "postgresql":
        if lock_mode == "update":
            stmt = stmt.with_for_update()
        elif lock_mode == "no_key_update":
            stmt = stmt.with_for_update(key_share=False)

    result = session.execute(stmt)
    return result.scalar_one_or_none()


def get_pool_status() -> dict:
    """
    Get connection pool statistics for monitoring.

    Returns:
        dict: Connection pool statistics
    """
    if sync_engine is None:
        return {"error": "Database not initialized"}

    pool = sync_engine.pool
    db_type = get_database_type()

    checked_out = pool.checkedout()
    checked_in = pool.checkedin()
    overflow = pool.overflow()
    size = pool.size()

    max_overflow = getattr(pool, "_max_overflow", 0)

    total_capacity = size + max_overflow
    pool_usage_percent = (
        (checked_out / total_capacity * 100) if total_capacity > 0 else 0
    )
    connections_available = checked_in + max(0, max_overflow - overflow)

    base_stats = {
        "database_type": db_type,
        "size": size,
        "max_overflow": max_overflow,
        "checked_in": checked_in,
        "checked_out": checked_out,
        "overflow": overflow,
        "total_capacity": total_capacity,
        "pool_usage_percent": round(pool_usage_percent, 2),
        "connections_available": connections_available,
    }

    if db_type == "postgresql":
        base_stats.update(
            {
                "pool_recycle": 300,
                "pool_pre_ping": True,
                "statement_timeout_ms": 30000,
                "isolation_level": "READ COMMITTED",
            }
        )

    return base_stats


def get_pool_usage_warning() -> dict | None:
    """
    Check connection pool usage and return warning if near capacity.

    Returns:
        dict | None: Warning dictionary if usage > 90%, None otherwise
    """
    try:
        pool_stats = get_pool_status()
        usage_percent = pool_stats.get("pool_usage_percent", 0)

        if usage_percent > 90:
            return {
                "message": f"Connection pool near capacity: {usage_percent:.1f}% in use",
                "pool_usage_percent": usage_percent,
                "checked_out": pool_stats["checked_out"],
                "total_capacity": pool_stats["total_capacity"],
                "connections_available": pool_stats["connections_available"],
            }

        return None
    except Exception as e:
        logger.error(f"Error checking pool usage: {str(e)}")
        return None
