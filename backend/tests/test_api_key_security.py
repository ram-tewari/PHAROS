"""
API Key Security Tests

Tests for M2M API Key Authentication on the context assembly endpoint.

Phase 5.1: Security Layer Testing
"""

import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.shared.security import (
    _constant_time_compare,
    get_pharos_api_key,
    is_valid_api_key,
    verify_api_key,
)

# Test API key
TEST_API_KEY = "test-pharos-api-key-12345"
INVALID_API_KEY = "wrong-api-key-67890"


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def mock_api_key():
    """Mock PHAROS_API_KEY environment variable"""
    with patch.dict(os.environ, {"PHAROS_API_KEY": TEST_API_KEY}):
        yield TEST_API_KEY


# ============================================================================
# Unit Tests: Security Utilities
# ============================================================================


class TestSecurityUtilities:
    """Test security utility functions"""

    def test_constant_time_compare_equal(self):
        """Test constant-time comparison with equal strings"""
        assert _constant_time_compare("secret123", "secret123") is True

    def test_constant_time_compare_not_equal(self):
        """Test constant-time comparison with different strings"""
        assert _constant_time_compare("secret123", "secret456") is False

    def test_constant_time_compare_different_lengths(self):
        """Test constant-time comparison with different length strings"""
        assert _constant_time_compare("short", "much_longer_string") is False

    def test_constant_time_compare_empty_strings(self):
        """Test constant-time comparison with empty strings"""
        assert _constant_time_compare("", "") is True
        assert _constant_time_compare("", "nonempty") is False

    def test_get_pharos_api_key_success(self, mock_api_key):
        """Test getting API key from environment"""
        api_key = get_pharos_api_key()
        assert api_key == TEST_API_KEY

    def test_get_pharos_api_key_missing(self):
        """Test getting API key when not set"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="PHAROS_API_KEY"):
                get_pharos_api_key()

    def test_is_valid_api_key_success(self, mock_api_key):
        """Test API key validation with correct key"""
        assert is_valid_api_key(TEST_API_KEY) is True

    def test_is_valid_api_key_failure(self, mock_api_key):
        """Test API key validation with incorrect key"""
        assert is_valid_api_key(INVALID_API_KEY) is False

    def test_is_valid_api_key_missing_env(self):
        """Test API key validation when env var not set"""
        with patch.dict(os.environ, {}, clear=True):
            assert is_valid_api_key(TEST_API_KEY) is False


# ============================================================================
# Unit Tests: verify_api_key Dependency
# ============================================================================


class TestVerifyApiKeyDependency:
    """Test the verify_api_key FastAPI dependency"""

    @pytest.mark.asyncio
    async def test_verify_api_key_success(self, mock_api_key):
        """Test successful API key verification"""
        result = await verify_api_key(authorization=TEST_API_KEY)
        assert result == TEST_API_KEY

    @pytest.mark.asyncio
    async def test_verify_api_key_with_bearer_prefix(self, mock_api_key):
        """Test API key verification with Bearer prefix"""
        result = await verify_api_key(authorization=f"Bearer {TEST_API_KEY}")
        assert result == TEST_API_KEY

    @pytest.mark.asyncio
    async def test_verify_api_key_with_bearer_lowercase(self, mock_api_key):
        """Test API key verification with lowercase bearer prefix"""
        result = await verify_api_key(authorization=f"bearer {TEST_API_KEY}")
        assert result == TEST_API_KEY

    @pytest.mark.asyncio
    async def test_verify_api_key_with_bearer_mixed_case(self, mock_api_key):
        """Test API key verification with mixed case Bearer prefix"""
        result = await verify_api_key(authorization=f"BeArEr {TEST_API_KEY}")
        assert result == TEST_API_KEY

    @pytest.mark.asyncio
    async def test_verify_api_key_missing_header(self, mock_api_key):
        """Test API key verification with missing Authorization header"""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(authorization=None)

        assert exc_info.value.status_code == 403
        assert "Missing API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_api_key_invalid_key(self, mock_api_key):
        """Test API key verification with invalid key"""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(authorization=INVALID_API_KEY)

        assert exc_info.value.status_code == 403
        assert "Invalid API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_api_key_invalid_key_with_bearer(self, mock_api_key):
        """Test API key verification with invalid key and Bearer prefix"""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(authorization=f"Bearer {INVALID_API_KEY}")

        assert exc_info.value.status_code == 403
        assert "Invalid API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_api_key_empty_string(self, mock_api_key):
        """Test API key verification with empty string"""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(authorization="")

        assert exc_info.value.status_code == 403
        assert "Invalid API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_api_key_only_bearer(self, mock_api_key):
        """Test API key verification with only 'Bearer' and no key"""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(authorization="Bearer ")

        assert exc_info.value.status_code == 403
        assert "Invalid API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_api_key_env_not_set(self):
        """Test API key verification when PHAROS_API_KEY not set"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(authorization=TEST_API_KEY)

            assert exc_info.value.status_code == 500
            assert "Server configuration error" in exc_info.value.detail


# ============================================================================
# Integration Tests: Context Retrieval Endpoint
# ============================================================================


class TestContextRetrievalSecurity:
    """Test security on the /api/mcp/context/retrieve endpoint"""

    @pytest.mark.asyncio
    async def test_valid_auth_success(self, client, mock_api_key):
        """Test context retrieval with valid API key"""
        response = client.post(
            "/api/mcp/context/retrieve",
            json={
                "query": "test query",
                "codebase": "test-repo",
                "max_code_chunks": 5,
            },
            headers={"Authorization": f"Bearer {TEST_API_KEY}"},
        )

        # Should succeed (200) or return empty results, not 403
        assert response.status_code != 403
        # May be 200 with empty results or other status depending on data
        # The key point is it's NOT forbidden

    @pytest.mark.asyncio
    async def test_valid_auth_without_bearer_prefix(self, client, mock_api_key):
        """Test context retrieval with valid API key without Bearer prefix"""
        response = client.post(
            "/api/mcp/context/retrieve",
            json={
                "query": "test query",
                "codebase": "test-repo",
                "max_code_chunks": 5,
            },
            headers={"Authorization": TEST_API_KEY},
        )

        # Should succeed (not 403)
        assert response.status_code != 403

    @pytest.mark.asyncio
    async def test_missing_auth_forbidden(self, client, mock_api_key):
        """Test context retrieval without Authorization header"""
        response = client.post(
            "/api/mcp/context/retrieve",
            json={
                "query": "test query",
                "codebase": "test-repo",
                "max_code_chunks": 5,
            },
            # No Authorization header
        )

        assert response.status_code == 403
        assert "Missing API key" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_auth_forbidden(self, client, mock_api_key):
        """Test context retrieval with invalid API key"""
        response = client.post(
            "/api/mcp/context/retrieve",
            json={
                "query": "test query",
                "codebase": "test-repo",
                "max_code_chunks": 5,
            },
            headers={"Authorization": f"Bearer {INVALID_API_KEY}"},
        )

        assert response.status_code == 403
        assert "Invalid API key" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_malformed_auth_forbidden(self, client, mock_api_key):
        """Test context retrieval with malformed API key"""
        response = client.post(
            "/api/mcp/context/retrieve",
            json={
                "query": "test query",
                "codebase": "test-repo",
                "max_code_chunks": 5,
            },
            headers={"Authorization": "Bearer "},  # Empty key
        )

        assert response.status_code == 403
        assert "Invalid API key" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_empty_auth_header_forbidden(self, client, mock_api_key):
        """Test context retrieval with empty Authorization header"""
        response = client.post(
            "/api/mcp/context/retrieve",
            json={
                "query": "test query",
                "codebase": "test-repo",
                "max_code_chunks": 5,
            },
            headers={"Authorization": ""},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_wrong_header_name_forbidden(self, client, mock_api_key):
        """Test context retrieval with wrong header name"""
        response = client.post(
            "/api/mcp/context/retrieve",
            json={
                "query": "test query",
                "codebase": "test-repo",
                "max_code_chunks": 5,
            },
            headers={"X-API-Key": TEST_API_KEY},  # Wrong header name
        )

        assert response.status_code == 403
        assert "Missing API key" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_case_sensitive_key(self, client, mock_api_key):
        """Test that API key comparison is case-sensitive"""
        response = client.post(
            "/api/mcp/context/retrieve",
            json={
                "query": "test query",
                "codebase": "test-repo",
                "max_code_chunks": 5,
            },
            headers={"Authorization": f"Bearer {TEST_API_KEY.upper()}"},
        )

        # Should fail because key is case-sensitive
        assert response.status_code == 403
        assert "Invalid API key" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_partial_key_forbidden(self, client, mock_api_key):
        """Test context retrieval with partial API key"""
        partial_key = TEST_API_KEY[:10]  # Only first 10 characters
        response = client.post(
            "/api/mcp/context/retrieve",
            json={
                "query": "test query",
                "codebase": "test-repo",
                "max_code_chunks": 5,
            },
            headers={"Authorization": f"Bearer {partial_key}"},
        )

        assert response.status_code == 403
        assert "Invalid API key" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_key_with_extra_characters_forbidden(self, client, mock_api_key):
        """Test context retrieval with API key plus extra characters"""
        modified_key = TEST_API_KEY + "extra"
        response = client.post(
            "/api/mcp/context/retrieve",
            json={
                "query": "test query",
                "codebase": "test-repo",
                "max_code_chunks": 5,
            },
            headers={"Authorization": f"Bearer {modified_key}"},
        )

        assert response.status_code == 403
        assert "Invalid API key" in response.json()["detail"]


# ============================================================================
# Integration Tests: Alternative Endpoint
# ============================================================================


class TestAlternativeEndpointSecurity:
    """Test security on the /api/v1/mcp/context/retrieve endpoint"""

    @pytest.mark.asyncio
    async def test_alternative_endpoint_valid_auth(self, client, mock_api_key):
        """Test alternative endpoint with valid API key"""
        response = client.post(
            "/api/v1/mcp/context/retrieve",
            json={
                "query": "test query",
                "codebase": "test-repo",
                "max_code_chunks": 5,
            },
            headers={"Authorization": f"Bearer {TEST_API_KEY}"},
        )

        # Should succeed (not 403)
        assert response.status_code != 403

    @pytest.mark.asyncio
    async def test_alternative_endpoint_missing_auth(self, client, mock_api_key):
        """Test alternative endpoint without Authorization header"""
        response = client.post(
            "/api/v1/mcp/context/retrieve",
            json={
                "query": "test query",
                "codebase": "test-repo",
                "max_code_chunks": 5,
            },
        )

        assert response.status_code == 403
        assert "Missing API key" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_alternative_endpoint_invalid_auth(self, client, mock_api_key):
        """Test alternative endpoint with invalid API key"""
        response = client.post(
            "/api/v1/mcp/context/retrieve",
            json={
                "query": "test query",
                "codebase": "test-repo",
                "max_code_chunks": 5,
            },
            headers={"Authorization": f"Bearer {INVALID_API_KEY}"},
        )

        assert response.status_code == 403
        assert "Invalid API key" in response.json()["detail"]


# ============================================================================
# Security Tests: Timing Attack Prevention
# ============================================================================


class TestTimingAttackPrevention:
    """Test that constant-time comparison prevents timing attacks"""

    def test_constant_time_comparison_used(self):
        """Verify that constant-time comparison is used"""
        # This test verifies the implementation uses secrets.compare_digest
        import inspect

        from app.shared.security import _constant_time_compare

        source = inspect.getsource(_constant_time_compare)
        assert "secrets.compare_digest" in source

    @pytest.mark.asyncio
    async def test_timing_attack_resistance(self, mock_api_key):
        """Test that verification time doesn't leak information"""
        import time

        # Test with completely wrong key
        wrong_key = "x" * len(TEST_API_KEY)
        start = time.perf_counter()
        try:
            await verify_api_key(authorization=wrong_key)
        except HTTPException:
            pass
        time_wrong = time.perf_counter() - start

        # Test with partially correct key (same prefix)
        partial_key = TEST_API_KEY[:10] + "x" * (len(TEST_API_KEY) - 10)
        start = time.perf_counter()
        try:
            await verify_api_key(authorization=partial_key)
        except HTTPException:
            pass
        time_partial = time.perf_counter() - start

        # Times should be similar (within 10ms)
        # This prevents attackers from using timing to guess the key
        time_diff = abs(time_wrong - time_partial)
        assert time_diff < 0.01, f"Timing difference too large: {time_diff}s"


# ============================================================================
# Security Tests: Audit Logging
# ============================================================================


class TestAuditLogging:
    """Test that security events are properly logged"""

    @pytest.mark.asyncio
    async def test_successful_auth_logged(self, client, mock_api_key, caplog):
        """Test that successful authentication is logged"""
        with caplog.at_level("INFO"):
            response = client.post(
                "/api/mcp/context/retrieve",
                json={
                    "query": "test query",
                    "codebase": "test-repo",
                    "max_code_chunks": 5,
                },
                headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            )

        # Check that authentication success was logged
        assert any(
            "API key authentication successful" in record.message
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_failed_auth_logged(self, client, mock_api_key, caplog):
        """Test that failed authentication is logged"""
        with caplog.at_level("WARNING"):
            response = client.post(
                "/api/mcp/context/retrieve",
                json={
                    "query": "test query",
                    "codebase": "test-repo",
                    "max_code_chunks": 5,
                },
                headers={"Authorization": f"Bearer {INVALID_API_KEY}"},
            )

        # Check that authentication failure was logged
        assert any(
            "API key authentication failed" in record.message
            for record in caplog.records
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
