"""Repository memory: candidates, evidence, incremental updates and the ledger.

Miners produce :class:`Candidate` items (facts and conventions) and
:class:`SkillCandidate` playbooks. :class:`MemoryWriter` applies them to the
database the ACE way: an item is *added* when its key is new, *patched* when
a later run derives it again (body, evidence and support move, the status a
human chose stays), and marked *stale* when its miner ran and no longer
derives it. Nothing is deleted or rewritten wholesale, and every change goes
to ``memory_ledger`` under the run's id, so a run can be rolled back.

Activation: a deterministic (L1) candidate the miner marks ``eligible``
(high support, see each miner) whose evidence checks out goes straight to
``active``. Everything else, and everything an LLM derived, starts
``proposed`` and needs a human to accept it.
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


def check_evidence(evidence: dict, checkout: Path, mirror: Path) -> bool:
    """Does this pointer still hold at the checkout's commit (or in its history)?"""
    kind = evidence.get("kind")
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


@dataclass
class WriteStats:
    added: int = 0
    patched: int = 0
    unchanged: int = 0
    staled: int = 0
    activated: int = 0
    proposed: int = 0
    ungrounded: int = 0
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
                    "invalidated_at_commit")


def _snapshot(row) -> dict:
    fields = _SNAPSHOT_FIELDS if isinstance(row, MemoryItem) else _SNAPSHOT_FIELDS[:1] + (
        "title", "description", "body", "resources", "support", "confidence", "scope", "evidence",
        "learned_at_commit", "invalidated_at_commit")
    return {f: getattr(row, f) for f in dict.fromkeys(fields)}


class MemoryWriter:
    """Applies one run's candidates to one repository's memory."""

    def __init__(self, db: Session, repository_id: uuid.UUID, commit: str, run_id: str, actor: str = "learner",
                 *, grounding=None) -> None:
        self.db = db
        self.repository_id = repository_id
        self.commit = commit
        self.run_id = run_id
        self.actor = actor
        self.grounding = grounding  # callable(evidence) -> bool, or None to trust the miner
        self.stats = WriteStats()

    def _ledger(self, target_type: str, target_id, action: str, before: dict | None, after: dict | None) -> None:
        self.db.add(MemoryLedger(repository_id=self.repository_id, run_id=self.run_id, target_type=target_type,
                                 target_id=target_id, action=action, actor=self.actor, before=before, after=after))

    def _grounded(self, evidence: list[dict]) -> bool:
        if not evidence:
            return False
        return self.grounding is None or all(self.grounding(e) for e in evidence)

    def _status(self, cand, existing: str | None) -> str:
        if existing in HUMAN_STATUSES:
            return existing
        if existing == "active" and cand.tier != "L1":
            return existing  # a human accepted it
        if cand.tier == "L1" and cand.eligible:
            return "active"
        return "proposed"

    def apply(self, candidates: Iterable[Candidate]) -> None:
        existing = {row.key: row for row in self.db.execute(
            select(MemoryItem).where(MemoryItem.repository_id == self.repository_id)).scalars()}
        for cand in candidates:
            if not self._grounded(cand.evidence):
                self.stats.ungrounded += 1
                continue
            row = existing.get(cand.key)
            body = cand.body[:MAX_BODY_CHARS]
            text = search_text(cand.title, body, " ".join((cand.scope or {}).get("paths", [])))
            if row is None:
                row = MemoryItem(repository_id=self.repository_id, key=cand.key, kind=cand.kind, title=cand.title,
                                 body=body, scope=cand.scope, evidence=cand.evidence, support=cand.support,
                                 confidence=round(cand.confidence, 4), source=cand.source, tier=cand.tier,
                                 status=self._status(cand, None), learned_at_commit=self.commit,
                                 valid_from_commit=cand.valid_from_commit or self.commit, search_text=text)
                self.db.add(row)
                self.db.flush()
                self._ledger("item", row.id, "add", None, _snapshot(row))
                self.stats.added += 1
                self.stats.changed_ids.append(row.id)
            else:
                before = _snapshot(row)
                status = self._status(cand, row.status)
                same = (row.title, row.body, row.support, row.scope, row.evidence, row.status) == (
                    cand.title, body, cand.support, cand.scope, cand.evidence, status)
                row.learned_at_commit = self.commit
                if same:
                    self.stats.unchanged += 1
                else:
                    text_changed = (row.title, row.body) != (cand.title, body)
                    row.title, row.body, row.scope, row.evidence = cand.title, body, cand.scope, cand.evidence
                    row.support, row.confidence, row.search_text = cand.support, round(cand.confidence, 4), text
                    if row.status == "stale" and status != "stale":
                        row.invalidated_at_commit = None
                    action = "activate" if status == "active" and row.status != "active" else "patch"
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
