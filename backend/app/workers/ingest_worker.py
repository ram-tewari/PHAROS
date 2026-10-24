"""Repository ingestion worker (CPU-capable, no GPU required).

Runs ingestion jobs from the ``ingestion_jobs`` table::

    python -m app.workers.ingest_worker          # run forever
    python -m app.workers.ingest_worker --once   # drain due jobs, then exit

The embedding backend comes from ``EMBEDDING_BACKEND`` (``hash`` works on
any machine; ``sentence-transformers`` uses CUDA when available and falls
back to CPU). Wake-ups arrive through Redis when configured; otherwise the
worker polls the database every ``WORKER_POLL_INTERVAL`` seconds. On
SIGTERM / SIGINT it finishes the current job and exits; if it is killed
mid-job, the job's heartbeat goes stale and another worker re-queues it.

The production edge worker (``main_worker.py``) runs the same job runner
for jobs it receives on ``ingest_queue``.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
import uuid

from ..codeintel import jobs
from ..codeintel.embeddings import get_embedder
from ..codeintel.notify import get_notifier
from ..codeintel.runtime import job_ref, run_options, session_scope
from ..config.settings import get_settings

logger = logging.getLogger("pharos.ingest_worker")

RECOVERY_INTERVAL_SECONDS = 60


def process_job(job_id: uuid.UUID, worker_id: str, embedder) -> str | None:
    """Claim and run one job. Returns its final status, or None if not claimed."""
    with session_scope() as db:
        job = jobs.claim(db, job_id, worker_id)
        if job is None:
            return None
        logger.info("Claimed job %s (%s, attempt %d/%d)", job.id, job.repo_url, job.attempts, job.max_attempts)
        try:
            ref = job_ref(job.repo_url)
        except Exception as exc:
            job.status, job.error_kind, job.error = "failed", "invalid_repository", str(exc)[:2000]
            job.finished_at = jobs.utcnow()
            db.commit()
            return job.status
        job = jobs.run(db, job, ref, embedder, **run_options())
        return job.status


class Worker:
    def __init__(self, *, block_seconds: int | None = None) -> None:
        self.settings = get_settings()
        self.worker_id = jobs.default_worker_id()
        self.embedder = get_embedder(self.settings)
        self.notifier = get_notifier(self.settings)
        default_block = 30 if self.notifier.name == "upstash-rest" else 5
        self.block_seconds = block_seconds or (
            default_block if self.notifier.name != "none" else self.settings.WORKER_POLL_INTERVAL
        )
        self._stop = False
        self._last_recovery = 0.0

    def stop(self, *_args) -> None:
        logger.info("Shutdown requested; finishing the current job")
        self._stop = True

    def _recover(self) -> None:
        with session_scope() as db:
            for job_id in jobs.recover_stale(db, self.settings.INGESTION_JOB_STALE_SECONDS):
                self.notifier.notify(str(job_id))
        self._last_recovery = time.monotonic()

    def _due(self) -> list[uuid.UUID]:
        with session_scope() as db:
            return jobs.next_queued_ids(db, limit=5)

    def drain(self) -> int:
        """Run every due job once. Returns the number processed."""
        processed = 0
        for job_id in self._due():
            if self._stop:
                break
            if process_job(job_id, self.worker_id, self.embedder) is not None:
                processed += 1
        return processed

    def run_forever(self) -> None:
        logger.info(
            "Ingestion worker %s started (embedder=%s, notifier=%s, wait=%ss)",
            self.worker_id,
            self.embedder.model_id if self.embedder else "none",
            self.notifier.name,
            self.block_seconds,
        )
        self._recover()
        while not self._stop:
            if time.monotonic() - self._last_recovery > RECOVERY_INTERVAL_SECONDS:
                self._recover()
            # Jobs already due (including ones whose notification was lost).
            if self.drain():
                continue
            job_id = self.notifier.wait(self.block_seconds)
            if job_id:
                try:
                    process_job(uuid.UUID(job_id), self.worker_id, self.embedder)
                except ValueError:
                    logger.warning("Ignoring malformed job notification")
        logger.info("Ingestion worker %s stopped", self.worker_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pharos repository ingestion worker")
    parser.add_argument("--once", action="store_true", help="process due jobs and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    worker = Worker()
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    if args.once:
        worker._recover()
        n = worker.drain()
        logger.info("Processed %d job(s)", n)
        return 0
    worker.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
