"""Chunk-level code retrieval.

Modes
-----
``keyword``  PostgreSQL full-text search over ``search_text`` (identifier-split
             tokens of path, symbol, signature, docstring, referenced names),
             ranked with ``ts_rank_cd``.
``dense``    pgvector cosine distance between the query embedding and chunk
             embeddings **of the same embedding model** (HNSW index).
``hybrid``   Reciprocal Rank Fusion (k=60) of keyword and dense, plus an exact
             symbol-name boost.
``graph``    ``hybrid`` plus the resolved callers / callees of the top hits
             that retrieval missed, ranked just below the hit that pulled
             them in (no score bonus for chunks already retrieved).
``auto``     ``graph`` when dense retrieval is available, otherwise
             ``keyword`` — and the response says so (``mode_used`` and a
             warning). Explicitly requested modes never silently degrade:
             they raise :class:`ModeUnavailable` instead.

SQLite (unit tests) uses a Python BM25 and Python cosine over the same
columns, so behaviour can be tested without PostgreSQL. Retrieval quality and
latency numbers are only ever reported for PostgreSQL.
"""

from __future__ import annotations

import math
import re
import time
import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import Float, and_, bindparam, func, literal_column, or_, select, text
from sqlalchemy.orm import Session

from ..database.models import CodeEdge, DocumentChunk, Repository
from ..shared.vector_type import EmbeddingVector
from .embeddings import Embedder, EmbeddingUnavailable
from .text import query_terms, split_identifier, tsquery_from_terms

MODES = ("auto", "keyword", "dense", "hybrid", "graph")
RRF_K = 60
CANDIDATES = 50
GRAPH_SEEDS = 5
GRAPH_WEIGHTS = {"calls": 0.6, "called_by": 0.5}
TEST_PATH_FACTOR = 0.85
_TEST_PATH_RE = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*$|_test\.[a-z]+$|\.(spec|test)\.[jt]sx?$")

#: Must match the expression index in migration 0002 / models.DocumentChunk.
CHUNK_TSVECTOR_SQL = "to_tsvector('simple', coalesce(document_chunks.search_text, ''))"


class ModeUnavailable(RuntimeError):
    """The requested retrieval mode cannot run (e.g. no embedder / embeddings)."""

    def __init__(self, mode: str, reason: str) -> None:
        super().__init__(f"retrieval mode {mode!r} unavailable: {reason}")
        self.mode = mode
        self.reason = reason


@dataclass
class Filters:
    repository_ids: list[uuid.UUID] | None = None
    languages: list[str] | None = None
    kinds: list[str] | None = None
    path_prefix: str | None = None


@dataclass
class Evidence:
    keyword_rank: int | None = None
    keyword_score: float | None = None
    dense_rank: int | None = None
    dense_similarity: float | None = None
    graph: list[dict] = field(default_factory=list)
    boosts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "keyword_rank": self.keyword_rank,
            "keyword_score": None if self.keyword_score is None else round(self.keyword_score, 4),
            "dense_rank": self.dense_rank,
            "dense_similarity": None if self.dense_similarity is None else round(self.dense_similarity, 4),
            "graph": self.graph,
            "boosts": self.boosts,
        }


@dataclass
class Hit:
    chunk_id: str
    score: float
    evidence: Evidence
    # Populated by _hydrate:
    repository_id: str = ""
    repository_name: str = ""
    repository_url: str = ""
    source_type: str = ""
    path: str = ""
    language: str | None = None
    kind: str | None = None
    symbol: str | None = None
    name: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    commit_sha: str | None = None
    parser: str | None = None
    summary: str | None = None
    raw_url: str | None = None
    resource_id: str | None = None
    fallback_reason: str | None = None


@dataclass
class SearchOutcome:
    query: str
    mode_requested: str
    mode_used: str
    hits: list[Hit]
    warnings: list[str]
    embedding_model: str | None
    timings_ms: dict[str, float]
    candidates: dict[str, int]


def is_test_path(path: str) -> bool:
    return bool(_TEST_PATH_RE.search(path or ""))


_IDENTIFIER_SHAPE_RE = re.compile(r"_|\.|[a-z][A-Z]|\(\)")


def symbol_like_terms(query: str) -> set[str]:
    """Compound names the query spells out as identifiers.

    Only tokens written in code form (``verify_password``, ``TokenSigner.verify``,
    ``parseURL``, ``issue()``) — or the whole query when it is at most two
    words — count. A natural-language query that merely contains a word that
    happens to be a class name ("weight of a parcel" vs ``Parcel``) does not.
    """
    raw = re.findall(r"[A-Za-z_][\w.]*(?:\(\))?", query)
    out: set[str] = set()
    for tok in raw:
        if _IDENTIFIER_SHAPE_RE.search(tok):
            for part in tok.rstrip("()").split("."):
                if compound_name(part):
                    out.add(compound_name(part))
    words = query.split()
    if 0 < len(words) <= 2 and compound_name("_".join(words)):
        out.add(compound_name("_".join(words)))
    return out


def compound_name(identifier: str) -> str:
    """``verify_password`` / ``verifyPassword`` / ``VerifyPassword`` -> ``verifypassword``."""
    return "".join(split_identifier(identifier))


class Retriever:
    def __init__(self, db: Session, embedder: Embedder | None) -> None:
        self.db = db
        self.embedder = embedder
        self.is_pg = db.get_bind().dialect.name == "postgresql"

    # ── public ─────────────────────────────────────────────────────────

    def search(self, query: str, *, mode: str = "auto", k: int = 10,
               filters: Filters | None = None) -> SearchOutcome:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        filters = filters or Filters()
        warnings: list[str] = []
        timings: dict[str, float] = {}
        candidates: dict[str, int] = {}
        terms = query_terms(query)

        effective = mode
        dense_reason = self._dense_unavailable_reason(filters)
        if mode == "auto":
            effective = "graph" if dense_reason is None else "keyword"
            if dense_reason is not None:
                warnings.append(f"dense retrieval unavailable ({dense_reason}); used keyword retrieval only")
        elif mode in ("dense", "hybrid", "graph") and dense_reason is not None:
            raise ModeUnavailable(mode, dense_reason)

        keyword: list[tuple[str, float]] = []
        dense: list[tuple[str, float]] = []
        if effective in ("keyword", "hybrid", "graph"):
            t = time.perf_counter()
            keyword = self._keyword(terms, filters, CANDIDATES if effective != "keyword" else max(k * 3, CANDIDATES))
            timings["keyword"] = (time.perf_counter() - t) * 1000
            candidates["keyword"] = len(keyword)
            if not terms:
                warnings.append("query has no searchable terms for keyword retrieval")
        if effective in ("dense", "hybrid", "graph"):
            t = time.perf_counter()
            try:
                qvec = self.embedder.embed_query(query)  # type: ignore[union-attr]
            except EmbeddingUnavailable as exc:
                if mode == "auto":
                    warnings.append(f"query embedding failed ({exc}); used keyword retrieval only")
                    effective = "keyword"
                    qvec = None
                else:
                    raise ModeUnavailable(mode, str(exc)) from exc
            timings["embed_query"] = (time.perf_counter() - t) * 1000
            if qvec is not None:
                t = time.perf_counter()
                dense = self._dense(qvec, filters, CANDIDATES)
                timings["dense"] = (time.perf_counter() - t) * 1000
                candidates["dense"] = len(dense)

        t = time.perf_counter()
        hits = self._fuse(effective, keyword, dense, terms, query)
        if effective == "graph" and hits:
            hits = self._expand_graph(hits, filters)
        hits = self._finalize(hits, k)
        timings["fuse"] = (time.perf_counter() - t) * 1000

        t = time.perf_counter()
        self._hydrate(hits)
        timings["hydrate"] = (time.perf_counter() - t) * 1000
        timings["total"] = sum(timings.values())
        return SearchOutcome(
            query=query,
            mode_requested=mode,
            mode_used=effective,
            hits=hits,
            warnings=warnings,
            embedding_model=self.embedder.model_id if self.embedder else None,
            timings_ms={k_: round(v, 2) for k_, v in timings.items()},
            candidates=candidates,
        )

    # ── availability ───────────────────────────────────────────────────

    def _dense_unavailable_reason(self, filters: Filters) -> str | None:
        if self.embedder is None:
            return "no embedding backend configured (EMBEDDING_BACKEND=none)"
        stmt = select(DocumentChunk.id).where(
            DocumentChunk.embedding_model == self.embedder.model_id,
            *self._filter_clauses(filters),
        ).limit(1)
        if self.db.execute(stmt).first() is not None:
            return None
        models = self.db.execute(
            select(DocumentChunk.embedding_model)
            .where(DocumentChunk.embedding_model.isnot(None), *self._filter_clauses(filters))
            .distinct()
            .limit(5)
        ).scalars().all()
        if models:
            return (
                f"index was embedded with {sorted(models)}, query embedder is "
                f"{self.embedder.model_id!r}; re-index with the same EMBEDDING_BACKEND"
            )
        return "no chunk embeddings in the index"

    # ── filters ────────────────────────────────────────────────────────

    @staticmethod
    def _filter_clauses(filters: Filters) -> list:
        clauses = [DocumentChunk.repository_id.isnot(None)]
        if filters.repository_ids:
            clauses.append(DocumentChunk.repository_id.in_(filters.repository_ids))
        if filters.languages:
            clauses.append(DocumentChunk.language.in_(filters.languages))
        if filters.kinds:
            clauses.append(DocumentChunk.ast_node_type.in_(filters.kinds))
        if filters.path_prefix:
            prefix = filters.path_prefix.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
            clauses.append(DocumentChunk.chunk_metadata["path"].as_string().like(prefix + "%", escape="\\"))
        return clauses

    # ── keyword ────────────────────────────────────────────────────────

    def _keyword(self, terms: list[str], filters: Filters, limit: int) -> list[tuple[str, float]]:
        if not terms:
            return []
        if not self.is_pg:
            return self._keyword_python(terms, filters, limit)
        tsq_text = tsquery_from_terms(terms)
        if not tsq_text:
            return []
        # Literal SQL so the expression matches the GIN index definition.
        tsv = literal_column(CHUNK_TSVECTOR_SQL)
        tsq = func.to_tsquery(literal_column("'simple'"), bindparam("tsq", tsq_text))
        score = func.ts_rank_cd(tsv, tsq, 1)
        stmt = (
            select(DocumentChunk.id, score.label("score"))
            .where(tsv.op("@@")(tsq), *self._filter_clauses(filters))
            .order_by(score.desc(), DocumentChunk.id)
            .limit(limit)
        )
        return [(str(cid), float(sc)) for cid, sc in self.db.execute(stmt)]

    def _keyword_python(self, terms: list[str], filters: Filters, limit: int) -> list[tuple[str, float]]:
        rows = self.db.execute(
            select(DocumentChunk.id, DocumentChunk.search_text).where(*self._filter_clauses(filters))
        ).all()
        docs = [(str(cid), (txt or "").split()) for cid, txt in rows]
        if not docs:
            return []
        n = len(docs)
        avgdl = sum(len(d) for _, d in docs) / n or 1.0
        df = Counter()
        for _, toks in docs:
            df.update(set(toks))
        scored = []
        for cid, toks in docs:
            tf = Counter(toks)
            s = 0.0
            for term in terms:
                if term not in tf:
                    continue
                idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
                f = tf[term]
                s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(toks) / avgdl))
            if s > 0:
                scored.append((cid, s))
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:limit]

    # ── dense ──────────────────────────────────────────────────────────

    def _dense(self, qvec: list[float], filters: Filters, limit: int) -> list[tuple[str, float]]:
        assert self.embedder is not None
        model = self.embedder.model_id
        if not self.is_pg:
            rows = self.db.execute(
                select(DocumentChunk.id, DocumentChunk.embedding).where(
                    DocumentChunk.embedding_model == model, *self._filter_clauses(filters)
                )
            ).all()
            scored = [(str(cid), _cosine(qvec, emb)) for cid, emb in rows if emb]
            scored.sort(key=lambda x: (-x[1], x[0]))
            return scored[:limit]
        # Higher ef_search keeps recall up when filters discard candidates
        # after the HNSW scan (pgvector post-filters).
        self.db.execute(text("SELECT set_config('hnsw.ef_search', :ef, true)"), {"ef": str(max(100, limit * 4))})
        distance = DocumentChunk.embedding.op("<=>", return_type=Float)(
            bindparam("qvec", qvec, type_=EmbeddingVector())
        )
        stmt = (
            select(DocumentChunk.id, distance.label("distance"))
            .where(
                DocumentChunk.embedding.isnot(None),
                DocumentChunk.embedding_model == model,
                *self._filter_clauses(filters),
            )
            .order_by(distance)
            .limit(limit)
        )
        return [(str(cid), 1.0 - float(dist)) for cid, dist in self.db.execute(stmt)]

    # ── fusion ─────────────────────────────────────────────────────────

    def _fuse(self, mode: str, keyword, dense, terms: list[str], query: str) -> dict[str, Hit]:
        hits: dict[str, Hit] = {}

        def hit(cid: str) -> Hit:
            if cid not in hits:
                hits[cid] = Hit(chunk_id=cid, score=0.0, evidence=Evidence())
            return hits[cid]

        if mode == "keyword":
            for rank, (cid, score) in enumerate(keyword, start=1):
                h = hit(cid)
                h.score = score
                h.evidence.keyword_rank, h.evidence.keyword_score = rank, score
            return hits
        if mode == "dense":
            for rank, (cid, sim) in enumerate(dense, start=1):
                h = hit(cid)
                h.score = sim
                h.evidence.dense_rank, h.evidence.dense_similarity = rank, sim
            return hits

        for rank, (cid, score) in enumerate(keyword, start=1):
            h = hit(cid)
            h.score += 1.0 / (RRF_K + rank)
            h.evidence.keyword_rank, h.evidence.keyword_score = rank, score
        for rank, (cid, sim) in enumerate(dense, start=1):
            h = hit(cid)
            h.score += 1.0 / (RRF_K + rank)
            h.evidence.dense_rank, h.evidence.dense_similarity = rank, sim

        # Exact symbol-name match: the query names the symbol directly
        # (e.g. "verify_password" or "TokenSigner.verify").
        if hits:
            self._symbol_boost(hits, terms, query)
        return hits

    def _symbol_boost(self, hits: dict[str, Hit], terms: list[str], query: str) -> None:
        compounds = symbol_like_terms(query)
        if not compounds:
            return
        rows = self.db.execute(
            select(DocumentChunk.id, DocumentChunk.chunk_metadata).where(
                DocumentChunk.id.in_([uuid.UUID(c) for c in hits])
            )
        ).all()
        for cid, meta in rows:
            name = (meta or {}).get("name") or ""
            if name and compound_name(name) in compounds:
                h = hits[str(cid)]
                h.score += 1.0 / (RRF_K + 1)
                h.evidence.boosts.append("exact_symbol_name")

    def _expand_graph(self, hits: dict[str, Hit], filters: Filters) -> dict[str, Hit]:
        """Add callers / callees of the top hits that retrieval did not find.

        Conservative by design: a neighbour enters with ``seed score x
        weight`` (so it ranks below the hit that pulled it in) and chunks
        already retrieved get no bonus. An earlier additive variant let
        containers (a class containing several hits) outrank the best
        direct match.
        """
        seeds = sorted(hits.values(), key=lambda h: (-h.score, h.chunk_id))[:GRAPH_SEEDS]
        seed_score = {h.chunk_id: h.score for h in seeds}
        seed_ids = [uuid.UUID(h.chunk_id) for h in seeds]
        rows = self.db.execute(
            select(CodeEdge.source_chunk_id, CodeEdge.target_chunk_id, CodeEdge.edge_type).where(
                CodeEdge.edge_type == "calls",
                or_(CodeEdge.source_chunk_id.in_(seed_ids), CodeEdge.target_chunk_id.in_(seed_ids)),
            )
        ).all()
        candidates: dict[str, tuple[float, str, str]] = {}
        for src, dst, _etype in rows:
            src, dst = str(src), str(dst)
            if src in seed_score:
                seed, neighbor, relation = src, dst, "calls"
            else:
                seed, neighbor, relation = dst, src, "called_by"
            if neighbor in hits:
                continue
            score = seed_score[seed] * GRAPH_WEIGHTS[relation]
            if neighbor not in candidates or score > candidates[neighbor][0]:
                candidates[neighbor] = (score, seed, relation)
        if candidates and (filters.languages or filters.kinds or filters.path_prefix or filters.repository_ids):
            allowed = {
                str(c)
                for c in self.db.execute(
                    select(DocumentChunk.id).where(
                        DocumentChunk.id.in_([uuid.UUID(n) for n in candidates]),
                        *self._filter_clauses(filters),
                    )
                ).scalars()
            }
            candidates = {k: v for k, v in candidates.items() if k in allowed}
        for neighbor, (score, seed, relation) in candidates.items():
            h = hits[neighbor] = Hit(chunk_id=neighbor, score=score, evidence=Evidence())
            h.evidence.graph.append({"via": seed, "relation": relation})
        return hits

    def _finalize(self, hits: dict[str, Hit], k: int) -> list[Hit]:
        if not hits:
            return []
        # Mildly down-rank test files (they mirror the code they test and
        # crowd out implementations); applied after fusion so tests still
        # surface when they are the only match.
        paths = dict(
            self.db.execute(
                select(DocumentChunk.id, DocumentChunk.chunk_metadata["path"].as_string()).where(
                    DocumentChunk.id.in_([uuid.UUID(c) for c in hits])
                )
            ).all()
        )
        for cid, h in hits.items():
            if is_test_path(paths.get(uuid.UUID(cid)) or ""):
                h.score *= TEST_PATH_FACTOR
                h.evidence.boosts.append("test_path_penalty")
        ranked = sorted(hits.values(), key=lambda h: (-h.score, h.chunk_id))
        return ranked[:k]

    # ── hydration ──────────────────────────────────────────────────────

    def _hydrate(self, hits: list[Hit]) -> None:
        if not hits:
            return
        ids = [uuid.UUID(h.chunk_id) for h in hits]
        rows = self.db.execute(
            select(DocumentChunk, Repository)
            .join(Repository, Repository.id == DocumentChunk.repository_id)
            .where(DocumentChunk.id.in_(ids))
        ).all()
        by_id = {str(c.id): (c, r) for c, r in rows}
        for h in hits:
            c, r = by_id[h.chunk_id]
            meta = c.chunk_metadata or {}
            h.repository_id = str(r.id)
            h.repository_name = r.name
            h.repository_url = r.url
            h.source_type = r.source_type
            h.path = meta.get("path", "")
            h.language = c.language
            h.kind = c.ast_node_type
            h.symbol = c.symbol_name
            h.name = meta.get("name")
            h.start_line, h.end_line = c.start_line, c.end_line
            h.commit_sha = c.branch_reference
            h.parser = c.parser
            h.summary = c.semantic_summary
            h.raw_url = c.github_uri
            h.resource_id = str(c.resource_id)
            h.fallback_reason = meta.get("fallback_reason")

    # ── graph lookups for context assembly ─────────────────────────────

    def neighbors(self, chunk_ids: Iterable[str], limit: int = 10) -> list[tuple[str, str, str]]:
        """``(seed_id, neighbor_id, relation)`` for one hop around ``chunk_ids``."""
        ids = [uuid.UUID(c) for c in chunk_ids]
        if not ids:
            return []
        rows = self.db.execute(
            select(CodeEdge.source_chunk_id, CodeEdge.target_chunk_id, CodeEdge.edge_type)
            .where(
                and_(
                    CodeEdge.edge_type != "contains",
                    or_(CodeEdge.source_chunk_id.in_(ids), CodeEdge.target_chunk_id.in_(ids)),
                )
            )
            .limit(limit * 4)
        ).all()
        seeds = {str(i) for i in ids}
        out = []
        for s, t, etype in rows:
            s, t = str(s), str(t)
            if s in seeds and t not in seeds:
                out.append((s, t, etype))
            elif t in seeds and s not in seeds:
                out.append((t, s, {"calls": "called_by", "imports": "imported_by"}.get(etype, etype)))
        return out[:limit]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# Re-exported for callers that only need repository lookups.
def repositories_matching(db: Session, ref: str | None) -> list[Repository]:
    """Resolve a repository reference: id, canonical URL, name or URL suffix."""
    if not ref:
        return []
    ref = ref.strip()
    try:
        rid = uuid.UUID(ref)
        repo = db.get(Repository, rid)
        return [repo] if repo else []
    except ValueError:
        pass
    norm = ref.lower().removesuffix(".git").rstrip("/")
    repos = db.execute(select(Repository)).scalars().all()
    exact = [r for r in repos if r.url.lower() == norm or r.name.lower() == norm]
    if exact:
        return exact
    return [r for r in repos if r.url.lower().endswith("/" + norm) or r.name.lower().endswith("/" + norm)]


__all__ = [
    "CHUNK_TSVECTOR_SQL",
    "Filters",
    "Hit",
    "MODES",
    "ModeUnavailable",
    "Retriever",
    "SearchOutcome",
    "repositories_matching",
]
