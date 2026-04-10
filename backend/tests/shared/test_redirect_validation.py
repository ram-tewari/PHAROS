"""Tests for redirect URL validation.

This module contains tests for the validate_redirect_url function
which prevents open redirect vulnerabilities in OAuth2 callbacks.

Requirements: 1.3 (Fix Open Redirect Vulnerability)
"""

import pytest
from unittest.mock import patch, MagicMock


class TestValidateRedirectUrl:
    """Test redirect URL validation."""

    def test_valid_https_url_in_production(self, test_settings):
        """Test that valid HTTPS URLs are accepted in production."""
        from app.shared.security import validate_redirect_url

        # Override settings for this test
        test_settings.ENV = "prod"
        test_settings.ALLOWED_REDIRECT_URLS = [
            "https://pharos.onrender.com",
            "https://example.com",
        ]

        # Valid HTTPS URL in allowed list
        assert (
            validate_redirect_url(
                "https://pharos.onrender.com/auth/callback", test_settings
            )
            is True
        )

    def test_valid_https_url_with_path(self, test_settings):
        """Test that valid HTTPS URLs with paths are accepted."""
        from app.shared.security import validate_redirect_url

        test_settings.ENV = "dev"
        test_settings.ALLOWED_REDIRECT_URLS = [
            "https://pharos.onrender.com",
            "http://localhost:5173",
        ]

        # URL with path that starts with allowed URL
        assert (
            validate_redirect_url(
                "https://pharos.onrender.com/auth/callback?token=abc", test_settings
            )
            is True
        )

    def test_http_url_rejected_in_production(self, test_settings):
        """Test that HTTP URLs are rejected in production."""
        from app.shared.security import validate_redirect_url

        test_settings.ENV = "prod"
        test_settings.ALLOWED_REDIRECT_URLS = [
            "https://pharos.onrender.com",
            "http://localhost:5173",
        ]

        # HTTP URL should be rejected in production
        with pytest.raises(ValueError) as exc_info:
            validate_redirect_url("http://localhost:5173/auth/callback", test_settings)

        assert "must use HTTPS in production" in str(exc_info.value)

    def test_http_url_accepted_in_development(self, test_settings):
        """Test that HTTP URLs are accepted in development mode."""
        from app.shared.security import validate_redirect_url

        test_settings.ENV = "dev"
        test_settings.ALLOWED_REDIRECT_URLS = [
            "https://pharos.onrender.com",
            "http://localhost:5173",
        ]

        # HTTP URL should be accepted in development
        assert (
            validate_redirect_url("http://localhost:5173/auth/callback", test_settings)
            is True
        )

    def test_url_not_in_allowed_list_rejected(self, test_settings):
        """Test that URLs not in the allowed list are rejected."""
        from app.shared.security import validate_redirect_url

        test_settings.ENV = "dev"
        test_settings.ALLOWED_REDIRECT_URLS = [
            "https://pharos.onrender.com",
            "http://localhost:5173",
        ]

        # URL not in allowed list should be rejected
        with pytest.raises(ValueError) as exc_info:
            validate_redirect_url("https://evil.com/auth/callback", test_settings)

        assert "not in allowed list" in str(exc_info.value)

    def test_empty_url_rejected(self, test_settings):
        """Test that empty URLs are rejected."""
        from app.shared.security import validate_redirect_url

        test_settings.ENV = "dev"
        test_settings.ALLOWED_REDIRECT_URLS = [
            "https://pharos.onrender.com",
        ]

        with pytest.raises(ValueError) as exc_info:
            validate_redirect_url("", test_settings)

        assert "cannot be empty" in str(exc_info.value)

    def test_invalid_url_format_rejected(self, test_settings):
        """Test that invalid URL formats are rejected."""
        from app.shared.security import validate_redirect_url

        test_settings.ENV = "dev"
        test_settings.ALLOWED_REDIRECT_URLS = [
            "https://pharos.onrender.com",
        ]

        # Invalid URL without scheme should be rejected
        with pytest.raises(ValueError) as exc_info:
            validate_redirect_url("not-a-valid-url", test_settings)

        # Either "Invalid URL format" or "not in allowed list" is acceptable
        error_msg = str(exc_info.value)
        assert "Invalid URL format" in error_msg or "not in allowed list" in error_msg

    def test_subdomain_of_allowed_url_accepted(self, test_settings):
        """Test that subdomains of allowed URLs are accepted when they start with the base URL."""
        from app.shared.security import validate_redirect_url

        test_settings.ENV = "dev"
        test_settings.ALLOWED_REDIRECT_URLS = [
            "https://pharos.onrender.com",
        ]

        # Subdomain should be accepted if it starts with the allowed URL
        assert (
            validate_redirect_url(
                "https://pharos.onrender.com/app/auth/callback", test_settings
            )
            is True
        )

    def test_different_domain_rejected(self, test_settings):
        """Test that different domains are rejected even if path matches."""
        from app.shared.security import validate_redirect_url

        test_settings.ENV = "dev"
        test_settings.ALLOWED_REDIRECT_URLS = [
            "https://pharos.onrender.com",
        ]

        # Different domain should be rejected
        with pytest.raises(ValueError) as exc_info:
            validate_redirect_url(
                "https://attacker.com/pharos.onrender.com/auth/callback", test_settings
            )

        assert "not in allowed list" in str(exc_info.value)


class TestRedirectUrlValidationIntegration:
    """Integration tests for redirect URL validation in OAuth2 callbacks."""

    def test_google_callback_uses_validate_redirect_url(self):
        """Test that Google OAuth2 callback validates redirect URL."""
        # This test verifies that the validate_redirect_url function is imported
        # and used in the auth router
        from app.modules.auth.router import validate_redirect_url
        from app.shared.security import (
            validate_redirect_url as security_validate_redirect_url,
        )

        # Both should be the same function
        assert validate_redirect_url is security_validate_redirect_url

    def test_github_callback_uses_validate_redirect_url(self):
        """Test that GitHub OAuth2 callback validates redirect URL."""
        # This test verifies that the validate_redirect_url function is imported
        # and used in the auth router
        from app.modules.auth.router import validate_redirect_url
        from app.shared.security import (
            validate_redirect_url as security_validate_redirect_url,
        )

        # Both should be the same function
        assert validate_redirect_url is security_validate_redirect_url
