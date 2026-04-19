"""Check where embeddings are stored."""

import asyncio
import os
from sqlalchemy import text

# Force production database
os.environ["DATABASE_URL"] = "postgresql+asyncpg://neondb_owner:npg_2Lv8pxVJzgyd@ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech/neondb"

from app.shared.database import init_database, get_db

async def check():
    """Check embedding storage."""
    init_database()
    
    async for db in get_db():
        try:
            # Check resources table
            print("Checking resources.embedding column...")
            result = await db.execute(text("""
                SELECT id, title, 
                       CASE WHEN embedding IS NOT NULL THEN 'YES' ELSE 'NO' END as has_embedding,
                       LENGTH(CAST(embedding AS TEXT)) as emb_len
                FROM resources
                WHERE type = 'code'
                ORDER BY created_at DESC
                LIMIT 3
            """))
            
            print("\nResources with embeddings:")
            for row in result:
                print(f"  - {row.title}")
                print(f"    Has embedding: {row.has_embedding}")
                if row.emb_len:
                    print(f"    Embedding length: {row.emb_len} chars")
            
            # Check chunks table
            print("\n\nChecking document_chunks.chunk_metadata for embeddings...")
            result = await db.execute(text("""
                SELECT id, semantic_summary,
                       chunk_metadata::text LIKE '%embedding%' as has_embedding_in_metadata
                FROM document_chunks
                WHERE is_remote = TRUE
                LIMIT 3
            """))
            
            print("\nChunks with embedding in metadata:")
            for row in result:
                print(f"  - {row.semantic_summary[:50]}...")
                print(f"    Has embedding in metadata: {row.has_embedding_in_metadata}")
            
        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()
        finally:
            break

if __name__ == "__main__":
    asyncio.run(check())
