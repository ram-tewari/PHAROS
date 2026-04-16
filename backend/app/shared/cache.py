"""
Neo Alexandria 2.0 - Shared Cache Service

This module provides Redis-based caching with intelligent TTL management,
pattern-based invalidation, and statistics tracking for the shared kernel.

Features:
- Get/set operations with automatic TTL selection
- Pattern-based cache invalidation for bulk clearing
- Hit/miss/invalidation statistics tracking
- Key-based TTL strategy for different data types
- JSON serialization for complex objects

Related files:
- app/shared/embeddings.py: Uses cache for embedding storage
- app/config/settings.py: Redis configuration
"""

import json
import logging
from typing import Any, Optional

try:
    import os
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None  # type: ignore

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


class CacheService:
    """Redis-based caching with TTL and pattern invalidation.

    This class provides a high-level interface to Redis for caching
    with automatic TTL selection based on key patterns and statistics tracking.

    Attributes:
        redis: Redis client instance
        stats: CacheStats instance for tracking performance
    """

    def __init__(self, redis_client: Optional["redis.Redis"] = None):
        """Initialize cache service.

        Args:
            redis_client: Optional Redis client instance. If not provided,
                         creates a new client using settings.
        """
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available - caching will be disabled")
            self.redis = None
            self.stats = CacheStats()
            return

        if redis_client:
            self.redis = redis_client
        else:
            try:
                # ============================================================
                # UPSTASH REDIS (Serverless) - Priority Configuration
                # ============================================================
                # Upstash provides two connection methods:
                # 1. REST API (HTTP-based, serverless-friendly)
                # 2. Native Redis protocol (TCP-based, faster)
                #
                # We use native protocol for better performance, but with
                # serverless-optimized settings (SSL, retries, timeouts)
                #
                # SERVERLESS REDIS GOTCHA (Upstash):
                # Upstash routes traffic over the public internet and REQUIRES
                # secure connections. Standard local Redis uses redis://.
                # Upstash REQUIRES rediss:// (with two S's for SSL/TLS).
                # If you miss the second 's', connections will fail with SSL errors.
                
                upstash_url = os.getenv("UPSTASH_REDIS_REST_URL")
                upstash_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
                redis_url = os.getenv("REDIS_URL")

                # Detect if using Upstash (rediss:// protocol or upstash.io domain)
                is_upstash = (
                    (redis_url and ("upstash.io" in redis_url or redis_url.startswith("rediss://")))
                    or (upstash_url and upstash_token)
                )
                
                # Validate Redis URL format
                if redis_url:
                    if not redis_url.startswith("redis://") and not redis_url.startswith("rediss://"):
                        logger.error(
                            f"Invalid REDIS_URL format: {redis_url[:20]}... "
                            f"(must start with redis:// or rediss://)"
                        )
                        self.redis = None
                        self.stats = CacheStats()
                        return
                    
                    # Warn if using non-SSL with Upstash
                    if is_upstash and redis_url.startswith("redis://"):
                        logger.error(
                            f"CRITICAL: Upstash requires SSL/TLS. "
                            f"Your REDIS_URL starts with 'redis://' but should start with 'rediss://' (two S's). "
                            f"Connection will fail. Please update your REDIS_URL."
                        )
                        self.redis = None
                        self.stats = CacheStats()
                        return
                    
                    # Serverless-optimized connection settings
                    connection_kwargs = {
                        "decode_responses": True,  # Auto-decode bytes to strings
                        "socket_connect_timeout": 10,  # 10s for serverless wake-up
                        "socket_timeout": 10,  # 10s for command execution
                        "socket_keepalive": True,  # Keep connections alive
                        "socket_keepalive_options": {
                            1: 30,  # TCP_KEEPIDLE: 30s
                            2: 10,  # TCP_KEEPINTVL: 10s
                            3: 5,   # TCP_KEEPCNT: 5 probes
                        },
                        "retry_on_timeout": True,  # Retry on timeout
                        "retry_on_error": [ConnectionError, TimeoutError],  # Retry on connection errors
                        "health_check_interval": 30,  # Health check every 30s
                    }
                    
                    # SSL/TLS configuration for Upstash
                    if is_upstash:
                        # Upstash REQUIRES SSL/TLS
                        # Use ssl_cert_reqs="none" for Upstash compatibility
                        # (Upstash uses valid certificates, but some Python environments
                        # have issues with certificate verification)
                        connection_kwargs["ssl"] = True
                        connection_kwargs["ssl_cert_reqs"] = None  # Don't verify SSL certificate
                        
                        logger.info(f"Connecting to Upstash Redis (native protocol with SSL): {redis_url[:50]}...")
                    else:
                        logger.info(f"Connecting to Redis: {redis_url[:30]}...")
                    
                    self.redis = redis.Redis.from_url(
                        redis_url,
                        **connection_kwargs
                    )
                    
                    # Test connection
                    try:
                        self.redis.ping()
                        logger.info("Redis connection successful")
                    except Exception as e:
                        logger.warning(f"Redis ping failed: {e} (will retry on first request)")
                
                elif upstash_url and upstash_token:
                    # Upstash REST API (fallback, slower but more reliable)
                    logger.info(f"Connecting to Upstash Redis (REST API): {upstash_url[:30]}...")
                    self.redis = redis.Redis.from_url(
                        upstash_url,
                        password=upstash_token,
                        decode_responses=True,
                        socket_connect_timeout=10,
                        socket_timeout=10,
                        retry_on_timeout=True,
                    )
                else:
                    # Local Redis (development)
                    logger.info("Connecting to local Redis (development)")
                    self.redis = redis.Redis(
                        host=getattr(settings, "REDIS_HOST", "localhost"),
                        port=getattr(settings, "REDIS_PORT", 6379),
                        db=getattr(settings, "REDIS_CACHE_DB", 2),
                        decode_responses=True,
                        socket_connect_timeout=5,
                        socket_timeout=5,
                    )
            except Exception as e:
                logger.error(
                    f"Redis cache initialization failed: {e} - caching will be disabled"
                )
                self.redis = None
        self.stats = CacheStats()

    def get(self, key: str) -> Optional[Any]:
        """Get cached value.

        Args:
            key: Cache key

        Returns:
            Cached value if found, None otherwise
        """
        if not self.redis:
            self.stats.record_miss()
            return None

        try:
            value = self.redis.get(key)
            if value:
                self.stats.record_hit()
                return json.loads(value)
            self.stats.record_miss()
            return None
        except Exception as e:
            logger.error(f"Redis get error for key {key}: {e}")
            self.stats.record_miss()
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set cached value with TTL.

        Args:
            key: Cache key
            value: Value to cache (will be JSON-serialized)
            ttl: Time-to-live in seconds. If None, uses get_default_ttl()
        """
        if not self.redis:
            return

        try:
            ttl_seconds = ttl if ttl is not None else self.get_default_ttl(key)
            serialized_value = json.dumps(value)
            self.redis.setex(key, ttl_seconds, serialized_value)
        except Exception as e:
            logger.error(f"Redis set error for key {key}: {e}")

    def delete(self, key: str):
        """Delete single key.

        Args:
            key: Cache key to delete
        """
        if not self.redis:
            return

        try:
            deleted = self.redis.delete(key)
            if deleted > 0:
                self.stats.record_invalidation()
        except Exception as e:
            logger.error(f"Redis delete error for key {key}: {e}")

    def invalidate(self, key: str):
        """Invalidate (delete) a single cache key.

        This is an alias for delete() to match the interface requirement.

        Args:
            key: Cache key to invalidate
        """
        self.delete(key)

    def delete_pattern(self, pattern: str):
        """Delete all keys matching pattern.

        Args:
            pattern: Redis key pattern (e.g., "search_query:*")
        """
        if not self.redis:
            return

        try:
            keys = self.redis.keys(pattern)
            if keys:
                deleted = self.redis.delete(*keys)
                self.stats.record_invalidation(deleted)
                logger.info(f"Deleted {deleted} keys matching pattern: {pattern}")
        except Exception as e:
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
        if not self.redis:
            return False

        try:
            return self.redis.ping()
        except Exception:
            return False


# Backward compatibility - maintain the old RedisCache class name
RedisCache = CacheService

# Global cache instance for backward compatibility
cache = CacheService()
