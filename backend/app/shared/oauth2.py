"""OAuth2 provider integration for third-party authentication.

This module provides OAuth2 authorization code flow support for
Google and GitHub authentication providers.

Uses circuit breaker pattern for resilience against OAuth provider outages.

Related files:
- app/shared/circuit_breaker.py: Circuit breaker implementation
"""

import logging
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# Circuit breaker for OAuth resilience using circuitbreaker library
try:
    from circuitbreaker import circuit, CircuitBreakerError

    CIRCUIT_BREAKER_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    CIRCUIT_BREAKER_AVAILABLE = False
    CircuitBreakerError = Exception

    # Provide a no-op decorator so @circuit(...) doesn't raise NameError
    def circuit(**kwargs):
        def decorator(func):
            return func

        return decorator

    logger.warning(
        "Circuit breaker not available (circuitbreaker not installed) - OAuth will work without resilience patterns"
    )


class OAuth2Provider:
    """Base class for OAuth2 provider integration.

    Implements the OAuth2 authorization code flow pattern:
    1. Generate authorization URL for user consent
    2. Exchange authorization code for access token
    3. Retrieve user information using access token
    """

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        """Initialize OAuth2 provider.

        Args:
            client_id: OAuth2 client ID from provider
            client_secret: OAuth2 client secret from provider
            redirect_uri: Callback URL for authorization code
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    async def get_authorization_url(self, state: str) -> str:
        """Get OAuth2 authorization URL for user consent.

        Args:
            state: Random state token for CSRF protection

        Returns:
            Authorization URL to redirect user to

        Raises:
            NotImplementedError: Must be implemented by subclass
        """
        raise NotImplementedError("Subclass must implement get_authorization_url")

    async def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth2 callback

        Returns:
            Token response containing access_token and other fields

        Raises:
            NotImplementedError: Must be implemented by subclass
        """
        raise NotImplementedError("Subclass must implement exchange_code_for_token")

    async def get_user_info(self, access_token: str) -> dict:
        """Get user information from provider using access token.

        Args:
            access_token: OAuth2 access token

        Returns:
            User information dictionary with provider-specific fields

        Raises:
            NotImplementedError: Must be implemented by subclass
        """
        raise NotImplementedError("Subclass must implement get_user_info")


class GoogleOAuth2Provider(OAuth2Provider):
    """Google OAuth2 provider implementation.

    Implements Google's OAuth2 authorization code flow for
    obtaining user email and profile information.
    """

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USER_INFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    async def get_authorization_url(self, state: str) -> str:
        """Get Google OAuth2 authorization URL.

        Args:
            state: Random state token for CSRF protection

        Returns:
            Google authorization URL with required parameters
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        auth_url = f"{self.AUTH_URL}?{urlencode(params)}"

        logger.info(f"Generated Google authorization URL for state: {state}")
        return auth_url

    @circuit(failure_threshold=3, recovery_timeout=120)
    async def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for Google access token.

        Args:
            code: Authorization code from Google callback

        Returns:
            Token response with access_token, refresh_token, etc.

        Raises:
            HTTPException: If token exchange fails or circuit breaker is open
        """
        try:
            # Log the redirect URI being used (for debugging)
            logger.info(f"Google token exchange - redirect_uri: {self.redirect_uri}")
            logger.info(f"Google token exchange - client_id: {self.client_id[:20]}...")
            logger.info(f"Google token exchange - code: {code[:20]}...")

            async with httpx.AsyncClient(timeout=15.0) as client:
                request_data = {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.redirect_uri,
                }

                response = await client.post(
                    self.TOKEN_URL,
                    data=request_data,
                    headers={"Accept": "application/json"},
                )

                if response.status_code != 200:
                    logger.error(
                        f"Google token exchange failed: {response.status_code} - {response.text}"
                    )
                    logger.error(f"Request redirect_uri was: {self.redirect_uri}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to exchange code for token",
                    )

                token_data = response.json()
                logger.info(
                    "Successfully exchanged Google authorization code for token"
                )
                return token_data

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during Google token exchange: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to communicate with Google OAuth2 service",
            )

    async def get_user_info(self, access_token: str) -> dict:
        """Get user information from Google.

        Args:
            access_token: Google OAuth2 access token

        Returns:
            User info with id, email, name, picture, etc.

        Raises:
            HTTPException: If user info retrieval fails
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    self.USER_INFO_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )

                if response.status_code != 200:
                    logger.error(
                        f"Google user info retrieval failed: {response.status_code} - {response.text}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to get user info",
                    )

                user_info = response.json()
                logger.info(
                    f"Successfully retrieved Google user info for: {user_info.get('email', 'unknown')}"
                )
                return user_info

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during Google user info retrieval: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to communicate with Google OAuth2 service",
            )


class GitHubOAuth2Provider(OAuth2Provider):
    """GitHub OAuth2 provider implementation.

    Implements GitHub's OAuth2 authorization code flow for
    obtaining user profile and email information.
    """

    AUTH_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USER_INFO_URL = "https://api.github.com/user"
    USER_EMAIL_URL = "https://api.github.com/user/emails"

    async def get_authorization_url(self, state: str) -> str:
        """Get GitHub OAuth2 authorization URL.

        Args:
            state: Random state token for CSRF protection

        Returns:
            GitHub authorization URL with required parameters
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "user:email",
            "state": state,
        }
        auth_url = f"{self.AUTH_URL}?{urlencode(params)}"

        logger.info(f"Generated GitHub authorization URL for state: {state}")
        return auth_url

    @circuit(failure_threshold=3, recovery_timeout=120)
    async def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for GitHub access token.

        Args:
            code: Authorization code from GitHub callback

        Returns:
            Token response with access_token

        Raises:
            HTTPException: If token exchange fails or circuit breaker is open
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    self.TOKEN_URL,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "code": code,
                        "redirect_uri": self.redirect_uri,
                    },
                    headers={"Accept": "application/json"},
                )

                if response.status_code != 200:
                    logger.error(
                        f"GitHub token exchange failed: {response.status_code} - {response.text}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to exchange code for token",
                    )

                token_data = response.json()

                # Check for error in response
                if "error" in token_data:
                    logger.error(
                        f"GitHub token exchange error: {token_data.get('error_description', token_data['error'])}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"GitHub OAuth2 error: {token_data.get('error_description', token_data['error'])}",
                    )

                logger.info(
                    "Successfully exchanged GitHub authorization code for token"
                )
                return token_data

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during GitHub token exchange: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to communicate with GitHub OAuth2 service",
            )

    async def get_user_info(self, access_token: str) -> dict:
        """Get user information from GitHub.

        Args:
            access_token: GitHub OAuth2 access token

        Returns:
            User info with id, login, email, name, etc.

        Raises:
            HTTPException: If user info retrieval fails
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Get user profile
                profile_response = await client.get(
                    self.USER_INFO_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )

                if profile_response.status_code != 200:
                    logger.error(
                        f"GitHub user info retrieval failed: {profile_response.status_code} - {profile_response.text}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to get user info",
                    )

                user_info = profile_response.json()

                # Get user emails if email is not public
                if not user_info.get("email"):
                    email_response = await client.get(
                        self.USER_EMAIL_URL,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Accept": "application/vnd.github.v3+json",
                        },
                    )

                    if email_response.status_code == 200:
                        emails = email_response.json()
                        # Find primary verified email
                        primary_email = next(
                            (
                                e["email"]
                                for e in emails
                                if e.get("primary") and e.get("verified")
                            ),
                            None,
                        )
                        if primary_email:
                            user_info["email"] = primary_email

                logger.info(
                    f"Successfully retrieved GitHub user info for: {user_info.get('login', 'unknown')}"
                )
                return user_info

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during GitHub user info retrieval: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to communicate with GitHub API",
            )
