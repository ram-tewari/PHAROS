"""Retrieval quality, latency, indexing throughput and storage benchmark.

Indexes the pinned repositories of a dataset (``benchmarks/datasets``) through
the real pipeline (clone -> AST -> embed -> PostgreSQL), then for every
retrieval mode measures Recall@5/10, MRR, nDCG@10 (graded) and latency, plus
context size, storage footprint and query plans.

    cd backend
    python -m benchmarks.retrieval_eval \\
        --database-url postgresql://postgres:postgres@localhost:5432/pharos_bench \\
        --embedder hash --embedder onnx=/path/to/all-MiniLM-L6-v2/onnx \\
        --out benchmarks/results/run.json

The target database is DROPPED and recreated for every embedder; the script
refuses database names that do not contain "bench".
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.codeintel.context import ContextRequest, assemble_context  # noqa: E402
from app.codeintel.embeddings import Embedder, HashEmbedder, OnnxEmbedder  # noqa: E402
from app.codeintel.git_source import parse_repo_spec  # noqa: E402
from app.codeintel.indexer import CodeIndexer  # noqa: E402
from app.codeintel.retrieval import Filters, Retriever, is_test_path  # noqa: E402
from app.database.models import DocumentChunk, Repository, Resource  # noqa: E402
from app.shared.db_url import normalize_database_url  # noqa: E402

MODES = ("keyword", "dense", "hybrid", "graph", "auto")
PAIRS = (("dense", "keyword"), ("hybrid", "dense"), ("graph", "hybrid"), ("auto", "dense"), ("auto", "graph"))
#: ``auto`` with the caller's identifier / keyword guesses (``--hints``), scored when hints are given.
HINTED = "auto+hints"
K = 10
BOOTSTRAP = 2000
TABLES = ("document_chunks", "resources", "code_edges", "repositories", "ingestion_jobs")


# ── metrics ─────────────────────────────────────────────────────────────────


def ranked_symbols(hits) -> list[str]:
    """Distinct symbols in rank order (a symbol can appear once per chunk)."""
    seen, out = set(), []
    for h in hits:
        if h.symbol and h.symbol not in seen:
            seen.add(h.symbol)
            out.append(h.symbol)
    return out


def query_metrics(ranked: list[str], relevant: dict[str, int]) -> dict[str, float]:
    def recall(k: int) -> float:
        return sum(1 for s in relevant if s in ranked[:k]) / len(relevant)

    rr = 0.0
    for i, s in enumerate(ranked[:K], start=1):
        if s in relevant:
            rr = 1.0 / i
            break
    dcg = sum((2 ** relevant.get(s, 0) - 1) / math.log2(i + 1) for i, s in enumerate(ranked[:K], start=1))
    ideal = sorted(relevant.values(), reverse=True)[:K]
    idcg = sum((2**g - 1) / math.log2(i + 1) for i, g in enumerate(ideal, start=1))
    primary = {s for s, g in relevant.items() if g == 2}
    return {
        "recall@5": recall(5),
        "recall@10": recall(10),
        "mrr": rr,
        "ndcg@10": dcg / idcg if idcg else 0.0,
        "success@1": 1.0 if ranked[:1] and ranked[0] in primary else 0.0,
    }


def summarize(per_query: list[dict], seed: int = 0) -> dict:
    """Mean of each metric with a percentile-bootstrap 95% CI over queries."""
    out: dict[str, dict] = {}
    rng = random.Random(seed)
    n = len(per_query)
    for metric in per_query[0]:
        values = [q[metric] for q in per_query]
        means = sorted(statistics.fmean(rng.choices(values, k=n)) for _ in range(BOOTSTRAP))
        out[metric] = {
            "mean": round(statistics.fmean(values), 4),
            "ci95": [round(means[int(0.025 * BOOTSTRAP)], 4), round(means[int(0.975 * BOOTSTRAP) - 1], 4)],
        }
    return out


def paired_delta(a: list[float], b: list[float], n: int = 5000, seed: int = 1) -> dict:
    """Mean per-query difference a − b with a paired percentile-bootstrap 95% CI."""
    rng = random.Random(seed)
    d = [x - y for x, y in zip(a, b, strict=True)]
    means = sorted(statistics.fmean(rng.choices(d, k=len(d))) for _ in range(n))
    return {"delta": round(statistics.fmean(d), 4),
            "ci95": [round(means[int(0.025 * n)], 4), round(means[int(0.975 * n) - 1], 4)],
            "wins": sum(x > 0 for x in d), "losses": sum(x < 0 for x in d)}


_NOISE_PREFIXES = ("docs/", "doc/", "examples/", "example/", "test/", "tests/", "testdata/")


def is_noise_path(path: str) -> bool:
    """Tests, docs and examples: results that usually crowd out the implementation."""
    p = (path or "").lower()
    return is_test_path(path) or p.startswith(_NOISE_PREFIXES) or "/examples/" in p or "/docs/" in p


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return round(s[min(len(s) - 1, max(0, math.ceil(p / 100 * len(s)) - 1))], 2)


# ── setup ───────────────────────────────────────────────────────────────────


def reset_database(url: str) -> None:
    from alembic.config import Config

    from alembic import command

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    with engine.begin() as conn:
        cfg = Config(str(BACKEND / "config" / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "alembic"))
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    engine.dispose()


def make_embedder(spec: str) -> Embedder:
    if spec == "hash":
        return HashEmbedder()
    if spec.startswith("onnx="):
        path = spec.split("=", 1)[1]
        # The model id comes from the directory's pharos_model.json when there is one.
        return OnnxEmbedder(path, model_id=os.getenv("BENCH_ONNX_MODEL_ID"))
    raise SystemExit(f"unknown embedder {spec!r} (use 'hash' or 'onnx=<dir>')")


def pinned_clone(repo: dict, workdir: Path, by_commit: bool = False) -> Path:
    """A working tree at the dataset's commit (raw-size and content counterfactual).

    ``by_commit`` fetches the pinned commit itself, so a branch that has moved on
    since the dataset was written still benchmarks the same code.
    """
    dest = workdir / repo["name"]
    if not dest.exists() and by_commit:
        subprocess.run(["git", "init", "-q", str(dest)], check=True)
        subprocess.run(["git", "-C", str(dest), "fetch", "-q", "--depth", "1", repo["url"], repo["commit"]],
                       check=True, timeout=600)
        subprocess.run(["git", "-C", str(dest), "checkout", "-q", "FETCH_HEAD"], check=True)
    elif not dest.exists():
        subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", repo["ref"], repo["url"], str(dest)],
                       check=True, timeout=600)
    head = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    if head != repo["commit"]:
        raise SystemExit(f"{repo['name']}: {repo['ref']} is {head}, dataset pins {repo['commit']}")
    return dest


def environment(db: Session) -> dict:
    def cmd(*args):
        try:
            return subprocess.run(args, capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            return None

    cpu = next((line.split(":", 1)[1].strip() for line in (cmd("lscpu") or "").splitlines()
                if line.startswith("Model name")), platform.processor())
    mem = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    try:
        import onnxruntime

        ort = onnxruntime.__version__
    except ImportError:
        ort = None
    return {
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "cpu": cpu,
        "cpus": os.cpu_count(),
        "memory_gib": round(mem, 1),
        "python": platform.python_version(),
        "postgres": db.execute(text("SHOW server_version")).scalar_one(),
        "pgvector": db.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'")).scalar_one(),
        "onnxruntime": ort,
        "pharos_commit": cmd("git", "-C", str(BACKEND), "rev-parse", "HEAD"),
        "gpu": "none (CPU only)",
    }


# ── measurements ────────────────────────────────────────────────────────────


def index_repositories(factory, dataset: dict, embedder: Embedder, clones: dict[str, Path] | None = None
                       ) -> tuple[dict, dict]:
    """Index each dataset repository: from GitHub at its ref, or from ``clones`` (pinned local checkouts)."""
    stats, repos = {}, {}
    for repo in dataset["repositories"]:
        if clones:
            ref = parse_repo_spec(str(clones[repo["name"]]), allowed_hosts=[], allow_local=True)
        else:
            ref = parse_repo_spec(repo["url"], allowed_hosts=["github.com"])
        with factory() as db:
            t0 = time.perf_counter()
            branch = None if clones else repo["ref"]
            s = CodeIndexer(db, embedder, clone_timeout=600).index(ref, branch=branch)
            wall = time.perf_counter() - t0
            if s.commit_sha != repo["commit"]:
                raise SystemExit(f"{repo['name']}: indexed {s.commit_sha}, dataset pins {repo['commit']}")
            row = db.execute(select(Repository).where(Repository.url == ref.canonical_url)).scalar_one()
            repos[repo["name"]] = row.id
            d = s.as_dict()
            stats[repo["name"]] = {
                "wall_seconds": round(wall, 2),
                "files_indexed": d["files_indexed"],
                "files_skipped": dict(d["skipped"]),
                "chunks": d["chunks_total"],
                "lines": d["lines_indexed"],
                "source_bytes": d["source_bytes_indexed"],
                "graph": d["graph"],
                "timings_s": d["timings_s"],
                "files_per_second": round(d["files_indexed"] / wall, 1),
                "chunks_per_second": round(d["chunks_total"] / wall, 1),
                "fallback_files": {k: v["fallback_files"] for k, v in d["languages"].items()},
            }
    return stats, repos


def evaluate(factory, dataset: dict, embedder: Embedder, repo_ids: dict, repeats: int,
             hints: dict[str, list[str]] | None = None) -> dict:
    results = {}
    with factory() as db:
        retriever = Retriever(db, embedder)
        # Query-embedding cost on its own (part of dense/hybrid/graph latency).
        embed_ms = []
        for q in dataset["queries"]:
            t0 = time.perf_counter()
            embedder.embed_query(q["query"])
            embed_ms.append((time.perf_counter() - t0) * 1000)
        for label in MODES + ((HINTED,) if hints else ()):
            mode = "auto" if label == HINTED else label
            per_query, latencies, rows, noise = [], [], [], []
            for q in dataset["queries"]:
                filters = Filters(repository_ids=[repo_ids[q["repo"]]])
                q_hints = hints.get(q["id"]) if label == HINTED else None
                retriever.search(q["query"], mode=mode, k=K, filters=filters, hints=q_hints)  # warm-up
                times, outcome = [], None
                for _ in range(repeats):
                    t0 = time.perf_counter()
                    outcome = retriever.search(q["query"], mode=mode, k=K, filters=filters, hints=q_hints)
                    times.append((time.perf_counter() - t0) * 1000)
                ranked = ranked_symbols(outcome.hits)
                m = query_metrics(ranked, q["relevant"])
                per_query.append(m)
                latencies.append(statistics.median(times))
                top5 = [h.path for h in outcome.hits[:5]]
                noise.append(sum(map(is_noise_path, top5)) / len(top5) if top5 else 0.0)
                rows.append({"id": q["id"], "category": q["category"], "mode_used": outcome.mode_used,
                             "top5": ranked[:5], **{k: round(v, 3) for k, v in m.items()}})
            by_cat = {}
            for cat in sorted({q["category"] for q in dataset["queries"]}):
                idx = [i for i, q in enumerate(dataset["queries"]) if q["category"] == cat]
                by_cat[cat] = {"n": len(idx), **summarize([per_query[i] for i in idx])}
            by_repo = {}
            for repo in repo_ids:
                idx = [i for i, q in enumerate(dataset["queries"]) if q["repo"] == repo]
                by_repo[repo] = {"n": len(idx), **summarize([per_query[i] for i in idx])}
            results[label] = {
                "overall": {"n": len(per_query), **summarize(per_query)},
                "by_category": by_cat,
                "by_repository": by_repo,
                "latency_ms": {"p50": pct(latencies, 50), "p95": pct(latencies, 95), "max": pct(latencies, 100)},
                "top5_noise_share": round(statistics.fmean(noise), 3),
                "queries": rows,
            }
        results["paired_ndcg"] = {f"{a}-{b}": paired_delta([r["ndcg@10"] for r in results[a]["queries"]],
                                                           [r["ndcg@10"] for r in results[b]["queries"]])
                                  for a, b in PAIRS + (((HINTED, "auto"),) if hints else ())}
        results["query_embedding_ms"] = {"p50": pct(embed_ms, 50), "p95": pct(embed_ms, 95)}
        results["ann"] = ann_quality(db, retriever, dataset, repo_ids)
    return results


def ann_quality(db: Session, retriever: Retriever, dataset: dict, repo_ids: dict, limit: int = 50) -> dict:
    """HNSW vs exact search for the dense candidate set.

    pgvector (< 0.8) applies WHERE filters after the HNSW graph search, so a
    filtered query can return fewer than ``limit`` candidates; and HNSW is
    approximate. Both are measured against an exact scan.
    """
    returned, overlap = [], []
    for q in dataset["queries"]:
        filters = Filters(repository_ids=[repo_ids[q["repo"]]])
        qvec = retriever.embedder.embed_query(q["query"])
        approx = [cid for cid, _ in retriever._dense(qvec, filters, limit)]
        db.execute(text("SET LOCAL enable_indexscan = off"))
        exact = [cid for cid, _ in retriever._dense(qvec, filters, limit)]
        db.rollback()
        returned.append(len(approx))
        overlap.append(len(set(approx) & set(exact)) / max(1, len(exact)))
    return {
        "requested": limit,
        "returned_min": min(returned),
        "returned_median": statistics.median(returned),
        "hnsw_recall_vs_exact_mean": round(statistics.fmean(overlap), 4),
        "hnsw_recall_vs_exact_min": round(min(overlap), 4),
    }


def context_sizes(factory, dataset: dict, embedder: Embedder) -> dict:
    chars, chunks, ms, verified, total = [], [], [], 0, 0
    with factory() as db:
        for q in dataset["queries"]:
            t0 = time.perf_counter()
            out = assemble_context(db, embedder, ContextRequest(query=q["query"], repository=q["repo"]),
                                   fetch_token=None)
            ms.append((time.perf_counter() - t0) * 1000)
            chars.append(len(out["context_text"]))
            chunks.append(len(out["chunks"]))
            total += len(out["chunks"])
            verified += sum(1 for c in out["chunks"] if c.get("verified"))
    return {
        "settings": "defaults: max_chunks=8, max_chars=24000, include_code/related/rules",
        "context_chars": {"p50": pct(chars, 50), "p95": pct(chars, 95), "max": max(chars)},
        "approx_tokens_p50": round(pct(chars, 50) / 4),
        "approx_tokens_note": "chars/4 heuristic, not a tokenizer count",
        "chunks_per_context_p50": pct(chunks, 50),
        "code_verified_fraction": round(verified / total, 3) if total else None,
        "latency_ms_including_code_fetch": {"p50": pct(ms, 50), "p95": pct(ms, 95)},
    }


def storage(factory, clones: dict[str, Path], repo_ids: dict) -> dict:
    engine = factory.kw["bind"]
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for t in TABLES:
            conn.execute(text(f"VACUUM (FULL, ANALYZE) {t}"))
        sizes = {}
        for t in TABLES:
            row = conn.execute(text(
                "SELECT pg_table_size(:t), pg_indexes_size(:t), pg_total_relation_size(:t)"
            ), {"t": t}).one()
            sizes[t] = {"table_bytes": row[0], "index_bytes": row[1], "total_bytes": row[2]}
        idx = dict(conn.execute(text(
            "SELECT indexname, pg_relation_size(quote_ident(indexname)::regclass) FROM pg_indexes "
            "WHERE tablename IN ('document_chunks','resources') ORDER BY 2 DESC"
        )).all())
        chunk_cols = conn.execute(text(
            "SELECT avg(pg_column_size(embedding)), avg(pg_column_size(search_text)), "
            "avg(pg_column_size(semantic_summary)), avg(pg_column_size(chunk_metadata)), count(*) "
            "FROM document_chunks"
        )).one()
    footprint = sum(s["total_bytes"] for s in sizes.values())

    # Counterfactual: the same rows with each chunk's source stored in
    # document_chunks.content (what "full content" storage would add).
    raw_bytes = 0
    with factory() as db:
        rows = db.execute(
            select(DocumentChunk.id, DocumentChunk.start_line, DocumentChunk.end_line, Resource.identifier,
                   DocumentChunk.repository_id)
            .join(Resource, Resource.id == DocumentChunk.resource_id)
        ).all()
        name_of = {rid: name for name, rid in repo_ids.items()}
        rows = [(cid, s, e, path, name_of[rid]) for cid, s, e, path, rid in rows]
        files: dict[tuple[str, str], list[str]] = {}
        for _, _, _, path, repo in rows:
            key = (repo, path)
            if key not in files:
                data = (clones[repo] / path).read_bytes()
                raw_bytes += len(data)
                files[key] = data.decode("utf-8", errors="replace").splitlines(keepends=True)
    engine = factory.kw["bind"]
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS bench_chunks_with_content"))
        conn.execute(text("CREATE TABLE bench_chunks_with_content AS TABLE document_chunks"))
        conn.execute(text("CREATE TEMP TABLE bench_content (id uuid PRIMARY KEY, content text)"))
        payload = [{"id": cid, "c": "".join(files[(repo, path)][(s or 1) - 1:(e or 1)])}
                   for cid, s, e, path, repo in rows]
        for i in range(0, len(payload), 500):
            conn.execute(text("INSERT INTO bench_content VALUES (:id, :c)"), payload[i:i + 500])
        conn.execute(text("UPDATE bench_chunks_with_content b SET content = c.content "
                          "FROM bench_content c WHERE b.id = c.id"))
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("VACUUM (FULL, ANALYZE) bench_chunks_with_content"))
        with_content = conn.execute(text("SELECT pg_table_size('bench_chunks_with_content')")).scalar_one()
        content_avg = conn.execute(text(
            "SELECT avg(pg_column_size(content)), avg(octet_length(content)) FROM bench_chunks_with_content"
        )).one()
        conn.execute(text("DROP TABLE bench_chunks_with_content"))
    added = with_content - sizes["document_chunks"]["table_bytes"]
    return {
        "tables": sizes,
        "indexes": idx,
        "footprint_bytes": footprint,
        "raw_source_bytes_of_indexed_files": raw_bytes,
        "per_chunk_avg_bytes": {
            "embedding": round(float(chunk_cols[0] or 0)), "search_text": round(float(chunk_cols[1] or 0)),
            "semantic_summary": round(float(chunk_cols[2] or 0)), "chunk_metadata": round(float(chunk_cols[3] or 0)),
            "content_if_stored_on_disk": round(float(content_avg[0] or 0)),
            "content_if_stored_raw": round(float(content_avg[1] or 0)),
        },
        "chunks": chunk_cols[4],
        "counterfactual_content_in_chunks": {
            "document_chunks_table_bytes_with_content": with_content,
            "added_bytes": added,
            "footprint_with_content_bytes": footprint + added,
            "ratio_full_over_hybrid": round((footprint + added) / footprint, 3),
        },
        "ratio_raw_source_over_footprint": round(raw_bytes / footprint, 3),
    }


def _plan_nodes(node: dict) -> list[str]:
    here = node["Node Type"] + (f" on {node['Index Name']}" if "Index Name" in node else "")
    return [here] + [n for child in node.get("Plans", []) for n in _plan_nodes(child)]


def query_plans(factory, embedder: Embedder, repo_ids: dict) -> dict:
    """Which index the planner uses for the dense and keyword candidate queries."""
    from app.codeintel.retrieval import CHUNK_TSVECTOR_SQL
    from app.shared.vector_type import to_vector_literal

    vec = to_vector_literal(embedder.embed_query("parse command line flags"))
    repo = str(next(iter(repo_ids.values())))
    sql = {
        "dense": ("SELECT id FROM document_chunks WHERE embedding_model = :m AND repository_id = :r "
                  "ORDER BY embedding <=> CAST(:v AS vector) LIMIT 50"),
        "dense_unfiltered": "SELECT id FROM document_chunks ORDER BY embedding <=> CAST(:v AS vector) LIMIT 50",
        "keyword": (f"SELECT id FROM document_chunks WHERE repository_id = :r AND {CHUNK_TSVECTOR_SQL} "
                    "@@ to_tsquery('simple', 'parse | flag') LIMIT 50"),
    }
    out = {}
    with factory() as db:
        for name, q in sql.items():
            plan = db.execute(text("EXPLAIN (FORMAT JSON) " + q),
                              {"m": embedder.model_id, "r": repo, "v": vec}).scalar_one()
            out[name] = _plan_nodes(plan[0]["Plan"])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database-url", required=True)
    ap.add_argument("--dataset", default=str(BACKEND / "benchmarks" / "datasets" / "codeqa_v1.json"))
    ap.add_argument("--embedder", action="append", required=True, help="'hash' or 'onnx=<model dir>'")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--workdir", default=None, help="where to keep pinned clones")
    ap.add_argument("--hints", help="JSON {query id: [identifier / keyword guesses]}; adds the auto+hints mode")
    ap.add_argument("--local-checkouts", action="store_true",
                    help="fetch each repository's pinned commit and index that checkout, instead of the ref on GitHub")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    url = normalize_database_url(args.database_url, async_driver=False)
    if "bench" not in url.rsplit("/", 1)[-1]:
        raise SystemExit("refusing to reset a database whose name does not contain 'bench'")
    dataset = json.loads(Path(args.dataset).read_text())
    workdir = Path(args.workdir or tempfile.mkdtemp(prefix="pharos_bench_"))
    clones = {r["name"]: pinned_clone(r, workdir, by_commit=args.local_checkouts) for r in dataset["repositories"]}

    report = {"dataset": {k: dataset[k] for k in ("name", "version", "labeling", "repositories")},
              "n_queries": len(dataset["queries"]), "k": K, "repeats": args.repeats, "runs": {}}
    for spec in args.embedder:
        embedder = make_embedder(spec)
        print(f"== {embedder.model_id}: resetting database and indexing", flush=True)
        reset_database(url)
        engine = create_engine(url)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as db:
            report.setdefault("environment", environment(db))
        indexing, repo_ids = index_repositories(factory, dataset, embedder,
                                                clones if args.local_checkouts else None)
        print(f"   indexed: {json.dumps({k: v['wall_seconds'] for k, v in indexing.items()})}", flush=True)
        hints = json.loads(Path(args.hints).read_text()) if args.hints else None
        retrieval = evaluate(factory, dataset, embedder, repo_ids, args.repeats, hints)
        for mode in MODES + ((HINTED,) if hints else ()):
            o = retrieval[mode]["overall"]
            print(f"   {mode:8s} R@10={o['recall@10']['mean']:.3f} MRR={o['mrr']['mean']:.3f} "
                  f"nDCG@10={o['ndcg@10']['mean']:.3f} {o['ndcg@10']['ci95']} "
                  f"noise@5={retrieval[mode]['top5_noise_share']} p50={retrieval[mode]['latency_ms']['p50']}ms",
                  flush=True)
        for pair, d in retrieval["paired_ndcg"].items():
            print(f"   {pair:15s} Δ nDCG@10 {d['delta']:+.4f} {d['ci95']} ({d['wins']}W/{d['losses']}L)", flush=True)
        run = {
            "embedder": {"spec": spec if spec == "hash" else "onnx", "model_id": embedder.model_id,
                         "semantic": embedder.semantic},
            "indexing": indexing,
            "retrieval": retrieval,
            "context": context_sizes(factory, dataset, embedder),
            "query_plans": query_plans(factory, embedder, repo_ids),
            "storage": storage(factory, clones, repo_ids),
        }
        report["runs"][embedder.model_id] = run
        engine.dispose()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=1, default=str))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
