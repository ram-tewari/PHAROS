"""Definition lookup and call-graph navigation by symbol name."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database.models import CodeEdge, DocumentChunk, Repository


def find_symbol(db: Session, name: str, *, repository_ids: list[uuid.UUID] | None = None,
                limit: int = 10) -> list[DocumentChunk]:
    """Chunks whose qualified name equals ``name`` or ends with ``.name``.

    Exact qualified matches sort first, then shorter names (``Cart.total``
    before ``shop.cart.Cart.total`` when searching ``total``).
    """
    name = name.strip()
    if not name or len(name) > 512:
        return []
    escaped = name.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    stmt = select(DocumentChunk).where(
        DocumentChunk.repository_id.isnot(None),
        DocumentChunk.ast_node_type.notin_(["block"]),
        or_(
            DocumentChunk.symbol_name == name,
            DocumentChunk.symbol_name.like(f"%.{escaped}", escape="\\"),
        ),
    )
    if repository_ids:
        stmt = stmt.where(DocumentChunk.repository_id.in_(repository_ids))
    rows = db.execute(stmt.limit(200)).scalars().all()
    rows.sort(key=lambda c: (c.symbol_name != name, len(c.symbol_name or ""), c.symbol_name or ""))
    return rows[:limit]


def symbol_graph(db: Session, chunk_id: uuid.UUID, *, limit: int = 50) -> dict[str, list[dict]]:
    """Resolved callers, callees, containment and imports around one chunk."""
    out: dict[str, list[dict]] = {"calls": [], "called_by": [], "contains": [], "contained_by": [],
                                  "imports": [], "imported_by": []}
    edges = db.execute(
        select(CodeEdge.source_chunk_id, CodeEdge.target_chunk_id, CodeEdge.edge_type, CodeEdge.resolution)
        .where(or_(CodeEdge.source_chunk_id == chunk_id, CodeEdge.target_chunk_id == chunk_id))
        .limit(limit * 6)
    ).all()
    other_ids = {t if s == chunk_id else s for s, t, _, _ in edges if t is not None}
    chunks = {
        c.id: c for c in db.execute(select(DocumentChunk).where(DocumentChunk.id.in_(other_ids))).scalars()
    } if other_ids else {}
    inverse = {"calls": "called_by", "contains": "contained_by", "imports": "imported_by"}
    for src, dst, etype, resolution in edges:
        outgoing = src == chunk_id
        other = chunks.get(dst if outgoing else src)
        if other is None:
            continue
        relation = etype if outgoing else inverse[etype]
        if len(out[relation]) >= limit:
            continue
        out[relation].append(chunk_ref(other) | {"resolution": resolution})
    return out


def chunk_ref(c: DocumentChunk) -> dict:
    meta = c.chunk_metadata or {}
    return {
        "chunk_id": str(c.id),
        "symbol": c.symbol_name,
        "kind": c.ast_node_type,
        "path": meta.get("path"),
        "start_line": c.start_line,
        "end_line": c.end_line,
        "language": c.language,
    }


def repository_summary(db: Session, repo: Repository) -> dict:
    stats = repo.stats or {}
    return {
        "id": str(repo.id),
        "name": repo.name,
        "url": repo.url,
        "source_type": repo.source_type,
        "branch": repo.branch,
        "index_status": repo.index_status,
        "last_commit_sha": repo.last_commit_sha,
        "last_indexed_at": repo.last_indexed_at.isoformat() if repo.last_indexed_at else None,
        "total_files": repo.total_files,
        "total_lines": repo.total_lines,
        "chunks": stats.get("chunks_total"),
        "embedding_model": stats.get("embedding_model"),
        "languages": {
            name: {k: v for k, v in lang.items() if k in ("files", "ast_files", "fallback_files", "chunks", "fallback_reasons")}
            for name, lang in (stats.get("languages") or {}).items()
        },
        "graph": stats.get("graph"),
    }


HOVER_CONTEXT_LINES = 3


def hover(db: Session, resource, line: int, *, fetch_token: str | None = None) -> dict:
    """Hover information for ``line`` of an indexed code file (``resource``).

    Picks the innermost indexed symbol whose span contains ``line``; its
    docstring/signature come from the index, the surrounding lines are read
    from git at the indexed commit and verified against the file's blob SHA
    (empty when the source cannot be resolved). Shape matches
    ``app.modules.graph.schema.HoverInformationResponse``.
    """
    from .source import SourceRequest, resolve_sources

    empty = {"symbol_name": None, "symbol_type": None, "definition_location": None,
             "documentation": None, "related_chunks": [], "context_lines": []}
    chunks = db.execute(
        select(DocumentChunk).where(
            DocumentChunk.resource_id == resource.id,
            DocumentChunk.start_line <= line,
            DocumentChunk.end_line >= line,
        )
    ).scalars().all()
    if not chunks:
        return empty
    # Innermost span wins; a module chunk only when nothing narrower matches.
    target = min(chunks, key=lambda c: (c.ast_node_type == "module", c.end_line - c.start_line))
    meta = target.chunk_metadata or {}
    path = meta.get("path") or resource.identifier

    graph = symbol_graph(db, target.id, limit=10)
    related = [
        {"chunk_id": n["chunk_id"], "content_preview": f"{relation}: {n['symbol']} ({n['path']}:{n['start_line']})",
         "similarity_score": None}
        for relation in ("calls", "called_by")
        for n in graph[relation]
    ]

    context_lines: list[str] = []
    repo = db.get(Repository, target.repository_id) if target.repository_id else None
    if repo is not None and target.branch_reference:
        start = max(1, line - HOVER_CONTEXT_LINES)
        result = resolve_sources([SourceRequest(
            key="hover", source_type=repo.source_type, repository_url=repo.url, local_path=repo.local_path,
            commit=target.branch_reference, path=path, start_line=start, end_line=line + HOVER_CONTEXT_LINES,
            blob_sha=resource.content_sha,
        )], fetch_token)["hover"]
        if result.verified and result.code is not None:
            context_lines = result.code.splitlines()

    return {
        "symbol_name": target.symbol_name,
        "symbol_type": target.ast_node_type,
        "definition_location": {"file_path": path, "line": target.start_line, "column": None},
        "documentation": meta.get("docstring") or meta.get("signature"),
        "related_chunks": related,
        "context_lines": context_lines,
    }
