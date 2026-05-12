"""A/B harness for the per-source MMR reranker.

Why a fixture: per project_silent_pipeline_failure, prod dense
retrieval is currently FTS-only (worker dies on model load), so I
can't query live semantic scores. Instead, we synthesize the exact
adversarial case the reranker is meant to fix:

  - linux-kernel dominates with 8 of 10 hits in a tight score band
  - pflag has 1 hit, score slightly below the leader
  - ronin has 1 hit, lowest score

Baseline (no rerank) is just sort-by-score-desc. MMR is the function
from app.modules.search.diversity. We report:
  - top-3 / top-5 source diversity (unique buckets)
  - whether pflag / ronin appear in top-3 / top-5
  - the actual ordering, so we can eyeball regressions
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.search.diversity import rerank_search_results, source_key  # noqa: E402


def _make(score: float, src: str, label: str) -> dict:
    return {
        "score": score,
        "parent_resource": {"source": src, "title": label},
        "chunk": {"github_uri": src + "/file.py"},
    }


# Adversarial fixture: linux-kernel has 8 tightly-clustered hits at
# the top; pflag and ronin are present but bracketed below the cluster.
FIXTURE: List[dict] = [
    _make(0.92, "https://github.com/torvalds/linux", "linux:sched_fair"),
    _make(0.91, "https://github.com/torvalds/linux", "linux:mm_slab"),
    _make(0.90, "https://github.com/torvalds/linux", "linux:net_tcp"),
    _make(0.89, "https://github.com/torvalds/linux", "linux:fs_ext4"),
    _make(0.87, "https://github.com/spf13/pflag", "pflag:flag.go"),
    _make(0.86, "https://github.com/torvalds/linux", "linux:kernel_irq"),
    _make(0.85, "https://github.com/torvalds/linux", "linux:drivers_pci"),
    _make(0.84, "https://github.com/torvalds/linux", "linux:lib_idr"),
    _make(0.82, "https://github.com/torvalds/linux", "linux:block_bio"),
    _make(0.78, "https://github.com/ram-tewari/ronin", "ronin:agent_loop"),
]


def diversity(results: List[dict], k: int) -> int:
    """Unique source buckets in the top-k."""
    keys = {source_key(((r.get("parent_resource") or {}).get("source")))
            for r in results[:k]}
    return len(keys)


def contains_bucket(results: List[dict], k: int, needle: str) -> bool:
    for r in results[:k]:
        src = (r.get("parent_resource") or {}).get("source")
        if needle in (src or ""):
            return True
    return False


def baseline(results: List[dict]) -> List[dict]:
    return sorted(results, key=lambda r: r["score"], reverse=True)


def render(results: List[dict], score_field: str) -> str:
    lines = []
    for r in results:
        src = (r.get("parent_resource") or {}).get("source", "")
        title = (r.get("parent_resource") or {}).get("title", "")
        score = r.get(score_field, r.get("score"))
        lines.append(f"  {score:0.3f}  {title:<24}  ({src})")
    return "\n".join(lines)


def run() -> None:
    print("=" * 72)
    print("A/B: per-source MMR reranker (top_k=5)")
    print("=" * 72)
    print(f"Fixture: {len(FIXTURE)} candidates, 8 from linux, 1 pflag, 1 ronin")
    print()

    base = baseline(FIXTURE)
    print("BASELINE (sort by score desc):")
    print(render(base[:5], "score"))
    print(f"  top-3 unique sources: {diversity(base, 3)}")
    print(f"  top-5 unique sources: {diversity(base, 5)}")
    print(f"  pflag in top-3:  {contains_bucket(base, 3, 'pflag')}")
    print(f"  pflag in top-5:  {contains_bucket(base, 5, 'pflag')}")
    print(f"  ronin in top-5:  {contains_bucket(base, 5, 'ronin')}")
    print()

    print("Lambda sweep (top_k=5):")
    print(f"{'lambda':>8} | {'top3_div':>8} | {'top5_div':>8} | "
          f"{'pflag@3':>7} | {'pflag@5':>7} | {'ronin@5':>7}")
    print("-" * 72)
    for lam in [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50]:
        # rerank_search_results mutates dicts → deepcopy substitute via fresh build
        fresh = [
            {"score": r["score"],
             "parent_resource": dict(r["parent_resource"]),
             "chunk": dict(r["chunk"])}
            for r in FIXTURE
        ]
        out = rerank_search_results(fresh, top_k=5, lambda_penalty=lam)
        print(f"{lam:>8.2f} | "
              f"{diversity(out, 3):>8} | "
              f"{diversity(out, 5):>8} | "
              f"{str(contains_bucket(out, 3, 'pflag')):>7} | "
              f"{str(contains_bucket(out, 5, 'pflag')):>7} | "
              f"{str(contains_bucket(out, 5, 'ronin')):>7}")
    print()

    # Detailed ordering at the recommended lambda
    fresh = [
        {"score": r["score"],
         "parent_resource": dict(r["parent_resource"]),
         "chunk": dict(r["chunk"])}
        for r in FIXTURE
    ]
    out = rerank_search_results(fresh, top_k=5, lambda_penalty=0.15)
    print("MMR at lambda=0.15 (top 5):")
    print(render(out, "mmr_score"))
    print()

    # Sanity: pure-relevance edge case — when one source has the only
    # high-scoring hits, MMR must not over-suppress them.
    print("Sanity check: single-source dataset (no diversity to gain)")
    homo = [_make(0.9 - 0.01 * i, "https://github.com/torvalds/linux", f"f{i}")
            for i in range(5)]
    fresh = [
        {"score": r["score"],
         "parent_resource": dict(r["parent_resource"]),
         "chunk": dict(r["chunk"])}
        for r in homo
    ]
    out = rerank_search_results(fresh, top_k=3, lambda_penalty=0.15)
    print(f"  baseline top-3 sources: {diversity(baseline(homo), 3)}")
    print(f"  MMR top-3 sources:      {diversity(out, 3)}")
    print(f"  -> MMR returns 3 results (no candidates dropped): "
          f"{'PASS' if len(out) == 3 else 'FAIL'}")


if __name__ == "__main__":
    run()
