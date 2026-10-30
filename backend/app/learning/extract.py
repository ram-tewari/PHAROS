"""L2: Codex reads a repository's own guidance and reviews, and proposes memory.

Evidence units are issued by PHAROS, never chosen by the model:

* ``D`` units: sections of the repository's contributing, style and
  internals documents at the learned commit (cited by line range and hash);
* ``R`` units: public pull-request review comments from before the commit
  (cited by URL and text hash, see :mod:`app.learning.reviews`).

Codex sees a batch of units plus the existing memory (``M`` ids) and answers
with ACE operations in strict JSON: ``add`` a convention or fact, ``patch``
an L2 item the evidence refines, or ``retire`` one it contradicts. An
operation survives only if it cites issued ids, every code-shaped token in
its text appears in the cited evidence (:func:`app.codeintel.describe.grounded`),
and its target, if any, is an L2 item (deterministic L1 items are never
rewritten by a model). Survivors are written ``proposed``: a human accepts
them (the approval gate). Units already read are remembered by hash, so a
nightly run only spends calls on new guidance and new reviews.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..codeintel.describe import grounded
from ..database.models import MemoryItem
from .history import HistoryError, _git, mirror_name
from .memory import Candidate, MemoryWriter, code_evidence, lines_sha256
from .miners import Snapshot
from .recall import glob_match
from .reviews import cache_dir, fetch_review_comments, github_slug, review_evidence

logger = logging.getLogger(__name__)

UNIT_CHARS = 1800
BATCH_CHARS = 14_000
BATCH_UNITS = 12
MAX_OPS = 5
MEMORY_LIST_CHARS = 5000

DOC_RE = re.compile(r"(^|/)(CONTRIBUTING|CONTRIBUTE|CODE_STYLE|CODING_STYLE|STYLE|HACKING|DEVELOPMENT|"
                    r"INTERNALS|DEVELOPERS?)(\.(md|rst|txt))?$", re.I)
DOC_DIR_RE = re.compile(r"(^|/)(docs?/(internals|contributing|development|dev)|\.github)/[^/]+\.(md|rst)$", re.I)
_RST_UNDERLINE = re.compile(r"^([=\-~^*+#])\1{2,}\s*$")

INSTRUCTIONS = """You maintain the memory of one software repository: the conventions and rules a contributor
must follow there, and facts about how the project works. You are given numbered evidence from the
repository itself (D: its documents; R: review comments maintainers left on pull requests) and the memory
it already has (M).

Propose operations:
- add: a convention, rule or fact the evidence states or a reviewer explicitly asks for, specific to this
  repository (names, files, macros, commands, thresholds), that will still apply to future, different changes.
  A decision about one pull request's particular code is not a convention; skip it. Never generic programming
  advice.
- patch: an existing M item the evidence makes more precise (give its id in target).
- retire: an existing M item the evidence contradicts (give its id in target).
Every operation cites the evidence ids that support it. Write the body as one or two plain sentences an
assistant can follow while editing code here; mention an identifier only if it appears in the cited
evidence. Do not repeat what an M item already says. Return at most 5 operations, and none if the
evidence holds no reusable, repository-specific rule. Most batches hold at most one or two. For each
operation say what it applies_to: any change in the repository, changes to the scoped files, or this pull
request only (those are discarded)."""

SCHEMA = {
    "type": "object",
    "properties": {"ops": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "op": {"type": "string", "enum": ["add", "patch", "retire"]},
            "target": {"type": "string"},
            "kind": {"type": "string", "enum": ["convention", "fact"]},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "scope_paths": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "applies_to": {"type": "string", "enum": ["any change", "changes to the scoped files",
                                                      "this pull request only"]},
        },
        "required": ["op", "title", "body", "evidence", "applies_to"]}}},
    "required": ["ops"],
}


@dataclass
class Unit:
    id: str
    text: str
    evidence: dict
    source: str  # code | review
    sha256: str


@dataclass
class ExtractStats:
    units: int = 0
    units_new: int = 0
    calls: int = 0
    failed_calls: int = 0
    ops: int = 0
    added: int = 0
    patched: int = 0
    retired: int = 0
    rejected: dict = field(default_factory=dict)

    def reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1


def doc_paths(snap: Snapshot) -> list[str]:
    """Contributing, style and internals documents; style and contribution guides first."""
    paths = [p for p in snap.files if DOC_RE.search(p) or DOC_DIR_RE.search(p)]
    return sorted(paths, key=lambda p: (0 if re.search(r"style|contribut", p, re.I) else
                                        1 if "internals" in p.lower() else 2, p))


def _sections(lines: list[str]) -> list[tuple[int, int]]:
    """(start, end) line ranges, 1-based inclusive: split at headings, then at paragraphs when too long."""
    starts = [1] + [i for i in range(2, len(lines) + 1)
                    if lines[i - 1].startswith("#")
                    or (i < len(lines) and lines[i - 1].strip() and _RST_UNDERLINE.match(lines[i]))]
    ranges = [(a, b - 1) for a, b in zip(starts, starts[1:] + [len(lines) + 1], strict=True) if b - 1 >= a]
    out: list[tuple[int, int]] = []
    for a, b in ranges:
        size, start = 0, a
        for i in range(a, b + 1):
            size += len(lines[i - 1]) + 1
            if size > UNIT_CHARS and i > start and not lines[i - 1].strip():
                out.append((start, i - 1))
                start, size = i + 1, 0
        if start <= b:
            out.append((start, b))
    merged: list[tuple[int, int]] = []
    for a, b in out:  # fold short sections into the previous one while it stays small
        if merged and sum(len(x) + 1 for x in lines[merged[-1][0] - 1:b]) <= UNIT_CHARS and (
                sum(len(x) + 1 for x in lines[a - 1:b]) < 300):
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


def doc_units(snap: Snapshot, limit: int = 80) -> list[Unit]:
    units: list[Unit] = []
    for path in doc_paths(snap):
        lines = snap.lines(path)
        for start, end in _sections(lines):
            text = "\n".join(lines[start - 1:end]).strip()
            if len(text) < 120:
                continue
            ev = code_evidence(snap.checkout, path, start, end)
            if ev:
                units.append(Unit(id="", text=f"({path}:{start}-{end})\n{text}", evidence=ev, source="code",
                                  sha256=ev["sha256"]))
            if len(units) >= limit:
                return units
    return units


def review_units(snap: Snapshot, url: str, *, before: str, limit: int, token: str | None) -> list[Unit]:
    out = []
    for c in fetch_review_comments(url, mirror_name(url), before=before, limit=limit, token=token):
        text = f"(PR #{c['pr']}, {c.get('path') or ''}, {c['created_at'][:10]})\n"
        if c.get("diff_hunk"):
            text += "code under review:\n" + c["diff_hunk"][-600:] + "\nreviewer: "
        text += c["body"][:1200]
        ev = review_evidence(c)
        out.append(Unit(id="", text=text, evidence=ev, source="review", sha256=ev["sha256"]))
    return out


def origin_url(repo, snap: Snapshot) -> str:
    """The repository's GitHub URL: its own, or a local checkout's ``origin`` remote."""
    if github_slug(repo.url):
        return repo.url
    try:
        return _git(snap.mirror, "remote", "get-url", "origin").strip()
    except HistoryError:
        return repo.url


def _seen_path(snap: Snapshot, url: str):
    return cache_dir(mirror_name(url)) / "l2_seen.json"


def _memory_listing(items: list[MemoryItem]) -> tuple[str, dict[str, MemoryItem]]:
    ids, lines, size = {}, [], 0
    for i, item in enumerate(sorted(items, key=lambda r: (r.tier != "L2", -r.support)), start=1):
        line = f"M{i} [{item.tier}] {item.title}: {item.body[:240]}"
        if size + len(line) > MEMORY_LIST_CHARS:
            break
        ids[f"M{i}"] = item
        lines.append(line)
        size += len(line)
    return "\n".join(lines), ids


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80] or "item"


def _batches(units: list[Unit]) -> list[list[Unit]]:
    batches, current, size = [], [], 0
    for unit in units:
        if current and (size + len(unit.text) > BATCH_CHARS or len(current) >= BATCH_UNITS):
            batches.append(current)
            current, size = [], 0
        current.append(unit)
        size += len(unit.text)
    if current:
        batches.append(current)
    return batches


def extract(db: Session, snap: Snapshot, repo, writer: MemoryWriter, llm, *, max_calls: int = 10,
            review_limit: int = 200, token: str | None = None, before: str | None = None) -> ExtractStats:
    """Run L2 over the evidence this repository has not had read yet. ``llm`` is a ``CodexCLI``."""
    stats = ExtractStats()
    commit_date = before or (snap.history[0].date if snap.history else "")
    url = origin_url(repo, snap)
    units = doc_units(snap)
    try:
        units += review_units(snap, url, before=commit_date, limit=review_limit, token=token)
    except OSError as exc:  # network trouble: documents alone this time
        logger.warning("review comments unavailable for %s: %s", repo.name, exc)
    stats.units = len(units)
    seen_path = _seen_path(snap, url)
    seen: set[str] = set(json.loads(seen_path.read_text())) if seen_path.exists() else set()
    todo = [u for u in units if u.sha256 not in seen]
    stats.units_new = len(todo)
    taken = set(db.execute(select(MemoryItem.key).where(MemoryItem.repository_id == repo.id)).scalars())
    for batch in _batches(todo):
        if stats.calls >= max_calls:
            break
        for n, unit in enumerate(batch, start=1):
            unit.id = f"{'D' if unit.source == 'code' else 'R'}{n}"
        items = list(db.execute(select(MemoryItem).where(
            MemoryItem.repository_id == repo.id, MemoryItem.status.in_(("active", "proposed")),
            MemoryItem.kind.in_(("convention", "fact")))).scalars())
        listing, mids = _memory_listing(items)
        issued = {u.id: u for u in batch}
        prompt = (f"Repository: {repo.name}\n\n# Existing memory\n{listing or '(none)'}\n\n# Evidence\n"
                  + "\n\n".join(f"## {u.id}\n{u.text}" for u in batch))
        stats.calls += 1
        try:
            answer = llm.complete(INSTRUCTIONS, prompt, SCHEMA)
        except Exception as exc:  # noqa: BLE001 - LLMUnavailable or a bad answer: keep the units for next time
            stats.failed_calls += 1
            logger.warning("L2 call failed for %s: %s", repo.name, exc)
            if "budget" in str(exc):
                break
            continue
        candidates: list[Candidate] = []
        for op in (answer.get("ops") or [])[:MAX_OPS]:
            stats.ops += 1
            if op.get("applies_to") == "this pull request only":
                stats.reject("one_off")
                continue
            cited = [issued[e] for e in op.get("evidence") or [] if e in issued]
            if not cited or len(cited) != len(op.get("evidence") or []):
                stats.reject("uncited_or_unknown_evidence")
                continue
            body = " ".join((op.get("body") or "").split())[:600]
            title = " ".join((op.get("title") or "").split())[:120]
            if not body or not title:
                stats.reject("empty")
                continue
            if not grounded(f"{title} {body}", "\n".join(u.text for u in cited)):
                stats.reject("ungrounded_identifier")
                continue
            target = mids.get(op.get("target") or "")
            if op["op"] in ("patch", "retire"):
                if target is None or target.tier != "L2":
                    stats.reject("target_not_l2")
                    continue
                if op["op"] == "retire":
                    writer.mark_stale(target, reason=f"contradicted by {', '.join(u.id for u in cited)}")
                    stats.retired += 1
                    continue
            scope_paths = [g for g in op.get("scope_paths") or [] if any(glob_match(g, p) for p in snap.files)]
            key = target.key if target is not None else f"l2/{_slug(title)}"
            if target is None and key in taken:
                key = f"{key[:240]}-{lines_sha256([body])[:8]}"
            taken.add(key)
            candidates.append(Candidate(
                key=key, kind=op.get("kind") or "convention", title=title, body=body,
                evidence=[u.evidence for u in cited], support=len(cited), confidence=0.5,
                source="review" if any(u.source == "review" for u in cited) else "code",
                scope={"paths": scope_paths} if scope_paths else None, tier="L2", eligible=False))
            if target is not None:
                stats.patched += 1
            else:
                stats.added += 1
        writer.apply(candidates)
        db.commit()
        seen |= {u.sha256 for u in batch}
        seen_path.write_text(json.dumps(sorted(seen)))
    return stats
