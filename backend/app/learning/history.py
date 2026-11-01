"""Git history for learning: full mirrors, a checkout at the indexed commit, and the log.

Indexing works from shallow clones; learning needs the whole history (who
changes what together, when a dependency was dropped, how commits are
written). Each repository gets one full clone under ``LEARNING_MIRROR_DIR``
(default ``~/.cache/pharos/git/<owner>_<repo>``), fetched before each run.
Code is read from a detached worktree at the indexed commit, so memory is
derived from exactly the code the index holds. Nothing here executes
repository code.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

MAX_FILES_PER_COMMIT = 60  # bigger commits are sweeping refactors, imports or reformatting


class HistoryError(RuntimeError):
    pass


@dataclass
class Commit:
    sha: str
    date: str  # ISO 8601, committer date
    author: str
    subject: str
    parents: int
    # (status letter, path at this commit's time mapped to its name at the learned commit)
    files: list[tuple[str, str]] = field(default_factory=list)
    renames: list[tuple[str, str]] = field(default_factory=list)  # (old, new) as recorded
    names: dict[str, str] = field(default_factory=dict)  # name at the learned commit -> path as recorded here

    def recorded(self, path: str) -> str:
        """``path`` (its name at the learned commit) as this commit recorded it."""
        return self.names.get(path, path)


def _git(cwd: Path, *args: str, timeout: float = 600) -> str:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, errors="replace",
                            timeout=timeout, env=env)
    if result.returncode != 0:
        raise HistoryError(f"git {args[0]} failed: {result.stderr.strip()[-300:]}")
    return result.stdout


def mirror_dir() -> Path:
    return Path(os.getenv("LEARNING_MIRROR_DIR") or Path.home() / ".cache" / "pharos" / "git").expanduser()


def mirror_name(url: str) -> str:
    """``https://github.com/pallets/click`` -> ``pallets_click``."""
    parts = [p for p in re.sub(r"\.git$", "", url.rstrip("/")).split("/") if p]
    return "_".join(parts[-2:]) if len(parts) >= 2 else parts[-1]


def ensure_mirror(url: str, commit: str, *, root: Path | None = None, local_path: str | None = None) -> Path:
    """A full clone that contains ``commit``: a local checkout as-is, or a fetched mirror."""
    if local_path:
        path = Path(local_path)
        _git(path, "cat-file", "-e", f"{commit}^{{commit}}")
        return path
    path = (root or mirror_dir()) / mirror_name(url)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--no-checkout", url, str(path)], check=True, timeout=1800,
                       env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    try:
        _git(path, "cat-file", "-e", f"{commit}^{{commit}}")
    except HistoryError:
        _git(path, "fetch", "-q", "origin", timeout=1800)
        _git(path, "cat-file", "-e", f"{commit}^{{commit}}")
    if _git(path, "rev-parse", "--is-shallow-repository").strip() == "true":
        _git(path, "fetch", "-q", "--unshallow", "origin", timeout=1800)
    return path


@contextmanager
def worktree(mirror: Path, commit: str) -> Iterator[Path]:
    """A detached working tree at ``commit``, removed afterwards."""
    parent = Path(tempfile.mkdtemp(prefix="pharos-learn-"))
    path = parent / "tree"
    _git(mirror, "worktree", "add", "-q", "--detach", str(path), commit)
    try:
        yield path
    finally:
        try:
            _git(mirror, "worktree", "remove", "--force", str(path))
        except HistoryError:
            pass
        shutil.rmtree(parent, ignore_errors=True)


def load_history(mirror: Path, commit: str, *, max_commits: int | None = None) -> list[Commit]:
    """Non-merge commits reachable from ``commit``, newest first, with renames followed.

    Every path is reported under its name at ``commit``: walking from new to
    old, a rename ``old -> new`` makes later (older) mentions of ``old``
    count as the file's current name. Commits touching more than
    ``MAX_FILES_PER_COMMIT`` files keep their metadata but no file list.
    """
    args = ["log", "--no-merges", "-M", "--name-status", "--format=%x1e%H%x00%cI%x00%an%x00%P%x00%s", commit]
    if max_commits:
        args.insert(1, f"-{max_commits}")
    out = _git(mirror, *args, timeout=1800)
    alias: dict[str, str] = {}
    commits: list[Commit] = []
    for record in out.split("\x1e"):
        if not record.strip():
            continue
        header, _, body = record.partition("\n")
        sha, date, author, parents, subject = header.split("\x00", 4)
        entry = Commit(sha=sha, date=date, author=author, subject=subject, parents=len(parents.split()))
        lines = [line for line in body.splitlines() if line.strip()]
        for line in lines:
            parts = line.split("\t")
            status = parts[0][:1]
            if status in "RC" and len(parts) == 3:
                old, new = parts[1], parts[2]
                current = alias.get(new, new)
                if status == "R":
                    alias[old] = current
                    entry.renames.append((old, new))
                if len(lines) <= MAX_FILES_PER_COMMIT:
                    entry.files.append((status, current))
                    if current != new:
                        entry.names[current] = new
            elif len(parts) >= 2 and len(lines) <= MAX_FILES_PER_COMMIT:
                current = alias.get(parts[1], parts[1])
                entry.files.append((status, current))
                if current != parts[1]:
                    entry.names[current] = parts[1]
        commits.append(entry)
    return commits


def commit_messages(mirror: Path, commit: str, limit: int = 500) -> list[tuple[str, str]]:
    """(sha, full message) of the latest non-merge commits."""
    out = _git(mirror, "log", "--no-merges", f"-{limit}", "--format=%x1e%H%x00%B", commit)
    return [tuple(r.strip("\n").split("\x00", 1)) for r in out.split("\x1e") if r.strip()]


def file_at(mirror: Path, commit: str, path: str) -> str | None:
    try:
        return _git(mirror, "show", f"{commit}:{path}")
    except HistoryError:
        return None


def commits_touching(mirror: Path, commit: str, paths: list[str], limit: int = 400,
                     first_parent: bool = False) -> list[tuple[str, str, str]]:
    """(sha, date, subject) of commits that touched any of ``paths``, newest first."""
    extra = ["--first-parent"] if first_parent else []
    out = _git(mirror, "log", f"-{limit}", *extra, "--format=%H%x00%cI%x00%s", commit, "--", *paths)
    return [tuple(line.split("\x00", 2)) for line in out.splitlines() if line]
