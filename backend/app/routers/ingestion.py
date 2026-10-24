"""Legacy ingestion endpoints (``/api/v1/ingestion``), kept for existing clients.

New clients should use ``POST /api/v1/repositories`` and
``GET /api/v1/ingestion/jobs/{id}`` (``app.modules.code``). These endpoints
now sit on the same durable job system:

* ``POST /ingest/{repo_url:path}`` queues a database-backed job instead of
  pushing a fire-and-forget payload onto Redis. It no longer refuses work
  while the edge worker is offline: the job is durable and runs when a
  worker comes back (the response says whether a wake-up was sent).
* ``GET /jobs/history`` reads jobs from the database.
* ``POST|GET /health/worker`` keep the edge-worker heartbeat (Upstash) used
  by ``main_worker.py``.

This router must be registered before ``app.modules.code`` so that
``/jobs/history`` is not captured by ``/ingestion/jobs/{job_id}``.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.codeintel import jobs
from app.codeintel.git_source import RepoSpecError, parse_repo_spec
from app.codeintel.notify import get_notifier
from app.config.settings import get_settings
from app.database.models import IngestionJob
from app.shared.auth import require_admin
from app.shared.database import get_sync_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])

WORKER_HEARTBEAT_KEY = "pharos:worker:last_seen"
WORKER_HEARTBEAT_META_KEY = "pharos:worker:meta"
WORKER_OFFLINE_THRESHOLD_SECONDS = 300
HEARTBEAT_TTL_SECONDS = 600


class LegacyIngestResponse(BaseModel):
    status: str = Field(..., description="queued | already_active")
    job_id: str
    repo_url: str
    notified: bool
    message: str


class WorkerHeartbeatRequest(BaseModel):
    worker_id: str | None = Field(default=None, max_length=128)
    version: str | None = Field(default=None, max_length=64)
    embedding_model: str | None = Field(default=None, max_length=128)
    queue_drained_count: int | None = None


class WorkerHeartbeatResponse(BaseModel):
    accepted: bool
    last_seen_unix: float
    worker_id: str | None = None


class WorkerHealthResponse(BaseModel):
    state: str = Field(..., description="online | degraded | offline | unknown")
    last_seen_unix: float | None = None
    seconds_since_last_seen: float | None = None
    threshold_seconds: int = WORKER_OFFLINE_THRESHOLD_SECONDS
    worker_meta: dict | None = None


class JobRecord(BaseModel):
    job_id: str
    repo_url: str
    status: str
    duration_seconds: float | None = None
    files_processed: int | None = None
    embeddings_generated: int | None = None
    timestamp: str
    error: str | None = None
    age_seconds: float | None = None


class JobHistoryResponse(BaseModel):
    jobs: list[JobRecord]


def _upstash():
    """Upstash REST client, or None when not configured (heartbeats only)."""
    url, token = os.getenv("UPSTASH_REDIS_REST_URL"), os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        return None
    from upstash_redis import Redis

    return Redis(url=url, token=token)


@router.post("/ingest/{repo_url:path}", response_model=LegacyIngestResponse, deprecated=True)
def trigger_remote_ingestion(repo_url: str, db: Session = Depends(get_sync_db), _=Depends(require_admin)):
    """Queue repository ingestion (deprecated: use ``POST /api/v1/repositories``)."""
    settings = get_settings()
    try:
        ref = parse_repo_spec(repo_url, allowed_hosts=settings.CODEINTEL_ALLOWED_GIT_HOSTS)
    except RepoSpecError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid repository URL: {exc}") from exc
    submission = jobs.submit(db, ref)
    notified = get_notifier(settings).notify(str(submission.job.id)) if submission.created else False
    return LegacyIngestResponse(
        status="queued" if submission.created else "already_active",
        job_id=str(submission.job.id),
        repo_url=ref.canonical_url,
        notified=notified,
        message=f"Track progress at GET /api/v1/ingestion/jobs/{submission.job.id}",
    )


@router.get("/jobs/history", response_model=JobHistoryResponse)
def get_job_history(limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_sync_db)):
    rows = db.execute(select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(limit)).scalars()
    now = datetime.now(UTC)
    out = []
    for job in rows:
        created = job.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        duration = None
        if job.started_at and job.finished_at:
            duration = (job.finished_at - job.started_at).total_seconds()
        stats = job.stats or {}
        out.append(
            JobRecord(
                job_id=str(job.id),
                repo_url=job.repo_url,
                status=job.status,
                duration_seconds=duration,
                files_processed=stats.get("files_indexed"),
                embeddings_generated=stats.get("embeddings_written"),
                timestamp=created.isoformat() if created else "",
                error=job.error,
                age_seconds=(now - created).total_seconds() if created else None,
            )
        )
    return JobHistoryResponse(jobs=out)


@router.get("/health")
def health_check():
    """Public liveness probe for the ingestion subsystem (no internals exposed)."""
    return {"status": "healthy"}


@router.post("/health/worker", response_model=WorkerHeartbeatResponse)
def record_worker_heartbeat(payload: WorkerHeartbeatRequest, _=Depends(require_admin)):
    """Edge worker heartbeat (``main_worker.heartbeat_loop``), stored in Upstash."""
    redis = _upstash()
    if redis is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Upstash is not configured")
    now = time.time()
    meta = payload.model_dump() | {"last_seen_iso": datetime.fromtimestamp(now, UTC).isoformat()}
    try:
        redis.set(WORKER_HEARTBEAT_KEY, str(now), ex=HEARTBEAT_TTL_SECONDS)
        redis.set(WORKER_HEARTBEAT_META_KEY, json.dumps(meta), ex=HEARTBEAT_TTL_SECONDS)
    except Exception as exc:
        logger.error("Heartbeat write failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="failed to persist heartbeat") from exc
    return WorkerHeartbeatResponse(accepted=True, last_seen_unix=now, worker_id=payload.worker_id)


@router.get("/health/worker", response_model=WorkerHealthResponse)
def get_worker_health():
    redis = _upstash()
    if redis is None:
        return WorkerHealthResponse(state="unknown")
    try:
        raw = redis.get(WORKER_HEARTBEAT_KEY)
        meta_raw = redis.get(WORKER_HEARTBEAT_META_KEY)
    except Exception:
        return WorkerHealthResponse(state="unknown")
    if not raw:
        return WorkerHealthResponse(state="offline")
    last_seen = float(raw.decode() if isinstance(raw, bytes) else raw)
    try:
        meta = json.loads(meta_raw) if meta_raw else None
    except (TypeError, ValueError):
        meta = None
    age = time.time() - last_seen
    return WorkerHealthResponse(
        state="online" if age <= WORKER_OFFLINE_THRESHOLD_SECONDS else "degraded",
        last_seen_unix=last_seen,
        seconds_since_last_seen=age,
        worker_meta=meta,
    )
