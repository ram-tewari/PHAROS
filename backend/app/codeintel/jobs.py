"""Durable ingestion jobs.

PostgreSQL is the source of truth; Redis (optional) only carries wake-up
notifications. Consequences:

* A lost notification never loses a job — workers also poll for queued jobs
  and re-notify on startup.
* A duplicated notification never runs a job twice — :func:`claim` is an
  atomic conditional UPDATE (``WHERE status = 'queued'``).
* A worker that dies mid-job leaves a ``running`` row with a stale
  heartbeat; :func:`recover_stale` puts it back in the queue (or fails it
  once attempts are exhausted).
* Submitting a repository that already has an active job returns that job
  (``uq_ingestion_jobs_active``) instead of queueing a second clone.

Every job ends in exactly one terminal state: ``succeeded``, ``failed`` or
``cancelled``.
"""

from __future__ import annotations

import logging
import socket
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database.models import IngestionJob, Repository
from .embeddings import Embedder, EmbeddingUnavailable
from .git_source import GitError, RepoRef, RepoSpecError
from .indexer import CodeIndexer

logger = logging.getLogger(__name__)

ACTIVE = ("queued", "running")
TERMINAL = ("succeeded", "failed", "cancelled")


def utcnow() -> datetime:
    return datetime.now(UTC)


def default_worker_id() -> str:
    return f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"


@dataclass
class Submission:
    job: IngestionJob
    created: bool


class QueueFull(Exception):
    """Too many queued jobs; the caller should retry later (HTTP 429)."""

    def __init__(self, queued: int, limit: int) -> None:
        super().__init__(f"{queued} ingestion jobs are already queued (limit {limit})")
        self.queued = queued
        self.limit = limit


def submit(db: Session, ref: RepoRef, branch: str | None = None, *, force: bool = False,
           max_attempts: int = 3, max_queued: int | None = None) -> Submission:
    """Queue an ingestion job, or return the repository's active job.

    ``max_queued`` caps how many jobs may wait in ``queued`` (the API passes
    ``QUEUE_SIZE``); resubmitting a repository that already has an active job
    is never refused. The cap is checked before the insert, so concurrent
    submissions can overshoot it slightly (a soft cap).
    """
    existing = db.execute(
        select(IngestionJob).where(IngestionJob.repo_url == ref.canonical_url, IngestionJob.status.in_(ACTIVE))
    ).scalar_one_or_none()
    if existing is not None:
        return Submission(existing, created=False)
    if max_queued is not None:
        queued = db.execute(
            select(func.count()).select_from(IngestionJob).where(IngestionJob.status == "queued")
        ).scalar_one()
        if queued >= max_queued:
            raise QueueFull(queued, max_queued)
    repo = db.execute(select(Repository).where(Repository.url == ref.canonical_url)).scalar_one_or_none()
    job = IngestionJob(
        repository_id=repo.id if repo else None,
        repo_url=ref.canonical_url,
        branch_key=branch or "",
        force=force,
        status="queued",
        attempts=0,
        max_attempts=max_attempts,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        # Lost a race with a concurrent submission: return the winner.
        db.rollback()
        existing = db.execute(
            select(IngestionJob).where(
                IngestionJob.repo_url == ref.canonical_url, IngestionJob.status.in_(ACTIVE)
            )
        ).scalar_one()
        return Submission(existing, created=False)
    db.refresh(job)
    return Submission(job, created=True)


def claim(db: Session, job_id: uuid.UUID, worker_id: str) -> IngestionJob | None:
    """Atomically move a queued job to running. None if someone else got it."""
    now = utcnow()
    result = db.execute(
        update(IngestionJob)
        .where(
            IngestionJob.id == job_id,
            IngestionJob.status == "queued",
            or_(IngestionJob.available_at.is_(None), IngestionJob.available_at <= now),
        )
        .values(
            status="running",
            attempts=IngestionJob.attempts + 1,
            worker_id=worker_id,
            started_at=now,
            heartbeat_at=now,
            error=None,
            error_kind=None,
        )
    )
    db.commit()
    if result.rowcount != 1:
        return None
    return db.get(IngestionJob, job_id)


def next_queued_ids(db: Session, limit: int = 10) -> list[uuid.UUID]:
    """Queued jobs that are due (retry backoff elapsed), oldest first."""
    now = utcnow()
    return list(
        db.execute(
            select(IngestionJob.id)
            .where(
                IngestionJob.status == "queued",
                or_(IngestionJob.available_at.is_(None), IngestionJob.available_at <= now),
            )
            .order_by(IngestionJob.created_at)
            .limit(limit)
        ).scalars()
    )


def retry_delay_seconds(attempts: int) -> int:
    """30 s, 2 min, 8 min, ... capped at 1 h."""
    return min(3600, 30 * 4 ** max(0, attempts - 1))


def heartbeat(db: Session, job_id: uuid.UUID) -> None:
    db.execute(update(IngestionJob).where(IngestionJob.id == job_id).values(heartbeat_at=utcnow()))
    db.commit()


def cancel(db: Session, job_id: uuid.UUID) -> bool:
    result = db.execute(
        update(IngestionJob)
        .where(IngestionJob.id == job_id, IngestionJob.status == "queued")
        .values(status="cancelled", finished_at=utcnow())
    )
    db.commit()
    return result.rowcount == 1


def queue_summary(db: Session, stale_after_seconds: int) -> dict:
    """Worker health as seen from the durable job table.

    ``degraded`` when a running job stopped heartbeating, or a queued job has
    waited longer than ``stale_after_seconds`` (no worker is picking jobs up).
    """
    now = utcnow()
    cutoff = now - timedelta(seconds=stale_after_seconds)

    def count(*where) -> int:
        return db.execute(select(func.count()).select_from(IngestionJob).where(*where)).scalar_one()

    oldest = db.execute(
        select(func.min(IngestionJob.created_at)).where(IngestionJob.status == "queued")
    ).scalar_one()
    if oldest is not None and oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=now.tzinfo)
    summary = {
        "queued": count(IngestionJob.status == "queued"),
        "running": count(IngestionJob.status == "running"),
        "stale_running": count(IngestionJob.status == "running", IngestionJob.heartbeat_at < cutoff),
        "failed_last_24h": count(IngestionJob.status == "failed", IngestionJob.finished_at >= now - timedelta(days=1)),
        "oldest_queued_seconds": (now - oldest).total_seconds() if oldest is not None else None,
    }
    stuck = summary["stale_running"] > 0 or (
        summary["oldest_queued_seconds"] is not None and summary["oldest_queued_seconds"] > stale_after_seconds
    )
    summary["status"] = "degraded" if stuck else "healthy"
    return summary


def recover_stale(db: Session, stale_after_seconds: int) -> list[uuid.UUID]:
    """Re-queue running jobs whose worker stopped heartbeating.

    Returns the ids put back in the queue (callers re-notify them).
    """
    cutoff = utcnow() - timedelta(seconds=stale_after_seconds)
    stale = db.execute(
        select(IngestionJob).where(IngestionJob.status == "running", IngestionJob.heartbeat_at < cutoff)
    ).scalars().all()
    requeued = []
    for job in stale:
        if job.attempts >= job.max_attempts:
            job.status = "failed"
            job.error_kind = "worker_lost"
            job.error = f"worker {job.worker_id} stopped responding; attempts exhausted"
            job.finished_at = utcnow()
        else:
            job.status = "queued"
            job.error_kind = "worker_lost"
            job.error = f"worker {job.worker_id} stopped responding; re-queued"
            requeued.append(job.id)
    db.commit()
    if stale:
        logger.warning("Recovered %d stale ingestion job(s); %d re-queued", len(stale), len(requeued))
    return requeued


def classify_error(exc: BaseException) -> tuple[str, bool]:
    """(error_kind, retryable)."""
    if isinstance(exc, RepoSpecError):
        return "invalid_repository", False
    if isinstance(exc, GitError):
        return ("git_transient" if exc.retryable else "git_permanent"), exc.retryable
    if isinstance(exc, EmbeddingUnavailable):
        return "embedding_unavailable", True
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return "transient", True
    return "internal_error", False


def run(db: Session, job: IngestionJob, ref: RepoRef, embedder: Embedder | None, *,
        max_file_bytes: int, max_files: int, clone_timeout: int, clone_token: str | None) -> IngestionJob:
    """Execute a claimed job to a terminal (or re-queued) state. Never raises."""
    job_id = job.id

    def beat() -> None:
        try:
            heartbeat(db, job_id)
        except Exception:  # heartbeats are best-effort
            db.rollback()

    indexer = CodeIndexer(
        db, embedder,
        max_file_bytes=max_file_bytes, max_files=max_files,
        clone_timeout=clone_timeout, clone_token=clone_token, heartbeat=beat,
    )
    try:
        stats = indexer.index(ref, job.branch_key or None, force=job.force)
    except Exception as exc:
        db.rollback()
        kind, retryable = classify_error(exc)
        job = db.get(IngestionJob, job_id)
        job.error_kind = kind
        job.error = f"{type(exc).__name__}: {exc}"[:2000]
        if retryable and job.attempts < job.max_attempts:
            job.status = "queued"
            job.available_at = utcnow() + timedelta(seconds=retry_delay_seconds(job.attempts))
            logger.warning("Ingestion job %s failed (%s), will retry: %s", job_id, kind, exc)
        else:
            job.status = "failed"
            job.finished_at = utcnow()
            logger.error("Ingestion job %s failed permanently (%s): %s", job_id, kind, exc,
                         exc_info=kind == "internal_error")
        db.commit()
        return job

    job = db.get(IngestionJob, job_id)
    repo = db.execute(select(Repository).where(Repository.url == ref.canonical_url)).scalar_one()
    job.repository_id = repo.id
    job.status = "succeeded"
    job.commit_sha = stats.commit_sha
    job.stats = stats.as_dict()
    job.finished_at = utcnow()
    job.error = None
    job.error_kind = None
    db.commit()
    logger.info(
        "Ingestion job %s succeeded: %s @ %s (%s, %d files indexed, %d chunks)",
        job_id, ref.canonical_url, stats.commit_sha[:12], stats.outcome, stats.files_indexed, stats.chunks_total,
    )
    return job
