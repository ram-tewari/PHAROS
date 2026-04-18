"""GitHub integration module — async fetcher with Redis caching."""

from .router import github_router
from .fetcher import GitHubFetcher, FetchRequest, FetchResult, fetch_chunks_for_results
from .code_resolver import resolve_code_for_chunks

__all__ = [
    "github_router",
    "GitHubFetcher",
    "FetchRequest",
    "FetchResult",
    "fetch_chunks_for_results",
    "resolve_code_for_chunks",
]
