"""
Integration Tests — GitHubFetcher (Phase 2, Step 4)

Tests three scenarios per the spec:
  1. Cache MISS  — first fetch goes to GitHub (or mock), latency < 500 ms
  2. Cache HIT   — second fetch is served from Redis,    latency < 500 ms
  3. Invalid URI — SSRF guard raises ValueError immediately

Run
───
  # Requires a running Redis; set GITHUB_API_TOKEN for authenticated limits.
  pytest backend/tests/test_github_fetcher.py -v

  # Against a mock Redis + mock HTTP (no network or Redis required):
  pytest backend/tests/test_github_fetcher.py -v -m unit
"""

from __future__ import annotations

import asyncio
import time
import pytest
import pytest_asyncio

from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.github.fetcher import (
    FetchRequest,
    FetchResult,
    GitHubFetcher,
    _validate_github_uri,
    CACHE_TTL_SECONDS,
)

# ── Shared test fixtures ───────────────────────────────────────────────────────

# A real public file on GitHub.
# Pinned to a verified commit in psf/requests (v2.31.0 tag SHA).
# If this SHA is ever unreachable, fall back to branch "main".
_REAL_SHA   = "b811857e42dc8d9e69d2218ecd8d32b5e79dc1d4"
_REAL_URI   = f"https://raw.githubusercontent.com/psf/requests/{_REAL_SHA}/README.md"
_REAL_START = 1
_REAL_END   = 5

_MOCK_CODE = "def hello():\n    pass\n"

# ── Helper: build a FetchRequest ──────────────────────────────────────────────

def _make_request(
    uri: str = "https://raw.githubusercontent.com/owner/repo/abc123/path/file.py",
    start: int = 10,
    end: int = 20,
    ref: str = "abc123deadbeef" * 2 + "abcd",  # 40-char SHA
) -> FetchRequest:
    return FetchRequest(
        github_uri=uri,
        branch_reference=ref,
        start_line=start,
        end_line=end,
    )


# ── Unit tests (mock Redis + mock httpx) ──────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.unit
async def test_cache_miss_fetches_github_and_stores_in_redis():
    """Cache MISS path: fetches from GitHub, stores result, returns code."""
    req = _make_request()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)   # cache miss
    mock_redis.setex = AsyncMock()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "\n".join(f"line {i}" for i in range(1, 100))
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)

    async with GitHubFetcher(
        redis_client=mock_redis, http_client=mock_http
    ) as fetcher:
        t0 = time.monotonic()
        result = await fetcher.fetch_chunk(req)
        latency = (time.monotonic() - t0) * 1000

    assert result.cache_hit is False
    assert result.code is not None
    assert result.error is None
    assert latency < 500, f"Latency {latency:.1f} ms exceeds 500 ms SLA"

    # Verify Redis was written
    mock_redis.setex.assert_called_once()
    call_args = mock_redis.setex.call_args
    assert call_args.args[1] == CACHE_TTL_SECONDS   # correct TTL


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cache_hit_skips_github_and_meets_latency():
    """Cache HIT path: code is returned from Redis; no HTTP request made."""
    req = _make_request()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=_MOCK_CODE)   # cache hit
    mock_redis.setex = AsyncMock()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock()   # should NOT be called

    async with GitHubFetcher(
        redis_client=mock_redis, http_client=mock_http
    ) as fetcher:
        t0 = time.monotonic()
        result = await fetcher.fetch_chunk(req)
        latency = (time.monotonic() - t0) * 1000

    assert result.cache_hit is True
    assert result.code == _MOCK_CODE
    assert result.error is None
    assert latency < 500, f"Cache-hit latency {latency:.1f} ms exceeds 500 ms SLA"

    # Confirm no HTTP request was made
    mock_http.get.assert_not_called()
    mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_fetch_many_parallel_returns_ordered_results():
    """fetch_many returns results in the same order as requests."""
    requests = [_make_request(start=i, end=i + 5) for i in range(1, 11)]

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=[f"code_{i}" for i in range(10)])
    mock_redis.setex = AsyncMock()

    mock_http = AsyncMock()

    async with GitHubFetcher(
        redis_client=mock_redis, http_client=mock_http
    ) as fetcher:
        results = await fetcher.fetch_many(requests)

    assert len(results) == 10
    for i, result in enumerate(results):
        assert result.code == f"code_{i}", f"Result {i} out of order"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_github_404_returns_error_not_raises():
    """A 404 from GitHub is captured as result.error, not an unhandled exception."""
    req = _make_request()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock()

    mock_response = MagicMock()
    mock_response.status_code = 404

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)

    async with GitHubFetcher(
        redis_client=mock_redis, http_client=mock_http
    ) as fetcher:
        result = await fetcher.fetch_chunk(req)

    assert result.code is None
    assert result.error is not None
    assert "404" in result.error


@pytest.mark.asyncio
@pytest.mark.unit
async def test_redis_failure_falls_through_to_github():
    """If Redis is unavailable the fetcher still serves from GitHub."""
    import redis.asyncio as aioredis

    req = _make_request()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
    mock_redis.setex = AsyncMock(side_effect=ConnectionError("Redis down"))

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "\n".join(f"line {i}" for i in range(1, 50))
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)

    async with GitHubFetcher(
        redis_client=mock_redis, http_client=mock_http
    ) as fetcher:
        result = await fetcher.fetch_chunk(req)

    # Code should still be returned even though Redis is down
    assert result.code is not None
    assert result.error is None


# ── SSRF guard unit tests ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_ssrf_guard_rejects_non_github_host():
    """SSRF guard must reject non-GitHub hosts."""
    with pytest.raises(ValueError, match="not an allowed GitHub host"):
        _validate_github_uri("https://evil.com/payload")


@pytest.mark.unit
def test_ssrf_guard_rejects_http():
    """SSRF guard must reject plain HTTP."""
    with pytest.raises(ValueError, match="Only HTTPS"):
        _validate_github_uri("http://raw.githubusercontent.com/owner/repo/sha/file.py")


@pytest.mark.unit
def test_ssrf_guard_allows_raw_githubusercontent():
    """SSRF guard must accept raw.githubusercontent.com."""
    _validate_github_uri(
        "https://raw.githubusercontent.com/owner/repo/abc123/src/main.py"
    )  # Should not raise


# ── Line-range slicing test ───────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.unit
async def test_line_range_slicing_is_correct():
    """Fetcher must return only the requested line range (1-based, inclusive)."""
    source = "\n".join(f"line_{i}" for i in range(1, 101))   # 100 lines

    req = FetchRequest(
        github_uri="https://raw.githubusercontent.com/o/r/sha/f.py",
        branch_reference="sha",
        start_line=10,
        end_line=20,
    )

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = source
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)

    async with GitHubFetcher(
        redis_client=mock_redis, http_client=mock_http
    ) as fetcher:
        result = await fetcher.fetch_chunk(req)

    lines = result.code.split("\n")
    assert lines[0]  == "line_10",  f"Expected 'line_10', got {lines[0]!r}"
    assert lines[-1] == "line_20",  f"Expected 'line_20', got {lines[-1]!r}"
    assert len(lines) == 11,         f"Expected 11 lines (10–20 inclusive), got {len(lines)}"


# ── Integration tests (require network + Redis) ───────────────────────────────

@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_real_github_fetch_cache_miss_latency():
    """
    INTEGRATION: Fetch a real public file from GitHub.

    Assertions:
      - Code is returned (not None)
      - Latency < 500 ms (spec requirement)
      - Cache miss on first call

    Requires: network access + Redis running on localhost:6379
    Skip with: pytest -m "not integration"
    """
    req = FetchRequest(
        github_uri=_REAL_URI,
        branch_reference=_REAL_SHA,
        start_line=_REAL_START,
        end_line=_REAL_END,
    )

    async with GitHubFetcher() as fetcher:
        # Bust cache first
        cache_key = req.cache_key()
        await fetcher._redis.delete(cache_key)

        t0 = time.monotonic()
        result = await fetcher.fetch_chunk(req)
        latency = (time.monotonic() - t0) * 1000

    assert result.code is not None, f"Fetch failed: {result.error}"
    assert latency < 500, f"Cache MISS latency {latency:.1f} ms > 500 ms SLA"
    assert result.cache_hit is False


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_real_github_fetch_cache_hit_latency():
    """
    INTEGRATION: After populating the cache, hit latency must be < 500 ms.

    Requires: network access + Redis running on localhost:6379
    """
    req = FetchRequest(
        github_uri=_REAL_URI,
        branch_reference=_REAL_SHA,
        start_line=_REAL_START,
        end_line=_REAL_END,
    )

    async with GitHubFetcher() as fetcher:
        # Warm cache
        await fetcher.fetch_chunk(req)

        # Now measure cache hit
        t0 = time.monotonic()
        result = await fetcher.fetch_chunk(req)
        latency = (time.monotonic() - t0) * 1000

    assert result.code is not None
    assert result.cache_hit is True
    assert latency < 500, f"Cache HIT latency {latency:.1f} ms > 500 ms SLA"
