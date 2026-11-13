"""PHAROS steps that ``agent_eval.py`` runs inside a chosen PHAROS code checkout.

Each arm of the Phase 3 evaluation is served by a PHAROS code checkout (the current branch, or the
``phase2-baseline`` tag) over its own scratch database. To make sure an arm's index and memory are
built by that arm's code, this script is run as a subprocess with ``PYTHONPATH=<checkout>/backend``
and that directory as the working directory; it imports ``app`` from there and never from the
checkout this file lives in. Settings come from the environment (``DATABASE_URL``, the embedding
backend), the same environment the arm's server gets.

    python agent_eval_worker.py migrate
    python agent_eval_worker.py index <local repository path> <commit>
    python agent_eval_worker.py learn <local repository path> <checkout> <history clone> <commit>

Each command prints one JSON line with its statistics.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def _session():
    from app.codeintel.runtime import session_scope

    return session_scope()


def migrate() -> dict:
    from alembic.config import Config

    from alembic import command

    t0 = time.monotonic()
    cfg = Config("config/alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    command.upgrade(cfg, "head")
    return {"seconds": round(time.monotonic() - t0, 2)}


def index(path: str, commit: str) -> dict:
    from app.codeintel.embeddings import get_embedder
    from app.codeintel.git_source import parse_repo_spec
    from app.codeintel.indexer import CodeIndexer

    t0 = time.monotonic()
    ref = parse_repo_spec(path, allowed_hosts=[], allow_local=True)
    with _session() as db:
        stats = CodeIndexer(db, get_embedder()).index(ref, commit)
    out = stats.as_dict()
    out["errors"] = len(out.get("errors") or [])
    out.pop("languages", None)
    return out | {"seconds": round(time.monotonic() - t0, 2)}


def learn(path: str, checkout: str, history: str, commit: str) -> dict:
    """Deterministic learning at ``commit`` (no LLM), from a clone holding only that commit's history."""
    from sqlalchemy import select

    from app.codeintel.embeddings import get_embedder
    from app.codeintel.git_source import parse_repo_spec
    from app.database.models import Repository
    from app.learning.pipeline import learn_repository

    t0 = time.monotonic()
    ref = parse_repo_spec(path, allowed_hosts=[], allow_local=True)
    with _session() as db:
        repo = db.execute(select(Repository).where(Repository.url == ref.canonical_url)).scalar_one()
        if repo.last_commit_sha != commit:
            raise SystemExit(f"the index is at {repo.last_commit_sha}, learning needs {commit}")
        stats = learn_repository(db, repo, checkout=Path(checkout), mirror=Path(history), commit=commit,
                                 embedder=get_embedder(), llm=None,
                                 progress=lambda m: print(m, file=sys.stderr, flush=True))
    return {"seconds": round(time.monotonic() - t0, 2), **stats}


def main(argv: list[str]) -> int:
    commands = {"migrate": migrate, "index": index, "learn": learn}
    if not argv or argv[0] not in commands:
        print(__doc__, file=sys.stderr)
        return 2
    result = commands[argv[0]](*argv[1:])
    print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
