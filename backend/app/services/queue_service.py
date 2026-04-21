"""
Queue Service - Task queue management for Pharos

Provides Redis-based task queue with support for both CLOUD (Upstash)
and EDGE (local Redis) modes.
"""

import json
import uuid
from typing import Optional

from redis import Redis
from app.config.settings import get_settings


class QueueService:
    """
    Redis-based task queue service supporting both CLOUD and EDGE modes.

    CLOUD mode: Uses Upstash Redis REST API
    EDGE mode: Uses local Redis instance
    """

    QUEUE_KEY = "pharos:tasks"  # Must match edge worker queue key
    STATUS_KEY_PREFIX = "pharos:status:"
    HISTORY_KEY = "pharos:history"
    # Secondary hash index for O(1) job lookup by job_id. The queue list above
    # preserves FIFO order for the edge worker; this hash lets status / update
    # operations skip the O(n) LRANGE scan. See ADR-015.
    JOBS_HASH_KEY = "pharos:jobs"

    def __init__(self):
        self.settings = get_settings()
        self._redis: Optional[Redis] = None

    @property
    def redis(self) -> Redis:
        """Get or create Redis connection based on MODE."""
        if self._redis is None:
            if self.settings.MODE == "CLOUD":
                self._redis = self._get_upstash_redis()
            else:
                self._redis = self._get_local_redis()
        return self._redis

    def _get_upstash_redis(self) -> Redis:
        """Create Upstash Redis connection for CLOUD mode.
        
        Uses standard Redis protocol URL (rediss://) instead of REST API.
        This allows us to use the standard redis-py client.
        """
        # Use REDIS_URL which has the rediss:// protocol
        redis_url = self.settings.REDIS_URL
        
        if not redis_url:
            raise ValueError(
                "Queue service not configured: REDIS_URL must be set in CLOUD mode"
            )
        
        # Use standard Redis client with rediss:// URL
        return Redis.from_url(
            redis_url,
            decode_responses=True,
        )

    def _get_local_redis(self) -> Redis:
        """Create local Redis connection for EDGE mode."""
        return Redis(
            host=self.settings.REDIS_HOST,
            port=self.settings.REDIS_PORT,
            db=0,
            decode_responses=True,
        )

    async def submit_job(self, job_data: dict) -> str:
        """
        Submit a job to the queue.

        Args:
            job_data: Job data dictionary containing job details

        Returns:
            str: Job ID for the submitted job

        Raises:
            HTTPException: 429 if queue is full
            ValueError: If queue service is not configured
        """
        from fastapi import HTTPException
        import asyncio

        # Run sync Redis operations in thread pool
        loop = asyncio.get_event_loop()

        def _submit():
            job_id = str(uuid.uuid4())
            job_data["task_id"] = job_id  # Edge worker expects "task_id"
            job_data["job_id"] = job_id  # Keep for backward compatibility
            job_data["status"] = "pending"
            job_data["created_at"] = str(uuid.uuid1().time)  # timestamp

            # Check queue size
            queue_size = self.redis.llen(self.QUEUE_KEY)
            if queue_size >= self.settings.QUEUE_SIZE:
                raise HTTPException(
                    status_code=429,
                    detail=f"Queue is full ({queue_size}/{self.settings.QUEUE_SIZE})",
                )

            job_json = json.dumps(job_data)

            # Add to queue (FIFO order for edge worker)
            self.redis.rpush(self.QUEUE_KEY, job_json)

            # Secondary hash index: O(1) lookup by job_id
            self.redis.hset(self.JOBS_HASH_KEY, job_id, job_json)

            # Add to history
            self.redis.lpush(self.HISTORY_KEY, job_json)
            # Trim history to last 1000 entries
            self.redis.ltrim(self.HISTORY_KEY, 0, 999)

            return job_id

        return await loop.run_in_executor(None, _submit)

    async def get_job_status(self, job_id: str) -> Optional[dict]:
        """
        Get the status of a job.

        Args:
            job_id: The job ID to look up

        Returns:
            dict: Job status data or None if not found
        """
        import asyncio

        loop = asyncio.get_event_loop()

        def _get_status():
            # O(1) lookup via secondary hash index (ADR-015).
            job_json = self.redis.hget(self.JOBS_HASH_KEY, job_id)
            if job_json:
                if isinstance(job_json, bytes):
                    job_json = job_json.decode("utf-8")
                try:
                    job = json.loads(job_json)
                    status = job.get("status", "pending")
                    if status in ("pending", "processing"):
                        return {
                            "job_id": job_id,
                            "status": status,
                            "created_at": job.get("created_at"),
                        }
                    return {
                        "job_id": job_id,
                        "status": status,
                        "result": job.get("result"),
                        "error": job.get("error"),
                        "completed_at": job.get("completed_at"),
                    }
                except (json.JSONDecodeError, ValueError):
                    pass

            # Fall back to history scan for jobs evicted from the hash.
            history_jobs = self.redis.lrange(self.HISTORY_KEY, 0, -1)
            for entry in history_jobs:
                try:
                    if isinstance(entry, bytes):
                        entry = entry.decode("utf-8")
                    job = json.loads(entry)
                    if job.get("job_id") == job_id:
                        return {
                            "job_id": job_id,
                            "status": job.get("status", "unknown"),
                            "result": job.get("result"),
                            "error": job.get("error"),
                            "completed_at": job.get("completed_at"),
                        }
                except (json.JSONDecodeError, ValueError):
                    continue

            return None

        return await loop.run_in_executor(None, _get_status)

    async def get_job_history(self, limit: int = 10) -> list[dict]:
        """
        Get recent job history.

        Args:
            limit: Maximum number of jobs to return (max 100)

        Returns:
            list: List of job records from history
        """
        import asyncio

        # Cap limit at 100
        limit = min(limit, 100)

        loop = asyncio.get_event_loop()

        def _get_history():
            jobs_raw = self.redis.lrange(self.HISTORY_KEY, 0, limit - 1)
            jobs = []

            for job_data in jobs_raw:
                try:
                    if isinstance(job_data, bytes):
                        job_data = job_data.decode("utf-8")
                    job = json.loads(job_data)
                    jobs.append(job)
                except (json.JSONDecodeError, ValueError):
                    continue

            return jobs

        return await loop.run_in_executor(None, _get_history)

    async def update_job_status(
        self,
        job_id: str,
        status: str,
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> bool:
        """
        Update job status (called by worker).

        Args:
            job_id: The job ID to update
            status: New status (processing, completed, failed)
            result: Optional result data
            error: Optional error message

        Returns:
            bool: True if job was found and updated
        """
        import asyncio
        from datetime import datetime

        loop = asyncio.get_event_loop()

        def _update():
            # O(1) fetch via secondary hash index (ADR-015).
            job_json = self.redis.hget(self.JOBS_HASH_KEY, job_id)
            if not job_json:
                return False
            if isinstance(job_json, bytes):
                job_json = job_json.decode("utf-8")

            try:
                job = json.loads(job_json)
            except (json.JSONDecodeError, ValueError):
                return False

            original_json = job_json
            job["status"] = status
            if result:
                job["result"] = result
            if error:
                job["error"] = error
            job["completed_at"] = datetime.utcnow().isoformat()
            updated_json = json.dumps(job)

            # Remove the original entry from the FIFO queue (O(n) in Redis,
            # but only the n comparisons inside Redis, not per-item JSON
            # decoding in Python).
            self.redis.lrem(self.QUEUE_KEY, 0, original_json)

            # Drop from hash on terminal status; keep updated entry otherwise.
            if status in ("completed", "failed"):
                self.redis.hdel(self.JOBS_HASH_KEY, job_id)
            else:
                self.redis.hset(self.JOBS_HASH_KEY, job_id, updated_json)

            # Add to history
            self.redis.lpush(self.HISTORY_KEY, updated_json)
            self.redis.ltrim(self.HISTORY_KEY, 0, 999)

            return True

        return await loop.run_in_executor(None, _update)

    async def get_queue_position(self, job_id: str) -> Optional[int]:
        """
        Get the position of a job in the queue.

        Args:
            job_id: The job ID to look up

        Returns:
            int: Position in queue (1-based) or None if not found/not pending
        """
        import asyncio

        loop = asyncio.get_event_loop()

        def _get_position():
            # Short-circuit via hash: if the job isn't pending/processing,
            # it's not in the queue anymore — skip the O(n) scan entirely.
            job_json = self.redis.hget(self.JOBS_HASH_KEY, job_id)
            if not job_json:
                return None

            queue_jobs = self.redis.lrange(self.QUEUE_KEY, 0, -1)
            for i, entry in enumerate(queue_jobs):
                try:
                    if isinstance(entry, bytes):
                        entry = entry.decode("utf-8")
                    job = json.loads(entry)
                    if job.get("job_id") == job_id:
                        return i + 1
                except (json.JSONDecodeError, ValueError):
                    continue
            return None

        return await loop.run_in_executor(None, _get_position)

    async def get_queue_size(self) -> int:
        """
        Get the current queue size.

        Returns:
            int: Number of pending jobs in queue
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.redis.llen, self.QUEUE_KEY)

    async def clear_queue(self) -> int:
        """
        Clear all pending jobs from the queue.

        Returns:
            int: Number of jobs removed
        """
        import asyncio

        loop = asyncio.get_event_loop()

        def _clear():
            size = self.redis.llen(self.QUEUE_KEY)
            self.redis.delete(self.QUEUE_KEY)
            # Drop the secondary hash index alongside the queue.
            self.redis.delete(self.JOBS_HASH_KEY)
            return size

        return await loop.run_in_executor(None, _clear)
