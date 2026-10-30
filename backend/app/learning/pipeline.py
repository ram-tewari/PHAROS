"""One learning run: mine an indexed repository and update its memory.

Runs on the owner's Mac (``learning_worker`` or ``pharos learn``), never in
the API process: it needs the full git history and, for L2, Codex.

``learn_repository`` reads the index and a checkout of the indexed commit,
runs every L1 miner, applies the candidates through
:class:`~app.learning.memory.MemoryWriter` (add / patch / stale, ledgered
under one run id), embeds the items whose text changed, and freezes a new
repository brief for the commit.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..codeintel import jobs
from ..codeintel.embeddings import Embedder
from ..codeintel.retrieval import path_role
from ..database.models import CodeEdge, DocumentChunk, LearningJob, MemoryItem, MemorySkill, RepoBrief, Repository
from .brief import compose_brief
from .extract import extract
from .history import HistoryError, _git, ensure_mirror, load_history, mirror_name, worktree
from .memory import MemoryWriter, check_evidence
from .miners import MINERS, Chunk, Snapshot, mine_playbooks, tracked_files
from .reviews import check_review

logger = logging.getLogger(__name__)


def load_snapshot(db: Session, repo: Repository, checkout: Path, mirror: Path, commit: str,
                  *, history: bool = True) -> Snapshot:
    rows = db.execute(
        select(DocumentChunk.chunk_metadata, DocumentChunk.ast_node_type, DocumentChunk.symbol_name,
               DocumentChunk.language, DocumentChunk.start_line, DocumentChunk.end_line)
        .where(DocumentChunk.repository_id == repo.id)
    ).all()
    chunks = []
    for meta, kind, symbol, language, start, end in rows:
        meta = meta or {}
        path = meta.get("path", "")
        chunks.append(Chunk(path=path, kind=kind or "", symbol=symbol or "", name=meta.get("name") or "",
                            parent=meta.get("parent"), language=language or "", start=start or 1,
                            end=end or start or 1, signature=meta.get("signature") or "",
                            docstring=meta.get("docstring") or "", role=path_role(path)))
    snap = Snapshot(name=repo.name, commit=commit, checkout=checkout, mirror=mirror, chunks=chunks,
                    files=tracked_files(checkout))
    target = DocumentChunk.__table__.alias("target")
    target_path = target.c.chunk_metadata["path"].as_string()
    for path, n in db.execute(
        select(target_path, func.count())
        .select_from(CodeEdge).join(target, target.c.id == CodeEdge.target_chunk_id)
        .where(CodeEdge.repository_id == repo.id, CodeEdge.edge_type == "calls")
        .group_by(target_path)
    ):
        snap.callers[path or ""] += n
    if history:
        snap.history = load_history(mirror, commit)
    return snap


def _grounding(snap: Snapshot, url: str) -> Callable[[dict], bool]:
    known = {c.sha for c in snap.history}
    origin = url
    if not url.startswith("https://"):
        try:
            origin = _git(snap.mirror, "remote", "get-url", "origin").strip()
        except HistoryError:
            pass

    def check(evidence: dict) -> bool:
        if evidence.get("kind") == "commit" and evidence.get("sha") in known:
            return True
        if evidence.get("kind") == "review":
            return check_review(evidence, mirror_name(origin)) or check_review(evidence, mirror_name(url))
        return check_evidence(evidence, snap.checkout, snap.mirror)

    return check


def embed_items(db: Session, repository_id, embedder: Embedder | None, batch: int = 64) -> int:
    if embedder is None:
        return 0
    rows = db.execute(select(MemoryItem).where(
        MemoryItem.repository_id == repository_id,
        (MemoryItem.embedding.is_(None)) | (MemoryItem.embedding_model != embedder.model_id),
    )).scalars().all()
    for start in range(0, len(rows), batch):
        part = rows[start:start + batch]
        vectors = embedder.embed_documents([f"{r.title}\n{r.body}" for r in part])
        for row, vector in zip(part, vectors, strict=True):
            row.embedding, row.embedding_model = vector, embedder.model_id
    return len(rows)


def learn_repository(db: Session, repo: Repository, *, checkout: Path, mirror: Path, commit: str,
                     embedder: Embedder | None = None, run_id: str | None = None,
                     families: list[str] | None = None, llm=None, max_llm_calls: int = 10,
                     review_token: str | None = None,
                     progress: Callable[[str], None] = lambda _m: None) -> dict:
    """Mine ``repo`` at ``commit`` (``checkout`` must be that commit's tree) and update its memory.

    With ``llm`` (a ``CodexCLI``), L2 extraction runs after the deterministic
    miners, spending at most ``max_llm_calls`` calls on evidence it has not read.
    """
    run_id = run_id or f"learn-{uuid.uuid4().hex[:16]}"
    t0 = time.perf_counter()
    snap = load_snapshot(db, repo, checkout, mirror, commit)
    progress(f"{repo.name}: {len(snap.chunks)} chunks, {len(snap.files)} files, {len(snap.history)} commits")
    timings = {"load": round(time.perf_counter() - t0, 2)}
    candidates, ran, by_family = [], set(), {}
    for family, miner in MINERS.items():
        if families and family not in families:
            continue
        t = time.perf_counter()
        try:
            found = miner(snap)
        except (HistoryError, OSError, ValueError) as exc:  # one miner failing never blocks the others
            logger.warning("miner %s failed on %s: %s", family, repo.name, exc)
            by_family[family] = f"failed: {exc}"[:200]
            continue
        for cand in found:
            cand.family = family
        candidates += found
        ran.add(family)
        by_family[family] = len(found)
        timings[family] = round(time.perf_counter() - t, 2)
    skills = mine_playbooks(snap) if not families or "playbooks" in families else []
    grounding = _grounding(snap, repo.url)
    writer = MemoryWriter(db, repo.id, commit, run_id, grounding=grounding)
    writer.apply(candidates)
    # A family's items are retired only when that family ran: key prefixes map to families.
    prefixes = {"naming": "naming", "docs": "docs", "typing": "typing", "exceptions": "exceptions",
                "deprecation": "deprecation", "tests": "tests", "changelog": "changelog", "commits": "commits",
                "tooling": "tooling", "cochange": "cochange", "history": "history"}
    writer.retire({prefixes[f] for f in ran}, {c.key for c in candidates})
    if not families or "playbooks" in families:
        writer.apply_skills(skills)
    # Model-derived items stay only while what they cite still holds (documents can change).
    for row in db.execute(select(MemoryItem).where(MemoryItem.repository_id == repo.id, MemoryItem.tier == "L2",
                                                   MemoryItem.status.in_(("active", "proposed")))).scalars():
        if not all(grounding(e) for e in row.evidence or []):
            writer.mark_stale(row, reason="evidence no longer holds")
    db.flush()
    l2 = None
    if llm is not None and (not families or "l2" in families):
        t = time.perf_counter()
        writer.actor = "codex"
        l2 = vars(extract(db, snap, repo, writer, llm, max_calls=max_llm_calls, token=review_token))
        writer.actor = "learner"
        timings["l2"] = round(time.perf_counter() - t, 2)
        progress(f"{repo.name}: L2 {l2['calls']} calls, {l2['added']} proposed, {l2['patched']} patched, "
                 f"rejected {l2['rejected']}")
    embedded = embed_items(db, repo.id, embedder)
    items = db.execute(select(MemoryItem).where(MemoryItem.repository_id == repo.id,
                                                MemoryItem.status == "active")).scalars().all()
    active_skills = db.execute(select(MemorySkill).where(MemorySkill.repository_id == repo.id,
                                                         MemorySkill.status == "active")).scalars().all()
    text, sections = compose_brief(snap, list(items), list(active_skills))
    brief = db.execute(select(RepoBrief).where(RepoBrief.repository_id == repo.id,
                                               RepoBrief.commit_sha == commit)).scalar_one_or_none()
    if brief is None:
        db.add(RepoBrief(repository_id=repo.id, commit_sha=commit, text=text, sections=sections))
    else:
        brief.text, brief.sections = text, sections
    db.commit()
    timings["total"] = round(time.perf_counter() - t0, 2)
    stats = {"run_id": run_id, "commit": commit, "candidates": len(candidates), "skills": len(skills),
             "by_family": by_family, **writer.stats.as_dict(), "embedded": embedded, "brief_chars": len(text),
             "l2": l2, "timings_s": timings}
    progress(f"{repo.name}: {stats['added']} added, {stats['patched']} patched, {stats['staled']} stale, "
             f"{stats['activated']} active, {stats['proposed']} proposed")
    return stats


# ── jobs ────────────────────────────────────────────────────────────────

def submit_learning(db: Session, repo: Repository, *, commit: str | None = None, options: dict | None = None,
                    max_attempts: int = 3) -> tuple[LearningJob, bool]:
    """Queue a learning job for ``repo`` (at its indexed commit), or return its active one."""
    existing = db.execute(select(LearningJob).where(LearningJob.repository_id == repo.id,
                                                    LearningJob.status.in_(jobs.ACTIVE))).scalar_one_or_none()
    if existing is not None:
        return existing, False
    job = LearningJob(repository_id=repo.id, commit_sha=commit or repo.last_commit_sha, options=options,
                      status="queued", attempts=0, max_attempts=max_attempts)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.execute(select(LearningJob).where(LearningJob.repository_id == repo.id,
                                                    LearningJob.status.in_(jobs.ACTIVE))).scalar_one(), False
    db.refresh(job)
    return job, True


def queue_unlearned(db: Session) -> list[LearningJob]:
    """Queue learning for every indexed repository whose current commit has no brief yet."""
    queued = []
    for repo in db.execute(select(Repository).where(Repository.index_status == "ready",
                                                    Repository.last_commit_sha.isnot(None))).scalars():
        has_brief = db.execute(select(RepoBrief.id).where(RepoBrief.repository_id == repo.id,
                                                          RepoBrief.commit_sha == repo.last_commit_sha)).first()
        if not has_brief:
            job, created = submit_learning(db, repo)
            if created:
                queued.append(job)
    return queued


def run_learning_job(db: Session, job: LearningJob, embedder: Embedder | None, *,
                     mirror_root: Path | None = None, llm=None, max_llm_calls: int = 10,
                     review_token: str | None = None) -> LearningJob:
    """Execute a claimed learning job to a terminal (or re-queued) state. Never raises."""
    job_id = job.id
    try:
        repo = db.get(Repository, job.repository_id)
        commit = job.commit_sha or repo.last_commit_sha
        if not commit:
            raise HistoryError("repository has no indexed commit")
        if commit != repo.last_commit_sha:
            raise HistoryError(f"job is for {commit[:12]} but the index is at {(repo.last_commit_sha or '?')[:12]}")
        mirror = ensure_mirror(repo.url, commit, root=mirror_root,
                               local_path=repo.local_path if repo.source_type == "local" else None)
        with worktree(mirror, commit) as checkout:
            stats = learn_repository(db, repo, checkout=checkout, mirror=mirror, commit=commit, embedder=embedder,
                                     run_id=f"job-{job_id}", llm=llm, max_llm_calls=max_llm_calls,
                                     review_token=review_token,
                                     progress=lambda m: jobs.heartbeat(db, job_id, LearningJob) or logger.info(m))
    except Exception as exc:  # noqa: BLE001 - a job records every failure
        db.rollback()
        job = db.get(LearningJob, job_id)
        retryable = isinstance(exc, (HistoryError, OSError, TimeoutError)) and not str(exc).startswith("job is for")
        job.error_kind = "history" if isinstance(exc, HistoryError) else "internal_error"
        job.error = f"{type(exc).__name__}: {exc}"[:2000]
        if retryable and job.attempts < job.max_attempts:
            job.status = "queued"
            job.available_at = jobs.utcnow() + timedelta(seconds=jobs.retry_delay_seconds(job.attempts))
        else:
            job.status, job.finished_at = "failed", jobs.utcnow()
        logger.warning("learning job %s failed (%s): %s", job_id, job.error_kind, exc)
        db.commit()
        return job
    job = db.get(LearningJob, job_id)
    job.status, job.stats, job.finished_at = "succeeded", stats, jobs.utcnow()
    job.error = job.error_kind = None
    db.commit()
    return job
