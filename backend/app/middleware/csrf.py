"""
CSRF Protection Middleware for FastAPI

This module provides CSRF protection for the Pharos API by validating
Origin and Referer headers on state-changing requests.

Related files:
- app/__init__.py: Middleware registration
- app/config/settings.py: Configuration for allowed origins

CSRF Protection Strategy:
- Safe methods (GET, HEAD, OPTIONS) are exempt from CSRF checks
- State-changing methods (POST, PUT, DELETE, PATCH) require Origin/Referer validation
- Same-origin requests are automatically allowed
- Cross-origin requests are validated against allowed origins list
"""

import logging
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection middleware for FastAPI applications.

    This middleware validates the Origin and Referer headers on state-changing
    requests (POST, PUT, DELETE, PATCH) to prevent Cross-Site Request Forgery attacks.

    Security Features:
    - Validates Origin header for cross-origin requests
    - Falls back to Referer header if Origin is not present
    - Allows same-origin requests without header validation
    - Configurable allowed origins list
    - Exempts safe methods (GET, HEAD, OPTIONS) from validation

    Configuration:
    - ALLOWED_ORIGINS: List of allowed origin URLs for cross-origin requests
    - FRONTEND_URL: Default frontend URL added to allowed origins

    Examples:
        >>> # Add to FastAPI app
        >>> app.add_middleware(CSRFMiddleware)

        >>> # Configure allowed origins in settings
        >>> ALLOWED_ORIGINS = [
        ...     "http://localhost:5173",
        ...     "https://pharos.onrender.com",
        ... ]
    """

    # Safe methods that don't require CSRF validation
    SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

    # State-changing methods that require CSRF validation
    STATE_CHANGING_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

    def __init__(self, app, allowed_origins: list[str] | None = None):
        """
        Initialize the CSRF middleware.

        Args:
            app: The FastAPI application
            allowed_origins: Optional list of allowed origins. If None, uses settings.
        """
        super().__init__(app)
        self.allowed_origins = allowed_origins

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        """
        Process the request and validate CSRF tokens/headers.

        Args:
            request: The incoming request
            call_next: The next middleware/handler in the chain

        Returns:
            JSONResponse: The response from the next handler

        Raises:
            HTTPException: 403 if CSRF validation fails
        """
        # Skip CSRF validation for safe methods
        if request.method in self.SAFE_METHODS:
            return await call_next(request)

        # Get the origin header (primary) or referer (fallback)
        origin = request.headers.get("Origin") or request.headers.get("Referer")

        # For state-changing methods, validate the origin
        if request.method in self.STATE_CHANGING_METHODS:
            # Check if this is a same-origin request
            if self._is_same_origin(request, origin):
                # Same-origin request - no CSRF risk
                return await call_next(request)

            # Cross-origin request - validate against allowed origins
            if origin:
                if not self._is_allowed_origin(origin):
                    logger.warning(
                        f"CSRF validation failed: Invalid origin '{origin}' for "
                        f"{request.method} request to {request.url.path}"
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": "CSRF validation failed: Invalid or disallowed origin",
                            "error_code": "CSRF_ERROR",
                        },
                    )
            else:
                # Cross-origin request without Origin/Referer header
                # This is suspicious - reject it
                logger.warning(
                    f"CSRF validation failed: Missing Origin/Referer header for "
                    f"{request.method} request to {request.url.path}"
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "CSRF validation failed: Missing Origin or Referer header",
                        "error_code": "CSRF_ERROR",
                    },
                )

        return await call_next(request)

    def _is_same_origin(self, request: Request, origin: str | None) -> bool:
        """
        Check if the request is same-origin.

        A request is considered same-origin only if the Origin/Referer header
        is present and matches the request URL's origin. Absent headers on
        state-changing requests are treated as cross-origin so that callers
        without an Origin/Referer (curl, non-browser clients) are rejected.

        Args:
            request: The incoming request
            origin: The Origin or Referer header value

        Returns:
            bool: True if the request is same-origin
        """
        # No origin header - cannot confirm same-origin for state-changing requests
        if not origin:
            return False

        # Parse the request URL to get its origin
        request_origin = f"{request.url.scheme}://{request.url.netloc}"

        # Check if the origin matches the request URL
        return origin == request_origin or origin.startswith(request_origin)

    def _is_allowed_origin(self, origin: str) -> bool:
        """
        Check if the origin is in the allowed origins list.

        Args:
            origin: The origin URL to check

        Returns:
            bool: True if the origin is allowed
        """
        allowed_origins = self._get_allowed_origins()

        for allowed_origin in allowed_origins:
            # Exact match
            if origin == allowed_origin:
                return True

            # Prefix match (e.g., https://example.com matches https://example.com/path)
            if origin.startswith(allowed_origin.rstrip("/") + "/"):
                return True

            # Subdomain match (e.g., https://app.example.com matches https://*.example.com)
            if allowed_origin.startswith("*."):
                base_domain = allowed_origin[2:]  # Remove *.
                if origin.endswith(base_domain) or origin.startswith(
                    f"https://{base_domain}"
                ):
                    return True

        return False

    def _get_allowed_origins(self) -> list[str]:
        """
        Get the list of allowed origins.

        Returns:
            list[str]: List of allowed origin URLs
        """
        if self.allowed_origins is not None:
            return self.allowed_origins

        # Load from settings
        settings = get_settings()

        # Build allowed origins list
        allowed = []

        # Add FRONTEND_URL if set
        if settings.FRONTEND_URL:
            allowed.append(settings.FRONTEND_URL)

        # Add API URL if set
        if hasattr(settings, "API_URL") and settings.API_URL  # type: ignore[attr-defined]:
            allowed.append(settings.API_URL  # type: ignore[attr-defined])

        # Add localhost origins for development
        allowed.extend(
            [
                "http://localhost:3000",
                "http://localhost:5173",
                "http://localhost:8000",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:8000",
            ]
        )

        return allowed


def validate_csrf_origin(
    origin: str,
    allowed_origins: list[str] | None = None,
    frontend_url: str | None = None,
) -> tuple[bool, str]:
    """
    Validate an origin against the allowed origins list.

    This utility function can be used for programmatic CSRF validation,
    such as in API endpoints that need to validate custom origins.

    Args:
        origin: The origin URL to validate
        allowed_origins: Optional custom list of allowed origins
        frontend_url: Optional frontend URL to include in allowed origins

    Returns:
        tuple: (is_valid: bool, error_message: str)

    Examples:
        >>> validate_csrf_origin("https://pharos.onrender.com")
        (True, "")

        >>> validate_csrf_origin("https://evil.com")
        (False, "Origin not in allowed list")
    """
    if not origin:
        return False, "Origin cannot be empty"

    # Build allowed origins list (copy to avoid mutating caller's list)
    allowed = list(allowed_origins) if allowed_origins else []

    if frontend_url and frontend_url not in allowed:
        allowed.append(frontend_url)

    # Add localhost for development
    allowed.extend(
        [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8000",
        ]
    )

    # Check against allowed origins
    for allowed_origin in allowed:
        # Exact match
        if origin == allowed_origin:
            return True, ""

        # Prefix match
        if origin.startswith(allowed_origin.rstrip("/") + "/"):
            return True, ""

        # Subdomain match
        if allowed_origin.startswith("*."):
            base_domain = allowed_origin[2:]
            if origin.endswith(base_domain):
                return True, ""

    return False, f"Origin not in allowed list: {origin}"
