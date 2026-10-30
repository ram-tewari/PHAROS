"""Select the Phase 2 utility A/B tasks: recent real commits, chosen by fixed rules.

For each repository, walk the default branch's first-parent history back from
a recorded head and keep the most recent commits that a coding assistant could
plausibly have been asked to make:

* written by a person (no ``[bot]``, dependabot, renovate or pre-commit-ci);
* not a revert, a release or a merge of one branch into another;
* changing 1-6 source files that PHAROS parses (``path_role == "source"``,
  an AST language, outside ``.github/``), at most 15 files in all, and
  3-400 changed lines in those source files.

The task text is the commit message without trailers (``Signed-off-by``,
``Closes``, ...) and without the pull-request number. The repository's
cutoff ``C0`` is the first parent of the oldest selected commit: memory is
learned and code is indexed from history up to C0 only, so no task's answer
is in what PHAROS learned.

The rules were fixed before any task was looked at, and the output is
hashed and locked in docs/benchmarks/phase2-eval-protocol.md::

    python benchmarks/make_utility_tasks.py --mirrors ~/.cache/pharos/git \\
        --out benchmarks/datasets/utility_v1.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.codeintel.languages import detect_language  # noqa: E402
from app.codeintel.retrieval import path_role  # noqa: E402

REPOSITORIES = [
    {"name": "click", "url": "https://github.com/pallets/click", "mirror": "pallets_click", "language": "python"},
    {"name": "requests", "url": "https://github.com/psf/requests", "mirror": "psf_requests", "language": "python"},
    {"name": "cobra", "url": "https://github.com/spf13/cobra", "mirror": "spf13_cobra", "language": "go"},
    {"name": "curl", "url": "https://github.com/curl/curl", "mirror": "curl_curl", "language": "c"},
]
# Development repositories (tuning only; never the locked test set).
DEV_REPOSITORIES = [
    {"name": "flask", "url": "https://github.com/pallets/flask", "mirror": "pallets_flask", "language": "python"},
    {"name": "ky", "url": "https://github.com/sindresorhus/ky", "mirror": "sindresorhus_ky",
     "language": "typescript"},
]
TASKS_PER_REPO = 20
MAX_SOURCE_FILES = 6
MAX_FILES = 15
MIN_SOURCE_LINES, MAX_SOURCE_LINES = 3, 400
BOT_RE = re.compile(r"\[bot\]|dependabot|renovate|pre-commit-ci", re.I)
SKIP_SUBJECT_RE = re.compile(r"^(revert\b|release\b|merge (branch|remote|stable|main|master|commit)\b|"
                             r"merge pull request .* from [^/]+/(stable|main|master)$)", re.I)
# Hyphenated keys (Signed-off-by, Reported-by, Follow-up-to, ...) and reference lines. Never the subject:
# curl's subjects are "area: what changed".
TRAILER_RE = re.compile(r"^[A-Za-z]+(-[A-Za-z]+)+: \S|^(Closes|Fixes|Ref|Refs|Bug|URL|See):? #?\S", re.I)
PR_NUMBER_RE = re.compile(r"\s*\(#\d+\)\s*$")


def git(mirror: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(mirror), *args], check=True, capture_output=True,
                          text=True, errors="replace").stdout


def is_source(path: str) -> bool:
    spec = detect_language(path)
    return bool(spec and spec.parser) and path_role(path) == "source" and not path.startswith(".github/")


def task_text(message: str) -> str:
    """The commit message as a request: no trailers, no PR number, no merge boilerplate."""
    lines = message.strip().splitlines()
    if lines and lines[0].lower().startswith("merge pull request") and len(lines) > 2:
        lines = lines[2:]  # GitHub merge commit: the PR title is the third line
    if not lines:
        return ""
    kept = lines[:1] + [line for line in lines[1:] if not TRAILER_RE.match(line.strip())]
    subject = PR_NUMBER_RE.sub("", kept[0])
    body = "\n".join(kept[1:]).strip()
    return (subject + ("\n\n" + body if body else "")).strip()


def changed_files(mirror: Path, commit: str, parent: str) -> list[dict]:
    out = []
    numstat = git(mirror, "diff", "--numstat", "-M", parent, commit).splitlines()
    status = git(mirror, "diff", "--name-status", "-M", parent, commit).splitlines()
    for stat_line, status_line in zip(numstat, status, strict=True):
        added, deleted, _ = stat_line.split("\t", 2)
        parts = status_line.split("\t")
        path = parts[-1]
        out.append({
            "path": path,
            "old_path": parts[1] if parts[0].startswith("R") else None,
            "status": parts[0][0],
            "lines": (0 if added == "-" else int(added)) + (0 if deleted == "-" else int(deleted)),
            "role": path_role(path),
            "source": is_source(path),
        })
    return out


def select(repo: dict, mirror: Path, head: str, n: int) -> tuple[list[dict], dict]:
    rows = git(mirror, "log", "--first-parent", "--format=%H%x00%P%x00%an <%ae>%x00%cI%x00%B%x1e", head)
    seen = rejected = 0
    reasons: dict[str, int] = {}
    tasks: list[dict] = []
    for record in rows.split("\x1e"):
        if not record.strip():
            continue
        sha, parents, author, date, message = record.strip("\n").split("\x00", 4)
        seen += 1
        reason = None
        subject = message.strip().splitlines()[0] if message.strip() else ""
        if not parents:
            reason = "root"
        elif BOT_RE.search(author):
            reason = "bot"
        elif SKIP_SUBJECT_RE.search(subject):
            reason = "revert_release_or_branch_merge"
        else:
            files = changed_files(mirror, sha, parents.split()[0])
            source = [f for f in files if f["source"]]
            lines = sum(f["lines"] for f in source)
            if not source:
                reason = "no_source_files"
            elif len(source) > MAX_SOURCE_FILES or len(files) > MAX_FILES:
                reason = "too_many_files"
            elif not MIN_SOURCE_LINES <= lines <= MAX_SOURCE_LINES:
                reason = "source_lines_out_of_range"
            elif len(task_text(message)) < 20:
                reason = "message_too_short"
        if reason:
            rejected += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            continue
        tasks.append({
            "id": f"{repo['name']}-u{len(tasks) + 1:02d}",
            "repo": repo["name"],
            "commit": sha,
            "parent": parents.split()[0],
            "date": date,
            "task": task_text(message),
            "files": files,
            "source_files": [f["path"] for f in source],
            "source_lines": lines,
        })
        if len(tasks) == n:
            break
    tasks.reverse()  # chronological
    for i, task in enumerate(tasks, start=1):
        task["id"] = f"{repo['name']}-u{i:02d}"
    stats = {"commits_examined": seen, "rejected": rejected, "rejected_by_reason": reasons}
    return tasks, stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mirrors", required=True, help="directory of full clones named owner_repo")
    ap.add_argument("--out", required=True)
    ap.add_argument("-n", type=int, default=TASKS_PER_REPO)
    ap.add_argument("--dev", action="store_true", help="the development repositories instead of the test ones")
    args = ap.parse_args(argv)
    mirrors = Path(args.mirrors).expanduser()
    dataset = {
        "name": "pharos-utility-dev" if args.dev else "pharos-utility",
        "version": 1,
        "labeling": __doc__.split("\n\n")[1].strip(),
        "rules": {"tasks_per_repo": args.n, "max_source_files": MAX_SOURCE_FILES, "max_files": MAX_FILES,
                  "source_lines": [MIN_SOURCE_LINES, MAX_SOURCE_LINES]},
        "repositories": [],
        "tasks": [],
    }
    for repo in DEV_REPOSITORIES if args.dev else REPOSITORIES:
        mirror = mirrors / repo["mirror"]
        branch = git(mirror, "symbolic-ref", "--short", "HEAD").strip()
        head = git(mirror, "rev-parse", "HEAD").strip()
        tasks, stats = select(repo, mirror, head, args.n)
        cutoff = tasks[0]["parent"]
        dataset["repositories"].append({
            "name": repo["name"], "url": repo["url"], "language": repo["language"], "branch": branch,
            "head": head, "cutoff_commit": cutoff,
            "cutoff_date": git(mirror, "show", "-s", "--format=%cI", cutoff).strip(), **stats,
        })
        dataset["tasks"].extend(tasks)
        print(f"{repo['name']}: {len(tasks)} tasks from {stats['commits_examined']} commits, "
              f"C0 {cutoff[:10]} ({dataset['repositories'][-1]['cutoff_date'][:10]})", file=sys.stderr)
    Path(args.out).write_text(json.dumps(dataset, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
