"""Reading repository memory: what the API and MCP tools serve.

Production imports only this module from ``app.learning``: no git, no LLM,
no writes. Three entry points:

* :func:`memory_for_context` picks what leads a ``retrieve_context``
  answer: the repository brief, the active items scoped to the files that
  were retrieved (path globs) or to their languages, and the playbooks that
  touch those files.
* :func:`search_memory` is hybrid search over active items (keyword overlap
  fused with dense similarity when the items carry vectors of the query's
  embedding model).
* :func:`get_brief`, :func:`list_skills`, :func:`get_skill` serve the rest
  (skills with progressive disclosure: level 0 lists, 1 adds the steps,
  2 adds files with rates and example commits).
"""

from __future__ import annotations

import re
import uuid
from functools import lru_cache

from sqlalchemy import Float, bindparam, select
from sqlalchemy.orm import Session, defer

from ..codeintel.text import query_terms
from ..database.models import MemoryItem, MemorySkill, RepoBrief, Repository
from ..shared.vector_type import EmbeddingVector

MEMORY_CHARS = 4000
# History facts (file origins, removals) answer "when / why" questions; in a coding
# context they are noise, so they appear there only when the query asks.
_HISTORY_QUERY_RE = re.compile(r"\b(when|why|history|introduc|added|removed|deprecat|since|origin|renam|moved|"
                               r"dropped|changed)\w*", re.I)
MAX_ITEMS = 8
MAX_SKILLS = 3
RRF_K = 60


@lru_cache(maxsize=2048)
def _glob_re(pattern: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def glob_match(pattern: str, path: str) -> bool:
    """Path glob with ``**`` (any depth), ``*`` and ``?`` (within one segment)."""
    return bool(_glob_re(pattern).match(path))


def _compact(evidence: dict) -> dict:
    """A tally without its rows (``GET /memory/items`` returns them in full)."""
    if evidence.get("kind") != "tally":
        return evidence
    return evidence | {"groups": [{"label": g["label"], "count": g["count"]} for g in evidence.get("groups", [])]}


def item_to_dict(item: MemoryItem, *, full: bool = False) -> dict:
    evidence = item.evidence or []
    out = {
        "id": str(item.id), "key": item.key, "kind": item.kind, "title": item.title, "body": item.body,
        "scope": item.scope or {}, "support": item.support, "confidence": item.confidence,
        "source": item.source, "tier": item.tier, "status": item.status,
        "evidence": evidence if full else [_compact(e) for e in evidence], "learned_at_commit": item.learned_at_commit,
    }
    if full:
        out |= {"valid_from_commit": item.valid_from_commit, "invalidated_at_commit": item.invalidated_at_commit,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None}
    return out


def skill_to_dict(skill: MemorySkill, level: int = 0) -> dict:
    out = {"name": skill.name, "title": skill.title, "description": skill.description, "support": skill.support,
           "status": skill.status, "tier": skill.tier, "learned_at_commit": skill.learned_at_commit}
    if level >= 1:
        out["body"] = skill.body
        out["evidence"] = skill.evidence or []
    if level >= 2:
        out["resources"] = skill.resources or {}
    return out


def get_brief(db: Session, repo: Repository) -> RepoBrief | None:
    """The brief for the indexed commit, else the latest one."""
    rows = db.execute(select(RepoBrief).where(RepoBrief.repository_id == repo.id)
                      .order_by(RepoBrief.created_at.desc())).scalars().all()
    for row in rows:
        if row.commit_sha == repo.last_commit_sha:
            return row
    return rows[0] if rows else None


def _active_items(db: Session, repo_ids: list[uuid.UUID]) -> list[MemoryItem]:
    return list(db.execute(select(MemoryItem).options(defer(MemoryItem.embedding))
                           .where(MemoryItem.repository_id.in_(repo_ids), MemoryItem.status == "active")).scalars())


def _overlap(terms: set[str], text: str | None) -> float:
    if not terms or not text:
        return 0.0
    words = set(text.split())
    return len(terms & words) / len(terms)


def brief_conventions(text: str, name: str) -> str:
    """The brief's Conventions section: retrieval already shows the layout and main modules."""
    for section in text.split("\n## ")[1:]:
        if section.startswith("Conventions\n"):
            return f"# {name} conventions\n" + section.split("\n", 1)[1]
    return ""


def memory_for_context(db: Session, repos: list[Repository], chunks: list[dict], query: str) -> dict:
    """Brief + items + playbooks for these retrieved chunks (empty when nothing was learned)."""
    repo_ids = [r.id for r in repos] or list({uuid.UUID(c["repository"]["id"]) for c in chunks})
    if not repo_ids:
        return {"briefs": [], "items": [], "skills": []}
    repo_rows = repos or list(db.execute(select(Repository).where(Repository.id.in_(repo_ids))).scalars())
    briefs, in_brief = [], set()
    for repo in repo_rows[:2]:
        brief = get_brief(db, repo)
        if brief is not None:
            briefs.append({"repository": repo.name, "commit_sha": brief.commit_sha,
                           "text": brief_conventions(brief.text, repo.name)})
            in_brief |= set((brief.sections or {}).get("keys", []))
    rank_of_path: dict[str, int] = {}
    for c in chunks:
        rank_of_path.setdefault(c["path"], c["rank"])
    languages = {c.get("language") for c in chunks}
    terms = set(query_terms(query))
    wants_history = bool(_HISTORY_QUERY_RE.search(query))
    scoped, general = [], []
    for item in _active_items(db, repo_ids):
        if item.key in in_brief or (item.kind == "history" and not wants_history):
            continue
        paths = (item.scope or {}).get("paths") or []
        if paths:
            ranks = [rank for path, rank in rank_of_path.items() if any(glob_match(g, path) for g in paths)]
            if ranks:
                scoped.append((not item.key.startswith("testhome/"), min(ranks), -item.confidence, item))
            continue
        langs = (item.scope or {}).get("languages") or []
        if langs and not languages & set(langs):
            continue
        general.append((-_overlap(terms, item.search_text), -item.support, item))
    scoped.sort(key=lambda t: (t[0], t[1], t[2], t[3].key))
    general.sort(key=lambda t: (t[0], t[1], t[2].key))
    # Where the retrieved files' tests live, then other items about those files; two slots for
    # repository-wide items the query mentions.
    relevant_general = [t[2] for t in general if t[0] < 0][:2]
    picked = [t[3] for t in scoped][:MAX_ITEMS - len(relevant_general)] + relevant_general
    skills = []
    for skill in db.execute(select(MemorySkill).where(MemorySkill.repository_id.in_(repo_ids),
                                                      MemorySkill.status == "active")
                            .order_by(MemorySkill.support.desc())).scalars():
        globs = (skill.scope or {}).get("paths") or []
        if any(glob_match(g, p) for g in globs for p in rank_of_path):
            skills.append(skill_to_dict(skill))
        if len(skills) >= MAX_SKILLS:
            break
    return {"briefs": briefs, "items": [item_to_dict(i) for i in picked[:MAX_ITEMS]], "skills": skills}


def search_memory(db: Session, embedder, query: str, repo_ids: list[uuid.UUID] | None, *, k: int = 8,
                  kinds: list[str] | None = None) -> list[dict]:
    """Active memory items for ``query``: keyword overlap and dense similarity, fused by RRF."""
    stmt = select(MemoryItem).options(defer(MemoryItem.embedding)).where(MemoryItem.status == "active")
    if repo_ids:
        stmt = stmt.where(MemoryItem.repository_id.in_(repo_ids))
    if kinds:
        stmt = stmt.where(MemoryItem.kind.in_(kinds))
    items = {str(i.id): i for i in db.execute(stmt).scalars()}
    if not items:
        return []
    terms = set(query_terms(query))
    keyword = sorted(((i, _overlap(terms, item.search_text)) for i, item in items.items()), key=lambda t: -t[1])
    keyword = [i for i, score in keyword if score > 0][:50]
    dense: list[str] = []
    if embedder is not None:
        try:
            qvec = embedder.embed_query(query)
        except Exception:  # noqa: BLE001 - memory search degrades to keyword, never fails the call
            qvec = None
        if qvec is not None:
            dense = _dense(db, qvec, embedder.model_id, list(items))
    scores: dict[str, float] = {}
    for ranking in (keyword, dense):
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (RRF_K + rank)
    ranked = sorted(scores, key=lambda i: -scores[i])[:k]
    return [item_to_dict(items[i]) | {"score": round(scores[i], 5)} for i in ranked]


def _dense(db: Session, qvec: list[float], model_id: str, ids: list[str], limit: int = 50) -> list[str]:
    uuids = [uuid.UUID(i) for i in ids]
    if db.get_bind().dialect.name == "postgresql":
        distance = MemoryItem.embedding.op("<=>", return_type=Float)(bindparam("qvec", qvec, type_=EmbeddingVector()))
        rows = db.execute(select(MemoryItem.id).where(MemoryItem.id.in_(uuids), MemoryItem.embedding_model == model_id,
                                                      MemoryItem.embedding.isnot(None))
                          .order_by(distance).limit(limit)).scalars()
        return [str(r) for r in rows]
    rows = db.execute(select(MemoryItem.id, MemoryItem.embedding).where(
        MemoryItem.id.in_(uuids), MemoryItem.embedding_model == model_id, MemoryItem.embedding.isnot(None))).all()

    def cos(a, b):
        num = sum(x * y for x, y in zip(a, b, strict=False))
        den = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
        return num / den if den else 0.0

    return [str(i) for i, _ in sorted(rows, key=lambda r: -cos(qvec, r[1]))[:limit]]


def list_skills(db: Session, repo_ids: list[uuid.UUID] | None) -> list[dict]:
    stmt = select(MemorySkill).where(MemorySkill.status == "active").order_by(MemorySkill.support.desc())
    if repo_ids:
        stmt = stmt.where(MemorySkill.repository_id.in_(repo_ids))
    return [skill_to_dict(s) for s in db.execute(stmt).scalars()]


def get_skill(db: Session, repo_ids: list[uuid.UUID] | None, name: str, level: int = 1) -> dict | None:
    stmt = select(MemorySkill).where(MemorySkill.name == name, MemorySkill.status == "active")
    if repo_ids:
        stmt = stmt.where(MemorySkill.repository_id.in_(repo_ids))
    skill = db.execute(stmt).scalars().first()
    return skill_to_dict(skill, level=max(0, min(level, 2))) if skill else None
