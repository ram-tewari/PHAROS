"""Test search locally to verify the fix works."""

import asyncio
import os
from sqlalchemy import text

# Force production database
os.environ["DATABASE_URL"] = "postgresql+asyncpg://neondb_owner:npg_2Lv8pxVJzgyd@ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech/neondb"

from app.shared.database import init_database, get_db
from app.modules.search.service import SearchService

async def test_search():
    """Test search."""
    init_database()
    
    print("=" * 60)
    print("Testing Search Locally")
    print("=" * 60)
    print()
    
    async for db in get_db():
        try:
            # Create search service
            search_service = SearchService(db)
            
            # Test parent-child search
            print("[TEST] Running parent-child search for 'langchain'...")
            results = search_service.parent_child_search(
                query="langchain",
                top_k=5,
                context_window=2
            )
            
            print(f"\n[RESULT] Found {len(results)} results")
            
            if results:
                print("\nTop results:")
                for i, result in enumerate(results[:3], 1):
                    chunk = result["chunk"]
                    score = result["score"]
                    print(f"\n{i}. Score: {score:.4f}")
                    print(f"   Resource ID: {chunk['resource_id']}")
                    print(f"   Chunk Index: {chunk['chunk_index']}")
                    if chunk.get("chunk_metadata"):
                        metadata = chunk["chunk_metadata"]
                        if isinstance(metadata, dict):
                            print(f"   File: {metadata.get('file_path', 'N/A')}")
            else:
                print("\n[WARN] No results found!")
                print("\nDebugging info:")
                
                # Check if there are any chunks
                result = await db.execute(text("SELECT COUNT(*) FROM document_chunks"))
                chunk_count = result.scalar()
                print(f"  Total chunks: {chunk_count}")
                
                # Check if there are any resources with embeddings
                result = await db.execute(text("SELECT COUNT(*) FROM resources WHERE embedding IS NOT NULL"))
                emb_count = result.scalar()
                print(f"  Resources with embeddings: {emb_count}")
                
                # Check a sample resource
                result = await db.execute(text("""
                    SELECT r.id, r.title, 
                           CASE WHEN r.embedding IS NOT NULL THEN 'YES' ELSE 'NO' END as has_emb,
                           LENGTH(CAST(r.embedding AS TEXT)) as emb_len
                    FROM resources r
                    WHERE r.type = 'code' AND r.embedding IS NOT NULL
                    LIMIT 1
                """))
                row = result.first()
                if row:
                    print(f"\n  Sample resource:")
                    print(f"    Title: {row.title}")
                    print(f"    Has embedding: {row.has_emb}")
                    print(f"    Embedding length: {row.emb_len} chars")
            
        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()
        finally:
            break

if __name__ == "__main__":
    asyncio.run(test_search())
