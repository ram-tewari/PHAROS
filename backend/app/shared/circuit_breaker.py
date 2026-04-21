"""
Neo Alexandria 2.0 - Circuit Breaker Utility

This module provides circuit breaker pattern implementation for external service calls.
Uses pybreaker to prevent cascading failures and implement graceful degradation.

Features:
- Configurable failure thresholds and recovery timeouts
- Pre-configured breakers for common services (HTTP, OAuth, AI APIs)
- Decorator for easy integration with existing functions
- State monitoring for observability

Related files:
- app/utils/content_extractor.py: URL fetching with circuit breaker
- app/shared/oauth2.py: OAuth provider calls with circuit breaker
- app/config/settings.py: Circuit breaker configuration
"""

import asyncio
import logging
from functools import wraps
from typing import Callable, Optional, TypeVar, ParamSpec

try:
    import pybreaker

    PYBREAKER_AVAILABLE = True
except ImportError:
    PYBREAKER_AVAILABLE = False
    pybreaker = None  # type: ignore

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


# ============================================================================
# Circuit Breaker Configuration
# ============================================================================


class CircuitBreakerConfig:
    """Configuration for circuit breakers."""

    # Default settings
    DEFAULT_FAIL_MAX = 5  # Open circuit after 5 failures
    DEFAULT_RESET_TIMEOUT = 30  # Try to close after 30 seconds

    # HTTP/External API settings (more lenient)
    HTTP_FAIL_MAX = 3
    HTTP_RESET_TIMEOUT = 60

    # OAuth settings (stricter for auth failures)
    OAUTH_FAIL_MAX = 3
    OAUTH_RESET_TIMEOUT = 120

    # AI/ML API settings (handle model loading issues)
    AI_FAIL_MAX = 2
    AI_RESET_TIMEOUT = 300  # 5 minutes for model recovery


# ============================================================================
# Circuit Breaker Listeners
# ============================================================================


class CircuitBreakerListener(pybreaker.CircuitBreakerListener):
    """Listener for circuit breaker state changes with logging."""

    def __init__(self, name: str):
        self.name = name

    def state_change(
        self, cb: pybreaker.CircuitBreaker, old_state: str, new_state: str
    ):
        """Log state transitions."""
        logger.warning(
            f"Circuit breaker '{self.name}' state changed: {old_state} -> {new_state}"
        )

        if new_state == "open":
            logger.error(
                f"Circuit breaker '{self.name}' is OPEN - requests will fail fast"
            )
        elif new_state == "closed":
            logger.info(f"Circuit breaker '{self.name}' is CLOSED - service recovered")

    def failure(self, cb: pybreaker.CircuitBreaker, exc: Exception):
        """Log failures."""
        logger.warning(
            f"Circuit breaker '{self.name}' recorded failure: {type(exc).__name__}: {exc}"
        )

    def success(self, cb: pybreaker.CircuitBreaker):
        """Log successful calls when recovering."""
        if cb.state.name == "half-open":
            logger.info(f"Circuit breaker '{self.name}' success in half-open state")


# ============================================================================
# Circuit Breaker Factory
# ============================================================================


class CircuitBreakerFactory:
    """Factory for creating and managing circuit breakers."""

    _instances: dict = {}

    @classmethod
    def get_breaker(
        cls,
        name: str,
        fail_max: int = CircuitBreakerConfig.DEFAULT_FAIL_MAX,
        reset_timeout: int = CircuitBreakerConfig.DEFAULT_RESET_TIMEOUT,
        exclude: Optional[list] = None,
    ):
        """
        Get or create a circuit breaker instance.

        Args:
            name: Unique name for the circuit breaker
            fail_max: Number of failures before opening
            reset_timeout: Seconds before attempting recovery
            exclude: Exception types to not count as failures

        Returns:
            Circuit breaker instance or None if pybreaker not available
        """
        if not PYBREAKER_AVAILABLE:
            logger.warning(
                f"Circuit breaker '{name}' requested but pybreaker not available"
            )
            return None

        if name not in cls._instances:
            listener = CircuitBreakerListener(name)
            cls._instances[name] = pybreaker.CircuitBreaker(
                name=name,
                fail_max=fail_max,
                reset_timeout=reset_timeout,
                exclude=exclude or [],
                listeners=[listener],
            )
            logger.info(
                f"Created circuit breaker '{name}' (fail_max={fail_max}, reset_timeout={reset_timeout}s)"
            )

        return cls._instances[name]

    @classmethod
    def get_http_breaker(cls, name: str = "http") -> pybreaker.CircuitBreaker:
        """Get circuit breaker configured for HTTP requests."""
        return cls.get_breaker(
            name=f"http_{name}",
            fail_max=CircuitBreakerConfig.HTTP_FAIL_MAX,
            reset_timeout=CircuitBreakerConfig.HTTP_RESET_TIMEOUT,
            exclude=[ValueError],  # Don't count validation errors
        )

    @classmethod
    def get_oauth_breaker(cls, provider: str) -> pybreaker.CircuitBreaker:
        """Get circuit breaker configured for OAuth provider."""
        return cls.get_breaker(
            name=f"oauth_{provider}",
            fail_max=CircuitBreakerConfig.OAUTH_FAIL_MAX,
            reset_timeout=CircuitBreakerConfig.OAUTH_RESET_TIMEOUT,
        )

    @classmethod
    def get_ai_breaker(cls, service: str) -> pybreaker.CircuitBreaker:
        """Get circuit breaker configured for AI/ML services."""
        return cls.get_breaker(
            name=f"ai_{service}",
            fail_max=CircuitBreakerConfig.AI_FAIL_MAX,
            reset_timeout=CircuitBreakerConfig.AI_RESET_TIMEOUT,
        )

    @classmethod
    def get_all_states(cls) -> dict:
        """Get states of all circuit breakers for monitoring."""
        return {
            name: {
                "state": cb.state.name,
                "fail_counter": cb.fail_counter,
                "fail_max": cb.fail_max,
                "reset_timeout": cb.reset_timeout,
            }
            for name, cb in cls._instances.items()
        }

    @classmethod
    def reset_all(cls):
        """Reset all circuit breakers (useful for testing)."""
        for name, cb in cls._instances.items():
            cb.close()
            logger.info(f"Reset circuit breaker '{name}'")


# ============================================================================
# Decorators
# ============================================================================


def with_circuit_breaker(
    breaker: pybreaker.CircuitBreaker, fallback: Optional[Callable[..., T]] = None
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator to wrap a function with circuit breaker protection.

    Args:
        breaker: Circuit breaker instance to use
        fallback: Optional fallback function to call when circuit is open

    Returns:
        Decorated function

    Example:
        >>> http_breaker = CircuitBreakerFactory.get_http_breaker()
        >>> @with_circuit_breaker(http_breaker, fallback=lambda url: {"error": "Service unavailable"})
        ... def fetch_data(url: str) -> dict:
        ...     return requests.get(url).json()
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                return breaker.call(func, *args, **kwargs)
            except pybreaker.CircuitBreakerError:
                logger.warning(
                    f"Circuit breaker '{breaker.name}' is open, using fallback"
                )
                if fallback is not None:
                    return fallback(*args, **kwargs)
                raise

        return wrapper

    return decorator


def with_circuit_breaker_async(
    breaker: pybreaker.CircuitBreaker, fallback: Optional[Callable[..., T]] = None
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Async decorator to wrap a function with circuit breaker protection.

    Args:
        breaker: Circuit breaker instance to use
        fallback: Optional async fallback function to call when circuit is open

    Returns:
        Decorated async function
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                # For async, we need to handle differently
                # pybreaker doesn't natively support async, so we wrap
                def sync_wrapper():
                    import asyncio

                    loop = asyncio.get_event_loop()
                    return loop.run_until_complete(func(*args, **kwargs))

                # Actually for async, just check state manually
                if breaker.state.name == "open":
                    raise pybreaker.CircuitBreakerError(breaker)

                try:
                    result = await func(*args, **kwargs)
                    breaker.success()
                    return result
                except Exception as e:
                    breaker.failure(e)
                    raise

            except pybreaker.CircuitBreakerError:
                logger.warning(
                    f"Circuit breaker '{breaker.name}' is open, using fallback"
                )
                if fallback is not None:
                    if asyncio.iscoroutinefunction(fallback):
                        return await fallback(*args, **kwargs)
                    return fallback(*args, **kwargs)
                raise

        return wrapper

    return decorator


# ============================================================================
# Pre-configured Breakers (Singletons)
# ============================================================================

if PYBREAKER_AVAILABLE:
    # HTTP content fetching
    http_content_breaker = CircuitBreakerFactory.get_http_breaker("content")

    # OAuth providers
    oauth_google_breaker = CircuitBreakerFactory.get_oauth_breaker("google")
    oauth_github_breaker = CircuitBreakerFactory.get_oauth_breaker("github")

    # AI/ML services - only create in EDGE mode
    import os
    deployment_mode = os.getenv("MODE", "EDGE")
    if deployment_mode == "EDGE":
        ai_embedding_breaker = CircuitBreakerFactory.get_ai_breaker("embedding")
        ai_llm_breaker = CircuitBreakerFactory.get_ai_breaker("llm")
        logger.info("Created AI circuit breakers for EDGE mode")
    else:
        # CLOUD mode: AI operations are queued to edge worker, no local circuit breakers needed
        ai_embedding_breaker = None
        ai_llm_breaker = None
        logger.info("Cloud mode: Skipping AI circuit breakers (handled by edge worker)")
else:
    # Fallback: No circuit breakers available
    http_content_breaker = None
    oauth_google_breaker = None
    oauth_github_breaker = None
    ai_embedding_breaker = None
    ai_llm_breaker = None
    logger.warning(
        "Circuit breakers not available - pybreaker not installed. Services will operate without resilience patterns."
    )
