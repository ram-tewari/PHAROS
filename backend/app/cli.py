"""``pharos`` command-line interface.

Run from ``backend/`` (or via ``make``)::

    python -m app.cli doctor                      # check configuration and dependencies
    python -m app.cli ingest ../path/to/repo      # index a local git repository now
    python -m app.cli ingest github.com/owner/repo --queue   # leave it to a worker
    python -m app.cli search "where are passwords verified" --repo tinyshop
    python -m app.cli context "how does checkout work" --repo tinyshop
    python -m app.cli symbol TokenSigner.verify
    python -m app.cli repos | jobs | worker | gen-token

Local repositories can only be registered here — never through the API — so
API callers cannot point the worker at arbitrary paths on its filesystem.
"""

from __future__ import annotations

import argparse
import json
import logging
import secrets
import shutil
import sys
from pathlib import Path

from .config.settings import get_settings


def _print(data, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(data)


def cmd_ingest(args) -> int:
    from .codeintel import jobs
    from .codeintel.embeddings import get_embedder
    from .codeintel.git_source import RepoSpecError, parse_repo_spec
    from .codeintel.notify import get_notifier
    from .codeintel.runtime import run_options, session_scope

    settings = get_settings()
    try:
        ref = parse_repo_spec(args.repository, allowed_hosts=settings.CODEINTEL_ALLOWED_GIT_HOSTS, allow_local=True)
    except RepoSpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    with session_scope() as db:
        submission = jobs.submit(db, ref, args.branch, force=args.force)
        job = submission.job
        if not submission.created:
            print(f"An ingestion job for {ref.canonical_url} is already {job.status}: {job.id}", file=sys.stderr)
            return 1
        if args.queue:
            notified = get_notifier(settings).notify(str(job.id))
            _print({"job_id": str(job.id), "status": job.status, "notified": notified}, True)
            return 0
        claimed = jobs.claim(db, job.id, worker_id="cli")
        if claimed is None:
            print("error: job was claimed by a worker before the CLI could run it", file=sys.stderr)
            return 1
        job = jobs.run(db, claimed, ref, get_embedder(settings), **run_options())
        summary = {
            "job_id": str(job.id),
            "status": job.status,
            "repository": ref.canonical_url,
            "commit_sha": job.commit_sha,
            "error": job.error,
        }
        if job.stats:
            st = job.stats
            summary |= {
                "outcome": st.get("outcome"),
                "files_indexed": st.get("files_indexed"),
                "files_unchanged": st.get("files_unchanged"),
                "files_deleted": st.get("files_deleted"),
                "chunks_total": st.get("chunks_total"),
                "embedding_model": st.get("embedding_model"),
                "languages": {
                    k: {"files": v["files"], "ast": v["ast_files"], "fallback": v["fallback_files"]}
                    for k, v in (st.get("languages") or {}).items()
                },
                "graph_edges": (st.get("graph") or {}).get("edges"),
                "skipped": st.get("skipped"),
                "seconds": (st.get("timings_s") or {}).get("total"),
            }
        _print(summary, True)
        return 0 if job.status == "succeeded" else 1


def cmd_search(args) -> int:
    from .codeintel.context import hit_to_dict, resolve_repositories
    from .codeintel.embeddings import get_embedder
    from .codeintel.retrieval import Filters, ModeUnavailable, Retriever
    from .codeintel.runtime import session_scope

    with session_scope() as db:
        repos = resolve_repositories(db, args.repo)
        try:
            outcome = Retriever(db, get_embedder()).search(
                args.query, mode=args.mode, k=args.k,
                filters=Filters(repository_ids=[r.id for r in repos] or None, languages=args.language),
            )
        except ModeUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        if args.json:
            _print({"mode_used": outcome.mode_used, "warnings": outcome.warnings,
                    "results": [hit_to_dict(h, i) for i, h in enumerate(outcome.hits, 1)],
                    "timings_ms": outcome.timings_ms}, True)
            return 0
        for w in outcome.warnings:
            print(f"warning: {w}", file=sys.stderr)
        print(f"mode={outcome.mode_used} ({outcome.timings_ms.get('total', 0):.1f} ms)")
        for i, h in enumerate(outcome.hits, 1):
            ev = h.evidence
            print(f"{i:2}. {h.score:.4f}  {h.path}:{h.start_line}-{h.end_line}  {h.symbol}  [{h.kind}, {h.parser}]"
                  f"  kw={ev.keyword_rank} dense={ev.dense_rank}{' graph' if ev.graph else ''}")
        return 0


def cmd_context(args) -> int:
    from .codeintel.context import ContextRequest, assemble_context
    from .codeintel.embeddings import get_embedder
    from .codeintel.runtime import secret, session_scope

    with session_scope() as db:
        result = assemble_context(
            db, get_embedder(),
            ContextRequest(query=args.query, repository=args.repo, max_chunks=args.k, mode=args.mode),
            fetch_token=secret(get_settings().GIT_CLONE_TOKEN),
        )
    if args.json:
        _print(result, True)
    else:
        for w in result["warnings"]:
            print(f"warning: {w}", file=sys.stderr)
        print(result["context_text"])
    return 0


def cmd_symbol(args) -> int:
    from .codeintel.context import resolve_repositories
    from .codeintel.runtime import session_scope
    from .codeintel.symbols import chunk_ref, find_symbol, symbol_graph

    with session_scope() as db:
        repos = resolve_repositories(db, args.repo)
        matches = find_symbol(db, args.name, repository_ids=[r.id for r in repos] or None)
        _print([chunk_ref(c) | {"graph": symbol_graph(db, c.id)} for c in matches], True)
    return 0 if matches else 1


def cmd_repos(args) -> int:
    from sqlalchemy import select

    from .codeintel.runtime import session_scope
    from .codeintel.symbols import repository_summary
    from .database.models import Repository

    with session_scope() as db:
        repos = db.execute(select(Repository).order_by(Repository.name)).scalars().all()
        _print([repository_summary(db, r) for r in repos], True)
    return 0


def cmd_jobs(args) -> int:
    from sqlalchemy import select

    from .codeintel.runtime import session_scope
    from .database.models import IngestionJob

    with session_scope() as db:
        stmt = select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(args.limit)
        if args.status:
            stmt = stmt.where(IngestionJob.status == args.status)
        rows = [
            {"id": str(j.id), "repo_url": j.repo_url, "status": j.status, "attempts": j.attempts,
             "error_kind": j.error_kind, "commit_sha": j.commit_sha, "created_at": j.created_at}
            for j in db.execute(stmt).scalars()
        ]
    _print(rows, True)
    return 0


def cmd_worker(args) -> int:
    from .workers.ingest_worker import main as worker_main

    return worker_main(["--once"] if args.once else [])


def cmd_gen_token(_args) -> int:
    print(secrets.token_hex(32))
    return 0


def _migration_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "config" / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def cmd_doctor(_args) -> int:
    """Report on everything the core workflow needs. Exit 1 on hard failures."""
    from sqlalchemy import text

    from .codeintel.embeddings import get_embedder
    from .codeintel.notify import get_notifier
    from .codeintel.parsers import grammar_status
    from .shared.auth import token_problems
    from .shared.db_url import database_kind, redact_database_url

    settings = get_settings()
    failures = 0

    def report(ok: bool | None, label: str, detail: str = "") -> None:
        nonlocal failures
        mark = {True: "ok  ", False: "FAIL", None: "warn"}[ok]
        if ok is False:
            failures += 1
        print(f"[{mark}] {label}{': ' + detail if detail else ''}")

    report(sys.version_info >= (3, 11), "python", sys.version.split()[0])
    report(shutil.which("git") is not None, "git executable", shutil.which("git") or "not found")

    url = settings.get_database_url()
    report(True, "database url", redact_database_url(url))
    try:
        from .codeintel.runtime import session_scope

        with session_scope() as db:
            db.execute(text("SELECT 1"))
            report(True, "database connection")
            if database_kind(url) == "postgresql":
                ext = db.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")).scalar()
                report(ext is not None, "pgvector extension", ext or "missing: CREATE EXTENSION vector")
            else:
                report(None, "database", "SQLite: fine for tests, use PostgreSQL + pgvector for real use")
            head = _migration_head()
            try:
                rev = db.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
            except Exception:
                db.rollback()
                rev = []
            if not rev:
                report(False, "schema", "not migrated: run `make migrate` (alembic -c config/alembic.ini upgrade head)")
            elif head in rev:
                report(True, "schema", f"at head ({head})")
            else:
                report(False, "schema", f"at {', '.join(rev)}, code expects {head}: run `make migrate` "
                       "(pre-2026-10 databases: see docs/operations/database-migrations.md)")
    except Exception as exc:
        report(False, "database connection", f"{type(exc).__name__}: {exc}"[:200])

    for grammar, status in grammar_status().items():
        report(status == "ok", f"tree-sitter grammar {grammar}", status)

    try:
        embedder = get_embedder(settings)
        if embedder is None:
            report(None, "embeddings", "EMBEDDING_BACKEND=none: keyword retrieval only")
        else:
            vec = embedder.embed_query("doctor probe")
            sem = "" if embedder.semantic else " (lexical hash model, not semantic)"
            report(len(vec) == embedder.dim, "embeddings", f"{embedder.model_id}, dim={len(vec)}{sem}")
    except Exception as exc:
        report(False, "embeddings", f"{type(exc).__name__}: {exc}"[:200])

    notifier = get_notifier(settings)
    report(None if notifier.name == "none" else True, "job notifications",
           notifier.name if notifier.name != "none" else "none: workers poll the database")
    problems = token_problems()
    report(None if problems else True, "api tokens", "; ".join(problems) or "configured")
    return 1 if failures else 0


def cmd_describe(args) -> int:
    import subprocess
    from pathlib import Path

    from .codeintel.context import resolve_repositories
    from .codeintel.describe import describe_repository
    from .codeintel.embeddings import get_embedder
    from .codeintel.runtime import session_scope
    from .learning.llm import CodexCLI

    llm = CodexCLI(effort="low", timeout=300, max_calls=args.max_calls)
    if not llm.ready():
        print("error: Codex CLI is not installed or not signed in with ChatGPT (codex login)", file=sys.stderr)
        return 1
    checkout = Path(args.checkout)
    with session_scope() as db:
        repos = resolve_repositories(db, args.repo)
        if len(repos) != 1:
            print(f"error: {args.repo!r} matches {len(repos)} repositories", file=sys.stderr)
            return 1
        repo = repos[0]
        head = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], capture_output=True, text=True)
        if head.stdout.strip() != repo.last_commit_sha:
            print(f"error: checkout is at {head.stdout.strip() or '?'}, the index at {repo.last_commit_sha}",
                  file=sys.stderr)
            return 1
        stats = describe_repository(db, repo.id, checkout, llm, get_embedder(), limit=args.limit,
                                    only_undocumented=not args.include_documented,
                                    progress=lambda m: print(m, file=sys.stderr, flush=True))
    _print({"repository": repo.name, **{k: v for k, v in vars(stats).items()},
            "codex": {"calls": llm.usage.calls, "input_tokens": llm.usage.input_tokens,
                      "output_tokens": llm.usage.output_tokens, "seconds": round(llm.usage.seconds)}}, True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pharos", description="Pharos code-intelligence CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest", help="index a repository (local path or remote URL)")
    s.add_argument("repository")
    s.add_argument("--branch")
    s.add_argument("--force", action="store_true", help="re-index even if the commit is unchanged")
    s.add_argument("--queue", action="store_true", help="queue for a worker instead of running now")
    s.set_defaults(func=cmd_ingest)

    for name, func in (("search", cmd_search), ("context", cmd_context)):
        s = sub.add_parser(name)
        s.add_argument("query")
        s.add_argument("--repo")
        s.add_argument("--mode", default="auto", choices=["auto", "keyword", "dense", "hybrid", "graph"])
        s.add_argument("-k", type=int, default=8)
        s.add_argument("--json", action="store_true")
        if name == "search":
            s.add_argument("--language", action="append")
        s.set_defaults(func=func)

    s = sub.add_parser("describe", help="write contextual descriptions with Codex (owner's machine only)")
    s.add_argument("repo", help="indexed repository id, URL or name")
    s.add_argument("--checkout", required=True, help="working tree at the indexed commit")
    s.add_argument("--limit", type=int, help="describe at most this many functions")
    s.add_argument("--include-documented", action="store_true", help="also functions that have a doc comment")
    s.add_argument("--max-calls", type=int, default=200, help="Codex call budget for this run")
    s.set_defaults(func=cmd_describe)

    s = sub.add_parser("symbol", help="find a definition and its callers / callees")
    s.add_argument("name")
    s.add_argument("--repo")
    s.set_defaults(func=cmd_symbol)

    sub.add_parser("repos", help="list indexed repositories").set_defaults(func=cmd_repos)
    s = sub.add_parser("jobs", help="list ingestion jobs")
    s.add_argument("--status")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_jobs)
    s = sub.add_parser("worker", help="run the ingestion worker")
    s.add_argument("--once", action="store_true")
    s.set_defaults(func=cmd_worker)
    sub.add_parser("gen-token", help="print a new random API token").set_defaults(func=cmd_gen_token)
    sub.add_parser("doctor", help="check configuration and dependencies").set_defaults(func=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
