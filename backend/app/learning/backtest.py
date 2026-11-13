"""Time-split backtests: does a learned rule hold on the commits that came after it?

Two uses, one mechanism (mine at one commit, check on later first-parent commits):

* **Activation** (:func:`holdout_records`). To learn at commit C, the miners also
  run at S, ``window`` first-parent commits before C, on history reachable from
  S only. Each rule they derive is checked on the commits S..C. The learning
  pipeline serves a rule learned at C only if the same rule, derived at S,
  held there (see :func:`~app.learning.checks.decide`). Nothing after C is read.
* **The locked precision measure** (:func:`protocol_precision`,
  ``docs/benchmarks/phase3-eval-protocol.md``). Learn at C exactly as the
  pipeline would (including its activation backtest), then check every active
  requirement on the next ``n`` first-parent commits after C. Precision is held
  over applied, pooled over (rule, commit) pairs.

A first-parent commit is diffed against its first parent, so a merged pull
request counts as one change, as the protocol's unit is the first-parent
commit. Paths a hold-out commit renames are mapped back to their names at the
learned commit, so a rule about a file follows the file. No LLM is involved.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from ..codeintel.languages import detect_language
from ..codeintel.retrieval import path_role
from ..utils.path_exclusions import has_excluded_ancestor, is_excluded_file
from .checks import (
    DEFAULT_ACTIVATION,
    REQUIREMENT,
    Activation,
    Change,
    Check,
    FileChange,
    check_from_json,
    decide,
    parse_diff,
    wilson_lower,
)
from .history import HistoryError, _git, load_history, worktree
from .memory import Candidate, SkillCandidate
from .miners import Chunk, Snapshot, mine_playbooks, run_miners, tracked_files

logger = logging.getLogger(__name__)

MAX_FILES = 60  # line diffs are read for changes of at most this many files (as history.MAX_FILES_PER_COMMIT)
MAX_FILE_BYTES = 1_000_000  # as the indexer
MAX_SYMBOLS_PER_FILE = 2000
COUNTER_EXAMPLES = 5


# ── commits ────────────────────────────────────────────────────────────

def first_parent(mirror: Path, commit: str, limit: int | None = None) -> list[str]:
    """``commit`` and its first-parent ancestors, newest first."""
    args = ["rev-list", "--first-parent", *([f"-{limit}"] if limit else []), commit]
    return _git(mirror, *args).split()


def holdout_window(mirror: Path, commit: str, window: int) -> tuple[str, list[str]]:
    """(S, the hold-out commits S..commit oldest first): S is ``window`` first-parent commits before
    ``commit``, or halfway back when the first-parent chain is shorter than twice that."""
    chain = first_parent(mirror, commit, 2 * window + 1)
    if len(chain) < 2 * window + 1:
        window = (len(chain) - 1) // 2
    if window < 1:
        raise HistoryError("too few first-parent commits for a hold-out window")
    return chain[window], list(reversed(chain[:window]))


def following(mirror: Path, commit: str, n: int, head: str = "HEAD") -> list[str]:
    """The next ``n`` first-parent commits after ``commit`` on ``head``'s first-parent chain, oldest first.

    When ``commit`` is not itself on that chain (a commit of a merged branch), these are the first-parent
    commits of ``head`` that descend from it."""
    out = _git(mirror, "rev-list", "--first-parent", "--ancestry-path", "--reverse", f"{commit}..{head}").split()
    return out[:n]


def load_changes(mirror: Path, shas: list[str], *, max_files: int = MAX_FILES, batch: int = 40) -> list[Change]:
    """Each commit as a :class:`Change` against its first parent, in the order given.

    Changes of more than ``max_files`` files keep their file list and message but no lines
    (``lines=False``): sweeping commits say nothing about line-level habits."""
    if not shas:
        return []
    meta: dict[str, Change] = {}
    for i in range(0, len(shas), 200):
        raw = _git(mirror, "-c", "core.quotepath=false", "log", "--no-walk=unsorted", "-M", "--name-status",
                   "--diff-merges=first-parent", "--format=%x1e%H%x00%P%x00%cI%x00%B%x1f", *shas[i:i + 200])
        for record in raw.split("\x1e"):
            if not record.strip():
                continue
            header, _, body = record.partition("\x1f")
            sha, parents, date, message = header.split("\x00", 3)
            files = []
            for line in body.splitlines():
                parts = line.split("\t")
                if len(parts) == 3 and parts[0][:1] in "RC":
                    files.append(FileChange("R" if parts[0][0] == "R" else "A", parts[2],
                                            parts[1] if parts[0][0] == "R" else None))
                elif len(parts) == 2 and parts[0][:1] in "AMDT":
                    files.append(FileChange("M" if parts[0][0] == "T" else parts[0][0], parts[1]))
            meta[sha] = Change(files=files, message=message.strip("\n"), sha=sha, date=date,
                               merge=len(parents.split()) > 1, lines=False)
    small = [s for s in shas if s in meta and len(meta[s].files) <= max_files]
    for i in range(0, len(small), batch):
        raw = _git(mirror, "-c", "core.quotepath=false", "show", "--format=%x1e%H", "-M", "--unified=0",
                   "--no-color", "--no-ext-diff", "--no-textconv", "--diff-merges=first-parent", *small[i:i + batch])
        for record in raw.split("\x1e"):
            if not record.strip():
                continue
            sha, _, body = record.partition("\n")
            change = meta.get(sha.strip())
            if change is not None:
                change.files, change.lines = parse_diff(body), True
    return [meta[s] for s in shas if s in meta]


def under_learned_names(changes: Iterable[Change]) -> list[Change]:
    """The changes (oldest first) with every path under its name at the learned commit: a rename in the
    hold-out window maps the new name back to the old one, so a rule about a file keeps applying to it."""
    back: dict[str, str] = {}
    out = []
    for change in changes:
        files = []
        for f in change.files:
            if f.status == "R" and f.old_path:
                learned = back.get(f.old_path, f.old_path)
                back[f.path] = learned
                files.append(FileChange("R", learned, f.old_path, f.added, f.removed))
            else:
                files.append(FileChange(f.status, back.get(f.path, f.path), f.old_path, f.added, f.removed))
        out.append(Change(files=files, message=change.message, sha=change.sha, date=change.date,
                          merge=change.merge, lines=change.lines))
    return out


# ── mining at a commit, from the tree (no index needed) ────────────────

def _decode(data: bytes) -> str | None:
    if b"\0" in data[:8192]:
        return None
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def tree_chunks(checkout: Path, files: Iterable[str]) -> list[Chunk]:
    """The chunks the indexer would store for ``checkout``: the same parsers and the same exclusions."""
    from ..codeintel.parsers import parse_file

    chunks = []
    for path in sorted(files):
        parts = path.split("/")
        if detect_language(path) is None or has_excluded_ancestor(parts[:-1]) or is_excluded_file(parts[-1]):
            continue
        target = checkout / path
        try:
            if target.is_symlink() or target.stat().st_size > MAX_FILE_BYTES:
                continue
            text = _decode(target.read_bytes())
        except OSError:
            continue
        if text is None or (len(text) >= 5000 and len(text) / (text.count("\n") + 1) > 300):
            continue
        try:
            parsed = parse_file(path, text)
        except Exception:  # noqa: BLE001 - one bad file never fails the run (as the indexer)
            continue
        if parsed is None:
            continue
        line_count = text.count("\n") + (0 if text.endswith("\n") else 1)
        role = path_role(path)
        for sym in parsed.symbols[:MAX_SYMBOLS_PER_FILE]:
            chunks.append(Chunk(path=path, kind=sym.kind, symbol=sym.qualified_name[:512], name=sym.name,
                                parent=sym.parent, language=parsed.language, start=sym.start_line,
                                end=max(sym.start_line, min(sym.end_line, line_count)),
                                signature=(sym.signature or "")[:500], docstring=(sym.docstring or "")[:2000],
                                role=role))
    return chunks


def tree_snapshot(mirror: Path, commit: str, checkout: Path, name: str = "") -> Snapshot:
    files = tracked_files(checkout)
    return Snapshot(name=name or mirror.name, commit=commit, checkout=checkout, mirror=mirror,
                    chunks=tree_chunks(checkout, files), files=files, history=load_history(mirror, commit))


@dataclass
class Mined:
    commit: str
    candidates: list[Candidate]
    skills: list[SkillCandidate]
    report: dict = field(default_factory=dict)
    grounded: dict[str, bool] = field(default_factory=dict)  # key -> every piece of evidence re-checks

    def checks(self) -> dict[str, Check]:
        return {c.key: check for c in self.candidates if (check := check_from_json(c.check)) is not None}


@contextmanager
def mined_at(mirror: Path, commit: str, *, families: list[str] | None = None,
             grounding: bool = False) -> Iterator[Mined]:
    """Run the miners at ``commit`` in a temporary worktree (removed on exit)."""
    with worktree(mirror, commit) as checkout:
        t = time.perf_counter()
        snap = tree_snapshot(mirror, commit, checkout)
        load = round(time.perf_counter() - t, 2)
        candidates, report = run_miners(snap, families)
        report["timings"]["load"] = load
        skills = mine_playbooks(snap) if not families or "playbooks" in families else []
        mined = Mined(commit=commit, candidates=candidates, skills=skills, report=report)
        if grounding:
            from .pipeline import _grounding

            check = _grounding(snap, str(mirror))
            mined.grounded = {c.key: bool(c.evidence) and all(check(e) for e in c.evidence) for c in candidates}
        yield mined


# ── evaluation ─────────────────────────────────────────────────────────

def evaluate(checks: dict[str, Check], changes: list[Change], *, counter: int = COUNTER_EXAMPLES) -> dict[str, dict]:
    """Per rule: how often it applied to ``changes``, how often it held, and the first counter-examples."""
    out = {}
    for key, check in checks.items():
        applied = held = 0
        misses: list[dict] = []
        for change in changes:
            try:
                result = check.evaluate(change)
            except Exception as exc:  # noqa: BLE001 - a broken pattern counts as not applying, and is logged
                logger.warning("check %s failed on %s: %s", key, change.sha, exc)
                result = None
            if result is None:
                continue
            applied += 1
            if result:
                held += 1
            elif len(misses) < counter:
                misses.append(change.describe())
        out[key] = {"check": check.to_json(), "applied": applied, "held": held,
                    "rate": round(held / applied, 4) if applied else None,
                    "lower": round(wilson_lower(held, applied), 4), "counter_examples": misses}
    return out


def holdout_records(mirror: Path, commit: str, window: int, *, families: list[str] | None = None
                    ) -> tuple[dict[str, dict], dict]:
    """The activation backtest for learning at ``commit``: mine at S (``window`` first-parent commits back),
    check each rule on S..commit. Returns (key -> record, a summary)."""
    t = time.perf_counter()
    split, shas = holdout_window(mirror, commit, window)
    changes = under_learned_names(load_changes(mirror, shas))
    with mined_at(mirror, split, families=families) as mined:
        checks = mined.checks()
    records = evaluate(checks, changes)
    span = {"from": split[:12], "to": commit[:12], "commits": len(shas)}
    for record in records.values():
        record["window"] = span
    summary = {"split": split[:12], "commits": len(shas), "rules": len(records),
               "applied": sum(r["applied"] > 0 for r in records.values()), "seconds": round(time.perf_counter() - t, 1)}
    return records, summary


# ── the locked precision measure ───────────────────────────────────────

def pooled(rows: Iterable[dict]) -> dict:
    rows = list(rows)
    applied = sum(r["applied"] for r in rows)
    held = sum(r["held"] for r in rows)
    return {"rules": len(rows), "applied": applied, "held": held,
            "precision": round(held / applied, 4) if applied else None}


def protocol_precision(mirror: Path, commit: str, *, n: int = 200, head: str = "HEAD",
                       activation: Activation = DEFAULT_ACTIVATION, families: list[str] | None = None,
                       progress=lambda _m: None) -> dict:
    """Learn at ``commit`` as the pipeline does, then check its rules on the next ``n`` first-parent commits.

    Every checkable candidate is evaluated on the protocol window, so any activation rule can be scored from
    the result afterwards; ``after`` pools the active requirements under ``activation``, ``before`` the rules
    the Phase 2 rule (``eligible``) would have activated. Ungrounded candidates are dropped, as the writer does."""
    t0 = time.perf_counter()
    later = following(mirror, commit, n, head)
    changes = under_learned_names(load_changes(mirror, later))
    progress(f"{commit[:10]}: {len(later)} later first-parent commits loaded")
    with mined_at(mirror, commit, families=families, grounding=True) as mined:
        candidates = [c for c in mined.candidates if mined.grounded.get(c.key)]
        report = mined.report
        ungrounded = len(mined.candidates) - len(candidates)
    progress(f"{commit[:10]}: {len(candidates)} grounded candidates ({ungrounded} ungrounded)")
    inner, inner_summary = holdout_records(mirror, commit, activation.window, families=families)
    progress(f"{commit[:10]}: activation backtest {inner_summary}")
    checks = {c.key: check for c in candidates if (check := check_from_json(c.check)) is not None}
    measured = evaluate(checks, changes)
    rules = []
    for cand in candidates:
        if cand.key not in checks:
            continue
        record = inner.get(cand.key)
        decision = decide(cand.check, record, activation)
        same = bool(record) and record.get("check") == cand.check
        rules.append({"key": cand.key, "family": cand.family, "kind": cand.check["kind"], "eligible": cand.eligible,
                      "inner": {k: record[k] for k in ("applied", "held", "lower")} if same else None,
                      "outcome": decision.outcome, "status": decision.status, "strength": decision.strength,
                      "render": checks[cand.key].render(),
                      **{k: measured[cand.key][k] for k in ("applied", "held", "rate", "counter_examples")}})
    after = [r for r in rules if r["status"] == "active" and r["strength"] == REQUIREMENT]
    before = [r for r in rules if r["eligible"]]
    advisory = [c for c in candidates if c.key not in checks]
    return {
        "commit": commit, "later_commits": len(later), "window_to": later[-1] if later else None,
        "candidates": len(candidates), "ungrounded": ungrounded, "checkable": len(rules),
        "advisory": len(advisory), "advisory_active_before": sum(c.eligible for c in advisory),
        "before": pooled(before) | {"active": len(before)},
        "after": pooled(after) | {"active": len(after)},
        "observations": pooled(r for r in rules if r["status"] == "active" and r["strength"] != REQUIREMENT),
        "inner": inner_summary, "rules": rules, "miners": {k: v for k, v in report.items() if k != "ran"},
        "seconds": round(time.perf_counter() - t0, 1),
    }
