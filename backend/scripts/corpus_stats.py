"""Corpus stats: how much is actually searchable."""
import asyncio, os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _async(url: str) -> str:
    return url.replace("postgresql://", "postgresql+asyncpg://", 1) if url.startswith("postgresql://") else url


async def main():
    engine = create_async_engine(_async(os.environ["DATABASE_URL"]))
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        for q, label in [
            ("SELECT COUNT(*) FROM resources", "total resources"),
            ("SELECT COUNT(*) FROM resources WHERE embedding IS NOT NULL", "with embedding"),
            ("SELECT COUNT(DISTINCT resource_id) FROM document_chunks", "with chunks"),
            (
                "SELECT COUNT(*) FROM resources r WHERE embedding IS NOT NULL "
                "AND EXISTS (SELECT 1 FROM document_chunks WHERE resource_id = r.id)",
                "searchable (embedded + chunks)",
            ),
            ("SELECT COUNT(*) FROM document_chunks", "total chunks"),
            ("SELECT COUNT(*) FROM document_chunks WHERE is_remote=TRUE", "remote chunks"),
        ]:
            n = (await s.execute(text(q))).scalar()
            print(f"{label:40s} {n:>8}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
