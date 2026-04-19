"""
Create repositories table in production database.

This script manually creates the repositories table without using Alembic,
since we need to fix the production database immediately.
"""

import os
import asyncio
from sqlalchemy import text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def create_repositories_table():
    """Create repositories table in production database."""
    from app.shared.database import init_database, get_db
    
    # Initialize database first
    init_database()
    
    print("[MIGRATION] Creating repositories table...")
    
    async for db in get_db():
        try:
            # Check if table already exists
            result = await db.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'repositories'
                )
            """))
            exists = result.scalar()
            
            if exists:
                print("[OK] Table 'repositories' already exists")
                return
            
            # Create table
            await db.execute(text("""
                CREATE TABLE repositories (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    url VARCHAR(2048) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    metadata JSONB NOT NULL,
                    total_files INTEGER NOT NULL DEFAULT 0,
                    total_lines INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Create indexes
            await db.execute(text("""
                CREATE UNIQUE INDEX idx_repository_url ON repositories(url)
            """))
            
            await db.execute(text("""
                CREATE INDEX idx_repository_name ON repositories(name)
            """))
            
            await db.execute(text("""
                CREATE INDEX idx_repository_created ON repositories(created_at)
            """))
            
            await db.commit()
            
            print("[OK] Table 'repositories' created successfully")
            print("[OK] Indexes created: idx_repository_url, idx_repository_name, idx_repository_created")
            
        except Exception as e:
            print(f"[ERROR] Failed to create table: {e}")
            await db.rollback()
            raise
        finally:
            break


if __name__ == "__main__":
    print("=" * 60)
    print("Create Repositories Table")
    print("=" * 60)
    print()
    
    asyncio.run(create_repositories_table())
    
    print()
    print("=" * 60)
    print("Migration Complete")
    print("=" * 60)
