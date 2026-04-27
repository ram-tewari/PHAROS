"""Centralized path exclusions for ingestion pipelines.

Used by repo_parser, repo_ingestion, and ast_pipeline to skip
boilerplate, generated, and vendored paths that would otherwise
poison the temporal sieve.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        # VCS
        ".git", ".hg", ".svn",
        # Package managers / vendored deps
        "node_modules", "bower_components", "vendor",
        # Python envs / caches
        "__pycache__", "venv", ".venv", "env",
        ".pytest_cache", ".hypothesis", ".mypy_cache", ".ruff_cache", ".tox",
        # Build outputs
        "dist", "build", "target", "out", ".next", ".nuxt", ".output",
        # DB schema migrations (Alembic, Django, Rails, etc.)
        "migrations", "alembic",
        # Generated artifacts
        "__generated__", "generated",
        # Coverage
        "coverage", "htmlcov",
        # IDE
        ".idea", ".vscode",
    }
)

EXCLUDE_FILE_SUFFIXES: tuple[str, ...] = (
    ".generated.ts", ".generated.tsx", ".generated.js", ".generated.jsx",
    ".pb.go", ".pb.py", "_pb2.py", "_pb2_grpc.py",
    ".min.js", ".min.css",
    ".lock",
)

EXCLUDE_FILENAMES: frozenset[str] = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Pipfile.lock",
        "Cargo.lock",
        "composer.lock",
        "Gemfile.lock",
    }
)


def has_excluded_ancestor(parts: Iterable[str]) -> bool:
    """True if any path component is an excluded directory name."""
    return any(p in EXCLUDE_DIRS for p in parts)


def is_excluded_file(filename: str) -> bool:
    """True if a filename is a known boilerplate/generated artifact."""
    if filename in EXCLUDE_FILENAMES:
        return True
    return any(filename.endswith(suf) for suf in EXCLUDE_FILE_SUFFIXES)


def is_excluded_path(path: Path) -> bool:
    """True if any ancestor dir is excluded or the filename matches a boilerplate pattern."""
    return has_excluded_ancestor(path.parts) or is_excluded_file(path.name)
