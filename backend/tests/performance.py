"""Performance regression testing infrastructure."""

import time
import functools
from typing import Callable, Any


class PerformanceRegressionError(AssertionError):
    """Raised when execution time exceeds limit."""

    pass


def performance_limit(max_ms: int) -> Callable:
    """
    Decorator to enforce strict execution time limits.

    Args:
        max_ms: Maximum allowed execution time in milliseconds

    Raises:
        PerformanceRegressionError: If execution exceeds max_ms

    Example:
        @performance_limit(max_ms=50)
        def test_fast_operation():
            # Test code here
            pass
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            result = func(*args, **kwargs)
            end_time = time.perf_counter()

            actual_ms = (end_time - start_time) * 1000

            if actual_ms > max_ms:
                raise PerformanceRegressionError(
                    f"PERFORMANCE REGRESSION DETECTED\n"
                    f"Function: {func.__name__}\n"
                    f"Expected: <{max_ms}ms\n"
                    f"Actual: {actual_ms:.2f}ms\n"
                    f"Regression: {actual_ms - max_ms:.2f}ms\n"
                    f"\n"
                    f"DO NOT INCREASE THE TIMEOUT\n"
                    f"This indicates a performance regression in the implementation.\n"
                    f"Fix the implementation, not the test."
                )

            return result

        return wrapper

    return decorator
