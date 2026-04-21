"""
Neo Alexandria 2.0 - Redis Cache Layer

This module provides Redis-based caching with intelligent TTL management,
pattern-based invalidation, and statistics tracking.

Features:
- Get/set operations with automatic TTL selection
- Pattern-based cache invalidation for bulk clearing
- Hit/miss/invalidation statistics tracking
- Key-based TTL strategy for different data types
- JSON serialization for complex objects

Related files:
- app/events/hooks.py: Cache invalidation hooks
- app/tasks/celery_tasks.py: Cache invalidation tasks
- app/config/settings.py: Redis configuration
"""

import json
import logging
from typing import Any, Optional
import redis

from ..config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class CacheStats:
    """Track cache performance statistics.

    Attributes:
        hits: Number of successful cache retrievals
        misses: Number of cache misses
        invalidations: Number of cache invalidations
    """

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.invalidations = 0

    def record_hit(self):
        """Record a cache hit."""
        self.hits += 1

    def record_miss(self):
        """Record a cache miss."""
        self.misses += 1

    def record_invalidation(self, count: int = 1):
        """Record cache invalidation(s).

        Args:
            count: Number of keys invalidated (default: 1)
        """
        self.invalidations += count

    def hit_rate(self) -> float:
        """Calculate cache hit rate.

        Returns:
            Hit rate as a float between 0.0 and 1.0
        """
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def reset(self):
        """Reset all statistics to zero."""
        self.hits = 0
        self.misses = 0
        self.invalidations = 0


class RedisCache:
    """Redis-based caching with TTL and pattern invalidation.

    This class provides a high-level interface to Redis for caching
    with automatic TTL selection based on key patterns and statistics tracking.

    Attributes:
        redis: Redis client instance
        stats: CacheStats instance for tracking performance
    """

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize Redis cache.

        Args:
            redis_client: Optional Redis client instance. If not provided,
                         creates a new client using settings.
        """
        if redis_client:
            self.redis = redis_client
        else:
            self.redis = redis.Redis(
                host=getattr(settings, "REDIS_HOST", "localhost"),
                port=getattr(settings, "REDIS_PORT", 6379),
                db=getattr(settings, "REDIS_CACHE_DB", 2),
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        self.stats = CacheStats()

    def get(self, key: str) -> Optional[Any]:
        """Get cached value.

        Args:
            key: Cache key

        Returns:
            Cached value if found, None otherwise
        """
        try:
            value = self.redis.get(key)
            if value:
                self.stats.record_hit()
                return json.loads(value)  # type: ignore[arg-type]
            self.stats.record_miss()
            return None
        except redis.RedisError as e:
            logger.error(f"Redis get error for key {key}: {e}")
            self.stats.record_miss()
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for key {key}: {e}")
            self.stats.record_miss()
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set cached value with TTL.

        Args:
            key: Cache key
            value: Value to cache (will be JSON-serialized)
            ttl: Time-to-live in seconds. If None, uses get_default_ttl()
        """
        try:
            ttl_seconds = ttl if ttl is not None else self.get_default_ttl(key)
            serialized_value = json.dumps(value)
            self.redis.setex(key, ttl_seconds, serialized_value)
        except redis.RedisError as e:
            logger.error(f"Redis set error for key {key}: {e}")
        except (TypeError, ValueError) as e:
            logger.error(f"JSON serialization error for key {key}: {e}")

    def delete(self, key: str):
        """Delete single key.

        Args:
            key: Cache key to delete
        """
        try:
            deleted = self.redis.delete(key)
            if deleted > 0:
                self.stats.record_invalidation()
        except redis.RedisError as e:
            logger.error(f"Redis delete error for key {key}: {e}")

    def delete_pattern(self, pattern: str):
        """Delete all keys matching pattern.

        Args:
            pattern: Redis key pattern (e.g., "search_query:*")
        """
        try:
            keys = self.redis.keys(pattern)
            if keys:
                deleted = self.redis.delete(*keys)
                self.stats.record_invalidation(deleted)
                logger.info(f"Deleted {deleted} keys matching pattern: {pattern}")
        except redis.RedisError as e:
            logger.error(f"Redis delete_pattern error for pattern {pattern}: {e}")

    def get_default_ttl(self, key: str) -> int:
        """Get TTL based on key type.

        Different data types have different volatility and should be
        cached for different durations:
        - Embeddings: 1 hour (expensive to compute, relatively stable)
        - Quality scores: 30 minutes (moderate computation, may change)
        - Search queries: 5 minutes (fast changing, user-specific)
        - Resources: 10 minutes (moderate stability)
        - Default: 5 minutes (conservative default)

        Args:
            key: Cache key

        Returns:
            TTL in seconds
        """
        if key.startswith("embedding:"):
            return 3600  # 1 hour
        elif key.startswith("quality:"):
            return 1800  # 30 minutes
        elif key.startswith("search_query:"):
            return 300  # 5 minutes
        elif key.startswith("resource:"):
            return 600  # 10 minutes
        return 300  # Default 5 minutes

    def ping(self) -> bool:
        """Check if Redis connection is alive.

        Returns:
            True if connection is alive, False otherwise
        """
        try:
            return self.redis.ping()
        except redis.RedisError:
            return False


# Global cache instance
cache = RedisCache()
