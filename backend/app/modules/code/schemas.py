"""Request / response models for the code-intelligence API (``/api/v1``)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["auto", "keyword", "dense", "hybrid", "graph"]


class RepositorySubmit(BaseModel):
    repository: str = Field(
        ...,
        max_length=2048,
        description="https URL, host/owner/repo, or owner/repo (GitHub). Hosts must be in "
        "CODEINTEL_ALLOWED_GIT_HOSTS. Local paths are only accepted by the CLI.",
        examples=["github.com/fatih/color"],
    )
    branch: str | None = Field(None, max_length=200, description="Defaults to the remote's default branch.")
    force: bool = Field(False, description="Re-index even if the commit is already indexed.")


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repo_url: str
    branch: str | None
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    attempts: int
    max_attempts: int
    error_kind: str | None = None
    error: str | None = None
    commit_sha: str | None = None
    repository_id: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    available_at: datetime | None = None
    stats: dict | None = None


class JobSubmitted(BaseModel):
    job: JobOut
    created: bool = Field(..., description="False when an active job for this repository already existed.")
    notified: bool = Field(..., description="Whether a worker wake-up was sent (jobs are durable either way).")


class RepositoryOut(BaseModel):
    id: str
    name: str
    url: str
    source_type: str
    branch: str | None
    index_status: str
    last_commit_sha: str | None
    last_indexed_at: str | None
    total_files: int
    total_lines: int
    chunks: int | None
    embedding_model: str | None
    languages: dict
    graph: dict | None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    repository: str | None = Field(None, description="Repository id, URL or name; all repositories when omitted.")
    mode: Mode = "auto"
    k: int = Field(10, ge=1, le=100)
    languages: list[str] | None = Field(None, max_length=20)
    kinds: list[str] | None = Field(None, max_length=20, description="e.g. function, method, class, module")
    path_prefix: str | None = Field(None, max_length=1024)


class RepositoryRef(BaseModel):
    id: str
    name: str
    url: str


class EvidenceOut(BaseModel):
    keyword_rank: int | None
    keyword_score: float | None
    dense_rank: int | None
    dense_similarity: float | None
    graph: list[dict]
    boosts: list[str]


class ChunkHit(BaseModel):
    rank: int
    chunk_id: str
    score: float
    repository: RepositoryRef
    path: str
    language: str | None
    kind: str | None
    symbol: str | None
    start_line: int | None
    end_line: int | None
    commit_sha: str | None
    parser: str | None = Field(None, description="python-ast | tree-sitter | line-fallback")
    fallback_reason: str | None
    summary: str | None
    evidence: EvidenceOut
    source_url: str | None = None


class SearchResponse(BaseModel):
    query: str
    mode_requested: Mode
    mode_used: Mode
    embedding_model: str | None
    warnings: list[str]
    results: list[ChunkHit]
    timings_ms: dict[str, float]
    candidates: dict[str, int]


class ContextRequestIn(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    repository: str | None = None
    max_chunks: int = Field(8, ge=1, le=50)
    mode: Mode = "auto"
    include_code: bool = True
    include_related: bool = True
    include_rules: bool = True
    profile_id: str | None = Field(
        None, max_length=64, description="Apply this CodingProfile's rules instead of the repository's"
    )
    max_chars: int = Field(24_000, ge=1_000, le=400_000)
    languages: list[str] | None = None
    kinds: list[str] | None = None
    path_prefix: str | None = Field(None, max_length=1024)


class ContextChunk(ChunkHit):
    code: str | None
    code_status: str = Field(..., description="resolved | not_requested | unavailable:<reason>")
    verified: bool = Field(..., description="Code matches the git blob SHA recorded at index time.")
    code_truncated_to_lines: int | None = None


class RelatedChunk(BaseModel):
    chunk_id: str
    relation: str
    via_chunk_id: str
    path: str | None
    symbol: str | None
    kind: str | None
    start_line: int | None
    end_line: int | None
    summary: str | None


class ContextResponse(BaseModel):
    query: str
    mode_requested: Mode
    mode_used: Mode
    embedding_model: str | None
    warnings: list[str]
    repositories: list[dict]
    chunks: list[ContextChunk]
    related: list[RelatedChunk]
    rules: list[dict]
    context_text: str
    stats: dict


class SymbolRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=512, examples=["TokenSigner.verify"])
    repository: str | None = None
    include_code: bool = True
    include_graph: bool = True
    limit: int = Field(5, ge=1, le=50)


class ErrorDetail(BaseModel):
    error: str
    detail: str
