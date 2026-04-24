"""Inspect document_chunks.github_uri to diagnose fetcher failures."""
import asyncio
import os
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
    engine = create_async_engine(_async_url(os.environ["DATABASE_URL"]))
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        r = await s.execute(text("""
            SELECT is_remote, github_uri, branch_reference, start_line, end_line,
                   chunk_metadata->>'file_path' AS file_path
            FROM document_chunks
            WHERE resource_id IN (
                SELECT id FROM resources
                WHERE title LIKE '%check_version.py%'
                LIMIT 2
            )
            LIMIT 5
        """))
        for row in r.fetchall():
            print(f"is_remote={row[0]} branch={row[2]} lines={row[3]}-{row[4]}")
            print(f"  github_uri: {row[1]}")
            print(f"  file_path:  {row[5]}")
            print()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
