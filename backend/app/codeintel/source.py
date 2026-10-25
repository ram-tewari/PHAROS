"""On-demand source resolution for hybrid storage.

Pharos stores pointers (repository, commit, path, line span) instead of
source code. This module turns a pointer back into code:

* **local repositories** — ``git cat-file`` from the registered checkout's
  object database (works offline, no network);
* **GitHub / GitLab / Bitbucket** — the host's raw-file endpoint at the
  pinned commit, over https, from an allowlist of hosts, without following
  redirects, with a size cap and a short timeout.

Every fetched file is checked against the git blob SHA recorded at index
time (``sha1("blob <len>\\0" + bytes)``). A mismatch is reported as
``unavailable:content_mismatch`` instead of returning code that may not be
what was indexed. Because URLs pin a commit, fetched files are immutable and
are cached in-process.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from urllib.parse import urlsplit

from .git_source import RAW_CONTENT_HOSTS, GitError, local_git_dir, raw_file_url, read_file_at_commit

logger = logging.getLogger(__name__)

MAX_FETCH_BYTES = 2_000_000
FETCH_TIMEOUT_SECONDS = 5.0
FETCH_CONCURRENCY = 8
CACHE_FILES = 256


@dataclass
class SourceRequest:
    key: str  # caller's id (chunk id)
    source_type: str  # github | git | local
    repository_url: str
    local_path: str | None
    commit: str
    path: str
    start_line: int
    end_line: int
    blob_sha: str | None


@dataclass
class SourceResult:
    key: str
    status: str  # "resolved" | "unavailable:<reason>"
    code: str | None = None
    verified: bool = False
    origin: str | None = None  # "git" | "https"


class _FileCache:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._data: OrderedDict[str, bytes] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> bytes | None:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                return self._data[key]
            return None

    def put(self, key: str, value: bytes) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.capacity:
                self._data.popitem(last=False)


_cache = _FileCache(CACHE_FILES)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _slice(data: bytes, start: int, end: int) -> str:
    text = data.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    start = max(1, start)
    end = max(start, end)
    return "\n".join(lines[start - 1 : end])


def _fetch_https(url: str, token: str | None) -> bytes:
    import httpx

    host = urlsplit(url).hostname
    if urlsplit(url).scheme != "https" or host not in RAW_CONTENT_HOSTS:
        raise PermissionError(f"refusing to fetch from {host!r}")
    headers = {}
    if token and host == "raw.githubusercontent.com":
        headers["Authorization"] = f"token {token}"
    with httpx.Client(timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=False) as client:
        with client.stream("GET", url, headers=headers) as resp:
            if resp.status_code == 404:
                raise FileNotFoundError(url)
            if resp.status_code != 200:
                raise ConnectionError(f"HTTP {resp.status_code}")
            chunks, size = [], 0
            for part in resp.iter_bytes():
                size += len(part)
                if size > MAX_FETCH_BYTES:
                    raise OverflowError("file too large")
                chunks.append(part)
    return b"".join(chunks)


def _load(req: SourceRequest, token: str | None) -> tuple[bytes, str]:
    cache_key = f"{req.repository_url}@{req.commit}:{req.path}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached, "cache"
    if req.source_type == "local":
        if not req.local_path:
            raise FileNotFoundError("local repository path not recorded")
        data = read_file_at_commit(local_git_dir(req.local_path), req.commit, req.path)
        origin = "git"
    else:
        url = raw_file_url(req.repository_url, req.commit, req.path)
        if url is None:
            raise LookupError("no raw-content endpoint for this host")
        data = _fetch_https(url, token)
        origin = "https"
    _cache.put(cache_key, data)
    return data, origin


def _resolve_one(req: SourceRequest, token: str | None) -> SourceResult:
    try:
        data, origin = _load(req, token)
    except PermissionError:
        return SourceResult(req.key, "unavailable:host_not_allowed")
    except FileNotFoundError:
        return SourceResult(req.key, "unavailable:not_found")
    except OverflowError:
        return SourceResult(req.key, "unavailable:too_large")
    except LookupError:
        return SourceResult(req.key, "unavailable:no_raw_endpoint")
    except GitError:
        return SourceResult(req.key, "unavailable:git_error")
    except Exception as exc:  # network errors, timeouts
        logger.info("source fetch failed for %s: %s", req.path, type(exc).__name__)
        return SourceResult(req.key, "unavailable:fetch_failed")
    verified = False
    if req.blob_sha:
        if git_blob_sha(data) != req.blob_sha:
            return SourceResult(req.key, "unavailable:content_mismatch")
        verified = True
    return SourceResult(req.key, "resolved", _slice(data, req.start_line, req.end_line), verified, origin)


def resolve_sources(requests: list[SourceRequest], token: str | None = None) -> dict[str, SourceResult]:
    """Resolve many pointers concurrently; never raises."""
    if not requests:
        return {}
    if len(requests) == 1:
        return {requests[0].key: _resolve_one(requests[0], token)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(FETCH_CONCURRENCY, len(requests))) as pool:
        results = list(pool.map(lambda r: _resolve_one(r, token), requests))
    return {r.key: r for r in results}
