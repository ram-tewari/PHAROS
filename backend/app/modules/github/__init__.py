"""GitHub integration module — async fetcher with Redis caching."""

from app.shared.code_resolution import register_code_resolver

from .router import github_router
from .fetcher import GitHubFetcher, FetchRequest, FetchResult, fetch_chunks_for_results
from .code_resolver import resolve_code_for_chunks

# Expose the resolver through the shared kernel so consumers (search)
# don't have to import across the module boundary.
register_code_resolver(resolve_code_for_chunks)

__all__ = [
    "github_router",
    "GitHubFetcher",
    "FetchRequest",
    "FetchResult",
    "fetch_chunks_for_results",
    "resolve_code_for_chunks",
]
