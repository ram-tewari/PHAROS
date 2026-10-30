"""Public pull-request review comments, the conventions reviewers enforce.

Fetched from the GitHub REST API (``/repos/{owner}/{repo}/pulls/comments``)
on the owner's Mac and cached as JSON next to the repository's mirror, so a
nightly run only asks for what is new. A token is optional
(``GIT_CLONE_TOKEN``, sent as a header): public data is readable without one
at 60 requests an hour. Only comments created at or before the learned
commit's date are used, so memory never sees the future of its commit.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

API = "https://api.github.com"
MAX_PAGES = 30
# Maintainers enforce conventions; drive-by comments mostly discuss one change.
MAINTAINERS = ("OWNER", "MEMBER", "COLLABORATOR")
BOT_RE = re.compile(r"\[bot\]$|^(dependabot|renovate|codecov|coveralls|github-actions)", re.I)
TRIVIAL_RE = re.compile(r"^\s*(lgtm|thanks?|thank you|nice|done|fixed|\+1|good catch|agreed)[!. ]*$", re.I)


def cache_dir(name: str) -> Path:
    root = Path(os.getenv("LEARNING_CACHE_DIR") or Path.home() / ".cache" / "pharos" / "learn").expanduser()
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def github_slug(url: str) -> str | None:
    m = re.match(r"https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url or "")
    return f"{m.group(1)}/{m.group(2)}" if m else None


def body_sha256(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


def _get(url: str, token: str | None) -> list[dict]:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "pharos-learning",
                                                   **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed https host
        return json.loads(response.read().decode())


def fetch_review_comments(url: str, cache_name: str, *, before: str, limit: int = 300,
                          token: str | None = None) -> list[dict]:
    """Up to ``limit`` substantive review comments created at or before ``before`` (ISO date), newest first."""
    slug = github_slug(url)
    if slug is None:
        return []
    path = cache_dir(cache_name) / "review_comments.json"
    cached: dict[str, dict] = {}
    if path.exists():
        cached = {str(c["id"]): c for c in json.loads(path.read_text())}
    newest_known = max((c["created_at"] for c in cached.values()), default="")
    for page in range(1, MAX_PAGES + 1):
        try:
            rows = _get(f"{API}/repos/{slug}/pulls/comments?sort=created&direction=desc&per_page=100&page={page}",
                        token)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            logger.warning("review comments for %s: %s (using %d cached)", slug, exc, len(cached))
            break
        if not rows:
            break
        for row in rows:
            cached[str(row["id"])] = {
                "id": row["id"], "pr": int(row.get("pull_request_url", "0").rsplit("/", 1)[-1] or 0),
                "url": row.get("html_url"), "path": row.get("path"), "created_at": row.get("created_at"),
                "user": (row.get("user") or {}).get("login", ""), "body": row.get("body") or "",
                "association": row.get("author_association", ""),
                "diff_hunk": "\n".join((row.get("diff_hunk") or "").splitlines()[-6:]),
            }
        oldest = rows[-1].get("created_at", "")
        enough = sum(1 for c in cached.values() if c["created_at"] <= before) >= limit * 2
        if (newest_known and oldest <= newest_known and enough) or (oldest <= before and enough):
            break
        time.sleep(0.5)
    path.write_text(json.dumps(sorted(cached.values(), key=lambda c: c["created_at"], reverse=True)))
    useful = [c for c in cached.values()
              if c["created_at"] <= before and not BOT_RE.search(c["user"]) and len(c["body"]) >= 60
              and not TRIVIAL_RE.match(c["body"]) and c.get("association", "OWNER") in MAINTAINERS]
    return sorted(useful, key=lambda c: c["created_at"], reverse=True)[:limit]


def review_evidence(comment: dict) -> dict:
    return {"kind": "review", "url": comment["url"], "pr": comment["pr"], "path": comment.get("path"),
            "date": (comment.get("created_at") or "")[:10], "sha256": body_sha256(comment["body"])}


def check_review(evidence: dict, cache_name: str) -> bool:
    """A review comment cannot be re-checked in git: it must be in the cache with the same text."""
    path = cache_dir(cache_name) / "review_comments.json"
    if not path.exists():
        return False
    for c in json.loads(path.read_text()):
        if c.get("url") == evidence.get("url"):
            return body_sha256(c.get("body") or "") == evidence.get("sha256")
    return False
