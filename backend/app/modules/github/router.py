"""
GitHub API Router — thin wrappers over GitHubFetcher.

Endpoints:
  POST /api/github/fetch        — single chunk
  POST /api/github/fetch-batch  — up to 50 chunks
  GET  /api/github/health       — module health check
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, status

from .fetcher import FetchRequest, GitHubFetcher
from .schema import (
    GitHubBatchFetchRequest,
    GitHubBatchFetchResponse,
    GitHubFetchRequest,
    GitHubFetchResponse,
    GitHubHealthResponse,
)

logger = logging.getLogger(__name__)

github_router = APIRouter(prefix="/api/github", tags=["github"])


@github_router.post(
    "/fetch",
    response_model=GitHubFetchResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch a single code chunk from GitHub",
)
async def fetch_single(payload: GitHubFetchRequest) -> GitHubFetchResponse:
    """
    Fetch raw source code for a single line range from a GitHub file.

    The URI must be a `raw.githubusercontent.com` URL (SSRF guard enforced
    by the underlying fetcher). Results are cached in Redis for 1 hour.
    """
    req = FetchRequest(
        github_uri=payload.github_uri,
        branch_reference=payload.branch_reference,
        start_line=payload.start_line,
        end_line=payload.end_line,
    )

    try:
        async with GitHubFetcher() as fetcher:
            result = await fetcher.fetch_chunk(req)
    except Exception as exc:
        logger.error("GitHub fetch error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub fetch failed: {exc}",
        ) from exc

    return GitHubFetchResponse(
        code=result.code,
        cache_hit=result.cache_hit,
        latency_ms=round(result.latency_ms, 1),
        error=result.error,
    )


@github_router.post(
    "/fetch-batch",
    response_model=GitHubBatchFetchResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch up to 50 code chunks from GitHub in parallel",
)
async def fetch_batch(payload: GitHubBatchFetchRequest) -> GitHubBatchFetchResponse:
    """
    Fetch raw source code for multiple line ranges in a single request.

    Chunks are fetched in parallel (bounded by GITHUB_FETCH_CONCURRENCY).
    Per-chunk timeout is 10 s (inherited from GitHubFetcher's HTTP client).
    """
    requests = [
        FetchRequest(
            github_uri=chunk.github_uri,
            branch_reference=chunk.branch_reference,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
        )
        for chunk in payload.chunks
    ]

    t0 = time.monotonic()
    try:
        async with GitHubFetcher() as fetcher:
            results = await fetcher.fetch_many(requests)
    except Exception as exc:
        logger.error("GitHub batch fetch error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub batch fetch failed: {exc}",
        ) from exc

    total_latency_ms = round((time.monotonic() - t0) * 1000, 1)
    cache_hits = sum(1 for r in results if r.cache_hit)
    errors = sum(1 for r in results if r.code is None)

    return GitHubBatchFetchResponse(
        results=[
            GitHubFetchResponse(
                code=r.code,
                cache_hit=r.cache_hit,
                latency_ms=round(r.latency_ms, 1),
                error=r.error,
            )
            for r in results
        ],
        total=len(results),
        cache_hits=cache_hits,
        errors=errors,
        total_latency_ms=total_latency_ms,
    )


@github_router.get(
    "/health",
    response_model=GitHubHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="GitHub module health check",
)
async def github_health() -> GitHubHealthResponse:
    """Check Redis availability and configuration for the GitHub module."""
    from app.config.settings import get_settings
    from .fetcher import _make_redis_client

    settings = get_settings()
    cache_available = False

    try:
        redis = _make_redis_client()
        await redis.ping()
        await redis.aclose()
        cache_available = True
    except Exception as exc:
        logger.warning("GitHub health check: Redis unavailable — %s", exc)

    return GitHubHealthResponse(
        status="healthy" if cache_available else "degraded",
        cache_available=cache_available,
        github_token_configured=bool(settings.GITHUB_API_TOKEN),
        max_concurrency=settings.GITHUB_FETCH_CONCURRENCY,
    )
