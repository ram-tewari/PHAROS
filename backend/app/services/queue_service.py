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

    QUEUE_KEY = "pharos:jobs"
    STATUS_KEY_PREFIX = "pharos:status:"
    HISTORY_KEY = "pharos:history"

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
        """Create Upstash Redis connection for CLOUD mode."""
        upstash_url = self.settings.UPSTASH_REDIS_REST_URL
        upstash_token = self.settings.UPSTASH_REDIS_REST_TOKEN

        if not upstash_url:
            raise ValueError(
                "Queue service not configured: UPSTASH_REDIS_REST_URL must be set in CLOUD mode"
            )
        if not upstash_token:
            raise ValueError(
                "Queue service not configured: UPSTASH_REDIS_REST_TOKEN must be set in CLOUD mode"
            )

        # Upstash uses HTTP/REST API, Redis.from_url works with the REST URL
        return Redis.from_url(
            upstash_url,
            password=upstash_token.get_secret_value() if upstash_token else None,
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
            job_data["job_id"] = job_id
            job_data["status"] = "pending"
            job_data["created_at"] = str(uuid.uuid1().time)  # timestamp

            # Check queue size
            queue_size = self.redis.llen(self.QUEUE_KEY)
            if queue_size >= self.settings.QUEUE_SIZE:
                raise HTTPException(
                    status_code=429,
                    detail=f"Queue is full ({queue_size}/{self.settings.QUEUE_SIZE})",
                )

            # Add to queue
            self.redis.rpush(self.QUEUE_KEY, json.dumps(job_data))

            # Add to history
            self.redis.lpush(self.HISTORY_KEY, json.dumps(job_data))
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
            # Check current queue for pending jobs
            queue_jobs = self.redis.lrange(self.QUEUE_KEY, 0, -1)
            for job_json in queue_jobs:
                try:
                    if isinstance(job_json, bytes):
                        job_json = job_json.decode("utf-8")
                    job = json.loads(job_json)
                    if job.get("job_id") == job_id:
                        return {
                            "job_id": job_id,
                            "status": job.get("status", "pending"),
                            "position": queue_jobs.index(job_json) + 1,
                            "created_at": job.get("created_at"),
                        }
                except (json.JSONDecodeError, ValueError):
                    continue

            # Check history for completed/failed jobs
            history_jobs = self.redis.lrange(self.HISTORY_KEY, 0, -1)
            for job_json in history_jobs:
                try:
                    if isinstance(job_json, bytes):
                        job_json = job_json.decode("utf-8")
                    job = json.loads(job_json)
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
            # Find and update in queue
            queue_jobs = self.redis.lrange(self.QUEUE_KEY, 0, -1)
            for i, job_json in enumerate(queue_jobs):
                try:
                    if isinstance(job_json, bytes):
                        job_json = job_json.decode("utf-8")
                    job = json.loads(job_json)
                    if job.get("job_id") == job_id:
                        job["status"] = status
                        if result:
                            job["result"] = result
                        if error:
                            job["error"] = error
                        job["completed_at"] = datetime.utcnow().isoformat()

                        # Remove from queue
                        self.redis.lrem(self.QUEUE_KEY, 0, job_json)

                        # Add to history
                        self.redis.lpush(self.HISTORY_KEY, json.dumps(job))
                        self.redis.ltrim(self.HISTORY_KEY, 0, 999)

                        return True
                except (json.JSONDecodeError, ValueError):
                    continue

            return False

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
            queue_jobs = self.redis.lrange(self.QUEUE_KEY, 0, -1)
            for i, job_json in enumerate(queue_jobs):
                try:
                    if isinstance(job_json, bytes):
                        job_json = job_json.decode("utf-8")
                    job = json.loads(job_json)
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
            return size

        return await loop.run_in_executor(None, _clear)
