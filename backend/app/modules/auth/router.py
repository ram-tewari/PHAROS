"""Authentication router for Neo Alexandria 2.0.

This module provides REST API endpoints for authentication, including:
- OAuth2 password flow login
- Token refresh
- Logout
- OAuth2 Google and GitHub flows
- User info and rate limit status
"""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.security import OAuth2PasswordRequestForm
from starlette.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.database import get_db
from ...shared.security import (
    get_current_user,
    TokenData,
    oauth2_scheme,
    revoke_token,
    decode_token,
    validate_token_type,
    validate_redirect_url,
)
from ...shared.cache import cache
from ...config.settings import get_settings
from .schema import (
    TokenResponse,
    RefreshTokenRequest,
    OAuth2AuthorizationResponse,
    UserInfoResponse,
    RateLimitInfo,
)
from .service import (
    authenticate_user,
    get_user_by_id,
    get_or_create_oauth_user,
    get_google_provider,
    get_github_provider,
    generate_state_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


# ============================================================================
# Auth Rate Limiting
# ============================================================================

# Auth-specific rate limits
AUTH_LOGIN_RATE_LIMIT = 5  # 5 attempts per 15 minutes
AUTH_LOGIN_WINDOW = 15 * 60  # 15 minutes in seconds
AUTH_REFRESH_RATE_LIMIT = 10  # 10 attempts per hour
AUTH_REFRESH_WINDOW = 60 * 60  # 1 hour in seconds


async def check_auth_login_rate_limit(request: Request) -> None:
    """Check rate limit for /auth/login endpoint.

    Rate limit: 5 attempts per 15 minutes per IP address.

    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    client_ip = request.client.host if request.client else "unknown"
    window_key = f"auth_login_rate_limit:{client_ip}"

    try:
        from ...shared.cache import RedisCache

        cache = RedisCache()

        # Get current count
        current = cache.redis.get(window_key)
        count = int(current) if current else 0

        if count >= AUTH_LOGIN_RATE_LIMIT:
            # Rate limit exceeded
            ttl = cache.redis.ttl(window_key)
            reset_time = int(time.time()) + ttl

            logger.warning(
                f"Auth login rate limit exceeded for IP {client_ip}: "
                f"{count}/{AUTH_LOGIN_RATE_LIMIT} attempts"
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Please try again in 15 minutes.",
                headers={
                    "Retry-After": str(ttl),
                    "X-RateLimit-Limit": str(AUTH_LOGIN_RATE_LIMIT),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                },
            )

        # Increment counter
        pipe = cache.redis.pipeline()
        pipe.incr(window_key)
        pipe.expire(window_key, AUTH_LOGIN_WINDOW)
        pipe.execute()

    except HTTPException:
        raise
    except Exception as e:
        # Fail open - allow request if Redis is unavailable
        logger.warning(f"Auth rate limit check failed: {e}")
        return


async def check_auth_refresh_rate_limit(request: Request) -> None:
    """Check rate limit for /auth/refresh endpoint.

    Rate limit: 10 attempts per hour per IP address.

    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    client_ip = request.client.host if request.client else "unknown"
    window_key = f"auth_refresh_rate_limit:{client_ip}"

    try:
        from ...shared.cache import RedisCache

        cache = RedisCache()

        # Get current count
        current = cache.redis.get(window_key)
        count = int(current) if current else 0

        if count >= AUTH_REFRESH_RATE_LIMIT:
            # Rate limit exceeded
            ttl = cache.redis.ttl(window_key)
            reset_time = int(time.time()) + ttl

            logger.warning(
                f"Auth refresh rate limit exceeded for IP {client_ip}: "
                f"{count}/{AUTH_REFRESH_RATE_LIMIT} attempts"
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many token refresh attempts. Please try again in 1 hour.",
                headers={
                    "Retry-After": str(ttl),
                    "X-RateLimit-Limit": str(AUTH_REFRESH_RATE_LIMIT),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                },
            )

        # Increment counter
        pipe = cache.redis.pipeline()
        pipe.incr(window_key)
        pipe.expire(window_key, AUTH_REFRESH_WINDOW)
        pipe.execute()

    except HTTPException:
        raise
    except Exception as e:
        # Fail open - allow request if Redis is unavailable
        logger.warning(f"Auth refresh rate limit check failed: {e}")
        return


# ============================================================================
# OAuth2 Password Flow Endpoints
# ============================================================================


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db),
):
    """OAuth2 password flow login.

    Authenticates user with username/email and password, returns JWT tokens.
    Rate limited to 5 attempts per 15 minutes per IP address.

    Args:
        request: FastAPI request object (for rate limiting)
        form_data: OAuth2 password request form (username, password, scopes)
        db: Database session

    Returns:
        TokenResponse with access_token and refresh_token

    Raises:
        HTTPException: 401 if authentication fails
        HTTPException: 429 if rate limit exceeded
    """
    # Check rate limit
    await check_auth_login_rate_limit(request)
    # Authenticate user
    user = await authenticate_user(db, form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create tokens
    from ...shared.security import create_access_token, create_refresh_token

    access_token = create_access_token(
        data={
            "user_id": str(user.id),  # Convert UUID to string
            "username": user.username,
            "tier": user.tier,
            "scopes": form_data.scopes,
        }
    )

    refresh_token = create_refresh_token(
        data={
            "user_id": str(user.id),  # Convert UUID to string
            "username": user.username,
        }
    )

    logger.info(f"User logged in: {user.username}")

    return TokenResponse(
        access_token=access_token, refresh_token=refresh_token, token_type="bearer"
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_endpoint(
    request: Request,
    refresh_request: RefreshTokenRequest,
):
    """Refresh access token using refresh token.
    Rate limited to 10 attempts per hour per IP address.

    Args:
        request: FastAPI request object (for rate limiting)
        refresh_request: Request containing refresh token

    Returns:
        TokenResponse with new access_token and same refresh_token

    Raises:
        HTTPException: 401 if refresh token is invalid or expired
        HTTPException: 429 if rate limit exceeded
    """
    # Check rate limit
    await check_auth_refresh_rate_limit(request)
    try:
        # Decode and validate refresh token
        payload = decode_token(refresh_request.refresh_token)

        # Validate token type
        if not validate_token_type(payload, "refresh"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type"
            )

        # Create new access token
        from ...shared.security import create_access_token

        access_token = create_access_token(
            data={
                "user_id": payload["user_id"],
                "username": payload["username"],
                "tier": payload.get("tier", "free"),
                "scopes": payload.get("scopes", []),
            }
        )

        logger.info(f"Token refreshed for user: {payload['username']}")

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_request.refresh_token,
            token_type="bearer",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )


@router.post("/logout")
async def logout(
    current_user: TokenData = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    """Logout and revoke current access token.

    Args:
        current_user: Current authenticated user
        token: Current access token

    Returns:
        Success message
    """
    await revoke_token(token)
    logger.info(f"User logged out: {current_user.username}")

    return {"message": "Successfully logged out"}


# ============================================================================
# OAuth2 Google Endpoints
# ============================================================================


@router.get("/google", response_model=OAuth2AuthorizationResponse)
async def google_login():
    """Initiate Google OAuth2 authorization flow.

    Returns:
        OAuth2AuthorizationResponse with authorization URL and state token

    Raises:
        HTTPException: 501 if Google OAuth2 is not configured
    """
    provider = get_google_provider()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth2 not configured",
        )

    state = generate_state_token()
    auth_url = await provider.get_authorization_url(state)

    logger.info(f"Google OAuth2 flow initiated with state: {state}")

    return OAuth2AuthorizationResponse(authorization_url=auth_url, state=state)


@router.get("/google/callback", response_model=TokenResponse)
async def google_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State token for CSRF protection"),
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth2 callback.

    Exchanges authorization code for access token, retrieves user info,
    creates or links user account, and returns JWT tokens.

    Args:
        code: Authorization code from Google
        state: State token for CSRF protection
        db: Database session

    Returns:
        TokenResponse with JWT access_token and refresh_token

    Raises:
        HTTPException: 400 if code exchange or user info retrieval fails
    """
    provider = get_google_provider()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth2 not configured",
        )

    # Exchange code for token
    token_data = await provider.exchange_code_for_token(code)

    # Get user info
    user_info = await provider.get_user_info(token_data["access_token"])

    # Create or get user
    user = await get_or_create_oauth_user(
        db=db,
        provider="google",
        provider_user_id=user_info["id"],
        email=user_info["email"],
        username=user_info.get("name", user_info["email"]),
    )

    # Create JWT tokens
    from ...shared.security import create_access_token, create_refresh_token

    access_token = create_access_token(
        data={
            "user_id": str(user.id),
            "username": user.username,
            "tier": user.tier,
            "scopes": [],
        }
    )

    refresh_token = create_refresh_token(
        data={"user_id": str(user.id), "username": user.username}
    )

    logger.info(f"Google OAuth2 login successful for user: {user.username}")

    # Validate redirect URL before redirecting
    settings = get_settings()
    frontend_callback_url = f"{settings.FRONTEND_URL}/auth/callback"
    try:
        validate_redirect_url(frontend_callback_url)
    except ValueError as e:
        logger.error(f"Redirect URL validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid redirect URL: {str(e)}",
        )

    # Redirect to frontend callback with tokens in HTTP-only cookie
    response = RedirectResponse(url=frontend_callback_url)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.ENV == "prod",
        samesite="lax",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.ENV == "prod",
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )
    return response


# ============================================================================
# OAuth2 GitHub Endpoints
# ============================================================================


@router.get("/github", response_model=OAuth2AuthorizationResponse)
async def github_login():
    """Initiate GitHub OAuth2 authorization flow.

    Returns:
        OAuth2AuthorizationResponse with authorization URL and state token

    Raises:
        HTTPException: 501 if GitHub OAuth2 is not configured
    """
    provider = get_github_provider()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GitHub OAuth2 not configured",
        )

    state = generate_state_token()
    auth_url = await provider.get_authorization_url(state)

    logger.info(f"GitHub OAuth2 flow initiated with state: {state}")

    return OAuth2AuthorizationResponse(authorization_url=auth_url, state=state)


@router.get("/github/callback", response_model=TokenResponse)
async def github_callback(
    code: str = Query(..., description="Authorization code from GitHub"),
    state: str = Query(..., description="State token for CSRF protection"),
    db: AsyncSession = Depends(get_db),
):
    """Handle GitHub OAuth2 callback.

    Exchanges authorization code for access token, retrieves user info,
    creates or links user account, and returns JWT tokens.

    Args:
        code: Authorization code from GitHub
        state: State token for CSRF protection
        db: Database session

    Returns:
        TokenResponse with JWT access_token and refresh_token

    Raises:
        HTTPException: 400 if code exchange or user info retrieval fails
    """
    provider = get_github_provider()

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GitHub OAuth2 not configured",
        )

    # Exchange code for token
    token_data = await provider.exchange_code_for_token(code)

    # Get user info
    user_info = await provider.get_user_info(token_data["access_token"])

    # Create or get user
    user = await get_or_create_oauth_user(
        db=db,
        provider="github",
        provider_user_id=str(user_info["id"]),
        email=user_info.get("email", f"{user_info['login']}@github.local"),
        username=user_info["login"],
    )

    # Create JWT tokens
    from ...shared.security import create_access_token, create_refresh_token

    access_token = create_access_token(
        data={
            "user_id": str(user.id),
            "username": user.username,
            "tier": user.tier,
            "scopes": [],
        }
    )

    refresh_token = create_refresh_token(
        data={"user_id": str(user.id), "username": user.username}
    )

    logger.info(f"GitHub OAuth2 login successful for user: {user.username}")

    # Validate redirect URL before redirecting
    settings = get_settings()
    frontend_callback_url = f"{settings.FRONTEND_URL}/auth/callback"
    try:
        validate_redirect_url(frontend_callback_url)
    except ValueError as e:
        logger.error(f"Redirect URL validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid redirect URL: {str(e)}",
        )

    # Redirect to frontend callback with tokens in HTTP-only cookie
    response = RedirectResponse(url=frontend_callback_url)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.ENV == "prod",
        samesite="lax",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.ENV == "prod",
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )
    return response


# ============================================================================
# User Info and Rate Limit Endpoints
# ============================================================================


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user information.

    Args:
        current_user: Current authenticated user from token
        db: Database session

    Returns:
        UserInfoResponse with user details

    Raises:
        HTTPException: 404 if user not found
    """
    user = await get_user_by_id(db, current_user.user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return UserInfoResponse(
        id=str(user.id),  # Convert UUID to string
        username=user.username,
        email=user.email,
        tier=user.tier,
        is_active=user.is_active,
    )


@router.get("/rate-limit", response_model=RateLimitInfo)
async def get_rate_limit_status(current_user: TokenData = Depends(get_current_user)):
    """Get current rate limit status for authenticated user.

    Args:
        current_user: Current authenticated user from token

    Returns:
        RateLimitInfo with limit, remaining, reset, and tier
    """
    settings = get_settings()

    # Determine rate limit based on tier
    if current_user.tier == "admin":
        limit = 0  # Unlimited
    elif current_user.tier == "premium":
        limit = settings.RATE_LIMIT_PREMIUM_TIER
    else:
        limit = settings.RATE_LIMIT_FREE_TIER

    # Get current usage from Redis
    window_key = f"rate_limit:{current_user.user_id}:{int(time.time() // 60)}"

    try:
        current = cache.get(window_key) or 0
        remaining = max(0, limit - current) if limit > 0 else 0
        reset = int(time.time() // 60 + 1) * 60
    except Exception as e:
        logger.warning(f"Error getting rate limit status: {e}")
        # Return default values if Redis unavailable
        remaining = limit if limit > 0 else 0
        reset = int(time.time() // 60 + 1) * 60

    return RateLimitInfo(
        limit=limit, remaining=remaining, reset=reset, tier=current_user.tier
    )


# ============================================================================
# Health Check Endpoint
# ============================================================================


@router.get("/health")
async def health_check():
    """Health check endpoint for auth module.

    Returns:
        Health status of auth module
    """
    return {"status": "healthy", "module": "authentication", "timestamp": time.time()}
