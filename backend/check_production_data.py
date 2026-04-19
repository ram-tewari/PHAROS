"""Check production database for repositories and resources."""

import asyncio
import os
from sqlalchemy import text
from dotenv import load_dotenv

# Force production database
os.environ["DATABASE_URL"] = "postgresql+asyncpg://neondb_owner:npg_2Lv8pxVJzgyd@ep-flat-meadow-ahvsmoyw-pooler.c-3.us-east-1.aws.neon.tech/neondb"

from app.shared.database import init_database, get_db

async def check_data():
    """Check production database."""
    init_database()
    
    print("=" * 60)
    print("Production Database Check")
    print("=" * 60)
    print()
    
    async for db in get_db():
        try:
            # Check repositories
            print("[CHECK] Repositories table...")
            result = await db.execute(text("SELECT COUNT(*) FROM repositories"))
            repo_count = result.scalar()
            print(f"  Repositories: {repo_count}")
            
            if repo_count > 0:
                result = await db.execute(text("""
                    SELECT id, name, url, total_files, total_lines, created_at
                    FROM repositories
                    ORDER BY created_at DESC
                    LIMIT 5
                """))
                print("\n  Recent repositories:")
                for row in result:
                    print(f"    - {row.name}: {row.total_files} files, {row.total_lines} lines")
                    print(f"      ID: {row.id}")
                    print(f"      Created: {row.created_at}")
            
            print()
            
            # Check resources
            print("[CHECK] Resources table...")
            result = await db.execute(text("SELECT COUNT(*) FROM resources"))
            resource_count = result.scalar()
            print(f"  Resources: {resource_count}")
            
            if resource_count > 0:
                result = await db.execute(text("""
                    SELECT id, title, type, created_at
                    FROM resources
                    WHERE type = 'code'
                    ORDER BY created_at DESC
                    LIMIT 5
                """))
                print("\n  Recent code resources:")
                for row in result:
                    print(f"    - {row.title}")
                    print(f"      ID: {row.id}")
                    print(f"      Created: {row.created_at}")
            
            print()
            
            # Check chunks
            print("[CHECK] Document chunks table...")
            result = await db.execute(text("SELECT COUNT(*) FROM document_chunks"))
            chunk_count = result.scalar()
            print(f"  Chunks: {chunk_count}")
            
            if chunk_count > 0:
                result = await db.execute(text("""
                    SELECT COUNT(*) FROM document_chunks
                    WHERE is_remote = TRUE
                """))
                remote_count = result.scalar()
                print(f"  Remote chunks (GitHub): {remote_count}")
            
            print()
            print("=" * 60)
            print(f"Summary: {repo_count} repos, {resource_count} resources, {chunk_count} chunks")
            print("=" * 60)
            
        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()
        finally:
            break

if __name__ == "__main__":
    asyncio.run(check_data())
