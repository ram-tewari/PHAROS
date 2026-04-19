"""
Manual converter runner for LangChain repository
"""
import asyncio
import sys
from app.shared.database import get_db, init_database
from app.config.settings import get_settings
from app.modules.resources.repository_converter import RepositoryConverter

async def main():
    # Initialize database
    settings = get_settings()
    init_database(settings.get_database_url(), settings.ENV)
    
    repo_id = "dcce1b56-1dc9-4edf-8cf3-9b081f7ca48d"
    
    print(f"Converting repository {repo_id}...")
    
    async for db in get_db():
        try:
            converter = RepositoryConverter(db)
            stats = await converter.convert_repository(repo_id)
            
            print("\n" + "=" * 60)
            print("CONVERSION COMPLETE")
            print("=" * 60)
            print(f"Resources created: {stats['resources_created']}")
            print(f"Chunks created: {stats['chunks_created']}")
            print(f"Embeddings linked: {stats['embeddings_linked']}")
            print(f"Entities created: {stats['entities_created']}")
            if stats['errors']:
                print(f"Errors: {len(stats['errors'])}")
                for error in stats['errors'][:5]:  # Show first 5 errors
                    print(f"  - {error['file']}: {error['error']}")
            print("=" * 60)
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
        finally:
            break

if __name__ == "__main__":
    asyncio.run(main())
