#!/usr/bin/env python3
"""
Patch Redis connection to use Upstash instead of localhost
"""

import os

def patch_redis_connection():
    cache_file = "/mnt/c/Users/rooma/PycharmProjects/neo_alexadria/backend/app/shared/cache.py"
    
    with open(cache_file, 'r') as f:
        content = f.read()
    
    # Add os import if not present
    if 'import os' not in content:
        content = content.replace('import redis', 'import os\nimport redis')
    
    # Replace Redis connection logic
    old_redis = '''self.redis = redis.Redis(
                    host=getattr(settings, "REDIS_HOST", "localhost"),
                    port=getattr(settings, "REDIS_PORT", 6379),
                    db=getattr(settings, "REDIS_CACHE_DB", 2),
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                )'''
    
    new_redis = '''# Check for Upstash Redis first
                upstash_url = os.getenv("UPSTASH_REDIS_REST_URL")
                upstash_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
                
                if upstash_url and upstash_token:
                    self.redis = redis.Redis.from_url(
                        upstash_url,
                        password=upstash_token,
                        decode_responses=True,
                        socket_connect_timeout=5,
                        socket_timeout=5,
                    )
                    logger.info(f"Connected to Upstash Redis: {upstash_url}")
                else:
                    self.redis = redis.Redis(
                        host=getattr(settings, "REDIS_HOST", "localhost"),
                        port=getattr(settings, "REDIS_PORT", 6379),
                        db=getattr(settings, "REDIS_CACHE_DB", 2),
                        decode_responses=True,
                        socket_connect_timeout=5,
                        socket_timeout=5,
                    )'''
    
    content = content.replace(old_redis, new_redis)
    
    with open(cache_file, 'w') as f:
        f.write(content)
    
    print("✅ Patched Redis connection to use Upstash")

if __name__ == "__main__":
    patch_redis_connection()
