"""Check if resources have embeddings."""

import asyncio
import os
from sqlalchemy import text

# Force production database
os.environ["DATABASE_URL"] = "postgresql+asyncpg://neondb_owner:npg_2Lv8pxVJzgyd@ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech/neondb"

from app.shared.database import init_database, get_db

async def check_embeddings():
    """Check embeddings."""
    init_database()
    
    print("=" * 60)
    print("Embeddings Check")
    print("=" * 60)
    print()
    
    async for db in get_db():
        try:
            # Count resources with embeddings
            result = await db.execute(text("""
                SELECT COUNT(*) FROM resources WHERE embedding IS NOT NULL
            """))
            with_embeddings = result.scalar()
            
            result = await db.execute(text("""
                SELECT COUNT(*) FROM resources WHERE embedding IS NULL
            """))
            without_embeddings = result.scalar()
            
            print(f"Resources with embeddings: {with_embeddings}")
            print(f"Resources without embeddings: {without_embeddings}")
            
            # Check a sample
            if with_embeddings > 0:
                result = await db.execute(text("""
                    SELECT id, title, 
                           CASE 
                               WHEN embedding IS NOT NULL THEN 'YES'
                               ELSE 'NO'
                           END as has_embedding,
                           LENGTH(CAST(embedding AS TEXT)) as embedding_length
                    FROM resources
                    WHERE type = 'code'
                    ORDER BY created_at DESC
                    LIMIT 5
                """))
                
                print("\nSample resources:")
                for row in result:
                    print(f"  - {row.title}")
                    print(f"    Has embedding: {row.has_embedding}")
                    if row.embedding_length:
                        print(f"    Embedding length: {row.embedding_length} chars")
            
        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()
        finally:
            break

if __name__ == "__main__":
    asyncio.run(check_embeddings())
