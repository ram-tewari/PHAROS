"""Initialize the database with all tables."""

import asyncio
from app.database.base import Base, async_engine
from app.database.models import *  # Import all models


async def init_db():
    """Create all tables."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database initialized successfully!")


if __name__ == "__main__":
    asyncio.run(init_db())
