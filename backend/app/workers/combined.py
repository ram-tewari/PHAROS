"""
Pharos Combined Worker - Edge GPU + Repo Ingestion in One Process

Polls pharos:tasks and dispatches by payload shape:
  - {repo_url: ...}       -> clone/parse/embed/store via RepositoryWorker
  - {resource_id: ...}    -> existing-resource ingestion via process_ingestion
Also runs the FastAPI /embed server on port 8001 for cloud-mode query embedding.

Usage:
    python worker.py combined
"""

import asyncio
import logging
import sys

from app.workers.edge import (
    check_environment,
    check_gpu,
    connect_to_database,
    connect_to_redis,
    load_embedding_model,
    process_task as edge_process_task,
    run_fastapi_server,
)

logger = logging.getLogger(__name__)


async def poll_and_dispatch(redis_client, embedding_service, db_session_factory, repo_worker):
    """Single poll loop that routes tasks to the right handler by payload shape."""
    from app.config.settings import get_settings

    poll_interval = get_settings().WORKER_POLL_INTERVAL
    logger.info(f"Dispatch loop started (poll interval {poll_interval}s)")

    processed = 0
    failed = 0

    while True:
        try:
            task = await redis_client.pop_task()
            if task is None:
                await asyncio.sleep(poll_interval)
                continue

            task_id = task.get("task_id")

            if "repo_url" in task:
                logger.info(f"[REPO] task={task_id} url={task.get('repo_url')}")
                try:
                    await repo_worker.process_ingestion(task)
                    processed += 1
                    await redis_client.update_task_status(task_id, "completed")
                except Exception as exc:
                    failed += 1
                    logger.error(f"Repo task failed: {exc}", exc_info=True)
                    await redis_client.update_task_status(task_id, "failed")
            elif "resource_id" in task:
                logger.info(f"[EDGE] task={task_id} resource={task.get('resource_id')}")
                success = await edge_process_task(task, embedding_service, db_session_factory)
                if success:
                    processed += 1
                    await redis_client.update_task_status(task_id, "completed")
                else:
                    failed += 1
                    await redis_client.update_task_status(task_id, "failed")
            else:
                logger.warning(f"Unknown task payload, skipping: {task}")
                failed += 1

            logger.info(f"Totals: processed={processed} failed={failed}")

        except KeyboardInterrupt:
            logger.info("Dispatch loop interrupted")
            break
        except Exception as exc:
            logger.error(f"Dispatch loop error: {exc}", exc_info=True)
            await asyncio.sleep(poll_interval)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger.info("=" * 60)
    logger.info("Pharos Combined Worker (edge + repo)")
    logger.info("=" * 60)

    check_environment()
    check_gpu()
    embedding_service = load_embedding_model()
    redis_client = await connect_to_redis()
    db_session_factory = await connect_to_database()

    # RepositoryWorker.__init__ re-pings Redis and re-inits the DB; both are
    # idempotent, so we keep it rather than duplicating its setup here.
    from app.workers.repo import RepositoryWorker
    repo_worker = RepositoryWorker()

    logger.info("=" * 60)
    logger.info("Combined worker ready - /embed server + dispatch loop")
    logger.info("=" * 60)

    await asyncio.gather(
        run_fastapi_server(embedding_service),
        poll_and_dispatch(
            redis_client, embedding_service, db_session_factory, repo_worker
        ),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Combined worker stopped")
        sys.exit(0)
