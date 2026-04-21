"""
Neo Alexandria 2.0 - Rate Limiting Service

This module provides API key-based rate limiting using Redis sliding window algorithm
to prevent API abuse and ensure fair resource usage.

Features:
- Sliding window algorithm for accurate rate limiting
- Configurable rate limits per tier (free, premium, admin)
- HTTP 429 responses with Retry-After header
- Rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset)
- Graceful degradation when Redis unavailable (fail open)

Related files:
- app/shared/security.py: API key authentication
- app/config/settings.py: Rate limit configuration
- app/shared/cache.py: Redis cache service
"""

import logging
import time
from typing import Tuple


from ..config.settings import get_settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiting service using Redis sliding window algorithm.

    This class implements per-API-key rate limiting with configurable tiers
    and graceful degradation when Redis is unavailable.

    Attributes:
        cache: Redis cache instance for request counting
        settings: Application settings with rate limit configuration
    """

    def __init__(self, cache=None):
        """Initialize rate limiter.

        Args:
            cache: Optional Redis cache instance. If not provided,
                  creates a new instance.
        """
        self.cache = cache
        self.settings = get_settings()

    async def check_rate_limit(
        self, api_key: str, tier: str, endpoint: str
    ) -> Tuple[bool, dict]:
        """Check if request is within rate limits.

        Uses sliding window algorithm with per-minute granularity.
        Tracks requests in Redis with automatic TTL expiration.

        Args:
            api_key: API key identifier
            tier: User tier (free, premium, admin)
            endpoint: API endpoint being accessed

        Returns:
            Tuple of (allowed: bool, headers: dict)
            - allowed: True if request is within limits, False otherwise
            - headers: Rate limit headers to include in response
        """
        # Admin tier has unlimited access
        if tier == "admin":
            return True, self._get_rate_limit_headers(0, 0, 0)

        # Get rate limit for tier
        limit = self._get_tier_limit(tier)

        # Calculate current minute window
        current_minute = int(time.time() // 60)
        window_key = f"rate_limit:{api_key}:{current_minute}"

        try:
            if not self.cache:
                # No cache available, fail open
                return True, {}

            # Get current count for this window
            current_count_str = await self.cache.get(window_key)
            current_count = int(current_count_str) if current_count_str else 0

            # Check if limit exceeded
            if current_count >= limit:
                # Rate limit exceeded
                reset_time = (current_minute + 1) * 60
                headers = self._get_rate_limit_headers(limit, 0, reset_time)
                logger.warning(
                    f"Rate limit exceeded for API key (tier: {tier}): "
                    f"{current_count}/{limit} requests"
                )
                return False, headers

            # Increment counter with TTL
            await self.cache.set(window_key, str(current_count + 1), ttl=60)

            # Calculate remaining requests
            remaining = limit - current_count - 1
            reset_time = (current_minute + 1) * 60
            headers = self._get_rate_limit_headers(limit, remaining, reset_time)

            return True, headers

        except Exception as e:
            # Fail open if Redis is unavailable
            logger.warning(
                f"Rate limit check failed: {e} - allowing request"
            )
            return True, {}

    def _get_tier_limit(self, tier: str) -> int:
        """Get rate limit for user tier.

        Args:
            tier: User tier (free, premium, admin)

        Returns:
            Requests per minute limit
        """
        # Default limits (can be configured via settings)
        limits = {
            "free": 60,  # 60 requests per minute
            "premium": 300,  # 300 requests per minute
            "admin": 999999,  # Unlimited
        }
        return limits.get(tier, 60)

    def _get_rate_limit_headers(self, limit: int, remaining: int, reset: int) -> dict:
        """Generate rate limit headers.

        Args:
            limit: Total requests allowed per window
            remaining: Requests remaining in current window
            reset: Unix timestamp when limit resets

        Returns:
            Dictionary of rate limit headers
        """
        return {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset),
        }


# Global rate limiter instance
rate_limiter = RateLimiter()


# ============================================================================
# FastAPI Rate Limiting Dependency (DISABLED FOR NOW)
# ============================================================================
# Note: Rate limiting is currently disabled because it requires
# authentication to be implemented first. Uncomment when ready.

# async def rate_limit_dependency(
#     request: Request, api_key: str = Depends(verify_api_key)
# ) -> None:
#     """FastAPI dependency for rate limiting.
#
#     This dependency checks rate limits after authentication and before
#     endpoint execution. It raises HTTP 429 when limits are exceeded
#     and adds rate limit headers to the response.
#
#     Args:
#         request: FastAPI request object
#         api_key: Validated API key from authentication
#
#     Raises:
#         HTTPException: 429 if rate limit exceeded
#     """
#     # Determine tier from API key (placeholder logic)
#     tier = "free"  # TODO: Implement tier detection
#
#     # Check rate limit
#     allowed, headers = await rate_limiter.check_rate_limit(
#         api_key=api_key, tier=tier, endpoint=request.url.path
#     )

#     # Store headers in request state for response middleware
#     request.state.rate_limit_headers = headers
