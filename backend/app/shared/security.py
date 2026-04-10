"""
Shared Security Components

Provides reusable security dependencies for API authentication.
Part of the shared kernel - can be imported by any module.

Phase 5: M2M API Key Authentication for Ronin Integration
"""

import logging
import os
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

# API Key header scheme
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


def get_pharos_api_key() -> str:
    """
    Get the Pharos API key from environment variable.

    Returns:
        str: The API key

    Raises:
        RuntimeError: If PHAROS_API_KEY is not set
    """
    api_key = os.environ.get("PHAROS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "PHAROS_API_KEY environment variable is not set. "
            "This is required for M2M authentication."
        )
    return api_key


async def verify_api_key(
    authorization: Optional[str] = Security(api_key_header),
) -> str:
    """
    Verify API key for M2M (Machine-to-Machine) authentication.

    This dependency validates the API key from the Authorization header.
    Supports both raw keys and Bearer token format.

    Args:
        authorization: Authorization header value (injected by FastAPI)

    Returns:
        str: The validated API key

    Raises:
        HTTPException: 403 Forbidden if key is missing or invalid

    Usage:
        ```python
        @router.post("/protected")
        async def protected_endpoint(
            api_key: str = Depends(verify_api_key)
        ):
            # Endpoint logic here
            pass
        ```

    Security Notes:
        - Uses constant-time comparison to prevent timing attacks
        - Logs authentication failures for security monitoring
        - Returns 403 (not 401) to indicate authorization failure
        - Strips "Bearer " prefix if present for flexibility
    """
    # Check if authorization header is present
    if not authorization:
        logger.warning(
            "API key authentication failed: Missing Authorization header"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing API key. Include 'Authorization: Bearer <key>' header.",
        )

    # Strip "Bearer " prefix if present (case-insensitive)
    api_key = authorization
    if authorization.lower().startswith("bearer "):
        api_key = authorization[7:].strip()  # Remove "Bearer " prefix

    # Validate against environment variable
    try:
        expected_key = get_pharos_api_key()
    except RuntimeError as e:
        logger.error(f"API key validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error. Contact administrator.",
        )

    # Constant-time comparison to prevent timing attacks
    if not _constant_time_compare(api_key, expected_key):
        logger.warning(
            f"API key authentication failed: Invalid key provided "
            f"(length: {len(api_key)}, expected: {len(expected_key)})"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key. Access denied.",
        )

    # Log successful authentication (without exposing the key)
    logger.info(
        f"API key authentication successful (key length: {len(api_key)})"
    )

    return api_key


def _constant_time_compare(a: str, b: str) -> bool:
    """
    Compare two strings in constant time to prevent timing attacks.

    This is critical for security - we don't want attackers to be able
    to determine the correct key by measuring response times.

    Args:
        a: First string
        b: Second string

    Returns:
        bool: True if strings are equal, False otherwise
    """
    # Use secrets.compare_digest for constant-time comparison
    import secrets

    return secrets.compare_digest(a, b)


# ============================================================================
# Optional: API Key Validation for Testing
# ============================================================================


def is_valid_api_key(api_key: str) -> bool:
    """
    Check if an API key is valid (for testing purposes).

    Args:
        api_key: API key to validate

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        expected_key = get_pharos_api_key()
        return _constant_time_compare(api_key, expected_key)
    except RuntimeError:
        return False


# ============================================================================
# Optional: Development/Testing Bypass
# ============================================================================


async def verify_api_key_optional(
    authorization: Optional[str] = Security(api_key_header),
) -> Optional[str]:
    """
    Optional API key verification for development/testing.

    This variant allows requests without API keys in development mode.
    Use only for non-production endpoints or testing.

    Args:
        authorization: Authorization header value (injected by FastAPI)

    Returns:
        Optional[str]: The validated API key, or None if not provided

    Raises:
        HTTPException: 403 Forbidden if key is provided but invalid
    """
    # Allow missing key in development
    if not authorization:
        logger.debug("API key not provided (optional mode)")
        return None

    # If key is provided, validate it
    return await verify_api_key(authorization)
