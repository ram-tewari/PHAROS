"""
Create an admin token for testing the frontend with the production backend.

This script generates a long-lived JWT token for an admin user that can be used
to test the frontend without going through the OAuth flow.

Usage:
    python backend/scripts/create_admin_token.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from jose import jwt

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.config.settings import get_settings


def create_admin_token(days_valid: int = 30) -> str:
    """Create a long-lived admin token.

    Args:
        days_valid: Number of days the token should be valid (default: 30)

    Returns:
        JWT token string
    """
    settings = get_settings()

    # Admin user data
    admin_email = "admin@neoalexandria.dev"

    # Token expiration
    expire = datetime.utcnow() + timedelta(days=days_valid)

    # Token payload
    payload = {
        "sub": admin_email,
        "exp": expire,
        "type": "access",
        "tier": "admin",
        "is_premium": True,
    }

    # Generate token
    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )

    return token


def main():
    """Generate and display admin token."""
    print("=" * 80)
    print("Neo Alexandria Admin Token Generator")
    print("=" * 80)
    print()

    # Generate token
    token = create_admin_token(days_valid=30)

    print("✅ Admin token generated successfully!")
    print()
    print("Token Details:")
    print(f"  - Email: admin@neoalexandria.dev")
    print(f"  - Tier: admin")
    print(f"  - Valid for: 30 days")
    print()
    print("=" * 80)
    print("TOKEN (copy this):")
    print("=" * 80)
    print(token)
    print("=" * 80)
    print()
    print("To use this token in the frontend:")
    print()
    print("1. Open browser console (F12)")
    print("2. Paste this command:")
    print()
    print(f"localStorage.setItem('access_token', '{token}');")
    print("localStorage.setItem('refresh_token', 'admin-refresh-token');")
    print()
    print("3. Refresh the page")
    print()
    print("=" * 80)
    print()
    print("Or add to frontend/.env.local:")
    print()
    print(f"VITE_ADMIN_TOKEN={token}")
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
