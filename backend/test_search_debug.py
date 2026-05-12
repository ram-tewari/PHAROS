"""Debug script to check search readiness"""
import asyncio
from sqlalchemy import select, func
from app.database.models import DocumentChunk, Resource
from app.shared.database import AsyncSessionLocal, init_database

async def check_search_readiness():
    # Initialize database (not async)
    init_database()
    
    async with AsyncSessionLocal() as db:
        # Count total chunks
        total_chunks = await db.scalar(select(func.count()).select_from(DocumentChunk))
        print(f"Total chunks: {total_chunks}")
        
        # Count chunks with embeddings
        chunks_with_embeddings = await db.scalar(
            select(func.count()).select_from(DocumentChunk).where(DocumentChunk.embedding.isnot(None))
        )
        print(f"Chunks with embeddings: {chunks_with_embeddings}")
        
        # Count chunks with semantic_summary
        chunks_with_summary = await db.scalar(
            select(func.count()).select_from(DocumentChunk).where(DocumentChunk.semantic_summary.isnot(None))
        )
        print(f"Chunks with semantic_summary: {chunks_with_summary}")
        
        # Sample a few chunks
        result = await db.execute(
            select(DocumentChunk.id, DocumentChunk.semantic_summary, DocumentChunk.embedding)
            .limit(5)
        )
        chunks = result.all()
        
        print("\nSample chunks:")
        for chunk_id, summary, embedding in chunks:
            has_embedding = "YES" if embedding else "NO"
            summary_preview = (summary[:80] + "...") if summary and len(summary) > 80 else summary
            print(f"  {chunk_id}: embedding={has_embedding}, summary={summary_preview}")
        
        # Count resources
        total_resources = await db.scalar(select(func.count()).select_from(Resource))
        print(f"\nTotal resources: {total_resources}")
        
        # Count resources with embeddings
        resources_with_embeddings = await db.scalar(
            select(func.count()).select_from(Resource).where(Resource.embedding.isnot(None))
        )
        print(f"Resources with embeddings: {resources_with_embeddings}")

if __name__ == "__main__":
    asyncio.run(check_search_readiness())
