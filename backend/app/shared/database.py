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
    
    Production-hardened connection pooling for Render deployment:
    - Strict pool limits to prevent connection exhaustion
    - Statement timeouts to prevent runaway queries
    - Pre-ping health checks for dropped connections (CRITICAL for NeonDB)
    - Exponential backoff for connection retries
    - Optimized for memory-constrained instances (512MB-2GB)
    
    SERVERLESS DATABASE GOTCHA (NeonDB):
    NeonDB scales to zero and actively kills idle connections. Without pool_pre_ping=True,
    your app will crash when trying to use a dead connection. This setting checks if the
    connection is alive before using it, preventing "connection closed" errors.

    Args:
        database_url: Database connection URL
        is_async: Whether to create async engine (True) or sync engine (False)
        env: Environment (dev/prod) for echo configuration

    Returns:
        SQLAlchemy Engine configured with database-specific parameters
    """
    db_type = get_database_type(database_url)

    # ========================================================================
    # CRITICAL: Convert URL to use appropriate driver
    # ========================================================================
    # NeonDB and other serverless PostgreSQL providers use standard postgresql://
    # URLs, but we need to convert them to use asyncpg (async) or psycopg2 (sync)
    # drivers for proper connection handling.
    
    if is_async:
        # Async: use aiosqlite for SQLite, asyncpg for PostgreSQL
        if database_url.startswith("sqlite:///"):
            database_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
        elif database_url.startswith("postgresql://"):
            # NeonDB provides postgresql:// URLs - convert to asyncpg
            database_url = database_url.replace(
                "postgresql://", "postgresql+asyncpg://"
            )
            logger.info("Converted PostgreSQL URL to use asyncpg driver (async)")
        elif database_url.startswith("postgresql+psycopg2://"):
            database_url = database_url.replace(
                "postgresql+psycopg2://", "postgresql+asyncpg://"
            )
            logger.info("Converted psycopg2 URL to use asyncpg driver (async)")
    else:
        # Sync: use default sqlite driver, psycopg2 for PostgreSQL
        if (
            database_url.startswith("postgresql://")
            and "+psycopg2" not in database_url
            and "+asyncpg" not in database_url
        ):
            # NeonDB provides postgresql:// URLs - convert to psycopg2
            database_url = database_url.replace(
                "postgresql://", "postgresql+psycopg2://"
            )
            logger.info("Converted PostgreSQL URL to use psycopg2 driver (sync)")
        elif database_url.startswith("postgresql+asyncpg://"):
            database_url = database_url.replace(
                "postgresql+asyncpg://", "postgresql+psycopg2://"
            )
            logger.info("Converted asyncpg URL to use psycopg2 driver (sync)")

    # Common parameters
    common_params = {
        "echo": True if env == "dev" else False,
        "echo_pool": env == "dev",  # Only log pool events in dev
    }

    # Database-specific parameters
    if db_type == "postgresql":
        # ====================================================================
        # PRODUCTION-HARDENED POSTGRESQL CONNECTION POOL
        # ====================================================================
        
        # Get pool configuration from environment (allows per-deployment tuning)
        pool_size = int(os.getenv("DB_POOL_SIZE", "3"))  # Reduced from 5 for Render
        max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "7"))  # Total: 10 connections per worker
        pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "300"))  # 5 minutes
        pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))  # 30 seconds
        statement_timeout = int(os.getenv("DB_STATEMENT_TIMEOUT", "30000"))  # 30 seconds
        
        # Calculate total connections: (pool_size + max_overflow) × workers
        # Example: (3 + 7) × 2 workers = 20 connections (safe for Render Starter: 22 max)
        # Example: (3 + 7) × 4 workers = 40 connections (safe for Render Standard: 97 max)
        
        logger.info(
            f"PostgreSQL connection pool: pool_size={pool_size}, max_overflow={max_overflow}, "
            f"total_per_worker={pool_size + max_overflow}, pool_recycle={pool_recycle}s, "
            f"pool_timeout={pool_timeout}s, statement_timeout={statement_timeout}ms"
        )
        
        # PostgreSQL-specific connection pool parameters
        engine_params = {
            **common_params,
            # Connection Pool Configuration
            "pool_size": pool_size,  # Base pool size (persistent connections)
            "max_overflow": max_overflow,  # Additional connections on demand
            "pool_recycle": pool_recycle,  # Recycle connections before they go stale
            "pool_pre_ping": True,  # CRITICAL: Health check before using connection
            "pool_timeout": pool_timeout,  # Wait time for connection from pool
            
            # Transaction Isolation
            "isolation_level": "READ COMMITTED",  # Default PostgreSQL isolation level
            
            # Connection Pool Behavior
            "pool_reset_on_return": "rollback",  # Reset connection state on return
            "pool_use_lifo": True,  # Use LIFO to keep hot connections active
        }

        # Add connect_args based on driver type
        if is_async:
            # ================================================================
            # ASYNCPG (Async Driver) - Production Configuration
            # ================================================================
            # Detect if using NeonDB (serverless PostgreSQL)
            is_neondb = "neon.tech" in database_url or "neon.db" in database_url
            
            connect_args = {
                # Statement Timeout: Prevent runaway queries
                "server_settings": {
                    "statement_timeout": str(statement_timeout),  # Milliseconds
                    "idle_in_transaction_session_timeout": "60000",  # 60s idle timeout
                },
                
                # Connection Timeout: Allow time for serverless database wake-up
                "timeout": 60,  # 60 seconds (handles Render/NeonDB cold start)
                
                # Command Timeout: Maximum time for any single command
                "command_timeout": 60,  # 60 seconds
                
                # NOTE: min_size and max_size are NOT valid for asyncpg.connect()
                # They are only for asyncpg.create_pool(), which SQLAlchemy doesn't use
                # SQLAlchemy manages its own connection pool via pool_size/max_overflow
            }
            
            # SSL Configuration
            if is_neondb:
                # NeonDB requires SSL with SNI routing
                connect_args["ssl"] = "require"  # Enforce SSL for NeonDB
                logger.info("NeonDB detected: SSL required, SNI routing enabled")
            else:
                # Other PostgreSQL providers (Render, AWS RDS, etc.)
                connect_args["ssl"] = "prefer"  # Use SSL if available
            
            engine_params["connect_args"] = connect_args
        else:
            # ================================================================
            # PSYCOPG2 (Sync Driver) - Production Configuration
            # ================================================================
            # Detect if using NeonDB (serverless PostgreSQL)
            is_neondb = "neon.tech" in database_url or "neon.db" in database_url
            
            # Detect if using NeonDB pooled connection (doesn't support statement_timeout in options)
            is_neondb_pooled = "pooler" in database_url and is_neondb
            
            connect_args = {}
            
            # Statement Timeout: Prevent runaway queries
            # NOTE: NeonDB pooled connections don't support statement_timeout in options
            # Use unpooled connection or set via SQL after connection
            if not is_neondb_pooled:
                connect_args["options"] = f"-c statement_timeout={statement_timeout}"  # Milliseconds
            
            # Connection Timeout: Allow time for serverless database wake-up
            connect_args["connect_timeout"] = 60  # 60 seconds (handles Render/NeonDB cold start)
            
            # Keepalive: Detect dropped connections
            connect_args["keepalives"] = 1  # Enable TCP keepalive
            connect_args["keepalives_idle"] = 30  # Start keepalive after 30s idle
            connect_args["keepalives_interval"] = 10  # Keepalive probe interval
            connect_args["keepalives_count"] = 5  # Number of keepalive probes
            
            # SSL Configuration
            if is_neondb:
                # NeonDB requires SSL with SNI routing
                connect_args["sslmode"] = "require"  # Enforce SSL for NeonDB
                logger.info("NeonDB detected: SSL required, SNI routing enabled")
            else:
                # Other PostgreSQL providers (Render, AWS RDS, etc.)
                connect_args["sslmode"] = "prefer"  # Use SSL if available
            
            engine_params["connect_args"] = connect_args
    else:  # sqlite
        # ====================================================================
        # SQLITE CONNECTION CONFIGURATION
        # ====================================================================
        engine_params = {
            **common_params,
            "connect_args": {
                "check_same_thread": False,  # Allow multi-threaded access
                "timeout": 30,  # 30 seconds timeout for locks
            },
        }

    # Create engine with error handling
    try:
        if is_async:
            engine = create_async_engine(database_url, **engine_params)
        else:
            engine = create_engine(database_url, **engine_params)
        
        logger.info(
            f"Database engine created: type={db_type}, async={is_async}, "
            f"pool_size={engine_params.get('pool_size', 'N/A')}"
        )
        
        return engine
        
    except Exception as e:
        logger.error(
            f"Failed to create database engine: {e}",
            exc_info=True,
            extra={
                "database_type": db_type,
                "is_async": is_async,
                "pool_size": engine_params.get("pool_size"),
                "max_overflow": engine_params.get("max_overflow"),
            }
        )
        raise


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
