"""Job wake-up notifications (Redis), with the database as the fallback.

Notifications are an optimisation: they let an idle worker block on a cheap
Redis BLPOP instead of polling PostgreSQL (which would keep a serverless
database awake). They are allowed to be lost or duplicated — see
``jobs.py``. The payload ``{"job_id": "..."}`` is pushed to the existing
``ingest_queue`` key by default, so the production edge worker
(``main_worker.py``), which already BLPOPs that key, picks jobs up without
an extra Redis connection.

Backends, chosen by :func:`get_notifier`:

* ``REDIS_URL`` (``redis://`` or Upstash's ``rediss://``) — redis-py;
* ``UPSTASH_REDIS_REST_URL`` + token — Upstash REST over https;
* neither — no notifications; workers poll the database.
"""

from __future__ import annotations

import json
import logging
import time

logger = logging.getLogger(__name__)


class Notifier:
    name = "none"

    def notify(self, job_id: str) -> bool:
        return False

    def wait(self, timeout: int) -> str | None:
        time.sleep(timeout)
        return None


def _parse(raw) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return str(data["job_id"]) if isinstance(data, dict) and data.get("job_id") else None


class RedisNotifier(Notifier):
    name = "redis"

    def __init__(self, url: str, key: str) -> None:
        import redis

        self.key = key
        self._client = redis.Redis.from_url(url, socket_timeout=60, socket_connect_timeout=10)

    def notify(self, job_id: str) -> bool:
        try:
            self._client.rpush(self.key, json.dumps({"job_id": job_id}))
            return True
        except Exception as exc:
            logger.warning("Job notification failed (job stays queued in the DB): %s", type(exc).__name__)
            return False

    def wait(self, timeout: int) -> str | None:
        try:
            item = self._client.blpop([self.key], timeout=timeout)
        except Exception as exc:
            logger.warning("Redis BLPOP failed (%s); falling back to DB polling", type(exc).__name__)
            time.sleep(min(timeout, 5))
            return None
        return _parse(item[1]) if item else None


class UpstashRestNotifier(Notifier):
    name = "upstash-rest"

    def __init__(self, url: str, token: str, key: str) -> None:
        self.url = url.rstrip("/")
        self.key = key
        self._headers = {"Authorization": f"Bearer {token}"}

    def _cmd(self, command: list, timeout: float) -> object:
        import httpx

        resp = httpx.post(self.url, json=command, headers=self._headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("result")

    def notify(self, job_id: str) -> bool:
        try:
            self._cmd(["RPUSH", self.key, json.dumps({"job_id": job_id})], timeout=10)
            return True
        except Exception as exc:
            logger.warning("Job notification failed (job stays queued in the DB): %s", type(exc).__name__)
            return False

    def wait(self, timeout: int) -> str | None:
        try:
            result = self._cmd(["BLPOP", self.key, str(timeout)], timeout=timeout + 15)
        except Exception as exc:
            logger.warning("Upstash BLPOP failed (%s); falling back to DB polling", type(exc).__name__)
            time.sleep(min(timeout, 5))
            return None
        if isinstance(result, list) and len(result) == 2:
            return _parse(result[1])
        return None


def get_notifier(settings) -> Notifier:
    key = settings.INGESTION_NOTIFY_KEY
    if settings.REDIS_URL:
        return RedisNotifier(settings.REDIS_URL, key)
    if settings.UPSTASH_REDIS_REST_URL and settings.UPSTASH_REDIS_REST_TOKEN:
        return UpstashRestNotifier(
            settings.UPSTASH_REDIS_REST_URL, settings.UPSTASH_REDIS_REST_TOKEN.get_secret_value(), key
        )
    return Notifier()
