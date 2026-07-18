"""Shared seam for chunk code resolution.

Search needs request/response access to the github module's code resolver,
which the event bus can't provide. Instead of importing across the module
boundary, github registers its implementation here at module load and
search calls through this indirection.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# (chunks, **kwargs) -> (code_map, metrics)
CodeResolver = Callable[..., Awaitable[tuple[dict[str, dict], Any]]]

_resolver: CodeResolver | None = None


def register_code_resolver(resolver: CodeResolver) -> None:
    global _resolver
    _resolver = resolver


async def resolve_code_for_chunks(
    chunks: list[Any], **kwargs: Any
) -> tuple[dict[str, dict], Any]:
    """Delegate to the registered resolver; empty result if none registered."""
    if _resolver is None:
        logger.warning(
            "No code resolver registered (github module not loaded); "
            "returning empty code map for %d chunks", len(chunks)
        )
        return {}, None
    return await _resolver(chunks, **kwargs)
