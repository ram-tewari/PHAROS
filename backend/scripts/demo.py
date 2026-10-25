"""End-to-end smoke demo: index a small multi-language repo and query it.

    cd backend && python scripts/demo.py                 # throwaway SQLite DB, hash embeddings
    DATABASE_URL=postgresql://... python scripts/demo.py # your database (must be migrated)

Copies tests/fixtures/tinyshop (Python, JS, TS, Go, Rust, C, C++, Java) into a
temporary git repository, then runs the real CLI: doctor -> ingest -> search
-> symbol -> context. Exits non-zero if any step fails. No network needed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
FIXTURE = BACKEND / "tests" / "fixtures" / "tinyshop"


def run(*args: str, env: dict, capture: bool = True) -> str:
    print(f"\n$ python -m app.cli {' '.join(args)}", flush=True)
    proc = subprocess.run([sys.executable, "-m", "app.cli", *args], cwd=BACKEND, env=env,
                          capture_output=capture, text=True)
    if proc.returncode != 0:
        print(proc.stdout, proc.stderr, sep="\n")
        raise SystemExit(f"step failed: {' '.join(args)} (exit {proc.returncode})")
    return proc.stdout if capture else ""


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="pharos_demo_"))
    repo = work / "tinyshop"
    shutil.copytree(FIXTURE, repo)
    git = ["git", "-c", "user.name=demo", "-c", "user.email=demo@example.invalid", "-C", str(repo)]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "tinyshop"], check=True)

    env = dict(os.environ)
    env.setdefault("EMBEDDING_BACKEND", "hash")
    env.setdefault("MODE", "CLOUD")
    if "DATABASE_URL" not in env:
        env["DATABASE_URL"] = f"sqlite:///{work / 'demo.db'}"
        subprocess.run([sys.executable, "-m", "alembic", "-c", "config/alembic.ini", "upgrade", "head"],
                       cwd=BACKEND, env=env, check=True, capture_output=True)
    print(f"database: {env['DATABASE_URL'].split('@')[-1]}   embeddings: {env['EMBEDDING_BACKEND']}")

    print(run("doctor", env=env))
    stats = json.loads(run("ingest", str(repo), env=env))
    print(json.dumps({k: stats[k] for k in ("outcome", "files_indexed", "chunks_total", "commit_sha")}, indent=1))
    langs = stats["languages"]
    print("AST-parsed files per language:", {k: v["ast"] for k, v in langs.items()},
          "| line-fallback files:", sum(v["fallback"] for v in langs.values()))

    print(run("search", "verify a user's password", "-k", "3", env=env))
    print(run("symbol", "Bucket.Allow", env=env))
    context = json.loads(run("context", "how are passwords checked during login", "-k", "3", "--json", env=env))
    first = context["chunks"][0]
    print(f"context: {len(context['chunks'])} chunks, {len(context['context_text'])} chars; "
          f"top: {first['symbol']} ({first['path']}:{first['start_line']}) code_verified={first['verified']}")
    if not first["verified"]:
        raise SystemExit("source was not verified against the git blob")
    print(f"\nOK. Temporary files: {work}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
