"""Resource staleness tracking.

A Resource becomes stale when the upstream source has advanced past
the snapshot Pharos indexed. Stale Resources should be filtered out
of retrieval so Ronin doesn't serve confidently-wrong answers about
code that no longer exists or has been refactored away.

The marking strategy:
  - `last_indexed_sha` records the commit SHA of the snapshot we ingested.
  - When a re-ingest runs (or a webhook fires), call
    `mark_repo_stale_by_sha(db, source, current_head_sha, fresh_resource_ids)`.
  - Any Resource matching `source` whose `last_indexed_sha` differs
    from `current_head_sha` AND whose id is not in `fresh_resource_ids`
    is flipped to `is_stale=True`.

Resources reingested in the same run get `is_stale=False` and an
updated `last_indexed_sha` via `mark_resources_fresh`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Sequence
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Resource

logger = logging.getLogger(__name__)


async def mark_resources_fresh(
    db: AsyncSession,
    resource_ids: Sequence[UUID],
    current_head_sha: str,
) -> int:
    """Mark a set of Resources as freshly indexed at `current_head_sha`."""
    if not resource_ids:
        return 0
    now = datetime.now(timezone.utc)
    stmt = (
        update(Resource)
        .where(Resource.id.in_(list(resource_ids)))
        .values(
            is_stale=False,
            last_indexed_sha=current_head_sha,
            last_indexed_at=now,
        )
    )
    result = await db.execute(stmt)
    return result.rowcount or 0


async def mark_repo_stale_by_sha(
    db: AsyncSession,
    source: str,
    current_head_sha: str,
    fresh_resource_ids: Iterable[UUID] = (),
) -> int:
    """Flip is_stale=True for Resources of `source` not present in the new ingest.

    Args:
        source: The git_url stored on Resource.source.
        current_head_sha: HEAD SHA of the upstream repo as of this run.
        fresh_resource_ids: Resources that were just (re)ingested in this run
            and should NOT be marked stale even if their prior SHA differs.

    Returns:
        Number of rows updated.
    """
    fresh_ids = list(fresh_resource_ids)
    stmt = (
        update(Resource)
        .where(Resource.source == source)
        .where(Resource.is_stale.is_(False))
        .where(
            (Resource.last_indexed_sha.is_(None))
            | (Resource.last_indexed_sha != current_head_sha)
        )
    )
    if fresh_ids:
        stmt = stmt.where(~Resource.id.in_(fresh_ids))
    stmt = stmt.values(is_stale=True)

    result = await db.execute(stmt)
    rowcount = result.rowcount or 0
    logger.info(
        "Marked %d resources stale for source=%s (head=%s)",
        rowcount,
        source,
        current_head_sha[:12] if current_head_sha else "?",
    )
    return rowcount
