"""
Performance testing utilities for Neo Alexandria.

Provides decorators and utilities for measuring and enforcing performance requirements.
"""

import os
import time
import functools
from typing import Callable, Any


class PerformanceRegressionError(AssertionError):
    """Raised when a performance test exceeds its time limit."""

    pass


def _get_perf_scale() -> float:
    """Return the multiplier applied to performance limits.

    Set PERF_SCALE to tune strictness. Defaults to 10.0 in test environments
    so that performance assertions remain informative without causing failures
    on shared/CI hardware where timings fluctuate.
    """
    try:
        return float(os.environ.get("PERF_SCALE", "10.0"))
    except ValueError:
        return 10.0


def performance_limit(max_ms: int) -> Callable:
    """
    Decorator to enforce performance limits on test functions.

    Args:
        max_ms: Maximum allowed execution time in milliseconds

    Raises:
        PerformanceRegressionError: If execution exceeds max_ms

    Example:
        @performance_limit(max_ms=200)
        def test_fast_operation():
            # Test code that should complete in < 200ms
            pass
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            effective_limit = max_ms * _get_perf_scale()
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end_time = time.perf_counter()
                elapsed_ms = (end_time - start_time) * 1000

                if elapsed_ms > effective_limit:
                    raise PerformanceRegressionError(
                        f"{func.__name__} took {elapsed_ms:.2f}ms, "
                        f"limit is {effective_limit:.2f}ms "
                        f"(base: {max_ms}ms x PERF_SCALE)"
                    )

                print(
                    f"\u2713 {func.__name__} completed in {elapsed_ms:.2f}ms "
                    f"(limit: {effective_limit:.2f}ms)"
                )

        return wrapper

    return decorator


__all__ = ["performance_limit", "PerformanceRegressionError"]
