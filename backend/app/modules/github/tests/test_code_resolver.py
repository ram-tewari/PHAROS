"""
Smoke tests for code_resolver.resolve_code_for_chunks.

Covers three scenarios:
  1. local-only  — chunks with is_remote=False (or missing)
  2. github-only — chunks with is_remote=True
  3. mixed       — combination of both

GitHubFetcher is patched so tests run without network or Redis.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.github.code_resolver import resolve_code_for_chunks
from app.modules.github.fetcher import FetchResult, FetchRequest


# ── Fixtures ─────────────────────────────────────────────────────────────────

@dataclass
class FakeChunk:
    id: str
    content: Optional[str] = None
    is_remote: bool = False
    github_uri: Optional[str] = None
    branch_reference: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None


def _make_fetch_result(req: FetchRequest, code: str, cache_hit: bool = False) -> FetchResult:
    return FetchResult(request=req, code=code, cache_hit=cache_hit, latency_ms=10.0)


def _mock_fetcher(results_by_uri: dict[str, str], cache_hit: bool = False):
    """Return a patched GitHubFetcher context manager."""
    async def _fetch_chunk(req: FetchRequest) -> FetchResult:
        code = results_by_uri.get(req.github_uri)
        return _make_fetch_result(req, code or "", cache_hit=cache_hit)

    fetcher_instance = MagicMock()
    fetcher_instance.fetch_chunk = _fetch_chunk
    fetcher_instance.__aenter__ = AsyncMock(return_value=fetcher_instance)
    fetcher_instance.__aexit__ = AsyncMock(return_value=None)

    return patch(
        "app.modules.github.code_resolver.GitHubFetcher",
        return_value=fetcher_instance,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_local_only():
    chunks = [
        FakeChunk(id="a1", content="print('hello')", is_remote=False),
        FakeChunk(id="a2", content="def foo(): pass", is_remote=False),
    ]

    code_map, metrics = await resolve_code_for_chunks(chunks)

    assert code_map["a1"]["code"] == "print('hello')"
    assert code_map["a1"]["source"] == "local"
    assert code_map["a1"]["cache_hit"] is None

    assert code_map["a2"]["code"] == "def foo(): pass"
    assert code_map["a2"]["source"] == "local"

    assert metrics["total_chunks"] == 2
    assert metrics["local_chunks"] == 2
    assert metrics["remote_chunks"] == 0
    assert metrics["fetched_ok"] == 0
    assert metrics["fetch_errors"] == 0


@pytest.mark.asyncio
async def test_github_only():
    chunks = [
        FakeChunk(
            id="b1",
            is_remote=True,
            github_uri="https://raw.githubusercontent.com/owner/repo/main/a.py",
            branch_reference="abc123",
            start_line=1,
            end_line=5,
        ),
        FakeChunk(
            id="b2",
            is_remote=True,
            github_uri="https://raw.githubusercontent.com/owner/repo/main/b.py",
            branch_reference="abc123",
            start_line=10,
            end_line=20,
        ),
    ]

    uri_map = {
        "https://raw.githubusercontent.com/owner/repo/main/a.py": "code_a",
        "https://raw.githubusercontent.com/owner/repo/main/b.py": "code_b",
    }

    with _mock_fetcher(uri_map, cache_hit=True):
        code_map, metrics = await resolve_code_for_chunks(chunks)

    assert code_map["b1"]["code"] == "code_a"
    assert code_map["b1"]["source"] == "github"
    assert code_map["b1"]["cache_hit"] is True

    assert code_map["b2"]["code"] == "code_b"

    assert metrics["total_chunks"] == 2
    assert metrics["local_chunks"] == 0
    assert metrics["remote_chunks"] == 2
    assert metrics["fetched_ok"] == 2
    assert metrics["cache_hits"] == 2
    assert metrics["fetch_errors"] == 0


@pytest.mark.asyncio
async def test_mixed():
    chunks = [
        FakeChunk(id="c1", content="local content", is_remote=False),
        FakeChunk(
            id="c2",
            is_remote=True,
            github_uri="https://raw.githubusercontent.com/owner/repo/main/c.py",
            branch_reference="HEAD",
            start_line=1,
            end_line=10,
        ),
    ]

    uri_map = {"https://raw.githubusercontent.com/owner/repo/main/c.py": "remote content"}

    with _mock_fetcher(uri_map):
        code_map, metrics = await resolve_code_for_chunks(chunks)

    assert code_map["c1"]["source"] == "local"
    assert code_map["c1"]["code"] == "local content"

    assert code_map["c2"]["source"] == "github"
    assert code_map["c2"]["code"] == "remote content"

    assert metrics["local_chunks"] == 1
    assert metrics["remote_chunks"] == 1
    assert metrics["fetched_ok"] == 1
    assert metrics["total_latency_ms"] >= 0


@pytest.mark.asyncio
async def test_remote_cap():
    """Chunks beyond max_remote=2 are silently dropped from fetching."""
    chunks = [
        FakeChunk(
            id=f"cap{i}",
            is_remote=True,
            github_uri=f"https://raw.githubusercontent.com/o/r/main/f{i}.py",
        )
        for i in range(5)
    ]

    with _mock_fetcher({}):
        code_map, metrics = await resolve_code_for_chunks(chunks, max_remote=2)

    assert metrics["remote_chunks"] == 2
    # Chunks beyond cap have no entry in code_map
    assert len(code_map) == 2


@pytest.mark.asyncio
async def test_fetch_error_handled_gracefully():
    """A fetch exception should not crash the resolver; chunk gets code=None."""
    chunk = FakeChunk(
        id="err1",
        is_remote=True,
        github_uri="https://raw.githubusercontent.com/owner/repo/main/err.py",
    )

    async def _failing_fetch(req):
        raise TimeoutError("timeout")

    fetcher_instance = MagicMock()
    fetcher_instance.fetch_chunk = _failing_fetch
    fetcher_instance.__aenter__ = AsyncMock(return_value=fetcher_instance)
    fetcher_instance.__aexit__ = AsyncMock(return_value=None)

    with patch("app.modules.github.code_resolver.GitHubFetcher", return_value=fetcher_instance):
        code_map, metrics = await resolve_code_for_chunks([chunk])

    assert code_map["err1"]["code"] is None
    assert code_map["err1"]["source"] == "github"
    assert metrics["fetch_errors"] == 1
