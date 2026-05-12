"""Per-source diversity reranker (MMR-style).

Why this exists: dense retrieval is volume-biased. linux-kernel has
~10x the chunks of pflag, so its candidates monopolize top-K. We
apply an MMR-style penalty keyed on the candidate's source repo so
the Nth hit from the same repo is downweighted relative to the first.

Penalty model:

    adjusted_i = score_i  -  lambda * f(k_i)

where k_i is the # of higher-ranked candidates already accepted from
the same source bucket and f is a saturating function (default
log1p) so the 5th hit from linux-kernel isn't penalized 5x the 2nd.

This is "per-source MMR" — we don't compute pairwise embedding
similarity. Repos *are* the redundancy axis we care about; the
cheaper bucketing gives us the diversity we want at O(N*K) instead
of O(N^2) and without needing chunk embeddings in memory.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple
from urllib.parse import urlparse

_GITHUB_REPO = re.compile(r"github\.com[:/]+([^/]+/[^/#?]+?)(?:\.git)?(?:[/#?]|$)")


def source_key(url_or_path: Optional[str]) -> str:
    """Collapse a chunk's source string to a canonical bucket.

    GitHub URLs collapse to 'gh:owner/repo' regardless of branch or
    path; everything else falls back to its netloc or the raw string.
    Stable across branch / path variation within one repo — which is
    exactly what we want to penalize.
    """
    if not url_or_path:
        return "__unknown__"
    m = _GITHUB_REPO.search(url_or_path)
    if m:
        return f"gh:{m.group(1).lower()}"
    try:
        netloc = urlparse(url_or_path).netloc.lower()
        if netloc:
            return netloc
    except Exception:
        pass
    return url_or_path.strip().lower()[:120]


@dataclass
class Candidate:
    """Thin adapter so the reranker doesn't care about upstream shape."""
    key: Any           # opaque id used to map back to caller's object
    score: float
    source: str        # already-bucketed source (see source_key)


def mmr_rerank(
    candidates: List[Candidate],
    top_k: int,
    lambda_penalty: float = 0.15,
    saturation: Callable[[int], float] = lambda k: math.log1p(k),
    min_score: float = -math.inf,
) -> List[Tuple[Candidate, float]]:
    """Greedy MMR over `candidates`, returning top_k with adjusted scores.

    Args:
        candidates: pre-sorted or unsorted — we don't assume order.
        top_k: number to keep.
        lambda_penalty: lambda in `adjusted = score - lambda * f(seen)`.
            0.15 dampens an 8-from-one-source bias without erasing
            strongly-relevant duplicates. Crank to 0.3 if one repo
            still dominates after eval.
        saturation: how the penalty grows with prior hits. log1p means
            penalty(1st duplicate) = ln2 ~= 0.69, penalty(5th) ~= 1.79.
        min_score: floor; rare safety net.

    Returns:
        List of (Candidate, adjusted_score) of length <= top_k.
    """
    if top_k <= 0 or not candidates:
        return []

    remaining = list(candidates)
    selected: List[Tuple[Candidate, float]] = []
    seen_by_source: dict[str, int] = {}

    while remaining and len(selected) < top_k:
        best_idx = -1
        best_adj = -math.inf
        for i, c in enumerate(remaining):
            k = seen_by_source.get(c.source, 0)
            adj = c.score - lambda_penalty * saturation(k)
            if adj > best_adj:
                best_adj = adj
                best_idx = i
        if best_idx < 0 or best_adj < min_score:
            break
        chosen = remaining.pop(best_idx)
        selected.append((chosen, best_adj))
        seen_by_source[chosen.source] = seen_by_source.get(chosen.source, 0) + 1

    return selected


def _extract_source(result: dict) -> Optional[str]:
    """Pull a source URL/string from either an ORM-object or dict
    parent_resource, matching the two shapes parent_child_search and
    parent_child_search_json produce."""
    parent = result.get("parent_resource")
    if isinstance(parent, dict):
        return parent.get("source") or parent.get("url")
    if parent is not None:
        # ORM object: prefer .source, fall back to .url
        return getattr(parent, "source", None) or getattr(parent, "url", None)
    chunk = result.get("chunk")
    if isinstance(chunk, dict):
        return chunk.get("github_uri")
    if chunk is not None:
        return getattr(chunk, "github_uri", None)
    return None


def rerank_search_results(
    results: List[dict],
    top_k: int,
    *,
    score_key: str = "score",
    lambda_penalty: float = 0.15,
) -> List[dict]:
    """Convenience wrapper for the dict shape `parent_child_search` returns.

    Mutates each kept dict to attach `mmr_score` and `source_bucket`
    so callers can log/inspect the rerank decision without re-deriving it.
    """
    if not results:
        return results
    cands = [
        Candidate(
            key=i,
            score=float(r.get(score_key, 0.0)),
            source=source_key(_extract_source(r)),
        )
        for i, r in enumerate(results)
    ]
    picked = mmr_rerank(cands, top_k=top_k, lambda_penalty=lambda_penalty)
    out: List[dict] = []
    for cand, adj in picked:
        r = results[cand.key]
        r["mmr_score"] = adj
        r["source_bucket"] = cand.source
        out.append(r)
    return out
