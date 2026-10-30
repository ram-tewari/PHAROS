"""Code-intelligence API.

=======  ==================================  ======  ==============================
Method   Path                                Scope   Purpose
=======  ==================================  ======  ==============================
POST     /api/v1/repositories                admin   queue an ingestion job
GET      /api/v1/repositories                read    indexed repositories
GET      /api/v1/repositories/{id}           read    one repository + index stats
DELETE   /api/v1/repositories/{id}           admin   remove a repository's index
GET      /api/v1/ingestion/jobs              read    recent jobs
GET      /api/v1/ingestion/jobs/{id}         read    job state
POST     /api/v1/ingestion/jobs/{id}/cancel  admin   cancel a queued job
POST     /api/v1/search/code                 read    chunk-level code search
POST     /api/v1/search/symbol               read    definition lookup + call graph
POST     /api/v1/context/retrieve            read    assistant context assembly
POST     /api/v1/repositories/{id}/learn     admin   queue a learning job (run on the Mac)
GET      /api/v1/learning/jobs               read    recent learning jobs
GET      /api/v1/memory/brief                read    a repository's brief (core memory)
POST     /api/v1/memory/search               read    search active memory items
GET      /api/v1/memory/items                read    memory items by status / kind
PATCH    /api/v1/memory/items/{id}           admin   accept / reject / archive / restore
GET      /api/v1/memory/skills               read    playbooks (level 0)
GET      /api/v1/memory/skills/{name}        read    one playbook (levels 1-2)
GET      /api/v1/system/status               read    backends, grammars, config
=======  ==================================  ======  ==============================
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from ...codeintel import jobs
from ...codeintel.context import (
    ContextRequest,
    RepositoryNotFound,
    assemble_context,
    hit_to_dict,
    resolve_repositories,
    source_requests,
)
from ...codeintel.embeddings import get_embedder
from ...codeintel.git_source import RepoSpecError, parse_repo_spec, validate_ref
from ...codeintel.notify import get_notifier
from ...codeintel.parsers import grammar_status
from ...codeintel.retrieval import Filters, Hit, ModeUnavailable, Retriever
from ...codeintel.runtime import secret
from ...codeintel.source import resolve_sources
from ...codeintel.symbols import chunk_ref, find_symbol, repository_summary, symbol_graph
from ...config.settings import get_settings
from ...database.models import (
    CodeEdge,
    DocumentChunk,
    IngestionJob,
    LearningJob,
    MemoryItem,
    Repository,
    Resource,
)
from ...learning import recall
from ...learning.memory import set_status
from ...shared.auth import require_admin, token_problems
from ...shared.database import get_sync_db
from .schemas import (
    ContextRequestIn,
    ContextResponse,
    JobOut,
    JobSubmitted,
    RepositoryOut,
    RepositorySubmit,
    MemorySearchRequest,
    SearchRequest,
    SearchResponse,
    SymbolRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["code-intelligence"])


def job_out(job: IngestionJob) -> JobOut:
    return JobOut(
        id=str(job.id),
        repo_url=job.repo_url,
        branch=job.branch_key or None,
        status=job.status,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        error_kind=job.error_kind,
        error=job.error,
        commit_sha=job.commit_sha,
        repository_id=str(job.repository_id) if job.repository_id else None,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        heartbeat_at=job.heartbeat_at,
        available_at=job.available_at,
        stats=job.stats,
    )


def _mode_unavailable(exc: ModeUnavailable) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"error": "mode_unavailable", "mode": exc.mode, "detail": exc.reason},
    )


# ── repositories & jobs ────────────────────────────────────────────────────


@router.post("/repositories", response_model=JobSubmitted, status_code=status.HTTP_202_ACCEPTED)
def submit_repository(body: RepositorySubmit, db: Session = Depends(get_sync_db), _=Depends(require_admin)):
    """Queue (or return the already-active) ingestion job for a repository."""
    settings = get_settings()
    try:
        ref = parse_repo_spec(body.repository, allowed_hosts=settings.CODEINTEL_ALLOWED_GIT_HOSTS)
        branch = validate_ref(body.branch)
    except RepoSpecError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_repository", "detail": str(exc)}) from exc
    try:
        submission = jobs.submit(db, ref, branch, force=body.force, max_queued=settings.QUEUE_SIZE)
    except jobs.QueueFull as exc:
        raise HTTPException(
            status_code=429,
            detail={"error": "queue_full", "detail": str(exc), "queued": exc.queued, "limit": exc.limit},
            headers={"Retry-After": "60"},
        ) from exc
    notified = get_notifier(settings).notify(str(submission.job.id)) if submission.created else False
    return JobSubmitted(job=job_out(submission.job), created=submission.created, notified=notified)


@router.get("/repositories", response_model=list[RepositoryOut])
def list_repositories(db: Session = Depends(get_sync_db)):
    repos = db.execute(select(Repository).order_by(Repository.name)).scalars().all()
    return [repository_summary(db, r) for r in repos]


def _get_repo(db: Session, repo_id: uuid.UUID) -> Repository:
    repo = db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "detail": "repository not found"})
    return repo


@router.get("/repositories/{repo_id}", response_model=RepositoryOut)
def get_repository(repo_id: uuid.UUID, db: Session = Depends(get_sync_db)):
    return repository_summary(db, _get_repo(db, repo_id))


@router.delete("/repositories/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repository(repo_id: uuid.UUID, db: Session = Depends(get_sync_db), _=Depends(require_admin)):
    """Delete a repository's index (chunks, edges, file records). Source is untouched."""
    repo = _get_repo(db, repo_id)
    active = db.execute(
        select(IngestionJob.id).where(IngestionJob.repo_url == repo.url, IngestionJob.status == "running")
    ).first()
    if active:
        raise HTTPException(status_code=409, detail={"error": "job_running", "detail": "wait for the running job"})
    db.execute(delete(CodeEdge).where(CodeEdge.repository_id == repo_id))
    db.execute(delete(DocumentChunk).where(DocumentChunk.repository_id == repo_id))
    db.execute(delete(Resource).where(Resource.repository_id == repo_id))
    db.execute(delete(Repository).where(Repository.id == repo_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/ingestion/jobs", response_model=list[JobOut])
def list_jobs(
    status_filter: str | None = Query(None, alias="status", pattern="^(queued|running|succeeded|failed|cancelled)$"),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_sync_db),
):
    stmt = select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(IngestionJob.status == status_filter)
    return [job_out(j) for j in db.execute(stmt).scalars()]


@router.get("/ingestion/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_sync_db)):
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "detail": "job not found"})
    return job_out(job)


@router.post("/ingestion/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: uuid.UUID, db: Session = Depends(get_sync_db), _=Depends(require_admin)):
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "detail": "job not found"})
    if not jobs.cancel(db, job_id):
        raise HTTPException(status_code=409, detail={"error": "not_cancellable", "detail": f"job is {job.status}"})
    db.refresh(job)
    return job_out(job)


# ── retrieval ──────────────────────────────────────────────────────────────


def _filters(db: Session, repository: str | None, languages, kinds, path_prefix) -> Filters:
    try:
        repos = resolve_repositories(db, repository)
    except RepositoryNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "repository_not_found", "detail": str(exc)}) from exc
    return Filters(
        repository_ids=[r.id for r in repos] or None,
        languages=languages,
        kinds=kinds,
        path_prefix=path_prefix,
    )


@router.post("/search/code", response_model=SearchResponse)
def search_code(body: SearchRequest, db: Session = Depends(get_sync_db)):
    """Chunk-level retrieval. ``mode=auto`` reports what it actually used."""
    filters = _filters(db, body.repository, body.languages, body.kinds, body.path_prefix)
    try:
        outcome = Retriever(db, get_embedder()).search(body.query, mode=body.mode, k=body.k, filters=filters,
                                                       hints=body.hints)
    except ModeUnavailable as exc:
        raise _mode_unavailable(exc) from exc
    return SearchResponse(
        query=outcome.query,
        mode_requested=outcome.mode_requested,
        mode_used=outcome.mode_used,
        embedding_model=outcome.embedding_model,
        warnings=outcome.warnings,
        results=[hit_to_dict(h, i) for i, h in enumerate(outcome.hits, start=1)],
        timings_ms=outcome.timings_ms,
        candidates=outcome.candidates,
    )


@router.post("/context/retrieve", response_model=ContextResponse)
def retrieve_context(body: ContextRequestIn, db: Session = Depends(get_sync_db)):
    """Everything an assistant needs to answer ``query``: ranked code with
    verified source, callers/callees, coding rules and a Markdown rendering."""
    settings = get_settings()
    try:
        return assemble_context(
            db,
            get_embedder(),
            ContextRequest(**body.model_dump()),
            fetch_token=secret(settings.GIT_CLONE_TOKEN),
        )
    except RepositoryNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "repository_not_found", "detail": str(exc)}) from exc
    except ModeUnavailable as exc:
        raise _mode_unavailable(exc) from exc


@router.post("/search/symbol")
def lookup_symbol(body: SymbolRequest, db: Session = Depends(get_sync_db)):
    """Find definitions by (qualified) name, with code and resolved call graph."""
    filters = _filters(db, body.repository, None, None, None)
    matches = find_symbol(db, body.name, repository_ids=filters.repository_ids, limit=body.limit)
    out = []
    hits = []
    for c in matches:
        repo = db.get(Repository, c.repository_id)
        item = chunk_ref(c) | {
            "repository": {"id": str(repo.id), "name": repo.name, "url": repo.url},
            "commit_sha": c.branch_reference,
            "summary": c.semantic_summary,
            "parser": c.parser,
        }
        if body.include_graph:
            item["graph"] = symbol_graph(db, c.id)
        out.append(item)
        hits.append(Hit(
            chunk_id=str(c.id), score=0.0, evidence=None, repository_id=str(repo.id),  # type: ignore[arg-type]
            repository_url=repo.url, path=(c.chunk_metadata or {}).get("path", ""), kind=c.ast_node_type,
            start_line=c.start_line, end_line=c.end_line, commit_sha=c.branch_reference,
            resource_id=str(c.resource_id),
        ))
    if body.include_code and hits:
        results = resolve_sources(source_requests(db, hits), token=secret(get_settings().GIT_CLONE_TOKEN))
        for item in out:
            res = results.get(item["chunk_id"])
            item["code_status"] = res.status if res else "unavailable:unknown"
            item["code"] = res.code if res else None
            item["verified"] = bool(res and res.verified)
    return {"name": body.name, "matches": out}


@router.get("/system/status")
def system_status(db: Session = Depends(get_sync_db)):
    """Which backends are configured and working. Contains no secrets."""
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        database = {"status": "ok", "dialect": db.get_bind().dialect.name}
    except Exception as exc:
        database = {"status": "error", "error": type(exc).__name__}
    try:
        embedder = get_embedder(settings)
        embedding = embedder.describe() if embedder else {"backend": "none"}
    except Exception as exc:
        embedding = {"backend": settings.EMBEDDING_BACKEND, "error": str(exc)}
    counts = {
        "repositories": db.execute(select(func.count(Repository.id))).scalar_one(),
        "chunks": db.execute(select(func.count(DocumentChunk.id)).where(DocumentChunk.repository_id.isnot(None))).scalar_one(),
        "jobs_queued": db.execute(select(func.count(IngestionJob.id)).where(IngestionJob.status == "queued")).scalar_one(),
        "jobs_running": db.execute(select(func.count(IngestionJob.id)).where(IngestionJob.status == "running")).scalar_one(),
        "memory_items_active": db.execute(
            select(func.count(MemoryItem.id)).where(MemoryItem.status == "active")).scalar_one(),
        "memory_items_proposed": db.execute(
            select(func.count(MemoryItem.id)).where(MemoryItem.status == "proposed")).scalar_one(),
        "learning_jobs_queued": db.execute(
            select(func.count(LearningJob.id)).where(LearningJob.status == "queued")).scalar_one(),
    }
    return {
        "mode": settings.MODE,
        "database": database,
        "embedding": embedding,
        "notifier": get_notifier(settings).name,
        "grammars": grammar_status(),
        "index": counts,
        "config_warnings": token_problems(),
    }


# ── learning and memory ─────────────────────────────────────────────────

def _repo_ids(db: Session, repository: str | None) -> list[uuid.UUID]:
    try:
        return [r.id for r in resolve_repositories(db, repository)]
    except RepositoryNotFound as exc:
        raise HTTPException(status_code=404, detail={"error": "repository_not_found", "detail": str(exc)}) from exc


def _learning_job_out(job: LearningJob) -> dict:
    return {"id": str(job.id), "repository_id": str(job.repository_id), "commit_sha": job.commit_sha,
            "status": job.status, "attempts": job.attempts, "error": job.error, "error_kind": job.error_kind,
            "stats": job.stats, "created_at": job.created_at, "finished_at": job.finished_at}


@router.post("/repositories/{repo_id}/learn", status_code=status.HTTP_202_ACCEPTED)
def queue_learning(repo_id: uuid.UUID, db: Session = Depends(get_sync_db), _=Depends(require_admin)):
    """Queue a learning job at the repository's indexed commit. The Mac's learning worker runs it."""
    from ...learning.pipeline import submit_learning

    repo = _get_repo(db, repo_id)
    if not repo.last_commit_sha:
        raise HTTPException(status_code=409, detail={"error": "not_indexed", "detail": "index the repository first"})
    job, created = submit_learning(db, repo)
    return {"created": created, "job": _learning_job_out(job)}


@router.get("/learning/jobs")
def list_learning_jobs(limit: int = Query(20, ge=1, le=200), db: Session = Depends(get_sync_db)):
    rows = db.execute(select(LearningJob).order_by(LearningJob.created_at.desc()).limit(limit)).scalars()
    return [_learning_job_out(j) for j in rows]


@router.get("/memory/brief")
def memory_brief(repository: str = Query(..., min_length=1), db: Session = Depends(get_sync_db)):
    """The repository brief (≤ 2,200 characters, frozen per indexed commit)."""
    out = []
    for repo_id in _repo_ids(db, repository):
        repo = db.get(Repository, repo_id)
        brief = recall.get_brief(db, repo)
        out.append({"repository": repo.name, "commit_sha": brief.commit_sha if brief else None,
                    "indexed_commit": repo.last_commit_sha, "text": brief.text if brief else None})
    return {"briefs": out}


@router.post("/memory/search")
def memory_search(body: MemorySearchRequest, db: Session = Depends(get_sync_db)):
    ids = _repo_ids(db, body.repository) if body.repository else None
    return {"query": body.query,
            "results": recall.search_memory(db, get_embedder(), body.query, ids, k=body.k, kinds=body.kinds)}


@router.get("/memory/items")
def memory_items(repository: str | None = None, status_: str = Query("active", alias="status"),
                 kind: str | None = None, limit: int = Query(100, ge=1, le=1000),
                 db: Session = Depends(get_sync_db)):
    stmt = select(MemoryItem).where(MemoryItem.status == status_).order_by(MemoryItem.key).limit(limit)
    if repository:
        stmt = stmt.where(MemoryItem.repository_id.in_(_repo_ids(db, repository)))
    if kind:
        stmt = stmt.where(MemoryItem.kind == kind)
    return {"items": [recall.item_to_dict(i, full=True) for i in db.execute(stmt).scalars()]}


@router.patch("/memory/items/{item_id}")
def review_memory_item(item_id: uuid.UUID, action: str = Query(..., pattern="^(accept|reject|archive|restore)$"),
                       db: Session = Depends(get_sync_db), _=Depends(require_admin)):
    """A human decision on a memory item. Learning runs never override it."""
    item = db.get(MemoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="memory item not found")
    set_status(db, item, action)
    db.commit()
    return recall.item_to_dict(item, full=True)


@router.get("/memory/skills")
def memory_skills(repository: str | None = None, db: Session = Depends(get_sync_db)):
    ids = _repo_ids(db, repository) if repository else None
    return {"skills": recall.list_skills(db, ids)}


@router.get("/memory/skills/{name}")
def memory_skill(name: str, repository: str | None = None, level: int = Query(1, ge=0, le=2),
                 db: Session = Depends(get_sync_db)):
    ids = _repo_ids(db, repository) if repository else None
    skill = recall.get_skill(db, ids, name, level)
    if skill is None:
        raise HTTPException(status_code=404, detail="skill not found")
    return skill
