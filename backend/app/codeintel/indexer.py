"""Incremental, idempotent repository indexing.

One call to :meth:`CodeIndexer.index` brings the database in line with a
repository at one commit:

1. Resolve the commit (shallow bare clone, or a local repository).
2. If the repository is already indexed at that commit with the same
   embedding model, stop: re-ingestion is a no-op.
3. Diff tracked files against the index by git blob SHA:
   * **new / changed** files are parsed, embedded and (re)written;
   * **deleted** files are removed with their chunks and edges;
   * **unchanged** files only have their commit pointers moved.
4. Rebuild the repository's call / import / contains graph.
5. Record the commit and statistics on the repository row.

The repository's ``last_commit_sha`` is written only after every step
succeeds. A crash mid-run leaves a mix of old and new files; the retry
diffs again and converges, because files already rewritten now match their
blob SHA. Raw source is never stored (hybrid storage): chunks keep a
pointer (commit, path, line span) and are resolved on demand.
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..database.models import ChunkDescription, CodeEdge, DocumentChunk, Repository, Resource
from ..utils.path_exclusions import has_excluded_ancestor, is_excluded_file
from .embeddings import Embedder, EmbeddingUnavailable
from .git_source import Checkout, RepoRef, TreeEntry, open_checkout
from .graph import ChunkNode, build_edges
from .languages import detect_language
from .parsers import ParseResult, parse_file
from .text import body_excerpt, search_text, semantic_summary

logger = logging.getLogger(__name__)

FILE_BATCH = 50
EMBED_BATCH = 64
MAX_SYMBOLS_PER_FILE = 2000


@dataclass
class LanguageStats:
    files: int = 0
    ast_files: int = 0
    fallback_files: int = 0
    chunks: int = 0
    fallback_reasons: dict[str, int] = field(default_factory=lambda: defaultdict(int))


@dataclass
class IndexStats:
    repository: str = ""
    commit_sha: str = ""
    outcome: str = ""  # "indexed" | "unchanged"
    embedding_model: str | None = None
    files_tracked: int = 0
    files_indexed: int = 0
    files_unchanged: int = 0
    files_deleted: int = 0
    files_failed: int = 0
    skipped: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    chunks_written: int = 0
    chunks_total: int = 0
    embeddings_written: int = 0
    source_bytes_indexed: int = 0
    lines_indexed: int = 0
    languages: dict[str, LanguageStats] = field(default_factory=dict)
    graph: dict = field(default_factory=dict)
    timings_s: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    errors: list[dict[str, str]] = field(default_factory=list)

    def lang(self, name: str) -> LanguageStats:
        return self.languages.setdefault(name, LanguageStats())

    def as_dict(self) -> dict:
        # asdict() rebuilds dicts as type(d)(pairs), which fails for
        # defaultdict on Python < 3.12: convert those fields first.
        plain = replace(
            self,
            skipped=dict(self.skipped),
            timings_s={k: round(v, 3) for k, v in self.timings_s.items()},
            languages={
                name: replace(lang, fallback_reasons=dict(lang.fallback_reasons))
                for name, lang in self.languages.items()
            },
            errors=self.errors[:50],
        )
        return asdict(plain)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _decode(data: bytes) -> str | None:
    """UTF-8 (with BOM handling), falling back to latin-1. None for binary."""
    if b"\0" in data[:8192]:
        return None
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _looks_minified(text: str) -> bool:
    if len(text) < 5000:
        return False
    lines = text.count("\n") + 1
    return len(text) / lines > 300


def _mean_vector(vectors: list[list[float]]) -> list[float] | None:
    if not vectors:
        return None
    dim = len(vectors[0])
    acc = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            acc[i] += x
    norm = math.sqrt(sum(x * x for x in acc))
    return [x / norm for x in acc] if norm else None


@dataclass
class _PreparedChunk:
    chunk: DocumentChunk
    summary: str


class CodeIndexer:
    def __init__(
        self,
        session: Session,
        embedder: Embedder | None,
        *,
        max_file_bytes: int = 1_000_000,
        max_files: int = 20_000,
        clone_timeout: int = 600,
        clone_token: str | None = None,
        heartbeat: Callable[[], None] | None = None,
    ) -> None:
        self.db = session
        self.embedder = embedder
        self.max_file_bytes = max_file_bytes
        self.max_files = max_files
        self.clone_timeout = clone_timeout
        self.clone_token = clone_token
        self.heartbeat = heartbeat or (lambda: None)

    # ── public ─────────────────────────────────────────────────────────

    def get_or_create_repository(self, ref: RepoRef, branch: str | None) -> Repository:
        repo = self.db.execute(
            select(Repository).where(Repository.url == ref.canonical_url)
        ).scalar_one_or_none()
        if repo is None:
            repo = Repository(
                url=ref.canonical_url,
                name=ref.name,
                repo_metadata={},
                source_type=ref.source_type,
                branch=branch,
                local_path=ref.local_path,
                index_status="never_indexed",
            )
            self.db.add(repo)
            self.db.flush()
        else:
            repo.branch = branch
            if ref.local_path:
                repo.local_path = ref.local_path
        return repo

    def index(self, ref: RepoRef, branch: str | None = None, *, force: bool = False) -> IndexStats:
        stats = IndexStats(repository=ref.canonical_url)
        stats.embedding_model = self.embedder.model_id if self.embedder else None
        t0 = time.monotonic()

        repo = self.get_or_create_repository(ref, branch)
        repo_id = repo.id
        previous_commit = repo.last_commit_sha
        previous_model = (repo.stats or {}).get("embedding_model")
        repo.index_status = "indexing"
        self.db.commit()

        try:
            t = time.monotonic()
            checkout = open_checkout(ref, branch=branch, token=self.clone_token, timeout=self.clone_timeout)
            stats.timings_s["checkout"] += time.monotonic() - t
            with checkout:
                stats.commit_sha = checkout.commit
                model_changed = previous_model != stats.embedding_model
                if (
                    not force
                    and previous_commit == checkout.commit
                    and not model_changed
                    and (repo.stats or {}).get("outcome") is not None
                ):
                    stats.outcome = "unchanged"
                    stats.chunks_total = self._count_chunks(repo_id)
                    repo = self.db.get(Repository, repo_id)
                    repo.index_status = "ready"
                    self.db.commit()
                    stats.timings_s["total"] = time.monotonic() - t0
                    return stats
                self._sync(repo_id, ref, checkout, stats, rewrite_all=force or model_changed)
            t = time.monotonic()
            self._rebuild_graph(repo_id, stats)
            stats.timings_s["graph"] += time.monotonic() - t
            stats.outcome = "indexed"
            stats.chunks_total = self._count_chunks(repo_id)
            stats.timings_s["total"] = time.monotonic() - t0

            repo = self.db.get(Repository, repo_id)
            repo.last_commit_sha = stats.commit_sha
            repo.last_indexed_at = _utcnow()
            repo.index_status = "ready"
            repo.total_files = stats.files_indexed + stats.files_unchanged
            repo.total_lines = self._count_lines(repo_id)
            repo.stats = stats.as_dict()
            self.db.commit()
            return stats
        except Exception:
            self.db.rollback()
            repo = self.db.get(Repository, repo_id)
            if repo is not None:
                # Keep last_commit_sha: the previous index stays searchable.
                repo.index_status = "failed"
                self.db.commit()
            raise

    # ── sync ───────────────────────────────────────────────────────────

    def _sync(self, repo_id, ref: RepoRef, checkout: Checkout, stats: IndexStats, *, rewrite_all: bool) -> None:
        existing = {
            path: (rid, sha, cov)
            for rid, path, sha, cov in self.db.execute(
                select(Resource.id, Resource.identifier, Resource.content_sha, Resource.coverage).where(
                    Resource.repository_id == repo_id
                )
            )
        }

        wanted: dict[str, TreeEntry] = {}
        for entry in checkout.list_files():
            stats.files_tracked += 1
            reason = self._skip_reason(entry)
            if reason:
                stats.skipped[reason] += 1
                continue
            if len(wanted) >= self.max_files:
                stats.skipped["max_files_exceeded"] += 1
                continue
            wanted[entry.path] = entry

        deleted = [existing[p][0] for p in existing if p not in wanted]
        changed: list[TreeEntry] = []
        unchanged: list[tuple[str, str]] = []  # (resource_id, old_commit)
        for path, entry in wanted.items():
            prev = existing.get(path)
            if prev is None or rewrite_all or prev[1] != entry.blob_sha:
                changed.append(entry)
            else:
                unchanged.append((prev[0], prev[2]))

        if deleted:
            self._delete_resources(deleted)
            stats.files_deleted = len(deleted)
            self.db.commit()

        self._repoint_unchanged(repo_id, unchanged, checkout.commit)
        stats.files_unchanged = len(unchanged)
        self.db.commit()

        for i in range(0, len(changed), FILE_BATCH):
            self._index_batch(repo_id, ref, checkout, changed[i : i + FILE_BATCH], existing, stats)
            self.db.commit()
            self.heartbeat()

    def _skip_reason(self, entry: TreeEntry) -> str | None:
        parts = entry.path.split("/")
        if detect_language(entry.path) is None:
            return "not_source"
        # Directory rules apply to ancestors only; a file's own name is
        # checked by is_excluded_file.
        if has_excluded_ancestor(parts[:-1]):
            return "excluded_path"
        if is_excluded_file(parts[-1]):
            return "excluded_file"
        if entry.size > self.max_file_bytes:
            return "too_large"
        return None

    def _delete_resources(self, resource_ids: list) -> None:
        for i in range(0, len(resource_ids), 500):
            ids = resource_ids[i : i + 500]
            chunk_ids = select(DocumentChunk.id).where(DocumentChunk.resource_id.in_(ids))
            self.db.execute(delete(CodeEdge).where(CodeEdge.source_chunk_id.in_(chunk_ids)))
            self.db.execute(delete(CodeEdge).where(CodeEdge.target_chunk_id.in_(chunk_ids)))
            self.db.execute(delete(DocumentChunk).where(DocumentChunk.resource_id.in_(ids)))
            self.db.execute(delete(Resource).where(Resource.id.in_(ids)))

    def _repoint_unchanged(self, repo_id, unchanged: list[tuple[str, str]], commit: str) -> None:
        by_old: dict[str, list] = defaultdict(list)
        for rid, old in unchanged:
            if old != commit:
                by_old[old or ""].append(rid)
        now = _utcnow()
        for old, rids in by_old.items():
            for i in range(0, len(rids), 500):
                ids = rids[i : i + 500]
                self.db.execute(
                    update(Resource)
                    .where(Resource.id.in_(ids))
                    .values(coverage=commit, last_indexed_sha=commit, last_indexed_at=now)
                )
                values = {"branch_reference": commit}
                if old:
                    values["github_uri"] = func.replace(DocumentChunk.github_uri, f"/{old}/", f"/{commit}/")
                self.db.execute(
                    update(DocumentChunk).where(DocumentChunk.resource_id.in_(ids)).values(**values)
                )

    def _index_batch(self, repo_id, ref: RepoRef, checkout: Checkout, entries: list[TreeEntry],
                     existing: dict, stats: IndexStats) -> None:
        prepared: list[_PreparedChunk] = []
        per_resource: dict[int, list[_PreparedChunk]] = defaultdict(list)
        resources: list[Resource] = []
        replaced: list = []

        t = time.monotonic()
        for entry in entries:
            try:
                text = _decode(checkout.read_blob(entry.blob_sha))
                if text is None:
                    stats.skipped["binary"] += 1
                    continue
                if _looks_minified(text):
                    stats.skipped["minified"] += 1
                    continue
                parsed = parse_file(entry.path, text)
                if parsed is None:
                    stats.skipped["not_source"] += 1
                    continue
            except Exception as exc:  # one bad file never fails the run
                stats.files_failed += 1
                stats.errors.append({"path": entry.path, "error": f"{type(exc).__name__}: {exc}"[:300]})
                logger.warning("Failed to parse %s: %s", entry.path, exc)
                continue

            if entry.path in existing:
                replaced.append(existing[entry.path][0])
            resource, chunks = self._build_rows(repo_id, ref, checkout.commit, entry, text, parsed, stats)
            resources.append(resource)
            per_resource[id(resource)] = chunks
            prepared.extend(chunks)
        stats.timings_s["parse"] += time.monotonic() - t

        t = time.monotonic()
        if self.embedder is not None and prepared:
            self._embed(prepared, stats)
        stats.timings_s["embed"] += time.monotonic() - t

        t = time.monotonic()
        if replaced:
            self._delete_resources(replaced)
        for resource in resources:
            chunks = per_resource[id(resource)]
            vectors = [p.chunk.embedding for p in chunks if p.chunk.embedding]
            resource.embedding = _mean_vector(vectors)
            self.db.add(resource)
            self.db.flush()
            for p in chunks:
                p.chunk.resource_id = resource.id
            self.db.add_all([p.chunk for p in chunks])
        self.db.flush()
        stats.chunks_written += len(prepared)
        stats.files_indexed += len(resources)
        stats.timings_s["db_write"] += time.monotonic() - t

    def _build_rows(self, repo_id, ref: RepoRef, commit: str, entry: TreeEntry, text: str,
                    parsed: ParseResult, stats: IndexStats) -> tuple[Resource, list[_PreparedChunk]]:
        lang = stats.lang(parsed.language)
        lang.files += 1
        if parsed.parser == "line-fallback":
            lang.fallback_files += 1
            lang.fallback_reasons[parsed.fallback_reason or "unknown"] += 1
        else:
            lang.ast_files += 1
        line_count = text.count("\n") + (0 if text.endswith("\n") else 1)
        stats.source_bytes_indexed += entry.size
        stats.lines_indexed += line_count

        now = _utcnow()
        resource = Resource(
            title=entry.path,
            description=f"{parsed.language} source file",
            source=ref.canonical_url,
            identifier=entry.path,
            coverage=commit,
            type="code_file",
            format=f"text/x-{parsed.language}",
            language=parsed.language[:16],
            subject=[parsed.language],
            relation=[f"repository:{ref.canonical_url}"],
            ingestion_status="completed",
            ingestion_completed_at=now,
            repository_id=repo_id,
            content_sha=entry.blob_sha,
            is_stale=False,
            last_indexed_sha=commit,
            last_indexed_at=now,
        )

        raw_url = ref.raw_url(commit, entry.path)
        module_name = parsed.symbols[0].qualified_name if parsed.symbols else ""
        chunks: list[_PreparedChunk] = []
        source_lines = text.splitlines()
        descriptions = dict(self.db.execute(
            select(ChunkDescription.symbol_name, ChunkDescription.description)
            .where(ChunkDescription.content_sha == entry.blob_sha)
        ).all())
        for idx, sym in enumerate(parsed.symbols[:MAX_SYMBOLS_PER_FILE]):
            summary = semantic_summary(sym, language=parsed.language, path=entry.path, module_name=module_name,
                                       body=body_excerpt(source_lines, sym),
                                       description=descriptions.get(sym.qualified_name[:512], ""))
            meta = {
                "path": entry.path,
                "name": sym.name,
                "parent": sym.parent,
                "calls": sym.calls,
            }
            if sym.signature:
                meta["signature"] = sym.signature[:500]
            if sym.docstring:
                meta["docstring"] = sym.docstring[:2000]
            if parsed.parser == "line-fallback":
                meta["fallback_reason"] = parsed.fallback_reason
            if parsed.partial:
                meta["partial_parse"] = True
            if sym.kind == "module":
                meta["imports"] = parsed.imports[:200]
                if parsed.import_map:
                    meta["import_map"] = dict(list(parsed.import_map.items())[:200])
            chunk = DocumentChunk(
                repository_id=repo_id,
                chunk_index=idx,
                content=None,  # hybrid storage: source stays in git
                is_remote=True,
                github_uri=raw_url,
                branch_reference=commit,
                start_line=sym.start_line,
                end_line=max(sym.start_line, min(sym.end_line, line_count)),
                ast_node_type=sym.kind,
                symbol_name=sym.qualified_name[:512],
                semantic_summary=summary,
                search_text=search_text(sym, path=entry.path, imports=parsed.imports),
                language=parsed.language,
                parser=parsed.parser,
                chunk_metadata=meta,
            )
            chunks.append(_PreparedChunk(chunk, summary))
        if len(parsed.symbols) > MAX_SYMBOLS_PER_FILE:
            stats.skipped["symbols_truncated"] += 1
        lang.chunks += len(chunks)
        return resource, chunks

    def _embed(self, prepared: list[_PreparedChunk], stats: IndexStats) -> None:
        assert self.embedder is not None
        for i in range(0, len(prepared), EMBED_BATCH):
            batch = prepared[i : i + EMBED_BATCH]
            try:
                vectors = self.embedder.embed_documents([p.summary for p in batch])
            except EmbeddingUnavailable:
                raise
            except Exception as exc:
                raise EmbeddingUnavailable(f"embedding failed: {type(exc).__name__}: {exc}") from exc
            if len(vectors) != len(batch):
                raise EmbeddingUnavailable("embedder returned the wrong number of vectors")
            for p, vec in zip(batch, vectors, strict=True):
                p.chunk.embedding = vec
                p.chunk.embedding_model = self.embedder.model_id
            stats.embeddings_written += len(batch)
            self.heartbeat()

    # ── graph ──────────────────────────────────────────────────────────

    def _rebuild_graph(self, repo_id, stats: IndexStats) -> None:
        rows = self.db.execute(
            select(
                DocumentChunk.id,
                DocumentChunk.language,
                DocumentChunk.ast_node_type,
                DocumentChunk.symbol_name,
                DocumentChunk.chunk_metadata,
            ).where(DocumentChunk.repository_id == repo_id)
        ).all()
        nodes = []
        for cid, language, kind, qual, meta in rows:
            meta = meta or {}
            nodes.append(
                ChunkNode(
                    id=str(cid),
                    path=meta.get("path", ""),
                    language=language or "",
                    kind=kind or "",
                    name=meta.get("name") or (qual or "").rsplit(".", 1)[-1],
                    qualified_name=qual or "",
                    parent=meta.get("parent"),
                    calls=meta.get("calls") or [],
                    imports=meta.get("imports") or [],
                    import_map=meta.get("import_map") or {},
                )
            )
        edges, gstats = build_edges(nodes)
        self.db.execute(delete(CodeEdge).where(CodeEdge.repository_id == repo_id))
        import uuid as _uuid

        rows_to_insert = [
            {
                "id": _uuid.uuid4(),
                "repository_id": repo_id,
                "source_chunk_id": _uuid.UUID(e.source_id),
                "target_chunk_id": _uuid.UUID(e.target_id),
                "target_name": e.target_name[:512],
                "edge_type": e.edge_type,
                "resolution": e.resolution,
            }
            for e in edges
        ]
        for i in range(0, len(rows_to_insert), 1000):
            self.db.execute(CodeEdge.__table__.insert(), rows_to_insert[i : i + 1000])
        self.db.commit()
        stats.graph = {"edges": len(edges), **gstats.as_dict()}

    # ── helpers ────────────────────────────────────────────────────────

    def _count_chunks(self, repo_id) -> int:
        return self.db.execute(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.repository_id == repo_id)
        ).scalar_one()

    def _count_lines(self, repo_id) -> int:
        # A file's length is the largest end_line among its chunks.
        per_file = (
            select(func.max(DocumentChunk.end_line).label("n"))
            .where(DocumentChunk.repository_id == repo_id)
            .group_by(DocumentChunk.resource_id)
            .subquery()
        )
        total = self.db.execute(select(func.coalesce(func.sum(per_file.c.n), 0))).scalar_one()
        return int(total or 0)
