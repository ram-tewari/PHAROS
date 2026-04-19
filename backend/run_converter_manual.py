"""Manually run the repository converter for LangChain."""

import asyncio
import os

# Force production database
os.environ["DATABASE_URL"] = "postgresql+asyncpg://neondb_owner:npg_2Lv8pxVJzgyd@ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech/neondb"

from app.shared.database import init_database, get_db
from app.modules.resources.repository_converter import RepositoryConverter

async def run_converter():
    """Run converter for LangChain repository."""
    init_database()
    
    # Use the most recent LangChain repository
    repo_id = "dcce1b56-1dc9-4edf-8cf3-9b081f7ca48d"
    
    print("=" * 60)
    print("Manual Repository Converter")
    print("=" * 60)
    print(f"Repository ID: {repo_id}")
    print()
    
    async for db in get_db():
        try:
            converter = RepositoryConverter(db)
            
            print("[CONVERT] Starting conversion...")
            stats = await converter.convert_repository(repo_id)
            
            print()
            print("=" * 60)
            print("[SUCCESS] Conversion Complete")
            print("=" * 60)
            print(f"Resources created: {stats['resources_created']}")
            print(f"Chunks created: {stats['chunks_created']}")
            print(f"Embeddings linked: {stats['embeddings_linked']}")
            print(f"Entities created: {stats['entities_created']}")
            if stats['errors']:
                print(f"Errors: {len(stats['errors'])}")
                print("\nFirst 5 errors:")
                for error in stats['errors'][:5]:
                    print(f"  - {error['file']}: {error['error']}")
            print("=" * 60)
            
        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()
        finally:
            break

if __name__ == "__main__":
    asyncio.run(run_converter())
