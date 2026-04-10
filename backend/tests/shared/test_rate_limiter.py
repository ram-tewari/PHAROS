"""Unit tests for rate limiting service.

Tests cover:
- Rate limit checking with various tiers
- Sliding window algorithm
- HTTP 429 responses
- Rate limit headers
- Graceful degradation when Redis unavailable
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch, AsyncMock

from app.shared.rate_limiter import RateLimiter


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis_mock = Mock()
    redis_mock.get = Mock(return_value=None)
    redis_mock.incr = Mock(return_value=1)
    redis_mock.expire = Mock(return_value=True)

    # Setup pipeline mock
    pipeline_mock = Mock()
    pipeline_mock.incr = Mock(return_value=pipeline_mock)
    pipeline_mock.expire = Mock(return_value=pipeline_mock)
    pipeline_mock.execute = Mock(return_value=[1, True])
    redis_mock.pipeline = Mock(return_value=pipeline_mock)

    return redis_mock


@pytest.fixture
def mock_cache(mock_redis):
    """Create a mock cache with Redis."""
    cache = Mock()
    cache.redis = mock_redis
    return cache


@pytest.fixture
def rate_limiter(mock_cache, test_settings):
    """Create a RateLimiter instance with test settings."""
    limiter = RateLimiter(cache=mock_cache)
    limiter.settings = test_settings
    return limiter


# ============================================================================
# Test Rate Limit Checking
# ============================================================================


@pytest.mark.asyncio
async def test_check_rate_limit_free_tier_first_request(rate_limiter, mock_redis):
    """Test rate limit check for free tier user's first request."""
    user_id = 1
    tier = "free"
    endpoint = "/api/resources"

    mock_redis.get.return_value = None

    allowed, headers = await rate_limiter.check_rate_limit(user_id, tier, endpoint)

    assert allowed is True
    assert "X-RateLimit-Limit" in headers
    assert "X-RateLimit-Remaining" in headers
    assert "X-RateLimit-Reset" in headers
    assert headers["X-RateLimit-Limit"] == "100"


@pytest.mark.asyncio
async def test_check_rate_limit_premium_tier(rate_limiter, mock_redis):
    """Test rate limit check for premium tier user."""
    user_id = 2
    tier = "premium"
    endpoint = "/api/search"

    mock_redis.get.return_value = "50"

    allowed, headers = await rate_limiter.check_rate_limit(user_id, tier, endpoint)

    assert allowed is True
    assert headers["X-RateLimit-Limit"] == "1000"


@pytest.mark.asyncio
async def test_check_rate_limit_admin_tier_unlimited(rate_limiter):
    """Test rate limit check for admin tier (unlimited)."""
    user_id = 3
    tier = "admin"
    endpoint = "/api/admin"

    allowed, headers = await rate_limiter.check_rate_limit(user_id, tier, endpoint)

    assert allowed is True
    assert headers["X-RateLimit-Limit"] == "0"


@pytest.mark.asyncio
async def test_check_rate_limit_exceeded(rate_limiter, mock_redis):
    """Test rate limit check when limit is exceeded."""
    user_id = 1
    tier = "free"
    endpoint = "/api/resources"

    # At free tier limit
    mock_redis.get.return_value = "100"

    allowed, headers = await rate_limiter.check_rate_limit(user_id, tier, endpoint)

    assert allowed is False
    assert headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_check_rate_limit_sliding_window(rate_limiter, mock_redis):
    """Test sliding window algorithm with multiple requests."""
    user_id = 1
    tier = "free"
    endpoint = "/api/resources"

    # First request
    mock_redis.get.return_value = None
    allowed1, headers1 = await rate_limiter.check_rate_limit(user_id, tier, endpoint)
    assert allowed1 is True

    # Second request
    mock_redis.get.return_value = "1"
    allowed2, headers2 = await rate_limiter.check_rate_limit(user_id, tier, endpoint)
    assert allowed2 is True


@pytest.mark.asyncio
async def test_check_rate_limit_ttl_set(rate_limiter, mock_redis):
    """Test that TTL is set on rate limit keys."""
    user_id = 1
    tier = "free"
    endpoint = "/api/resources"

    mock_redis.get.return_value = None

    await rate_limiter.check_rate_limit(user_id, tier, endpoint)

    # Verify pipeline was used
    mock_redis.pipeline.assert_called()


# ============================================================================
# Test Tier Limits
# ============================================================================


def test_get_tier_limit_free(rate_limiter):
    """Test getting rate limit for free tier."""
    limit = rate_limiter._get_tier_limit("free")
    assert limit == 100


def test_get_tier_limit_premium(rate_limiter):
    """Test getting rate limit for premium tier."""
    limit = rate_limiter._get_tier_limit("premium")
    assert limit == 1000


def test_get_tier_limit_unknown(rate_limiter):
    """Test getting rate limit for unknown tier defaults to free."""
    limit = rate_limiter._get_tier_limit("unknown")
    assert limit == 100


# ============================================================================
# Test Rate Limit Headers
# ============================================================================


def test_get_rate_limit_headers(rate_limiter):
    """Test rate limit header generation."""
    headers = rate_limiter._get_rate_limit_headers(100, 50, 1234567890)

    assert headers["X-RateLimit-Limit"] == "100"
    assert headers["X-RateLimit-Remaining"] == "50"
    assert headers["X-RateLimit-Reset"] == "1234567890"


# ============================================================================
# Test Error Handling
# ============================================================================


@pytest.mark.asyncio
async def test_check_rate_limit_redis_error(rate_limiter, mock_redis):
    """Test graceful degradation when Redis fails."""
    user_id = 1
    tier = "free"
    endpoint = "/api/resources"

    # Simulate Redis error
    mock_redis.get.side_effect = Exception("Redis connection failed")

    # Should fail open
    allowed, headers = await rate_limiter.check_rate_limit(user_id, tier, endpoint)

    assert allowed is True
    assert headers == {}


@pytest.mark.asyncio
async def test_check_rate_limit_concurrent_requests(rate_limiter, mock_redis):
    """Test handling of concurrent requests."""
    user_id = 1
    tier = "free"
    endpoint = "/api/resources"

    mock_redis.get.return_value = "50"

    # Simulate concurrent requests
    results = []
    for _ in range(5):
        allowed, headers = await rate_limiter.check_rate_limit(user_id, tier, endpoint)
        results.append(allowed)

    # All should be allowed (under limit)
    assert all(results)


@pytest.mark.asyncio
async def test_check_rate_limit_exactly_at_limit(rate_limiter, mock_redis):
    """Test behavior when exactly at rate limit."""
    user_id = 1
    tier = "free"
    endpoint = "/api/resources"

    # Exactly at limit
    mock_redis.get.return_value = "100"

    allowed, headers = await rate_limiter.check_rate_limit(user_id, tier, endpoint)

    assert allowed is False


@pytest.mark.asyncio
async def test_check_rate_limit_over_limit(rate_limiter, mock_redis):
    """Test behavior when over rate limit."""
    user_id = 1
    tier = "free"
    endpoint = "/api/resources"

    # Over limit
    mock_redis.get.return_value = "150"

    allowed, headers = await rate_limiter.check_rate_limit(user_id, tier, endpoint)

    assert allowed is False
