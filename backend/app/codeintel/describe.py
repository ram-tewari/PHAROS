"""Contextual descriptions: an LLM says what each function does, for dense retrieval.

Behaviour that lives only in a body ("run the persistent pre-run hooks") is
invisible to a summary of signature, docstring and calls. On the owner's Mac,
``pharos describe`` asks Codex for a one- or two-sentence description of each
source function (undocumented ones first), caches it per (git blob SHA,
symbol) in ``chunk_descriptions``, and re-embeds the chunk with it. Later
indexing reuses the cache, so a description is only written again when its
file changes. Production never calls an LLM.

Safety: the model sees only code PHAROS read from the checkout, answers only
for ids PHAROS issued, and a description that names an identifier the code
does not contain is dropped (it would teach retrieval something untrue).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database.models import ChunkDescription, DocumentChunk, Resource
from .embeddings import Embedder
from .retrieval import path_role
from .text import with_description

logger = logging.getLogger(__name__)

KINDS = ("function", "method", "macro")
BATCH = 12
MAX_CODE_CHARS = 1500
MAX_DESCRIPTION_CHARS = 400

INSTRUCTIONS = """You describe source code for a code-search index.
For each numbered snippet, write one or two plain sentences (at most 45 words) saying what the code does
and when someone would use it: its purpose and effect, not a line-by-line walkthrough.
Use ordinary words a developer would search with. Mention an identifier only if it appears in the snippet.
Do not speculate beyond the code. Answer for every id you were given and no others."""

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "description": {"type": "string"}},
        "required": ["id", "description"]}}},
    "required": ["items"],
}

_CODEISH = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:[._][A-Za-z0-9_]+)+\b|\b[a-z]+[A-Z][A-Za-z0-9]*\b|\b\w+\(\)")


@dataclass
class DescribeStats:
    candidates: int = 0
    described: int = 0
    rejected: int = 0
    failed_batches: int = 0
    reembedded: int = 0
    examples: list[dict] = field(default_factory=list)


def grounded(description: str, code: str) -> bool:
    """Every code-shaped token in the description (``parse_url``, ``req.body``,
    ``getValue``, ``f()``) appears in the code."""
    lowered = code.lower()
    for token in _CODEISH.findall(description):
        if token.rstrip("()").lower() not in lowered:
            return False
    return True


def _candidates(db: Session, repository_id, only_undocumented: bool, limit: int | None):
    rows = db.execute(
        select(DocumentChunk, Resource.content_sha)
        .join(Resource, Resource.id == DocumentChunk.resource_id)
        .where(DocumentChunk.repository_id == repository_id, DocumentChunk.ast_node_type.in_(KINDS))
        .order_by(DocumentChunk.chunk_metadata["path"].as_string(), DocumentChunk.start_line)
    ).all()
    cached = {
        (sha, sym) for sha, sym in db.execute(
            select(ChunkDescription.content_sha, ChunkDescription.symbol_name)
            .where(ChunkDescription.content_sha.in_({sha for _, sha in rows if sha}))
        )
    }
    out = []
    for chunk, sha in rows:
        meta = chunk.chunk_metadata or {}
        if not sha or (sha, chunk.symbol_name) in cached or path_role(meta.get("path", "")) != "source":
            continue
        if only_undocumented and meta.get("docstring"):
            continue
        out.append((chunk, sha))
    # Undocumented first: they gain most.
    out.sort(key=lambda item: bool((item[0].chunk_metadata or {}).get("docstring")))
    return out[:limit] if limit else out


def describe_repository(db: Session, repository_id, checkout: Path, llm, embedder: Embedder | None, *,
                        only_undocumented: bool = True, limit: int | None = None,
                        progress: Callable[[str], None] = lambda _msg: None) -> DescribeStats:
    """Describe the repository's source functions that have no cached description.

    ``checkout`` must be the indexed commit's working tree (the code is read
    from it, never fetched). ``llm`` has ``complete(instructions, prompt, schema)``
    and an optional ``model`` attribute (see ``app.learning.llm.CodexCLI``).
    """
    stats = DescribeStats()
    todo = _candidates(db, repository_id, only_undocumented, limit)
    stats.candidates = len(todo)
    files: dict[str, list[str]] = {}
    model_name = getattr(llm, "model", None) or "codex"
    for start in range(0, len(todo), BATCH):
        batch = todo[start:start + BATCH]
        issued: dict[str, tuple[DocumentChunk, str, str]] = {}
        for i, (chunk, sha) in enumerate(batch, start=1):
            path = (chunk.chunk_metadata or {}).get("path", "")
            if path not in files:
                try:
                    files[path] = (checkout / path).read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    files[path] = []
            code = "\n".join(files[path][(chunk.start_line or 1) - 1:chunk.end_line or 0])[:MAX_CODE_CHARS]
            if code.strip():
                issued[f"C{start + i}"] = (chunk, sha, code)
        if not issued:
            continue
        prompt = "\n\n".join(f"## {cid} ({chunk.language}, {(chunk.chunk_metadata or {}).get('path')})\n{code}"
                             for cid, (chunk, _sha, code) in issued.items())
        try:
            answer = llm.complete(INSTRUCTIONS, prompt, SCHEMA)
        except Exception as exc:  # LLMUnavailable, a bad answer: skip this batch, keep the rest
            stats.failed_batches += 1
            logger.warning("describe batch failed: %s", exc)
            continue
        written: list[tuple[DocumentChunk, str]] = []
        for item in answer.get("items", []):
            if item.get("id") not in issued:
                continue
            chunk, sha, code = issued.pop(item["id"])
            text = " ".join((item.get("description") or "").split())[:MAX_DESCRIPTION_CHARS]
            if not text or not grounded(text, code):
                stats.rejected += 1
                continue
            db.merge(ChunkDescription(content_sha=sha, symbol_name=chunk.symbol_name, description=text,
                                      model=model_name))
            chunk.semantic_summary = with_description(chunk.semantic_summary or "", text)
            written.append((chunk, text))
            if len(stats.examples) < 5:
                stats.examples.append({"symbol": chunk.symbol_name, "description": text})
        if written and embedder is not None:
            vectors = embedder.embed_documents([c.semantic_summary for c, _ in written])
            for (chunk, _), vector in zip(written, vectors, strict=True):
                chunk.embedding = vector
                chunk.embedding_model = embedder.model_id
            stats.reembedded += len(written)
        stats.described += len(written)
        db.commit()
        progress(f"{min(start + BATCH, len(todo))}/{len(todo)} chunks: {stats.described} described, "
                 f"{stats.rejected} rejected")
    return stats
