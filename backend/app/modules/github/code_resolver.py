"""
GitHub Code Resolver — hybrid local/remote chunk code retrieval.

Partitions a list of DocumentChunk objects (ORM or dict) by storage type:
  - Local chunks  → read content directly from chunk.content
  - Remote chunks → fetch from GitHub via GitHubFetcher with per-chunk timeout

Hard limits (configurable via kwargs):
  - max_remote: 50  — caps remote fetches per call to keep memory/rate usage bounded
  - timeout: 5.0 s  — per-chunk GitHub fetch timeout
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .fetcher import FetchRequest, GitHubFetcher

logger = logging.getLogger(__name__)

MAX_REMOTE_CHUNKS = 50
CHUNK_TIMEOUT_SECONDS = 5.0


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Unified attribute access for ORM objects and plain dicts."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


async def resolve_code_for_chunks(
    chunks: list[Any],
    timeout: float = CHUNK_TIMEOUT_SECONDS,
    max_remote: int = MAX_REMOTE_CHUNKS,
) -> tuple[dict[str, dict], dict]:
    """
    Resolve source code for a mixed list of local and remote chunks.

    Args:
        chunks: ORM DocumentChunk objects or dicts with the same fields.
        timeout: Per-chunk fetch timeout in seconds for remote chunks.
        max_remote: Maximum number of remote chunks to fetch in one call.

    Returns:
        Tuple of:
          - code_map: {chunk_id: {"code": str|None, "source": "local"|"github",
                                  "cache_hit": bool|None}}
          - metrics: aggregate stats dict
    """
    t0 = time.monotonic()

    local_chunks = [c for c in chunks if not _get(c, "is_remote", False)]
    remote_chunks = [
        c for c in chunks
        if _get(c, "is_remote", False) and _get(c, "github_uri")
    ]

    if len(remote_chunks) > max_remote:
        logger.warning(
            "resolve_code_for_chunks: capping remote chunks at %d (received %d)",
            max_remote,
            len(remote_chunks),
        )
        remote_chunks = remote_chunks[:max_remote]

    code_map: dict[str, dict] = {}

    # ── Local chunks: read content directly ───────────────────────────────────
    for chunk in local_chunks:
        chunk_id = str(_get(chunk, "id", ""))
        content = _get(chunk, "content") or ""
        code_map[chunk_id] = {"code": content, "source": "local", "cache_hit": None}

    # ── Remote chunks: fetch from GitHub ──────────────────────────────────────
    fetch_errors = 0
    cache_hits = 0
    fetched_ok = 0

    if remote_chunks:
        requests = [
            FetchRequest(
                github_uri=_get(c, "github_uri"),
                branch_reference=_get(c, "branch_reference") or "HEAD",
                start_line=_get(c, "start_line") or 1,
                end_line=_get(c, "end_line") or 9999,
            )
            for c in remote_chunks
        ]

        async with GitHubFetcher() as fetcher:
            tasks = [
                asyncio.wait_for(fetcher.fetch_chunk(req), timeout=timeout)
                for req in requests
            ]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for chunk, fetch_result in zip(remote_chunks, raw_results):
            chunk_id = str(_get(chunk, "id", ""))
            if isinstance(fetch_result, Exception):
                logger.warning(
                    "Code fetch failed for chunk %s: %s", chunk_id, fetch_result
                )
                code_map[chunk_id] = {
                    "code": None,
                    "source": "github",
                    "cache_hit": False,
                }
                fetch_errors += 1
            elif fetch_result.code is not None:
                code_map[chunk_id] = {
                    "code": fetch_result.code,
                    "source": "github",
                    "cache_hit": fetch_result.cache_hit,
                }
                cache_hits += int(fetch_result.cache_hit)
                fetched_ok += 1
            else:
                code_map[chunk_id] = {
                    "code": None,
                    "source": "github",
                    "cache_hit": False,
                }
                fetch_errors += 1

    total_latency_ms = (time.monotonic() - t0) * 1000
    metrics = {
        "total_chunks": len(chunks),
        "local_chunks": len(local_chunks),
        "remote_chunks": len(remote_chunks),
        "fetched_ok": fetched_ok,
        "fetch_errors": fetch_errors,
        "cache_hits": cache_hits,
        "total_latency_ms": round(total_latency_ms, 1),
    }

    return code_map, metrics
