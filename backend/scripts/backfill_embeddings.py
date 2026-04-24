"""Queue all resources with chunks for re-embedding.

Pushes one task per resource to Upstash pharos:tasks. The WSL embed
server pops them (BLPOP 9s) and updates resources.embedding. Use after
changing the embed text source so old embeddings get rewritten.

Throttling: we push in small batches and sleep briefly between batches
to keep Upstash REST calls under the free-tier 10k/day cap even when
the embed worker is idle polling alongside this backfill.

Usage (WSL):
    source backend/.wsl-venv/bin/activate
    python backend/scripts/backfill_embeddings.py
"""
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _async(url: str) -> str:
    return (
        url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://")
        else url
    )


async def main() -> None:
    redis_url = os.environ["UPSTASH_REDIS_REST_URL"].rstrip("/")
    redis_token = os.environ["UPSTASH_REDIS_REST_TOKEN"]

    engine = create_async_engine(_async(os.environ["DATABASE_URL"]))
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as s:
        r = await s.execute(text(
            "SELECT r.id::text "
            "FROM resources r "
            "WHERE EXISTS (SELECT 1 FROM document_chunks WHERE resource_id = r.id) "
            "ORDER BY r.id"
        ))
        resource_ids = [row[0] for row in r.fetchall()]

    await engine.dispose()
    total = len(resource_ids)
    print(f"Queuing {total} resources for re-embedding...")
    sys.stdout.flush()

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {redis_token}"}, timeout=15.0
    ) as client:
        queued = 0
        for rid in resource_ids:
            payload = json.dumps({
                "task_id": str(uuid.uuid4()),
                "resource_id": rid,
                "task_type": "embedding",
            })
            # RPUSH returns queue length; single-element version is fine,
            # batching multiple values per RPUSH would be 1 call for many
            # tasks but would all get popped in sequence anyway so the
            # Upstash request count is dominated by the worker BLPOPs, not
            # pushes. Keep it simple.
            r = await client.post(redis_url, json=["RPUSH", "pharos:tasks", payload])
            r.raise_for_status()
            queued += 1
            if queued % 100 == 0:
                print(f"  queued {queued}/{total}")
                sys.stdout.flush()
            # Small throttle so we don't hammer Upstash
            await asyncio.sleep(0.02)

    print(f"Done. {queued} tasks queued.")


if __name__ == "__main__":
    asyncio.run(main())
