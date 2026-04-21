"""
Neo Alexandria 2.0 - Database Configuration and Session Management

This module provides the core database infrastructure for Neo Alexandria 2.0.
It sets up SQLAlchemy async engine, session management, and declarative base class.

Related files:
- app/config/settings.py: Database URL and environment configuration
- app/database/models.py: SQLAlchemy models that inherit from Base
- app/routers/: API endpoints that use get_db() dependency
- alembic/: Database migration scripts

Features:
- Cross-database compatibility (SQLite, PostgreSQL) with async support
- Database-specific connection pool optimization
- Automatic table creation for development environments
- Async session lifecycle management with dependency injection
- Event listeners for robust table creation in test environments
- Transaction isolation and concurrency handling for PostgreSQL
- Retry logic for serialization errors
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Session as OrmSession, sessionmaker
from sqlalchemy import create_engine, event, Engine
from sqlalchemy.exc import OperationalError, DBAPIError
from typing import AsyncGenerator, Literal, Callable, TypeVar, ParamSpec
from functools import wraps
import asyncio
import os

from ..config.settings import get_settings

# Get settings instance
settings = get_settings()


def get_database_type(
    database_url: str | None = None,
) -> Literal["sqlite", "postgresql"]:
    """
    Detect database type from connection URL.

    Args:
        database_url: Database connection URL. If None, uses settings.DATABASE_URL

    Returns:
        Database type: "sqlite" or "postgresql"

    Raises:
        ValueError: If database type is not supported
    """
    url = database_url or settings.DATABASE_URL

    if url.startswith("sqlite"):
        return "sqlite"
    elif url.startswith("postgresql"):
        return "postgresql"
    else:
        raise ValueError(f"Unsupported database type in URL: {url}")


def get_async_database_url() -> str:
    """Convert synchronous DATABASE_URL to async format."""
    url = settings.DATABASE_URL
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///")
    elif url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://")
    elif url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    return url


def create_database_engine(database_url: str, is_async: bool = False) -> Engine:
    """
    Factory function to create database engine with database-specific parameters.

    Args:
        database_url: Database connection URL
        is_async: Whether to create async engine (True) or sync engine (False)

    Returns:
        SQLAlchemy Engine configured with database-specific parameters
    """
    db_type = get_database_type(database_url)

    # Convert to async URL if needed
    if is_async:
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

    # Common parameters
    common_params = {
        "echo": True if settings.ENV == "dev" else False,
        "echo_pool": True,
    }

    # Database-specific parameters
    if db_type == "postgresql":
        # PostgreSQL-specific connection pool parameters
        engine_params = {
            **common_params,
            "pool_size": 20,  # Base connections
            "max_overflow": 40,  # Additional connections (total: 60)
            "pool_recycle": 3600,  # Recycle connections after 1 hour
            "pool_pre_ping": True,  # Health check before using connection
            "isolation_level": "READ COMMITTED",  # Transaction isolation level
            "connect_args": {
                "options": "-c statement_timeout=30000",  # 30 seconds timeout for queries
            },
        }
    else:  # sqlite
        # SQLite-specific connection parameters
        # Note: SQLite with aiosqlite uses NullPool and doesn't support pool_size/max_overflow
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


# Lazy engine creation to avoid import-time errors
_async_engine = None
_sync_engine = None
_async_session_local = None
_session_local = None


def get_async_engine():
    """Get or create async engine."""
    global _async_engine
    if _async_engine is None:
        _async_engine = create_database_engine(settings.DATABASE_URL, is_async=True)
    return _async_engine


def get_sync_engine():
    """Get or create sync engine."""
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_database_engine(settings.DATABASE_URL, is_async=False)
    return _sync_engine


def get_async_session_local():
    """Get or create async sessionmaker."""
    global _async_session_local
    if _async_session_local is None:
        _async_session_local = async_sessionmaker(
            get_async_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _async_session_local


def get_session_local():
    """Get or create sync sessionmaker."""
    global _session_local
    if _session_local is None:
        _session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=get_sync_engine()
        )
    return _session_local


# For backward compatibility, expose as module-level variables
# These will be created on first access
async_engine = None  # Will be set by get_async_engine()
sync_engine = None  # Will be set by get_sync_engine()
AsyncSessionLocal = None  # Will be set by get_async_session_local()
SessionLocal = None  # Will be set by get_session_local()


# Initialize on module load for non-test environments
if not os.environ.get("TESTING"):
    async_engine = get_async_engine()
    sync_engine = get_sync_engine()
    AsyncSessionLocal = get_async_session_local()
    SessionLocal = get_session_local()


# ============================================================================
# Transaction Isolation and Concurrency Handling
# ============================================================================

# Type variables for generic decorator
P = ParamSpec("P")
T = TypeVar("T")


def is_serialization_error(error: Exception) -> bool:
    """
    Check if an exception is a PostgreSQL serialization error.

    Serialization errors occur when concurrent transactions conflict and
    PostgreSQL cannot complete the transaction. These errors are safe to
    retry as they indicate a transient concurrency issue.

    Args:
        error: Exception to check

    Returns:
        bool: True if error is a serialization error, False otherwise
    """
    error_msg = str(error).lower()

    # PostgreSQL serialization error codes and messages
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

    This decorator implements exponential backoff retry logic for handling
    transient concurrency errors in PostgreSQL. It only retries on serialization
    errors and deadlocks, which are safe to retry. Other errors are raised immediately.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_backoff: Initial backoff delay in seconds (default: 0.1)
        backoff_multiplier: Multiplier for exponential backoff (default: 2.0)

    Returns:
        Decorated function with retry logic

    Example:
        @retry_on_serialization_error(max_retries=3)
        async def update_resource(db: AsyncSession, resource_id: str, data: dict):
            # This operation will be retried up to 3 times on serialization errors
            resource = await db.get(Resource, resource_id)
            resource.update(data)
            await db.commit()
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

            # If we exhausted all retries, raise the last error
            if last_error:
                raise last_error

            # This should never happen, but satisfy type checker
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

            # If we exhausted all retries, raise the last error
            if last_error:
                raise last_error

            # This should never happen, but satisfy type checker
            return func(*args, **kwargs)

        # Return appropriate wrapper based on whether function is async
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

    This function uses SELECT FOR UPDATE to lock a specific row, preventing
    other transactions from modifying it until the current transaction completes.
    This is essential for preventing race conditions in concurrent update operations.

    Only applies to PostgreSQL databases. For SQLite, returns the record without locking
    since SQLite uses database-level locking.

    Args:
        session: SQLAlchemy async session
        model_class: SQLAlchemy model class
        record_id: Primary key value of the record to lock
        lock_mode: Lock mode - "update" (default) or "no_key_update"
            - "update": Full row lock (FOR UPDATE)
            - "no_key_update": Lock without blocking key updates (FOR NO KEY UPDATE)

    Returns:
        The locked database record, or None if not found

    Example:
        async with session.begin():
            resource = await with_row_lock(session, Resource, resource_id)
            if resource:
                resource.view_count += 1
                await session.commit()

    Raises:
        ValueError: If lock_mode is not supported
    """
    from sqlalchemy import select

    # Validate lock_mode parameter
    if lock_mode not in ("update", "no_key_update"):
        raise ValueError(f"Unsupported lock_mode: {lock_mode}")

    db_type = get_database_type()

    # Build base query
    stmt = select(model_class).where(model_class.id == record_id)

    # Apply row-level locking for PostgreSQL
    if db_type == "postgresql":
        if lock_mode == "update":
            stmt = stmt.with_for_update()
        elif lock_mode == "no_key_update":
            stmt = stmt.with_for_update(key_share=False)

    # Execute query
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def with_row_lock_sync(
    session: OrmSession, model_class, record_id, lock_mode: str = "update"
):
    """
    Synchronous version of with_row_lock for background tasks.

    Acquire a row-level lock on a database record for safe concurrent updates.
    Only applies to PostgreSQL databases. For SQLite, returns the record without locking.

    Args:
        session: SQLAlchemy sync session
        model_class: SQLAlchemy model class
        record_id: Primary key value of the record to lock
        lock_mode: Lock mode - "update" (default) or "no_key_update"

    Returns:
        The locked database record, or None if not found

    Example:
        with session.begin():
            resource = with_row_lock_sync(session, Resource, resource_id)
            if resource:
                resource.view_count += 1
                session.commit()
    """
    from sqlalchemy import select

    # Validate lock_mode parameter
    if lock_mode not in ("update", "no_key_update"):
        raise ValueError(f"Unsupported lock_mode: {lock_mode}")

    db_type = get_database_type()

    # Build base query
    stmt = select(model_class).where(model_class.id == record_id)

    # Apply row-level locking for PostgreSQL
    if db_type == "postgresql":
        if lock_mode == "update":
            stmt = stmt.with_for_update()
        elif lock_mode == "no_key_update":
            stmt = stmt.with_for_update(key_share=False)

    # Execute query
    result = session.execute(stmt)
    return result.scalar_one_or_none()


# ============================================================================
# Optimistic Concurrency Control
# ============================================================================


class OptimisticLockError(Exception):
    """
    Exception raised when optimistic lock check fails.

    This indicates that the record was modified by another transaction
    between the read and the update attempt.

    Attributes:
        resource_id: ID of the resource that had a conflict
        expected_version: Version number that was expected
        actual_version: Current version number in database
    """

    def __init__(self, resource_id: str, expected_version: int, actual_version: int):
        self.resource_id = resource_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"Optimistic lock conflict: Resource {resource_id} was modified. "
            f"Expected version {expected_version}, found {actual_version}"
        )


async def update_with_optimistic_lock(
    session: AsyncSession,
    model_class,
    record_id,
    expected_version: int,
    update_data: dict,
) -> tuple:
    """
    Update a record with optimistic concurrency control.

    This function implements optimistic locking by checking the version
    column before updating. If the current version doesn't match the
    expected version, it raises OptimisticLockError.

    Args:
        session: SQLAlchemy async session
        model_class: SQLAlchemy model class (must have 'version' column)
        record_id: Primary key value of the record to update
        expected_version: Expected version number from previous read
        update_data: Dictionary of fields to update

    Returns:
        tuple: (updated_record, new_version)

    Raises:
        OptimisticLockError: If version mismatch (concurrent modification)
        ValueError: If record not found

    Example:
        # Read resource with version
        resource = await session.get(Resource, resource_id)
        version = resource.version

        # ... user modifies data ...

        # Update with version check
        try:
            updated, new_version = await update_with_optimistic_lock(
                session, Resource, resource_id, version,
                {"title": "New Title"}
            )
        except OptimisticLockError as e:
            # Handle conflict - e.g., notify user of concurrent edit
            pass
    """
    from sqlalchemy import select, update

    # First, get current version
    stmt = select(model_class).where(model_class.id == record_id)
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()

    if record is None:
        raise ValueError(f"Record not found: {record_id}")

    # Check version
    if record.version != expected_version:
        raise OptimisticLockError(str(record_id), expected_version, record.version)

    # Update with incremented version
    new_version = expected_version + 1
    update_data_with_version = {**update_data, "version": new_version}

    # Perform update with version check in WHERE clause
    update_stmt = (
        update(model_class)
        .where(model_class.id == record_id)
        .where(model_class.version == expected_version)
        .values(**update_data_with_version)
        .returning(model_class)
    )

    result = await session.execute(update_stmt)
    updated_record = result.scalar_one_or_none()

    if updated_record is None:
        # Version changed between our check and update (race condition)
        raise OptimisticLockError(
            str(record_id), expected_version, expected_version + 1
        )

    return updated_record, new_version


def update_with_optimistic_lock_sync(
    session: OrmSession,
    model_class,
    record_id,
    expected_version: int,
    update_data: dict,
) -> tuple:
    """
    Synchronous version of update_with_optimistic_lock for background tasks.

    Update a record with optimistic concurrency control in sync context.

    Args:
        session: SQLAlchemy sync session
        model_class: SQLAlchemy model class (must have 'version' column)
        record_id: Primary key value of the record to update
        expected_version: Expected version number from previous read
        update_data: Dictionary of fields to update

    Returns:
        tuple: (updated_record, new_version)

    Raises:
        OptimisticLockError: If version mismatch (concurrent modification)
        ValueError: If record not found
    """
    from sqlalchemy import select, update

    # First, get current version
    stmt = select(model_class).where(model_class.id == record_id)
    result = session.execute(stmt)
    record = result.scalar_one_or_none()

    if record is None:
        raise ValueError(f"Record not found: {record_id}")

    # Check version
    if record.version != expected_version:
        raise OptimisticLockError(str(record_id), expected_version, record.version)

    # Update with incremented version
    new_version = expected_version + 1
    update_data_with_version = {**update_data, "version": new_version}

    # Perform update with version check in WHERE clause
    update_stmt = (
        update(model_class)
        .where(model_class.id == record_id)
        .where(model_class.version == expected_version)
        .values(**update_data_with_version)
        .returning(model_class)
    )

    result = session.execute(update_stmt)
    updated_record = result.scalar_one_or_none()

    if updated_record is None:
        # Version changed between our check and update (race condition)
        raise OptimisticLockError(
            str(record_id), expected_version, expected_version + 1
        )

    return updated_record, new_version


class Base(DeclarativeBase):
    """
    SQLAlchemy declarative base class.

    All database models inherit from this base class to ensure consistent
    metadata management and table creation across the application.
    """

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async database dependency for FastAPI dependency injection.

    Provides an async database session that is automatically created and closed
    for each request. Ensures table creation for SQLite environments
    and handles connection lifecycle management.

    Yields:
        AsyncSession: SQLAlchemy async database session
    """
    session_maker = get_async_session_local()
    async with session_maker() as session:
        # Ensure metadata exists for this connection (esp. sqlite in-memory)
        try:
            async with session.bind.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception:
            pass
        yield session


def get_sync_db():
    """
    Synchronous database dependency for background tasks.

    Provides a synchronous database session for background processing
    where async context is not available.

    Yields:
        Session: SQLAlchemy synchronous database session
    """
    session_maker = get_session_local()
    db = session_maker()
    try:
        # Ensure metadata exists for this connection (esp. sqlite in-memory)
        try:
            Base.metadata.create_all(bind=db.get_bind())
        except Exception:
            pass
        yield db
    finally:
        db.close()


# Ensure tables exist for any Session bind (helps in-memory SQLite tests)
@event.listens_for(OrmSession, "before_flush")
def _ensure_tables_before_flush(session: OrmSession, flush_context, instances):  # type: ignore[no-redef]
    """
    Event listener to ensure tables exist before any flush operation.

    This is particularly useful for in-memory SQLite databases used in tests,
    where tables need to be created on-demand for each session.
    """
    try:
        bind = session.get_bind()
        if bind is not None:
            Base.metadata.create_all(bind=bind)
    except Exception:
        # Best-effort; ignore if fails
        pass


def get_pool_status() -> dict:
    """
    Get connection pool statistics for monitoring.

    Returns detailed metrics about the current state of the database
    connection pool, including active connections, available connections,
    and overflow usage. Includes database type information and PostgreSQL-specific metrics.

    Returns:
        dict: Connection pool statistics with the following keys:
            - database_type: Type of database ("sqlite" or "postgresql")
            - size: Total pool size (base connections)
            - max_overflow: Maximum overflow connections allowed
            - checked_in: Number of connections available in the pool
            - checked_out: Number of connections currently in use
            - overflow: Number of overflow connections in use
            - total_capacity: Maximum possible connections (size + max_overflow)
            - pool_usage_percent: Percentage of pool capacity in use
            - connections_available: Number of connections available for use
            - pool_recycle: Connection recycle time in seconds (PostgreSQL)
            - pool_pre_ping: Whether pre-ping is enabled (PostgreSQL)
    """
    engine = get_sync_engine()
    pool = engine.pool
    db_type = get_database_type()

    checked_out = pool.checkedout()  # type: ignore[attr-defined]
    checked_in = pool.checkedin()  # type: ignore[attr-defined]
    overflow = pool.overflow()  # type: ignore[attr-defined]
    size = pool.size()  # type: ignore[attr-defined]

    # Get max_overflow from pool configuration
    max_overflow = getattr(pool, "_max_overflow", 0)

    # Calculate total capacity and usage
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

    # Add PostgreSQL-specific metrics
    if db_type == "postgresql":
        base_stats.update(
            {
                "pool_recycle": 3600,  # From configuration
                "pool_pre_ping": True,  # From configuration
                "statement_timeout_ms": 30000,  # From configuration
                "isolation_level": "READ COMMITTED",  # Transaction isolation level
            }
        )

    return base_stats


# ============================================================================
# Slow Query Logging and Connection Pool Monitoring
# ============================================================================

import time
import logging

logger = logging.getLogger(__name__)


# Store query start time in connection context
@event.listens_for(Engine, "before_cursor_execute")
def receive_before_cursor_execute(
    conn, cursor, statement, parameters, context, executemany
):
    """
    Event listener to record query start time.

    This listener is triggered before every SQL query execution and stores
    the start time in the connection context for later calculation of
    query execution time.
    """
    context._query_start_time = time.time()


@event.listens_for(Engine, "after_cursor_execute")
def receive_after_cursor_execute(
    conn, cursor, statement, parameters, context, executemany
):
    """
    Event listener to log slow queries.

    This listener is triggered after every SQL query execution and logs
    queries that exceed the 1-second threshold. Slow query logging helps
    identify performance bottlenecks and optimization opportunities.

    Threshold: 1.0 seconds
    """
    total_time = time.time() - context._query_start_time

    if total_time > 1.0:  # Log queries slower than 1 second
        # Truncate long statements for readability
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


def get_pool_usage_warning() -> dict | None:
    """
    Check connection pool usage and return warning if near capacity.

    Returns a warning dictionary if pool usage exceeds 90% of capacity,
    indicating potential connection exhaustion. This function is designed
    to be called by middleware to monitor pool health during request processing.

    Returns:
        dict | None: Warning dictionary with usage details if usage > 90%, None otherwise
            - message: Warning message
            - pool_usage_percent: Current pool usage percentage
            - checked_out: Number of connections in use
            - total_capacity: Maximum connections available
    """
    try:
        pool_stats = get_pool_status()
        usage_percent = pool_stats["pool_usage_percent"]

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
