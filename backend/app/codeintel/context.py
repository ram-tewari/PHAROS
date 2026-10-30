"""Context assembly for coding assistants.

``assemble_context`` answers "what code should the assistant look at for
this question?" with:

* ranked chunks, each with a source pointer (repository, commit, path,
  lines), the retrieval evidence, and — unless disabled — the code itself,
  verified against the indexed blob SHA;
* graph neighbours of the top hits (callers / callees / imports) as compact
  summaries;
* ACTIVE coding rules learned for the repository (pattern-learning loop);
* ``context_text``: the same material rendered as Markdown with
  ``path:start-end`` citations, cut to a character budget.

The response is plain JSON-serialisable data; the REST endpoint, the MCP
tool and the CLI all return it unchanged.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database.models import CodingProfile, DocumentChunk, ProposedRule, Repository, Resource
from .embeddings import Embedder
from .git_source import web_file_url
from .retrieval import Filters, Hit, Retriever, repositories_matching
from .source import SourceRequest, resolve_sources

MODULE_CODE_LINES = 40


class RepositoryNotFound(LookupError):
    pass


@dataclass
class ContextRequest:
    query: str
    repository: str | None = None
    max_chunks: int = 8
    mode: str = "auto"
    include_code: bool = True
    include_related: bool = True
    include_rules: bool = True
    profile_id: str | None = None  # a CodingProfile's rules instead of the repository's
    max_chars: int = 24_000
    languages: list[str] | None = None
    path_prefix: str | None = None
    kinds: list[str] | None = None
    hints: list[str] | None = None  # identifiers / keywords the caller guesses


@dataclass
class _Budget:
    limit: int
    used: int = 0
    truncated: bool = False

    def take(self, text: str) -> str | None:
        remaining = self.limit - self.used
        if remaining <= 0:
            self.truncated = True
            return None
        if len(text) > remaining:
            self.truncated = True
            text = text[:remaining]
        self.used += len(text)
        return text


def resolve_repositories(db: Session, ref: str | None) -> list[Repository]:
    if ref is None:
        return []
    repos = repositories_matching(db, ref)
    if not repos:
        raise RepositoryNotFound(f"no indexed repository matches {ref!r}")
    return repos


def hit_to_dict(h: Hit, rank: int) -> dict:
    return {
        "rank": rank,
        "chunk_id": h.chunk_id,
        "score": round(h.score, 6),
        "repository": {"id": h.repository_id, "name": h.repository_name, "url": h.repository_url},
        "path": h.path,
        "language": h.language,
        "kind": h.kind,
        "symbol": h.symbol,
        "start_line": h.start_line,
        "end_line": h.end_line,
        "commit_sha": h.commit_sha,
        "parser": h.parser,
        "fallback_reason": h.fallback_reason,
        "summary": h.summary,
        "evidence": h.evidence.as_dict(),
        "source_url": (
            web_file_url(h.repository_url, h.commit_sha, h.path, h.start_line, h.end_line)
            if h.commit_sha
            else None
        ),
    }


def source_requests(db: Session, hits: list[Hit]) -> list[SourceRequest]:
    if not hits:
        return []
    repo_rows = {
        str(r.id): r
        for r in db.execute(
            select(Repository).where(Repository.id.in_({uuid.UUID(h.repository_id) for h in hits}))
        ).scalars()
    }
    blob = dict(
        db.execute(
            select(Resource.id, Resource.content_sha).where(
                Resource.id.in_({uuid.UUID(h.resource_id) for h in hits if h.resource_id})
            )
        ).all()
    )
    reqs = []
    for h in hits:
        repo = repo_rows[h.repository_id]
        start, end = h.start_line or 1, h.end_line or 1
        if h.kind == "module":
            end = min(end, start + MODULE_CODE_LINES - 1)
        reqs.append(
            SourceRequest(
                key=h.chunk_id,
                source_type=repo.source_type,
                repository_url=repo.url,
                local_path=repo.local_path,
                commit=h.commit_sha or "",
                path=h.path,
                start_line=start,
                end_line=end,
                blob_sha=blob.get(uuid.UUID(h.resource_id)) if h.resource_id else None,
            )
        )
    return reqs


def assemble_context(db: Session, embedder: Embedder | None, req: ContextRequest,
                     *, fetch_token: str | None = None) -> dict:
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    repos = resolve_repositories(db, req.repository)
    filters = Filters(
        repository_ids=[r.id for r in repos] or None,
        languages=req.languages,
        kinds=req.kinds,
        path_prefix=req.path_prefix,
    )
    retriever = Retriever(db, embedder)
    outcome = retriever.search(req.query, mode=req.mode, k=req.max_chunks, filters=filters, hints=req.hints)
    timings.update({f"retrieval_{k}": v for k, v in outcome.timings_ms.items()})

    chunks = [hit_to_dict(h, i) for i, h in enumerate(outcome.hits, start=1)]

    t = time.perf_counter()
    if req.include_code and outcome.hits:
        results = resolve_sources(source_requests(db, outcome.hits), token=fetch_token)
        for c in chunks:
            res = results.get(c["chunk_id"])
            c["code_status"] = res.status if res else "unavailable:unknown"
            c["code"] = res.code if res else None
            c["verified"] = bool(res and res.verified)
            if c["kind"] == "module" and res and res.code is not None:
                c["code_truncated_to_lines"] = MODULE_CODE_LINES
    else:
        for c in chunks:
            c["code_status"] = "not_requested"
            c["code"] = None
            c["verified"] = False
    timings["resolve_code"] = (time.perf_counter() - t) * 1000

    related: list[dict] = []
    if req.include_related and outcome.hits:
        t = time.perf_counter()
        hit_ids = {h.chunk_id for h in outcome.hits}
        edges = retriever.neighbors([h.chunk_id for h in outcome.hits[:3]], limit=12)
        neighbor_ids = [uuid.UUID(n) for _, n, _ in edges if n not in hit_ids]
        rows = {
            str(c.id): c
            for c in db.execute(select(DocumentChunk).where(DocumentChunk.id.in_(neighbor_ids))).scalars()
        } if neighbor_ids else {}
        seen = set()
        for seed, neighbor, relation in edges:
            c = rows.get(neighbor)
            if c is None or neighbor in seen:
                continue
            seen.add(neighbor)
            meta = c.chunk_metadata or {}
            related.append({
                "chunk_id": neighbor,
                "relation": relation,
                "via_chunk_id": seed,
                "path": meta.get("path"),
                "symbol": c.symbol_name,
                "kind": c.ast_node_type,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "summary": c.semantic_summary,
            })
        timings["related"] = (time.perf_counter() - t) * 1000

    rules: list[dict] = []
    warnings = list(outcome.warnings)
    if req.include_rules:
        if req.profile_id:
            if db.get(CodingProfile, req.profile_id) is None:
                warnings.append(f"unknown coding profile {req.profile_id!r}: no profile rules applied")
            rules = select_rules(db, profile_id=req.profile_id)
        else:
            urls = [r.url for r in repos] or list({h.repository_url for h in outcome.hits})
            names = [r.name for r in repos] or list({h.repository_name for h in outcome.hits})
            rules = select_rules(db, repositories=urls + names)

    budget = _Budget(req.max_chars)
    context_text = _render(req.query, chunks, related, rules, budget)
    timings["total"] = (time.perf_counter() - t0) * 1000

    return {
        "query": req.query,
        "mode_requested": outcome.mode_requested,
        "mode_used": outcome.mode_used,
        "embedding_model": outcome.embedding_model,
        "warnings": warnings,
        "repositories": [
            {"id": str(r.id), "name": r.name, "url": r.url, "commit_sha": r.last_commit_sha}
            for r in repos
        ],
        "chunks": chunks,
        "related": related,
        "rules": rules,
        "context_text": context_text,
        "stats": {
            "timings_ms": {k: round(v, 2) for k, v in timings.items()},
            "chars": len(context_text),
            "approx_tokens": len(context_text) // 4,
            "truncated": budget.truncated,
        },
    }


def select_rules(db: Session, *, profile_id: str | None = None, repositories: list[str] | None = None) -> list[dict]:
    """ACTIVE coding rules: a CodingProfile's (when ``profile_id`` is given)
    or those learned for ``repositories``; highest confidence first."""
    if profile_id:
        scope, limit = ProposedRule.profile_id == profile_id, 20
    elif repositories:
        scope, limit = ProposedRule.repository.in_(repositories), 10
    else:
        return []
    stmt = (
        select(ProposedRule)
        .where(ProposedRule.status == "ACTIVE", scope)
        .order_by(ProposedRule.confidence.desc())
        .limit(limit)
    )
    out = []
    for rule in db.execute(stmt).scalars():
        schema = rule.rule_schema or {}
        out.append({
            "name": rule.rule_name,
            "description": rule.rule_description,
            "confidence": rule.confidence,
            "pattern_type": schema.get("pattern_type"),
            "example": schema.get("example_code") or None,
            "file_path": rule.file_path,
            "profile_id": rule.profile_id,
        })
    return out

def _render(query: str, chunks: list[dict], related: list[dict], rules: list[dict], budget: _Budget) -> str:
    parts: list[str] = []
    header = budget.take(f"# Code context for: {query}\n")
    if header:
        parts.append(header)
    for c in chunks:
        cite = f"{c['repository']['name']}:{c['path']}:{c['start_line']}-{c['end_line']}"
        title = f"\n## [{c['rank']}] {c['symbol'] or c['path']} ({c['kind']}) — {cite}\n"
        body = title
        if c.get("code"):
            body += f"```{c['language'] or ''}\n{c['code']}\n```\n"
        else:
            body += f"{c['summary']}\n"
        taken = budget.take(body)
        if taken is None:
            break
        parts.append(taken)
    if related:
        lines = ["\n## Related code (call graph)\n"]
        for r in related:
            lines.append(f"- {r['relation']}: {r['symbol']} — {r['path']}:{r['start_line']}-{r['end_line']}\n")
        taken = budget.take("".join(lines))
        if taken:
            parts.append(taken)
    if rules:
        profile = rules[0].get("profile_id")
        lines = [f"\n## Coding rules (profile {profile})\n" if profile else "\n## Coding rules for this repository\n"]
        for r in rules:
            lines.append(f"- **{r['name']}**: {r['description']}\n")
            if r.get("example"):
                lines.append(f"  Example: `{r['example']}`\n")
        taken = budget.take("".join(lines))
        if taken:
            parts.append(taken)
    return "".join(parts)
