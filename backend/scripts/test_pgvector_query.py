"""Diagnostic: run pgvector similarity query directly against NeonDB.

Usage (WSL):
    source backend/.wsl-venv/bin/activate
    python backend/scripts/test_pgvector_query.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def main() -> None:
    dsn = os.environ["DATABASE_URL"]
    engine = create_async_engine(_async_url(dsn))
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as s:
        # 1. How many resources have non-null embeddings?
        r = await s.execute(
            text("SELECT COUNT(*) FROM resources WHERE embedding IS NOT NULL")
        )
        total_embedded = r.scalar()
        print(f"resources WHERE embedding IS NOT NULL: {total_embedded}")

        # 2. What's the column type?
        r = await s.execute(
            text(
                "SELECT data_type, udt_name "
                "FROM information_schema.columns "
                "WHERE table_name='resources' AND column_name='embedding'"
            )
        )
        row = r.fetchone()
        print(f"resources.embedding: data_type={row[0]} udt_name={row[1]}")

        # 3. Sample one embedded resource
        r = await s.execute(
            text(
                "SELECT id::text, title, "
                "(SELECT COUNT(*) FROM document_chunks WHERE resource_id = r.id) AS chunks "
                "FROM resources r "
                "WHERE embedding IS NOT NULL LIMIT 3"
            )
        )
        print("Sample embedded resources:")
        for row in r.fetchall():
            print(f"  id={row[0]} chunks={row[2]} title={row[1][:60]}")

        # 4. Run the actual pgvector query with a fake 768-dim vector
        fake = [0.01] * 768
        emb_str = f"[{','.join(map(str, fake))}]"
        try:
            r = await s.execute(
                text(
                    "SELECT id::text, embedding <=> CAST(:emb AS vector) AS distance "
                    "FROM resources WHERE embedding IS NOT NULL "
                    "ORDER BY distance ASC LIMIT 3"
                ),
                {"emb": emb_str},
            )
            rows = r.fetchall()
            print(f"pgvector query returned {len(rows)} rows:")
            for row in rows:
                print(f"  id={row[0]} distance={float(row[1]):.4f}")
        except Exception as exc:
            print(f"pgvector query FAILED: {exc}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
