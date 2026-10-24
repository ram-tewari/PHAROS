"""Language detection: one table shared by every code path."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class LanguageSpec:
    name: str
    # "python-ast" (stdlib), "tree-sitter", or None (line chunks only).
    parser: str | None
    # tree-sitter grammar key (see parsers.treesitter) when parser == "tree-sitter".
    grammar: str | None = None


PYTHON = LanguageSpec("python", "python-ast")

_BY_EXTENSION: dict[str, LanguageSpec] = {
    ".py": PYTHON,
    ".pyi": PYTHON,
    ".js": LanguageSpec("javascript", "tree-sitter", "javascript"),
    ".jsx": LanguageSpec("javascript", "tree-sitter", "javascript"),
    ".mjs": LanguageSpec("javascript", "tree-sitter", "javascript"),
    ".cjs": LanguageSpec("javascript", "tree-sitter", "javascript"),
    ".ts": LanguageSpec("typescript", "tree-sitter", "typescript"),
    ".mts": LanguageSpec("typescript", "tree-sitter", "typescript"),
    ".cts": LanguageSpec("typescript", "tree-sitter", "typescript"),
    ".tsx": LanguageSpec("typescript", "tree-sitter", "tsx"),
    ".go": LanguageSpec("go", "tree-sitter", "go"),
    ".rs": LanguageSpec("rust", "tree-sitter", "rust"),
    ".c": LanguageSpec("c", "tree-sitter", "c"),
    # .h is ambiguous (C or C++); the C grammar parses the common subset.
    ".h": LanguageSpec("c", "tree-sitter", "c"),
    ".cc": LanguageSpec("cpp", "tree-sitter", "cpp"),
    ".cpp": LanguageSpec("cpp", "tree-sitter", "cpp"),
    ".cxx": LanguageSpec("cpp", "tree-sitter", "cpp"),
    ".hh": LanguageSpec("cpp", "tree-sitter", "cpp"),
    ".hpp": LanguageSpec("cpp", "tree-sitter", "cpp"),
    ".hxx": LanguageSpec("cpp", "tree-sitter", "cpp"),
    ".java": LanguageSpec("java", "tree-sitter", "java"),
    # Indexed as line chunks (no grammar wired up). Reported as
    # parser="line-fallback" with reason "unsupported_language".
    ".rb": LanguageSpec("ruby", None),
    ".php": LanguageSpec("php", None),
    ".swift": LanguageSpec("swift", None),
    ".kt": LanguageSpec("kotlin", None),
    ".scala": LanguageSpec("scala", None),
    ".cs": LanguageSpec("csharp", None),
}

#: Languages with AST extraction. Anything else is line-chunked.
AST_LANGUAGES = sorted({s.name for s in _BY_EXTENSION.values() if s.parser})


def detect_language(path: str) -> LanguageSpec | None:
    """Return the language for ``path`` or None if it is not source code we index."""
    return _BY_EXTENSION.get(PurePosixPath(path).suffix.lower())


def indexable_extensions() -> frozenset[str]:
    return frozenset(_BY_EXTENSION)
