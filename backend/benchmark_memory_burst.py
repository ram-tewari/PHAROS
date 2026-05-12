"""
Memory burst benchmark for /api/search/advanced — remote Render edition.

Fires 15 concurrent parent-child requests against the live Render API and
measures:
  • client-side Python peak heap (tracemalloc)
  • response-size distribution (proxy for server JSON pressure)
  • latency distribution + HTTP status mix

Server RSS cannot be sampled externally; the 502/503 mix and tail-latency
shape are the externally-visible OOM tells on Render's free tier.

Run:
    python backend/benchmark_memory_burst.py
"""
from __future__ import annotations

import asyncio
import os
import statistics
import time
import tracemalloc
from pathlib import Path
from typing import Any

import httpx

ENDPOINT = "https://pharos-cloud-api.onrender.com/api/search/advanced"
CONCURRENCY = 15
TIMEOUT_S = 90.0  # Render free tier can cold-start; first req may sit in queue


def _load_bearer_token() -> str | None:
    """Prefer env override; otherwise pull PHAROS_ADMIN_TOKEN from backend/.env."""
    for var in ("PHAROS_API_KEY", "PHAROS_ADMIN_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() in ("PHAROS_API_KEY", "PHAROS_ADMIN_TOKEN"):
                return v.strip().strip('"').strip("'")
    return None


BEARER = _load_bearer_token()
AUTH_HEADERS = {"Authorization": f"Bearer {BEARER}"} if BEARER else {}

PAYLOAD: dict[str, Any] = {
    "query": "asyncpg connection pool cleanup on shutdown",
    "strategy": "parent-child",
    "top_k": 10,
    "context_window": 2,
    "include_code": False,
}


async def _one_request(client: httpx.AsyncClient, idx: int) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        r = await client.post(
            ENDPOINT, json=PAYLOAD, headers=AUTH_HEADERS, timeout=TIMEOUT_S
        )
        elapsed = (time.perf_counter() - t0) * 1000
        return {
            "idx": idx,
            "status": r.status_code,
            "bytes": len(r.content),
            "ms": elapsed,
            "ok": r.status_code == 200,
        }
    except Exception as exc:
        return {
            "idx": idx,
            "status": 0,
            "bytes": 0,
            "ms": (time.perf_counter() - t0) * 1000,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def main() -> int:
    print(f"target   : {ENDPOINT}")
    print(f"burst    : {CONCURRENCY} concurrent")
    print(f"payload  : strategy=parent-child top_k=10 context_window=2")
    print(f"auth     : {'bearer token loaded' if BEARER else 'NO TOKEN — expect 401'}")
    print()

    # Warm-up: Render free tier sleeps after 15 min idle; fire one request
    # first so the 502/503 mix isn't dominated by cold-start, not OOM.
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as warm:
        print("warming up Render dyno...")
        wt0 = time.perf_counter()
        try:
            wr = await warm.get(
                "https://pharos-cloud-api.onrender.com/api/search/search/health",
                headers=AUTH_HEADERS,
            )
            print(f"  warm-up status={wr.status_code} "
                  f"in {(time.perf_counter()-wt0)*1000:.0f} ms")
        except Exception as exc:
            print(f"  warm-up failed: {type(exc).__name__}: {exc}")

    tracemalloc.start()

    limits = httpx.Limits(
        max_connections=CONCURRENCY * 2,
        max_keepalive_connections=CONCURRENCY,
    )
    async with httpx.AsyncClient(limits=limits) as client:
        wall_t0 = time.perf_counter()
        results = await asyncio.gather(
            *[_one_request(client, i) for i in range(CONCURRENCY)]
        )
        wall_ms = (time.perf_counter() - wall_t0) * 1000

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    ok = sum(1 for r in results if r["ok"])
    fail = CONCURRENCY - ok
    latencies = [r["ms"] for r in results if r["ok"]]
    sizes = [r["bytes"] for r in results if r["ok"]]

    # Bucket failures by status so OOM (502/503) is distinguishable from
    # timeouts and 4xx.
    status_mix: dict[int, int] = {}
    for r in results:
        status_mix[r["status"]] = status_mix.get(r["status"], 0) + 1

    print()
    print("=" * 68)
    print(f"BURST RESULT — {CONCURRENCY} concurrent requests")
    print("=" * 68)
    print(f"  wall time           : {wall_ms:8.1f} ms")
    print(f"  success / fail      : {ok} / {fail}")
    print(f"  status mix          : {status_mix}")
    for r in results:
        if not r["ok"]:
            print(f"    req#{r['idx']:02d}  status={r['status']:>3}  "
                  f"{r['ms']:7.0f} ms  err={r.get('error', '')}")
    if latencies:
        print(f"  latency p50 / p95   : {statistics.median(latencies):7.1f} ms / "
              f"{sorted(latencies)[max(0,int(len(latencies)*0.95)-1)]:7.1f} ms")
        print(f"  latency min / max   : {min(latencies):7.1f} ms / "
              f"{max(latencies):7.1f} ms")
        print(f"  payload avg / max   : {statistics.mean(sizes)/1024:6.2f} KB / "
              f"{max(sizes)/1024:6.2f} KB")
    print()
    print("  CLIENT (tracemalloc)")
    print(f"    current heap      : {current/1024/1024:6.2f} MB")
    print(f"    PEAK heap         : {peak/1024/1024:6.2f} MB")
    print()
    # External OOM signal: any 502/503 means Render killed/recycled the dyno
    # mid-burst. Timeouts (status=0) on the free tier are usually upstream
    # queue saturation, not OOM directly.
    oom_count = status_mix.get(502, 0) + status_mix.get(503, 0)
    if oom_count:
        print(f"  VERDICT: FAIL — {oom_count} response(s) returned 502/503 "
              "(Render OOM/restart signal)")
        return 1
    if fail:
        print(f"  VERDICT: PARTIAL — all 200s, but {fail} non-200 (non-OOM) failures")
        return 1
    print("  VERDICT: PASS — 15/15 returned 200, no 502/503, no timeouts")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
