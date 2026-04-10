"""
GitHub On-Demand Code Fetcher — Phase 2 Hybrid Storage

Fetches raw source-code line ranges from GitHub on demand and caches the
results in Redis for 1 hour to stay well within GitHub's rate limits.

Architecture
────────────
  Caller (semantic search result)
       │  chunk.github_uri, chunk.start_line, chunk.end_line
       ▼
  GitHubFetcher.fetch_chunk()
       │
       ├─ Cache HIT  → return from Redis  (< 5 ms)
       └─ Cache MISS → GET raw GitHub URL → slice lines → store in Redis
                                                         → return code

Rate limits
───────────
  Unauthenticated : 60  requests / hour  (per IP)
  Authenticated   : 5,000 requests / hour (per token)

Set GITHUB_API_TOKEN in your environment to use the authenticated limit.

Cache key format
────────────────
  github:chunk:{sha40}:{path_hash}:{start}:{end}

  Using the commit SHA (not branch name) guarantees cache correctness even
  when branches are force-pushed.

Dependencies
────────────
  pip install httpx redis[asyncio]
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx
import redis.asyncio as aioredis

from app.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Constants ──────────────────────────────────────────────────────────────────

CACHE_TTL_SECONDS = 3600          # 1-hour TTL matches vision doc
CACHE_KEY_PREFIX  = "github:chunk"
MAX_FILE_BYTES    = 2 * 1024 * 1024  # 2 MB safety cap for a single file fetch


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FetchRequest:
    """Describes a single code-chunk fetch operation."""
    github_uri: str       # https://raw.githubusercontent.com/…/file.py
    branch_reference: str # commit SHA (preferred) or branch name
    start_line: int       # 1-based, inclusive
    end_line: int         # 1-based, inclusive

    def cache_key(self) -> str:
        """Deterministic Redis key that is stable across file renames."""
        # Hash the URI so we handle long paths without key-length issues
        path_hash = hashlib.sha1(self.github_uri.encode()).hexdigest()[:16]
        ref_short = self.branch_reference[:40]   # cap SHA / branch length
        return f"{CACHE_KEY_PREFIX}:{ref_short}:{path_hash}:{self.start_line}:{self.end_line}"


@dataclass
class FetchResult:
    """Result of a single fetch operation."""
    request: FetchRequest
    code: Optional[str]       # None on hard failure
    cache_hit: bool
    latency_ms: float
    error: Optional[str] = None


# ── Redis connection factory ───────────────────────────────────────────────────

def _make_redis_client() -> aioredis.Redis:
    """
    Build an async Redis client from settings.

    Prefers REDIS_URL (e.g. on Render/Upstash), falls back to
    REDIS_HOST + REDIS_PORT + REDIS_CACHE_DB.
    """
    if settings.REDIS_URL:
        return aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return aioredis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_CACHE_DB,
        encoding="utf-8",
        decode_responses=True,
    )


# ── Core fetcher class ─────────────────────────────────────────────────────────

class GitHubFetcher:
    """
    Parallelised async fetcher for GitHub raw-content endpoints.

    Usage
    -----
    async with GitHubFetcher() as fetcher:
        results = await fetcher.fetch_many(requests)

    Or for a single chunk:
        result = await fetcher.fetch_chunk(req)
    """

    def __init__(
        self,
        concurrency: int | None = None,
        redis_client: aioredis.Redis | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._concurrency = concurrency or settings.GITHUB_FETCH_CONCURRENCY
        self._semaphore = asyncio.Semaphore(self._concurrency)
        self._redis = redis_client
        self._http = http_client
        self._owns_redis = redis_client is None
        self._owns_http  = http_client is None

    # ── Context manager ────────────────────────────────────────────────────

    async def __aenter__(self) -> "GitHubFetcher":
        if self._owns_redis:
            self._redis = _make_redis_client()
        if self._owns_http:
            self._http = httpx.AsyncClient(
                headers=self._build_headers(),
                timeout=httpx.Timeout(10.0, connect=5.0),
                follow_redirects=True,
                limits=httpx.Limits(
                    max_connections=self._concurrency + 5,
                    max_keepalive_connections=self._concurrency,
                ),
            )
        return self

    async def __aexit__(self, *_) -> None:
        if self._owns_http and self._http:
            await self._http.aclose()
        if self._owns_redis and self._redis:
            await self._redis.aclose()

    # ── Public API ─────────────────────────────────────────────────────────

    async def fetch_chunk(self, req: FetchRequest) -> FetchResult:
        """Fetch a single code chunk, serving from cache when available."""
        import time
        t0 = time.monotonic()

        cache_key = req.cache_key()

        # 1. Cache probe
        try:
            cached = await self._redis.get(cache_key)
        except Exception as exc:
            logger.warning("Redis GET failed, bypassing cache: %s", exc)
            cached = None

        if cached is not None:
            latency = (time.monotonic() - t0) * 1000
            logger.debug("Cache HIT %s (%.1f ms)", cache_key, latency)
            return FetchResult(req, cached, cache_hit=True, latency_ms=latency)

        # 2. Fetch from GitHub
        try:
            code = await self._fetch_raw(req)
        except Exception as exc:
            latency = (time.monotonic() - t0) * 1000
            logger.error("GitHub fetch failed for %s: %s", req.github_uri, exc)
            return FetchResult(req, None, cache_hit=False, latency_ms=latency, error=str(exc))

        # 3. Populate cache (fire-and-forget; don't let Redis errors surface)
        try:
            await self._redis.setex(cache_key, CACHE_TTL_SECONDS, code)
        except Exception as exc:
            logger.warning("Redis SETEX failed: %s", exc)

        latency = (time.monotonic() - t0) * 1000
        logger.debug("Cache MISS %s — fetched in %.1f ms", cache_key, latency)
        return FetchResult(req, code, cache_hit=False, latency_ms=latency)

    async def fetch_many(self, requests: list[FetchRequest]) -> list[FetchResult]:
        """
        Fetch multiple chunks in parallel, bounded by self._concurrency.

        Returns results in the same order as the input list.
        """
        async def _bounded(req: FetchRequest) -> FetchResult:
            async with self._semaphore:
                return await self.fetch_chunk(req)

        return list(await asyncio.gather(*[_bounded(r) for r in requests]))

    # ── Internal helpers ───────────────────────────────────────────────────

    async def _fetch_raw(self, req: FetchRequest) -> str:
        """
        Download the raw file from GitHub and slice the requested line range.

        Validates that the URI is a legitimate raw.githubusercontent.com URL
        before making the request to prevent SSRF.
        """
        _validate_github_uri(req.github_uri)

        async with self._semaphore:
            response = await self._http.get(req.github_uri)

        if response.status_code == 404:
            raise FileNotFoundError(
                f"GitHub returned 404 for {req.github_uri} "
                f"(ref={req.branch_reference!r})"
            )
        if response.status_code == 403:
            raise PermissionError(
                f"GitHub returned 403 — check GITHUB_API_TOKEN "
                f"and repository visibility ({req.github_uri})"
            )
        response.raise_for_status()

        content = response.text
        if len(content.encode()) > MAX_FILE_BYTES:
            raise ValueError(
                f"File exceeds {MAX_FILE_BYTES // 1024} KB safety cap: "
                f"{req.github_uri}"
            )

        lines = content.splitlines()
        # Convert 1-based inclusive range to 0-based Python slice
        start = max(0, req.start_line - 1)
        end   = min(len(lines), req.end_line)
        return "\n".join(lines[start:end])

    @staticmethod
    def _build_headers() -> dict[str, str]:
        """Build HTTP headers, adding auth token when configured."""
        headers: dict[str, str] = {
            "Accept": "application/vnd.github.v3.raw",
            "User-Agent": "Pharos-CodeIntelligence/2.0",
        }
        token = settings.GITHUB_API_TOKEN
        if token:
            headers["Authorization"] = f"Bearer {token.get_secret_value()}"
        return headers


# ── SSRF guard ─────────────────────────────────────────────────────────────────

_ALLOWED_GITHUB_HOSTS = frozenset({
    "raw.githubusercontent.com",
    "api.github.com",
})


def _validate_github_uri(uri: str) -> None:
    """
    Raise ValueError if the URI is not a legitimate GitHub raw-content URL.

    Prevents Server-Side Request Forgery (SSRF) by allowlisting hosts.
    """
    parsed = urlparse(uri)
    if parsed.scheme != "https":
        raise ValueError(f"Only HTTPS URIs are allowed, got: {uri!r}")
    if parsed.hostname not in _ALLOWED_GITHUB_HOSTS:
        raise ValueError(
            f"URI host {parsed.hostname!r} is not an allowed GitHub host. "
            f"Allowed: {sorted(_ALLOWED_GITHUB_HOSTS)}"
        )


# ── Convenience function ───────────────────────────────────────────────────────

async def fetch_chunks_for_results(
    chunks: list,  # list[DocumentChunk] from search results
) -> dict[str, str]:
    """
    Fetch raw code for a list of remote DocumentChunk ORM objects.

    Returns a dict mapping chunk.id (str) → code string.
    Chunks without github_uri are silently skipped.

    Example
    -------
    code_map = await fetch_chunks_for_results(top_chunks)
    for chunk in top_chunks:
        code = code_map.get(str(chunk.id), "")
    """
    remote = [c for c in chunks if getattr(c, "is_remote", False) and c.github_uri]
    if not remote:
        return {}

    requests = [
        FetchRequest(
            github_uri=c.github_uri,
            branch_reference=c.branch_reference or "HEAD",
            start_line=c.start_line or 1,
            end_line=c.end_line or 9999,
        )
        for c in remote
    ]

    async with GitHubFetcher() as fetcher:
        results = await fetcher.fetch_many(requests)

    return {
        str(chunk.id): result.code or ""
        for chunk, result in zip(remote, results)
        if result.code is not None
    }
