"""Check repositories table for existing data."""

import asyncio
from sqlalchemy import text
from app.shared.database import init_database, get_db

async def check_repositories():
    """Check repositories table."""
    init_database()
    
    async for db in get_db():
        try:
            # Count repositories
            result = await db.execute(text("SELECT COUNT(*) FROM repositories"))
            count = result.scalar()
            print(f"[INFO] Found {count} repositories in database")
            
            if count > 0:
                # Show repositories
                result = await db.execute(text("""
                    SELECT id, name, url, total_files, total_lines, created_at
                    FROM repositories
                    ORDER BY created_at DESC
                    LIMIT 10
                """))
                
                print("\n[INFO] Recent repositories:")
                for row in result:
                    print(f"  - {row.name}: {row.total_files} files, {row.total_lines} lines")
                    print(f"    ID: {row.id}")
                    print(f"    URL: {row.url}")
                    print(f"    Created: {row.created_at}")
                    print()
            
        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()
        finally:
            break

if __name__ == "__main__":
    asyncio.run(check_repositories())
