"""Score a retrieval dataset against a running deployment over HTTP.

Checks that the deployment indexed each dataset repository at the pinned
commit, then runs every query in every mode through ``POST /api/v1/search/code``
and scores it with the same metrics as ``retrieval_eval``. Reports client-side
latency (network included) and the server's own ``timings_ms``.

    cd backend
    python -m benchmarks.prod_eval --dataset benchmarks/datasets/heldout_v1.json \\
        --env-file ~/.pharos-deploy.env --out benchmarks/results/heldout_v1_prod.json

The env file needs PHAROS_SERVICE_URL and PHAROS_READ_TOKEN (KEY='value' lines).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from benchmarks.retrieval_eval import K, paired_delta, pct, query_metrics, summarize  # noqa: E402

MODES = ("keyword", "dense", "hybrid", "graph", "auto")


def read_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("'\"")
    return env


class Client:
    def __init__(self, base_url: str, token: str):
        self.base, self.token = base_url.rstrip("/"), token

    def call(self, method: str, path: str, body: dict | None = None, timeout: float = 180) -> tuple[dict, float]:
        req = urllib.request.Request(
            self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
            headers={"content-type": "application/json", "authorization": f"Bearer {self.token}"})
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"{method} {path}: HTTP {exc.code} {exc.read()[:300]!r}") from exc
        return data, (time.perf_counter() - t0) * 1000


def repo_name(url: str) -> str:
    """'https://github.com/pallets/click' -> 'pallets/click' (the deployment's repository name)."""
    return urlparse(url).path.strip("/").removesuffix(".git")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--env-file", default=str(Path.home() / ".pharos-deploy.env"))
    ap.add_argument("--mode", action="append", choices=MODES, help="modes to score (default: all)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    dataset = json.loads(Path(args.dataset).read_text())
    env = read_env(Path(args.env_file).expanduser())
    client = Client(env["PHAROS_SERVICE_URL"], env["PHAROS_READ_TOKEN"])

    t0 = time.perf_counter()
    urllib.request.urlopen(client.base + "/health", timeout=180).read()
    wake_s = round(time.perf_counter() - t0, 1)
    listed, _ = client.call("GET", "/api/v1/repositories")
    listed = listed if isinstance(listed, list) else listed.get("repositories", [])
    commits = {r["name"]: r.get("last_commit_sha") for r in listed}
    names = {r["name"]: repo_name(r["url"]) for r in dataset["repositories"]}
    for r in dataset["repositories"]:
        if commits.get(names[r["name"]]) != r["commit"]:
            raise SystemExit(f"{names[r['name']]}: deployment has {commits.get(names[r['name']])}, "
                             f"dataset pins {r['commit']}")
    print(f"wake {wake_s}s; deployment commits match the dataset", flush=True)
    client.call("POST", "/api/v1/search/code", {"query": "warm up", "k": 3})

    report = {"dataset": dataset["name"], "version": dataset["version"], "base_url": client.base,
              "wake_seconds": wake_s, "k": K, "modes": {}}
    for mode in args.mode or MODES:
        per_query, client_ms, server_ms, rows = [], [], [], []
        for q in dataset["queries"]:
            body = {"query": q["query"], "repository": names[q["repo"]], "mode": mode, "k": K}
            data, ms = client.call("POST", "/api/v1/search/code", body)
            seen, ranked = set(), []
            for hit in data["results"]:
                symbol = hit.get("symbol")
                if symbol and symbol not in seen:
                    seen.add(symbol)
                    ranked.append(symbol)
            m = query_metrics(ranked, q["relevant"])
            per_query.append(m)
            client_ms.append(ms)
            server_ms.append(data.get("timings_ms", {}).get("total", 0.0))
            rows.append({"id": q["id"], "mode_used": data.get("mode_used"), "top3": ranked[:3],
                         **{k: round(v, 3) for k, v in m.items()}})
        o = summarize(per_query)
        report["modes"][mode] = {"overall": o, "queries": rows,
                                 "client_ms": {"p50": pct(client_ms, 50), "p95": pct(client_ms, 95)},
                                 "server_ms": {"p50": pct(server_ms, 50), "p95": pct(server_ms, 95)}}
        print(f"{mode:8s} R@10={o['recall@10']['mean']:.3f} MRR={o['mrr']['mean']:.3f} "
              f"nDCG@10={o['ndcg@10']['mean']:.3f} {o['ndcg@10']['ci95']} "
              f"server p50/p95={pct(server_ms, 50)}/{pct(server_ms, 95)}ms "
              f"client p50/p95={pct(client_ms, 50)}/{pct(client_ms, 95)}ms", flush=True)
    scored = report["modes"]
    if "dense" in scored and "auto" in scored:
        report["auto_minus_dense"] = paired_delta([r["ndcg@10"] for r in scored["auto"]["queries"]],
                                                  [r["ndcg@10"] for r in scored["dense"]["queries"]])
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=1))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
