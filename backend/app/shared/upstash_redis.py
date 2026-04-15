"""
Upstash Redis Client for Hybrid Edge-Cloud Architecture

This client provides a simple interface to Upstash Redis REST API for:
- Task queue management (push, pop, status updates)
- Job status tracking
- Worker coordination

Uses Upstash Redis REST API (not redis-py) for serverless compatibility.
"""

import json
import logging
import os
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)


class UpstashRedisClient:
    """Client for Upstash Redis REST API."""

    def __init__(
        self,
        rest_url: Optional[str] = None,
        rest_token: Optional[str] = None,
    ):
        """Initialize Upstash Redis client.

        Args:
            rest_url: Upstash Redis REST URL (or from UPSTASH_REDIS_REST_URL env var)
            rest_token: Upstash Redis REST token (or from UPSTASH_REDIS_REST_TOKEN env var)
        """
        self.rest_url = rest_url or os.getenv("UPSTASH_REDIS_REST_URL")
        self.rest_token = rest_token or os.getenv("UPSTASH_REDIS_REST_TOKEN")

        if not self.rest_url:
            raise ValueError(
                "UPSTASH_REDIS_REST_URL must be set (either as parameter or environment variable)"
            )

        if not self.rest_token:
            raise ValueError(
                "UPSTASH_REDIS_REST_TOKEN must be set (either as parameter or environment variable)"
            )

        # Remove trailing slash from URL
        self.rest_url = self.rest_url.rstrip("/")

        # Create HTTP client
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.rest_token}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )

        logger.info(f"Upstash Redis client initialized: {self.rest_url}")

    async def _execute(self, command: list) -> Any:
        """Execute a Redis command via REST API.

        Args:
            command: Redis command as list (e.g., ["GET", "key"])

        Returns:
            Command result

        Raises:
            Exception: If command fails
        """
        try:
            response = await self.client.post(
                self.rest_url,
                json=command,
            )
            response.raise_for_status()

            data = response.json()
            return data.get("result")

        except httpx.HTTPStatusError as e:
            logger.error(f"Upstash Redis HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Upstash Redis error: {e}")
            raise

    async def ping(self) -> bool:
        """Test connection to Upstash Redis.

        Returns:
            True if connection successful
        """
        try:
            result = await self._execute(["PING"])
            return result == "PONG"
        except Exception as e:
            logger.error(f"Ping failed: {e}")
            return False

    async def push_task(self, task: Dict[str, Any]) -> bool:
        """Push a task to the queue.

        Args:
            task: Task dictionary with task_id, resource_id, text, etc.

        Returns:
            True if successful
        """
        try:
            task_json = json.dumps(task)
            await self._execute(["RPUSH", "pharos:tasks", task_json])
            logger.info(f"Pushed task to queue: {task.get('task_id')}")
            return True
        except Exception as e:
            logger.error(f"Failed to push task: {e}")
            return False

    async def pop_task(self) -> Optional[Dict[str, Any]]:
        """Pop a task from the queue (blocking with 1 second timeout).

        Returns:
            Task dictionary or None if queue is empty
        """
        try:
            # BLPOP with 1 second timeout
            result = await self._execute(["BLPOP", "pharos:tasks", "1"])

            if result:
                # BLPOP returns [key, value]
                task_json = result[1]
                task = json.loads(task_json)
                logger.debug(f"Popped task from queue: {task.get('task_id')}")
                return task
            else:
                # Queue is empty
                return None

        except Exception as e:
            logger.error(f"Failed to pop task: {e}")
            return None

    async def update_task_status(self, task_id: str, status: str) -> bool:
        """Update task status.

        Args:
            task_id: Task ID
            status: New status (pending, processing, completed, failed)

        Returns:
            True if successful
        """
        try:
            key = f"pharos:task:{task_id}:status"
            await self._execute(["SET", key, status, "EX", "86400"])  # 24 hour TTL
            logger.debug(f"Updated task {task_id} status to: {status}")
            return True
        except Exception as e:
            logger.error(f"Failed to update task status: {e}")
            return False

    async def get_task_status(self, task_id: str) -> Optional[str]:
        """Get task status.

        Args:
            task_id: Task ID

        Returns:
            Task status or None if not found
        """
        try:
            key = f"pharos:task:{task_id}:status"
            status = await self._execute(["GET", key])
            return status
        except Exception as e:
            logger.error(f"Failed to get task status: {e}")
            return None

    async def get_queue_length(self) -> int:
        """Get number of tasks in queue.

        Returns:
            Queue length
        """
        try:
            length = await self._execute(["LLEN", "pharos:tasks"])
            return length or 0
        except Exception as e:
            logger.error(f"Failed to get queue length: {e}")
            return 0

    async def clear_queue(self) -> bool:
        """Clear all tasks from queue (for testing/maintenance).

        Returns:
            True if successful
        """
        try:
            await self._execute(["DEL", "pharos:tasks"])
            logger.info("Cleared task queue")
            return True
        except Exception as e:
            logger.error(f"Failed to clear queue: {e}")
            return False

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
