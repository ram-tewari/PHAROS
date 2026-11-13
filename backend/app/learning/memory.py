"""Repository memory: candidates, evidence, incremental updates and the ledger.

Miners produce :class:`Candidate` items (facts and conventions) and
:class:`SkillCandidate` playbooks. :class:`MemoryWriter` applies them to the
database the ACE way: an item is *added* when its key is new, *patched* when
a later run derives it again (body, evidence and support move, the status a
human chose stays), and marked *stale* when its miner ran and no longer
derives it. Nothing is deleted or rewritten wholesale, and every change goes
to ``memory_ledger`` under the run's id, so a run can be rolled back.

Activation. A *checkable* L1 candidate (one with a ``check``) is active only
when its hold-out backtest clears :class:`~app.learning.checks.Activation`
(see :func:`~app.learning.checks.decide`): it is then a *requirement*, or an
*observation* when the pattern is real but too weak to require. Untested
rules stay ``proposed``; failed ones go ``stale`` with their record. A
deterministic candidate with no check (a history fact) keeps the old rule:
``eligible`` and grounded means ``active``, as an *advisory* item. Everything
an LLM derived starts ``proposed``. A human's accept, reject or archive
always wins over a learning run.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database.models import MemoryItem, MemoryLedger, MemorySkill
from .checks import (
    ADVISORY,
    DEFAULT_ACTIVATION,
    REQUIREMENT,
    Activation,
    Decision,
    check_from_json,
    decide,
    holdout_sentence,
)
from .history import HistoryError, _git

MIN_SUPPORT = 5
HUMAN_STATUSES = ("rejected", "archived")
MAX_BODY_CHARS = 700


def lines_sha256(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def code_evidence(checkout: Path, path: str, start: int, end: int) -> dict | None:
    """Evidence for lines ``start``..``end`` (1-based, inclusive) of ``path``; None if out of range."""
    try:
        lines = (checkout / path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if start < 1 or end < start or end > len(lines):
        return None
    return {"kind": "code", "path": path, "start_line": start, "end_line": end,
            "sha256": lines_sha256(lines[start - 1:end])}


def file_evidence(checkout: Path, path: str) -> dict | None:
    try:
        blob = _git(checkout, "rev-parse", f"HEAD:{path}").strip()
    except HistoryError:
        return None
    return {"kind": "file", "path": path, "blob": blob}


def commit_evidence(sha: str, date: str, subject: str) -> dict:
    return {"kind": "commit", "sha": sha, "date": date[:10], "subject": subject[:200]}


TALLY_ROWS = 80


def tally_evidence(label: str, total: int, groups: list[tuple[str, int, list[dict]]],
                   names: list[dict] | None = None) -> dict:
    """Everything a count was taken over, so the claim can be checked from its evidence alone.

    ``groups`` are (label, count, rows). A row is a commit (``sha`` (12 characters), date, subject and
    the claimed ``paths`` as that commit recorded them), a symbol (``path``, ``line``, ``name``) or a
    file (``path``). At most ``TALLY_ROWS`` rows are kept; ``count`` is always the full number.
    ``names`` connect a recorded path to its current name through the renames in between:
    ``{"recorded", "now", "renames": [{"sha", "date", "from", "to"}]}``."""
    return {"kind": "tally", "label": label, "total": total,
            "groups": [{"label": g, "count": n, "rows": rows[:TALLY_ROWS]} for g, n, rows in groups],
            "names": names or []}


def diff_evidence(sha: str, date: str, subject: str, path: str, *, removed: Iterable[str] = (),
                  added: Iterable[str] = ()) -> dict:
    """Lines one commit removed from or added to ``path`` (a dropped dependency, a version bump)."""
    return {"kind": "diff", "sha": sha, "date": date[:10], "subject": subject[:200], "path": path,
            "removed": list(removed), "added": list(added)}


def same_changelog(a: str, b: str) -> bool:
    """A root changelog that changed format keeps its identity (``CHANGES.rst`` is today's ``CHANGES.md``)."""
    return "/" not in a and "/" not in b and a.split(".", 1)[0].lower() == b.split(".", 1)[0].lower()


def check_tally(evidence: dict, *, commit_paths, commit_renames, commit_added, line_at, exists) -> bool:
    """Re-check a tally. ``commit_paths(sha12)`` is the set of paths a commit recorded (None when it is
    not in the history), ``commit_renames(sha12)`` its (old, new) renames, ``commit_added(sha12)`` the
    paths it added, ``line_at(path, n)`` line n of a file at the commit (None when out of range) and
    ``exists(path)`` whether a file is there."""
    for group in evidence.get("groups", []):
        if len(group.get("rows", [])) > group.get("count", 0):
            return False
        for row in group["rows"]:
            if "sha" in row:
                paths = commit_paths(row["sha"])
                if paths is None or not set(row.get("paths", [])) <= paths:
                    return False
                if row.get("added") and not set(row["added"]) <= (commit_added(row["sha"]) or set()):
                    return False
            elif "line" in row:
                text = line_at(row["path"], row["line"])
                if text is None or row["name"] not in text:
                    return False
            elif not exists(row["path"]):
                return False
    for name in evidence.get("names", []):
        current = name["recorded"]
        for hop in name.get("renames", []):
            if hop["from"] != current or (hop["from"], hop["to"]) not in (commit_renames(hop["sha"]) or set()):
                return False
            current = hop["to"]
        if current != name["now"] and not same_changelog(current, name["now"]):
            return False
    return True


def commits_at(mirror: Path, head: str, shas: set[str]) -> dict[str, tuple[set[str], set[tuple[str, str]], set[str]]]:
    """sha[:12] -> (recorded paths, renames, added paths) for those of ``shas`` reachable from ``head``."""
    if not shas:
        return {}
    reachable = {s[:12] for s in _git(mirror, "rev-list", head).split()}
    out = {}
    raw = _git(mirror, "show", "-M", "--name-status", "--format=%x1e%H", *sorted(s for s in shas if s in reachable))
    for record in raw.split("\x1e"):
        if not record.strip():
            continue
        sha, _, body = record.partition("\n")
        paths, renames, added = set(), set(), set()
        for line in body.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[0][:1] in "RC":
                paths.add(parts[2])
                if parts[0][:1] == "R":
                    renames.add((parts[1], parts[2]))
            elif len(parts) >= 2:
                paths.add(parts[1])
                if parts[0][:1] == "A":
                    added.add(parts[1])
        out[sha.strip()[:12]] = (paths, renames, added)
    return out


def _line_at(checkout: Path, path: str, n: int) -> str | None:
    try:
        lines = (checkout / path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    return lines[n - 1] if 1 <= n <= len(lines) else None


def check_diff(evidence: dict, mirror: Path) -> bool:
    """Did that commit really remove and add those lines in that file?"""
    try:
        diff = set(_git(mirror, "show", "-M", "--diff-merges=first-parent", "--format=", evidence["sha"], "--",
                        evidence["path"]).splitlines())
    except HistoryError:
        return False
    return (all(f"-{line}" in diff for line in evidence.get("removed", []))
            and all(f"+{line}" in diff for line in evidence.get("added", [])))


def check_evidence(evidence: dict, checkout: Path, mirror: Path) -> bool:
    """Does this pointer still hold at the checkout's commit (or in its history)?"""
    kind = evidence.get("kind")
    if kind == "tally":
        try:
            head = _git(checkout, "rev-parse", "HEAD").strip()
            shas = ({r["sha"] for g in evidence.get("groups", []) for r in g.get("rows", []) if "sha" in r}
                    | {h["sha"] for n in evidence.get("names", []) for h in n.get("renames", [])})
            commits = commits_at(mirror, head, shas)
        except HistoryError:
            return False
        return check_tally(evidence, commit_paths=lambda s: (commits.get(s[:12]) or (None,))[0],
                           commit_renames=lambda s: (commits.get(s[:12]) or (None, None))[1],
                           commit_added=lambda s: (commits.get(s[:12]) or (None, None, None))[2],
                           line_at=lambda p, n: _line_at(checkout, p, n), exists=lambda p: (checkout / p).is_file())
    if kind == "diff":
        reachable = check_evidence({"kind": "commit", "sha": evidence["sha"]}, checkout, mirror)
        return reachable and check_diff(evidence, mirror)
    if kind == "code":
        fresh = code_evidence(checkout, evidence["path"], evidence["start_line"], evidence["end_line"])
        return bool(fresh and fresh["sha256"] == evidence["sha256"])
    if kind == "file":
        fresh = file_evidence(checkout, evidence["path"])
        return bool(fresh and fresh["blob"] == evidence["blob"])
    if kind == "commit":
        try:
            head = _git(checkout, "rev-parse", "HEAD").strip()
            _git(mirror, "merge-base", "--is-ancestor", evidence["sha"], head)
            return True
        except HistoryError:
            return False
    return False


def cite(evidence: dict) -> str:
    """``path:12-20`` / ``path`` / ``abc1234 (2026-05-24)``."""
    if evidence.get("kind") == "code":
        return f"{evidence['path']}:{evidence['start_line']}-{evidence['end_line']}"
    if evidence.get("kind") == "file":
        return evidence["path"]
    if evidence.get("kind") == "commit":
        return f"{evidence['sha'][:10]} ({evidence.get('date', '')})"
    if evidence.get("kind") == "diff":
        return f"{evidence['sha'][:10]} {evidence['path']}"
    if evidence.get("kind") == "tally":
        return f"counted: {evidence['label']}"[:100]
    return "?"


@dataclass
class Candidate:
    key: str
    kind: str  # convention | co_change | history | fact
    title: str
    body: str
    evidence: list[dict]
    support: int
    confidence: float
    source: str  # code | history | review
    scope: dict | None = None
    tier: str = "L1"
    eligible: bool = False  # meets its miner's auto-activation rule
    valid_from_commit: str | None = None
    family: str = ""  # the miner that produced it; set by the pipeline
    check: dict | None = None  # a checks.Check in JSON form when the claim can be tested on a change


@dataclass
class SkillCandidate:
    name: str
    title: str
    description: str
    body: str
    resources: dict
    evidence: list[dict]
    support: int
    confidence: float
    source: str
    scope: dict | None = None
    tier: str = "L1"
    eligible: bool = False
    family: str = ""
    rules: list[str] = field(default_factory=list)  # keys of the checkable items that test its steps


@dataclass
class WriteStats:
    added: int = 0
    patched: int = 0
    unchanged: int = 0
    staled: int = 0
    activated: int = 0
    proposed: int = 0
    ungrounded: int = 0
    outcomes: dict = field(default_factory=dict)  # checkable items by backtest outcome (requirement, ...)
    changed_ids: list[uuid.UUID] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: v for k, v in vars(self).items() if k != "changed_ids"}


def search_text(*parts: str) -> str:
    from ..codeintel.text import split_identifier

    words: list[str] = []
    for part in parts:
        for token in part.replace("/", " ").replace(".", " ").split():
            words.append(token.lower())
            words.extend(split_identifier(token))
    return " ".join(dict.fromkeys(w for w in words if w))


_SNAPSHOT_FIELDS = ("status", "title", "body", "support", "confidence", "scope", "evidence", "learned_at_commit",
                    "invalidated_at_commit", "strength", "predicate", "holdout")


def _snapshot(row) -> dict:
    fields = _SNAPSHOT_FIELDS if isinstance(row, MemoryItem) else ("status",) + (
        "title", "description", "body", "resources", "support", "confidence", "scope", "evidence",
        "learned_at_commit", "invalidated_at_commit")
    return {f: getattr(row, f) for f in dict.fromkeys(fields)}


class MemoryWriter:
    """Applies one run's candidates to one repository's memory."""

    def __init__(self, db: Session, repository_id: uuid.UUID, commit: str, run_id: str, actor: str = "learner",
                 *, grounding=None, holdout: dict[str, dict] | None = None,
                 activation: Activation = DEFAULT_ACTIVATION) -> None:
        self.db = db
        self.repository_id = repository_id
        self.commit = commit
        self.run_id = run_id
        self.actor = actor
        self.grounding = grounding  # callable(evidence) -> bool, or None to trust the miner
        # key -> the rule's hold-out record (backtest.py); None when no backtest ran, so nothing checkable
        # can become active.
        self.holdout = holdout
        self.activation = activation
        self.decisions: dict[str, Decision] = {}
        self.stats = WriteStats()
        self._accepted: set | None = None

    def accepted(self) -> set:
        """Ids of the items whose latest human decision is ``accept``: a learning run keeps them active."""
        if self._accepted is None:
            latest: dict = {}
            for target, action in self.db.execute(
                    select(MemoryLedger.target_id, MemoryLedger.action).where(
                        MemoryLedger.repository_id == self.repository_id, MemoryLedger.target_type == "item",
                        MemoryLedger.action.in_(("accept", "reject", "archive", "restore")))
                    .order_by(MemoryLedger.created_at)):
                latest[target] = action
            self._accepted = {t for t, a in latest.items() if a == "accept"}
        return self._accepted

    def decision(self, cand: Candidate) -> Decision:
        """What the candidate's own record earns, before any human decision."""
        if getattr(cand, "check", None) is None or cand.tier != "L1":  # a fact, a skill or a model's rule
            status = "active" if cand.tier == "L1" and cand.eligible else "proposed"
            return Decision(status, ADVISORY, "advisory", "")
        record = None if self.holdout is None else self.holdout.get(cand.key)
        return decide(cand.check, record, self.activation)

    def _ledger(self, target_type: str, target_id, action: str, before: dict | None, after: dict | None) -> None:
        self.db.add(MemoryLedger(repository_id=self.repository_id, run_id=self.run_id, target_type=target_type,
                                 target_id=target_id, action=action, actor=self.actor, before=before, after=after))

    def _grounded(self, evidence: list[dict]) -> bool:
        if not evidence:
            return False
        return self.grounding is None or all(self.grounding(e) for e in evidence)

    def _status(self, cand, existing: str | None, decision: Decision | None = None, row_id=None) -> str:
        if existing in HUMAN_STATUSES:
            return existing
        if existing == "active" and (cand.tier != "L1" or row_id in self.accepted()):
            return existing  # a human accepted it
        return (decision or self.decision(cand)).status

    def _holdout(self, cand: Candidate, decision: Decision) -> dict | None:
        if cand.check is None or cand.tier != "L1":
            return None
        record = (self.holdout or {}).get(cand.key)
        tested = record if record and record.get("check") == cand.check else None
        out = {k: v for k, v in (tested or {}).items() if k != "check"}
        a = self.activation
        return out | {"outcome": decision.outcome, "reason": decision.reason,
                      "activation": {"window": a.window, "min_applied": a.min_applied, "min_lower": a.min_lower,
                                     "observe_lower": a.observe_lower}}

    def apply(self, candidates: Iterable[Candidate]) -> None:
        existing = {row.key: row for row in self.db.execute(
            select(MemoryItem).where(MemoryItem.repository_id == self.repository_id)).scalars()}
        for cand in candidates:
            if not self._grounded(cand.evidence):
                self.stats.ungrounded += 1
                continue
            row = existing.get(cand.key)
            decision = self.decision(cand)
            self.decisions[cand.key] = decision
            holdout = self._holdout(cand, decision)
            if cand.check is not None and cand.tier == "L1":
                self.stats.outcomes[decision.outcome] = self.stats.outcomes.get(decision.outcome, 0) + 1
            # The served text says what the hold-out test measured, never more.
            sentence = (holdout_sentence(holdout, check_from_json(cand.check).render())
                        if holdout and holdout.get("window") else "")
            body = cand.body[:MAX_BODY_CHARS - len(sentence)] + sentence
            text = search_text(cand.title, body, " ".join((cand.scope or {}).get("paths", [])))
            strength = decision.strength
            if row is None:
                status = self._status(cand, None, decision)
                row = MemoryItem(repository_id=self.repository_id, key=cand.key, kind=cand.kind, title=cand.title,
                                 body=body, scope=cand.scope, evidence=cand.evidence, support=cand.support,
                                 confidence=round(cand.confidence, 4), source=cand.source, tier=cand.tier,
                                 status=status, learned_at_commit=self.commit,
                                 valid_from_commit=cand.valid_from_commit or self.commit, search_text=text,
                                 predicate=cand.check, holdout=holdout, strength=strength,
                                 invalidated_at_commit=self.commit if status == "stale" else None)
                self.db.add(row)
                self.db.flush()
                self._ledger("item", row.id, "add", None, _snapshot(row))
                self.stats.added += 1
                self.stats.changed_ids.append(row.id)
            else:
                before = _snapshot(row)
                status = self._status(cand, row.status, decision, row.id)
                if status == "active" and decision.status != "active" and cand.check is not None:
                    strength = REQUIREMENT  # a human accepted it as a rule
                if cand.tier != "L1" and row.status == "active" and (row.title, row.body) != (cand.title, body):
                    status = "proposed"  # a model rewrote an accepted item: it needs accepting again
                same = (row.title, row.body, row.support, row.scope, row.evidence, row.status, row.predicate,
                        row.holdout, row.strength) == (cand.title, body, cand.support, cand.scope, cand.evidence,
                                                       status, cand.check, holdout, strength)
                row.learned_at_commit = self.commit
                if same:
                    self.stats.unchanged += 1
                else:
                    text_changed = (row.title, row.body) != (cand.title, body)
                    row.title, row.body, row.scope, row.evidence = cand.title, body, cand.scope, cand.evidence
                    row.support, row.confidence, row.search_text = cand.support, round(cand.confidence, 4), text
                    row.predicate, row.holdout, row.strength = cand.check, holdout, strength
                    if row.status == "stale" and status != "stale":
                        row.invalidated_at_commit = None
                    elif status == "stale" and row.status != "stale":
                        row.invalidated_at_commit = self.commit
                    action = ("activate" if status == "active" and row.status != "active"
                              else "stale" if status == "stale" and row.status != "stale" else "patch")
                    if action == "stale":
                        self.stats.staled += 1
                    row.status = status
                    self._ledger("item", row.id, action, before, _snapshot(row))
                    self.stats.patched += 1
                    if text_changed:
                        row.embedding = None
                        self.stats.changed_ids.append(row.id)
            if row.status == "active":
                self.stats.activated += 1
            elif row.status == "proposed":
                self.stats.proposed += 1

    def mark_stale(self, row: MemoryItem, reason: str = "") -> None:
        before = _snapshot(row)
        row.status, row.invalidated_at_commit = "stale", self.commit
        self._ledger("item", row.id, "stale", before, _snapshot(row) | ({"reason": reason} if reason else {}))
        self.stats.staled += 1

    def retire(self, families_ran: set[str], derived_keys: set[str], tier: str = "L1") -> None:
        """Mark stale the items of miners that ran this time but no longer derive them."""
        rows = self.db.execute(select(MemoryItem).where(
            MemoryItem.repository_id == self.repository_id, MemoryItem.tier == tier,
            MemoryItem.status.in_(("active", "proposed")))).scalars()
        for row in rows:
            if row.key in derived_keys or row.key.split("/", 1)[0] not in families_ran:
                continue
            before = _snapshot(row)
            row.status, row.invalidated_at_commit = "stale", self.commit
            self._ledger("item", row.id, "stale", before, _snapshot(row))
            self.stats.staled += 1

    def apply_skills(self, skills: Iterable[SkillCandidate]) -> None:
        existing = {row.name: row for row in self.db.execute(
            select(MemorySkill).where(MemorySkill.repository_id == self.repository_id)).scalars()}
        seen = set()
        for cand in skills:
            if not self._grounded(cand.evidence):
                self.stats.ungrounded += 1
                continue
            seen.add(cand.name)
            tested = [self.decisions[k] for k in cand.rules if k in self.decisions]
            if tested:  # a playbook is served only while one of its steps is a requirement
                cand.eligible = cand.eligible and any(d.strength == REQUIREMENT and d.status == "active"
                                                      for d in tested)
            row = existing.get(cand.name)
            text = search_text(cand.title, cand.description, cand.body)
            if row is None:
                row = MemorySkill(repository_id=self.repository_id, name=cand.name, title=cand.title,
                                  description=cand.description, body=cand.body, resources=cand.resources,
                                  scope=cand.scope, evidence=cand.evidence, support=cand.support,
                                  confidence=round(cand.confidence, 4), source=cand.source, tier=cand.tier,
                                  status=self._status(cand, None), learned_at_commit=self.commit,
                                  valid_from_commit=self.commit, search_text=text)
                self.db.add(row)
                self.db.flush()
                self._ledger("skill", row.id, "add", None, _snapshot(row))
                self.stats.added += 1
                continue
            before = _snapshot(row)
            status = self._status(cand, row.status)
            row.learned_at_commit = self.commit
            if (row.description, row.body, row.resources, row.support, row.status) == (
                    cand.description, cand.body, cand.resources, cand.support, status):
                self.stats.unchanged += 1
                continue
            row.title, row.description, row.body, row.resources = cand.title, cand.description, cand.body, \
                cand.resources
            row.scope, row.evidence, row.support = cand.scope, cand.evidence, cand.support
            row.confidence, row.search_text, row.status = round(cand.confidence, 4), text, status
            row.invalidated_at_commit = None
            self._ledger("skill", row.id, "patch", before, _snapshot(row))
            self.stats.patched += 1
        for name, row in existing.items():
            if name not in seen and row.tier == "L1" and row.status in ("active", "proposed"):
                before = _snapshot(row)
                row.status, row.invalidated_at_commit = "stale", self.commit
                self._ledger("skill", row.id, "stale", before, _snapshot(row))
                self.stats.staled += 1


def set_status(db: Session, item: MemoryItem | MemorySkill, action: str, actor: str = "admin") -> None:
    """A human decision: accept (-> active), reject, archive or restore (-> proposed)."""
    target = {"accept": "active", "reject": "rejected", "archive": "archived", "restore": "proposed"}[action]
    before = _snapshot(item)
    item.status = target
    db.add(MemoryLedger(repository_id=item.repository_id, run_id=f"{actor}-{uuid.uuid4().hex[:12]}",
                        target_type="item" if isinstance(item, MemoryItem) else "skill", target_id=item.id,
                        action=action, actor=actor, before=before, after=_snapshot(item)))


def rollback_run(db: Session, run_id: str) -> int:
    """Undo one run: added rows become ``archived``, patched or staled rows get their old state back."""
    entries = db.execute(select(MemoryLedger).where(MemoryLedger.run_id == run_id)
                         .order_by(MemoryLedger.created_at.desc())).scalars().all()
    undone = 0
    for entry in entries:
        model = MemoryItem if entry.target_type == "item" else MemorySkill
        row = db.get(model, entry.target_id)
        if row is None:
            continue
        current = _snapshot(row)
        if entry.action == "add":
            row.status = "archived"
        elif entry.before:
            for key, value in entry.before.items():
                setattr(row, key, value)
        db.add(MemoryLedger(repository_id=entry.repository_id, run_id=f"rollback-{run_id}"[:64],
                            target_type=entry.target_type, target_id=entry.target_id, action="rollback",
                            actor="rollback", before=current, after=_snapshot(row)))
        undone += 1
    return undone
