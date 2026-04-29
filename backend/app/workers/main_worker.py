"""
Pharos Unified Edge Worker

Single long-running process that:
  - Loads the local embedding model (RTX 4070).
  - Serves the FastAPI /embed endpoint on port EDGE_EMBED_PORT (default 8001).
  - Blocks on BOTH Redis queues with one connection:
        BLPOP pharos:tasks ingest_queue 30
    Routing by source queue:
        pharos:tasks   -> resource-level ingestion (process_ingestion)
        ingest_queue   -> repo-level clone/parse/embed/store

Upstash quota note: timeout=30s caps idle commands at ~2,880/day, well under
the 100,000/month free tier. DO NOT lower the timeout without re-doing the math.

Usage:
    python worker.py            # via dispatcher
    python -m app.workers.main_worker
    bash start_worker.sh        # bulletproof launcher
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Queue keys are exported so the dispatch banner in start_worker.sh stays in sync.
RESOURCE_QUEUE = "pharos:tasks"
REPO_QUEUE = "ingest_queue"
QUEUES = [RESOURCE_QUEUE, REPO_QUEUE]
BLPOP_TIMEOUT_SECONDS = 30

# Dead-letter queue. Tasks that sit in the main queue longer than
# DLQ_AGE_THRESHOLD_SECONDS are routed here instead of being processed, so
# a long-offline worker doesn't wake up and replay 6-hour-old jobs against a
# now-stale codebase. Drained back into the main queue on next clean boot.
DLQ_KEY = "pharos:dlq"
DLQ_AGE_THRESHOLD_SECONDS = 4 * 60 * 60  # 4 hours
DLQ_DRAIN_BATCH = 100  # cap LRANGE size on startup so we don't OOM
HEARTBEAT_INTERVAL_SECONDS = 60
WORKER_VERSION = "1.0.0"

# Dedicated executor for long-running ingestion work. The default asyncio /
# Starlette threadpool is left untouched so the FastAPI /embed endpoint can
# always grab a worker thread, even while a 35,000s Linux ingest is running.
# Linux ingest hammered the shared executor and stacked up /embed requests
# until Render's httpx timeout fired — see LINUX_INGESTION_STATUS.md.
INGESTION_THREADPOOL_SIZE = int(os.getenv("PHAROS_INGESTION_THREADS", "4"))
_ingestion_executor: ThreadPoolExecutor | None = None


def get_ingestion_executor() -> ThreadPoolExecutor:
    global _ingestion_executor
    if _ingestion_executor is None:
        _ingestion_executor = ThreadPoolExecutor(
            max_workers=INGESTION_THREADPOOL_SIZE,
            thread_name_prefix="pharos-ingest",
        )
    return _ingestion_executor


# ---------------------------------------------------------------------------
# Boot checks
# ---------------------------------------------------------------------------

def check_environment() -> None:
    """Validate required environment variables for EDGE mode."""
    required = [
        "MODE",
        "UPSTASH_REDIS_REST_URL",
        "UPSTASH_REDIS_REST_TOKEN",
        "DATABASE_URL",
    ]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        logger.error(f"Missing required env vars: {', '.join(missing)}")
        sys.exit(1)

    if os.getenv("MODE") != "EDGE":
        logger.error(f"MODE must be 'EDGE', got: {os.getenv('MODE')!r}")
        sys.exit(1)

    logger.info("Environment validated (MODE=EDGE)")


def check_gpu() -> str:
    """Log GPU status; never abort if CUDA is missing."""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            mem = torch.cuda.get_device_properties(0).total_memory / 1e9
            logger.info(f"GPU: {name} ({mem:.1f} GB), CUDA {torch.version.cuda}")
            return "cuda"
        logger.warning("CUDA unavailable — falling back to CPU")
        return "cpu"
    except ImportError:
        logger.error("PyTorch not installed; install requirements-edge.txt")
        sys.exit(1)


def load_embedding_model():
    from app.shared.embeddings import EmbeddingService

    logger.info("Loading embedding model...")
    t0 = time.time()
    svc = EmbeddingService()
    if not svc.warmup():
        logger.error("Embedding warmup failed")
        sys.exit(1)
    logger.info(f"Embedding model ready in {time.time() - t0:.1f}s")
    return svc


async def connect_to_redis():
    from app.shared.upstash_redis import UpstashRedisClient

    client = UpstashRedisClient()
    if not await client.ping():
        logger.error("Upstash PING failed")
        sys.exit(1)
    logger.info("Upstash Redis connected")
    return client


async def connect_to_database():
    from app.config.settings import get_settings
    from app.shared.database import get_db, init_database

    settings = get_settings()
    db_url = settings.get_database_url()
    init_database(db_url, env=settings.ENV)
    logger.info("Database connected")
    return get_db


# ---------------------------------------------------------------------------
# Resource-level handler (formerly edge.py / process_task)
# ---------------------------------------------------------------------------

async def handle_resource_task(task: Dict[str, Any]) -> bool:
    """Run the full single-resource ingestion pipeline in a worker thread."""
    task_id = task.get("task_id")
    resource_id = task.get("resource_id")
    if resource_id is None:
        logger.error(f"resource task {task_id} missing resource_id; payload={task}")
        return False

    logger.info(f"[RESOURCE] task={task_id} resource_id={resource_id}")

    def _run_sync() -> bool:
        from app.modules.resources.service import process_ingestion
        try:
            t0 = time.time()
            process_ingestion(resource_id=resource_id)
            logger.info(
                f"[RESOURCE] resource_id={resource_id} done in {time.time() - t0:.1f}s"
            )
            return True
        except Exception as exc:
            logger.error(
                f"[RESOURCE] resource_id={resource_id} failed: {exc}",
                exc_info=True,
            )
            return False

    return await asyncio.get_event_loop().run_in_executor(
        get_ingestion_executor(), _run_sync
    )


# ---------------------------------------------------------------------------
# Repository handler (formerly RepositoryWorker in repo.py)
# ---------------------------------------------------------------------------

class RepositoryIngestor:
    """Thin worker-side wrapper around HybridIngestionPipeline.

    The pipeline does the actual work (multi-language clone + chunk + embed +
    persist with proper vector CAST). We just hand it the worker's GPU-loaded
    EmbeddingService so we don't load a second model.
    """

    # Languages we walk into. Linux is C/C++/headers; the rest cover the
    # common cases the search backend already knows how to render.
    _DEFAULT_EXTENSIONS: tuple[str, ...] = (
        ".py", ".js", ".jsx", ".ts", ".tsx",
        ".go", ".rs", ".java", ".kt", ".scala",
        ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx",
        ".rb", ".php", ".swift",
    )

    def __init__(self, embedding_service):
        self.embedding_service = embedding_service

    async def ingest(self, task: Dict[str, Any]) -> bool:
        repo_url = task.get("repo_url") or task.get("payload")
        if not repo_url:
            logger.error(f"[REPO] task missing repo_url: {task}")
            return False

        # Pipeline requires an https:// clone URL; normalize bare github.com/x/y.
        if not repo_url.startswith(("http://", "https://")):
            repo_url = f"https://{repo_url}"

        # Branch is optional — when absent we let git pick the default
        # (Linux uses `master`, modern repos use `main`).
        branch = task.get("branch") or None
        extensions = tuple(task.get("file_extensions") or self._DEFAULT_EXTENSIONS)

        started = datetime.now()
        logger.info(f"[REPO] ingest {repo_url} (branch={branch or 'default'})")

        from app.modules.ingestion.ast_pipeline import HybridIngestionPipeline
        from app.shared.database import get_db

        try:
            async for session in get_db():
                pipeline = HybridIngestionPipeline(
                    db=session,
                    embedding_service=self.embedding_service,
                )
                result = await pipeline.ingest_github_repo(
                    git_url=repo_url,
                    branch=branch,
                    file_extensions=extensions,
                )
                duration = (datetime.now() - started).total_seconds()
                logger.info(
                    f"[REPO] {repo_url} done | "
                    f"resources={result.resources_created} "
                    f"chunks={result.chunks_created} "
                    f"failed={result.files_failed} "
                    f"duration={duration:.1f}s"
                )
                return result.resources_created > 0
            return False
        except Exception as exc:
            logger.error(f"[REPO] {repo_url} failed: {exc}", exc_info=True)
            return False

# ---------------------------------------------------------------------------
# FastAPI /embed server (kept from edge.py)
# ---------------------------------------------------------------------------

async def run_embed_server(embedding_service) -> None:
    import uvicorn
    from fastapi import FastAPI, HTTPException, Body

    app = FastAPI(title="Pharos Edge Embed Server", docs_url=None, redoc_url=None)

    # Use Body() instead of a Pydantic model defined in this local scope.
    # Locally-scoped Pydantic models break FastAPI's body-parameter inference
    # and the parameter falls back to a query param — causing every Render
    # call to /embed to 422 with `loc:["query","req"]`.
    @app.post("/embed")
    def embed(text: str = Body(..., embed=True)) -> dict:
        text = (text or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text must be non-empty")
        vec = embedding_service.generate_embedding(text)
        if not vec:
            raise HTTPException(status_code=503, detail="model unavailable")
        return {"embedding": vec}

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "model": embedding_service.embedding_generator.model_name}

    port = int(os.getenv("EDGE_EMBED_PORT", "8001"))
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info", access_log=False)
    logger.info(f"FastAPI /embed listening on 127.0.0.1:{port}")
    await uvicorn.Server(config).serve()


# ---------------------------------------------------------------------------
# Heartbeat — worker pings the cloud API every HEARTBEAT_INTERVAL_SECONDS.
# ---------------------------------------------------------------------------

import socket
import uuid


def _worker_id() -> str:
    """Stable-ish ID for this worker process (host + short uuid)."""
    return f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"


async def heartbeat_loop(
    worker_id: str,
    embedding_service,
    drained_count: int = 0,
) -> None:
    """Ping the cloud API's /health/worker endpoint every 60 seconds.

    The cloud API stores ``last_seen`` in Upstash Redis. When that key goes
    stale (> 5 min), the ingestion router responds with "System Degraded:
    Edge Worker Offline" instead of accepting new jobs.

    Heartbeat failures are logged but never crash the worker — a network
    blip should not take ingestion down. Worth: PHAROS_CLOUD_URL must be
    set; without it we log once and skip.
    """
    import httpx

    cloud_url = (
        os.getenv("PHAROS_CLOUD_URL")
        or os.getenv("PHAROS_API_URL")
        or "https://pharos-cloud-api.onrender.com"
    ).rstrip("/")
    admin_token = os.getenv("PHAROS_ADMIN_TOKEN")

    if not admin_token:
        logger.warning(
            "PHAROS_ADMIN_TOKEN unset — heartbeat disabled. "
            "Worker will appear OFFLINE to the cloud API."
        )
        return

    endpoint = f"{cloud_url}/api/v1/ingestion/health/worker"
    body = {
        "worker_id": worker_id,
        "version": WORKER_VERSION,
        "embedding_model": getattr(
            embedding_service.embedding_generator, "model_name", None
        ),
        "queue_drained_count": drained_count,
    }

    logger.info(
        f"Heartbeat → {endpoint} every {HEARTBEAT_INTERVAL_SECONDS}s "
        f"(worker_id={worker_id})"
    )

    async with httpx.AsyncClient(timeout=15.0) as client:
        consecutive_failures = 0
        while True:
            try:
                resp = await client.post(
                    endpoint,
                    json=body,
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                resp.raise_for_status()
                if consecutive_failures:
                    logger.info(
                        f"Heartbeat recovered after {consecutive_failures} failures"
                    )
                consecutive_failures = 0
            except Exception as exc:
                consecutive_failures += 1
                # Quiet log every minute, loud log every 10 failed beats.
                if consecutive_failures % 10 == 1:
                    logger.warning(
                        f"Heartbeat failed ({consecutive_failures}x): {exc}"
                    )

            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# DLQ helpers
# ---------------------------------------------------------------------------

def _task_age_seconds(task: Dict[str, Any]) -> float | None:
    """Return age of the task in seconds, or None if no timestamp present."""
    unix_ts = task.get("submitted_at_unix")
    if isinstance(unix_ts, (int, float)):
        return time.time() - float(unix_ts)

    submitted_at = task.get("submitted_at")
    if isinstance(submitted_at, str):
        try:
            ts = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
            return (datetime.now(ts.tzinfo) - ts).total_seconds()
        except (ValueError, TypeError):
            return None
    return None


async def _send_to_dlq(
    redis_client, task: Dict[str, Any], reason: str, source_queue: str
) -> None:
    """RPUSH a task into the DLQ with a reason annotation for later triage."""
    import json

    enriched = dict(task)
    enriched["_dlq"] = {
        "reason": reason,
        "source_queue": source_queue,
        "moved_at_unix": time.time(),
        "moved_at_iso": datetime.utcnow().isoformat() + "Z",
    }
    try:
        # Use _execute directly: RPUSH on the DLQ list is the simplest move.
        await redis_client._execute([
            "RPUSH", DLQ_KEY, json.dumps(enriched),
        ])
        # Cap DLQ at last 1000 entries so it can never grow without bound.
        await redis_client._execute(["LTRIM", DLQ_KEY, "-1000", "-1"])
        logger.warning(
            f"[DLQ] moved task_id={task.get('task_id')} "
            f"from={source_queue} reason={reason}"
        )
    except Exception as exc:
        logger.error(f"[DLQ] failed to move task to DLQ: {exc}", exc_info=True)


async def drain_dlq_on_startup(redis_client) -> int:
    """Drain ``pharos:dlq`` back into the main queues for one retry attempt.

    A clean restart usually means the previous failure mode (network blip,
    crash, OOM) is no longer present, so it's worth replaying queued work
    once. Tasks routed back to the DLQ a second time will simply sit there
    until manually inspected.

    Returns the number of tasks drained.
    """
    import json

    try:
        length = await redis_client._execute(["LLEN", DLQ_KEY]) or 0
        if not length:
            logger.info("[DLQ] empty on startup — nothing to drain")
            return 0

        drained = 0
        # Process in batches so we don't blow Upstash request size limits.
        while drained < length:
            entries = await redis_client._execute(
                ["LRANGE", DLQ_KEY, "0", str(DLQ_DRAIN_BATCH - 1)]
            ) or []
            if not entries:
                break
            for raw in entries:
                try:
                    task = json.loads(raw)
                except (TypeError, json.JSONDecodeError):
                    logger.warning("[DLQ] dropping un-parseable entry")
                    continue
                source_queue = (
                    task.get("_dlq", {}).get("source_queue") or REPO_QUEUE
                )
                # Strip the DLQ annotation and refresh the timestamp so the
                # age check in the dispatch loop doesn't immediately re-DLQ it.
                task.pop("_dlq", None)
                task["submitted_at_unix"] = time.time()
                task["submitted_at"] = datetime.utcnow().isoformat() + "Z"
                await redis_client._execute(
                    ["RPUSH", source_queue, json.dumps(task)]
                )
                drained += 1
            # LTRIM removes the slice we just re-queued.
            await redis_client._execute(
                ["LTRIM", DLQ_KEY, str(DLQ_DRAIN_BATCH), "-1"]
            )

        logger.info(f"[DLQ] drained {drained} task(s) back into main queues")
        return drained
    except Exception as exc:
        logger.error(f"[DLQ] drain failed: {exc}", exc_info=True)
        return 0


# ---------------------------------------------------------------------------
# Unified poll/dispatch loop
# ---------------------------------------------------------------------------

async def poll_and_dispatch(redis_client, embedding_service) -> None:
    """One BLPOP, two queues. Route by source queue, never crash on a poison pill."""
    repo_ingestor = RepositoryIngestor(embedding_service)
    processed = 0
    failed = 0

    logger.info(
        f"Polling {QUEUES} with BLPOP timeout={BLPOP_TIMEOUT_SECONDS}s "
        f"(~{86400 // BLPOP_TIMEOUT_SECONDS} idle cmds/day)"
    )

    while True:
        try:
            popped = await redis_client.pop_from_queues(
                QUEUES, timeout=BLPOP_TIMEOUT_SECONDS
            )
            if popped is None:
                continue  # idle, just re-block

            queue_key, task = popped
            task_id = task.get("task_id")

            # DLQ guard: a task that's been queued for > DLQ_AGE_THRESHOLD
            # hasn't been picked up in time. Likely the worker was down.
            # Move it to the DLQ rather than processing stale work — the repo
            # may have moved on, and a 6-hour-old resource ID may already be
            # gone from the database.
            age = _task_age_seconds(task)
            if age is not None and age > DLQ_AGE_THRESHOLD_SECONDS:
                await _send_to_dlq(
                    redis_client,
                    task,
                    reason=f"age_exceeded ({age:.0f}s > {DLQ_AGE_THRESHOLD_SECONDS}s)",
                    source_queue=queue_key,
                )
                if task_id:
                    try:
                        await redis_client.update_task_status(task_id, "dlq")
                    except Exception:
                        logger.exception("Failed to mark task as dlq")
                continue

            try:
                if queue_key == REPO_QUEUE:
                    success = await repo_ingestor.ingest(task)
                elif queue_key == RESOURCE_QUEUE:
                    success = await handle_resource_task(task)
                else:
                    logger.warning(f"Unknown queue {queue_key!r}; dropping task")
                    success = False

                if task_id:
                    await redis_client.update_task_status(
                        task_id, "completed" if success else "failed"
                    )
                processed += int(success)
                failed += int(not success)
                logger.info(f"Totals: processed={processed} failed={failed}")
            except Exception as exc:
                # Poison-pill containment: log + mark failed, keep the loop alive.
                failed += 1
                logger.error(
                    f"Handler crash on queue={queue_key} task={task_id}: {exc}",
                    exc_info=True,
                )
                if task_id:
                    try:
                        await redis_client.update_task_status(task_id, "failed")
                    except Exception:
                        logger.exception("Failed to mark task as failed")
        except KeyboardInterrupt:
            logger.info("Shutdown requested; exiting dispatch loop")
            return
        except Exception as exc:
            # Outer guard: never let a transport blip kill the worker.
            logger.error(f"Dispatch loop error: {exc}", exc_info=True)
            await asyncio.sleep(2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger.info("=" * 64)
    logger.info("Pharos Unified Edge Worker")
    logger.info(f"Queues : {QUEUES}")
    logger.info(f"BLPOP  : {BLPOP_TIMEOUT_SECONDS}s timeout (Upstash quota-safe)")
    logger.info("=" * 64)

    check_environment()
    check_gpu()
    embedding_service = load_embedding_model()
    redis_client = await connect_to_redis()
    await connect_to_database()

    # Drain the DLQ before we start polling so anything queued during the
    # outage gets a fresh shot at processing. drained_count is reported in
    # the first heartbeat for observability.
    drained = await drain_dlq_on_startup(redis_client)

    worker_id = _worker_id()
    logger.info(
        f"Boot complete (worker_id={worker_id}, dlq_drained={drained}); "
        f"serving /embed, dispatching tasks, sending heartbeats"
    )

    await asyncio.gather(
        run_embed_server(embedding_service),
        poll_and_dispatch(redis_client, embedding_service),
        heartbeat_loop(worker_id, embedding_service, drained_count=drained),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped")
        sys.exit(0)
    except Exception as exc:
        logger.error(f"Fatal error: {exc}", exc_info=True)
        sys.exit(1)
