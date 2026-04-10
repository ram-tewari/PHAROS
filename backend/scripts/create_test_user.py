"""Create test user for authentication testing.

This script creates a test user in the database with known credentials
for testing password-based authentication.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.shared.database import get_db_session
from app.database.models import User
from app.shared.security import get_password_hash


async def create_test_user():
    """Create test user with known credentials."""

    # Test user credentials
    test_email = "test@example.com"
    test_username = "testuser"
    test_password = "testpassword123"

    print("Creating test user...")
    print(f"Email: {test_email}")
    print(f"Username: {test_username}")
    print(f"Password: {test_password}")
    print()

    async for db in get_db_session():
        try:
            # Check if user already exists
            stmt = select(User).where(User.email == test_email)
            result = await db.execute(stmt)
            existing_user = result.scalar_one_or_none()

            if existing_user:
                print(f"✅ Test user already exists with ID: {existing_user.id}")
                print(f"   Username: {existing_user.username}")
                print(f"   Email: {existing_user.email}")
                print(f"   Tier: {existing_user.tier}")
                print(f"   Active: {existing_user.is_active}")

                # Update password to ensure it's correct
                existing_user.hashed_password = get_password_hash(test_password)
                await db.commit()
                print(f"✅ Password updated for test user")
                return

            # Create new test user
            hashed_password = get_password_hash(test_password)

            test_user = User(
                username=test_username,
                email=test_email,
                hashed_password=hashed_password,
                tier="free",
                is_active=True,
            )

            db.add(test_user)
            await db.commit()
            await db.refresh(test_user)

            print(f"✅ Test user created successfully!")
            print(f"   ID: {test_user.id}")
            print(f"   Username: {test_user.username}")
            print(f"   Email: {test_user.email}")
            print(f"   Tier: {test_user.tier}")
            print(f"   Active: {test_user.is_active}")
            print()
            print("You can now login with:")
            print(f"   Email: {test_email}")
            print(f"   Password: {test_password}")

        except Exception as e:
            print(f"❌ Error creating test user: {e}")
            await db.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(create_test_user())
