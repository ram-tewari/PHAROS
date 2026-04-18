"""Pydantic schemas for the GitHub on-demand code fetch API."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class GitHubFetchRequest(BaseModel):
    """Request a single code-chunk from a GitHub raw URL."""

    github_uri: str = Field(
        ...,
        description="Full raw.githubusercontent.com URL for the file",
        examples=["https://raw.githubusercontent.com/owner/repo/main/src/main.py"],
    )
    branch_reference: str = Field(
        default="HEAD",
        description="Commit SHA (preferred) or branch name",
    )
    start_line: int = Field(default=1, ge=1, description="First line to return (1-based, inclusive)")
    end_line: int = Field(default=9999, ge=1, description="Last line to return (1-based, inclusive)")

    @field_validator("github_uri")
    @classmethod
    def _validate_uri(cls, v: str) -> str:
        from .fetcher import _validate_github_uri
        _validate_github_uri(v)
        return v


class GitHubFetchResponse(BaseModel):
    """Result of a single code-chunk fetch."""

    code: Optional[str] = Field(None, description="Fetched source code, None on error")
    cache_hit: bool = Field(..., description="True if served from Redis cache")
    latency_ms: float = Field(..., description="End-to-end latency in milliseconds")
    error: Optional[str] = Field(None, description="Error message if fetch failed")


class GitHubBatchFetchRequest(BaseModel):
    """Batch request — up to 50 code chunks in one call."""

    chunks: List[GitHubFetchRequest] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="List of fetch requests (max 50)",
    )


class GitHubBatchFetchResponse(BaseModel):
    """Aggregated batch fetch response."""

    results: List[GitHubFetchResponse] = Field(..., description="Per-chunk results in request order")
    total: int = Field(..., description="Total chunks requested")
    cache_hits: int = Field(..., description="Number of results served from cache")
    errors: int = Field(..., description="Number of failed fetches")
    total_latency_ms: float = Field(..., description="Wall-clock latency for the full batch")


class GitHubHealthResponse(BaseModel):
    """Health check response for the GitHub module."""

    status: str
    cache_available: bool
    github_token_configured: bool
    max_concurrency: int
