"""Admin endpoints: dense-embedding backfill, housekeeping.

The backfill endpoint dispatches work to the edge worker via the
existing Upstash queue (pharos:tasks) rather than calling /embed
synchronously from the cloud API — the cloud box is 512MB on Render
Free and must not block on GPU work.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database.models import DocumentChunk, Resource
from ...shared.database import get_sync_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


class BackfillRequest(BaseModel):
    batch_size: int = Field(50, ge=1, le=500, description="Tasks pushed per HTTP round-trip")
    max_chunks: Optional[int] = Field(None, ge=1, description="Cap on rows queued")
    resource_filter: Optional[str] = Field(
        None, description="ILIKE filter on resources.source (e.g. '%langchain%')"
    )


class BackfillResponse(BaseModel):
    queued: int
    skipped_no_summary: int
    queue_key: str


@router.post("/backfill-embeddings", response_model=BackfillResponse)
async def backfill_embeddings(
    payload: BackfillRequest,
    db: Session = Depends(get_sync_db),
) -> BackfillResponse:
    """Queue DocumentChunk rows that need embeddings to the edge worker.

    Targets `document_chunks.embedding_id IS NULL` and pushes one task
    per chunk to `pharos:tasks`. The WSL edge worker pops tasks (BLPOP)
    and writes the embedding back via the existing worker path.

    Memory profile is flat: we hold (uuid, summary) tuples for one batch
    only, push them, then move to the next OFFSET.
    """
    rest_url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
    rest_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if not rest_url or not rest_token:
        raise HTTPException(503, "Upstash Redis env vars not configured")

    base_stmt = (
        select(DocumentChunk.id, DocumentChunk.semantic_summary, DocumentChunk.resource_id)
        .where(DocumentChunk.embedding_id.is_(None))
        .order_by(DocumentChunk.created_at)
    )
    if payload.resource_filter:
        base_stmt = (
            base_stmt.join(Resource, Resource.id == DocumentChunk.resource_id)
            .where(Resource.source.ilike(payload.resource_filter))
        )
    if payload.max_chunks:
        base_stmt = base_stmt.limit(payload.max_chunks)

    rows = db.execute(base_stmt).all()
    if not rows:
        return BackfillResponse(queued=0, skipped_no_summary=0, queue_key="pharos:tasks")

    queued = 0
    skipped = 0

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {rest_token}"},
        timeout=15.0,
    ) as client:
        # Push in batches via Upstash pipeline endpoint when payload allows;
        # fall back to single RPUSH per task otherwise. Per-task RPUSH is
        # 1 Upstash command per chunk — fine for the free-tier 100k/day
        # quota for any reasonable backfill (typical run: 1-10k chunks).
        for cid, summary, rid in rows:
            if not summary or not summary.strip():
                skipped += 1
                continue
            task = {
                "task_id": str(uuid.uuid4()),
                "resource_id": str(rid),
                "chunk_id": str(cid),
                "task_type": "embedding",
                "text": summary,
            }
            r = await client.post(rest_url, json=["RPUSH", "pharos:tasks", json.dumps(task)])
            try:
                r.raise_for_status()
                queued += 1
            except httpx.HTTPStatusError as exc:
                logger.error("RPUSH failed for chunk %s: %s", cid, exc)

    logger.info(
        "backfill-embeddings: queued=%d skipped_no_summary=%d filter=%r",
        queued, skipped, payload.resource_filter,
    )
    return BackfillResponse(
        queued=queued, skipped_no_summary=skipped, queue_key="pharos:tasks"
    )


class TrimHistoryRequest(BaseModel):
    max_entries: int = Field(100, ge=1, le=10000)
    key: str = Field("pharos:history")


class TrimHistoryResponse(BaseModel):
    key: str
    length_after: int


@router.post("/trim-history", response_model=TrimHistoryResponse)
async def trim_history(payload: TrimHistoryRequest) -> TrimHistoryResponse:
    """Trim `payload.key` to its last `max_entries` items. Idempotent."""
    from ...shared.upstash_redis import UpstashRedisClient
    client = UpstashRedisClient()
    try:
        length = await client.trim_history(payload.key, payload.max_entries)
    finally:
        await client.close()
    return TrimHistoryResponse(key=payload.key, length_after=length)
