"""Symbol extraction entry point.

:func:`parse_file` always returns a :class:`ParseResult`. When AST
extraction is not possible the result has ``parser="line-fallback"`` and a
machine-readable ``fallback_reason`` — fallbacks are visible in chunk
metadata, ingestion stats and the API, never reported as AST output.
"""

from __future__ import annotations

import re

from ..languages import detect_language
from .base import ParseResult, Symbol
from .python_parser import module_path_for, parse_python
from .treesitter_parser import grammar_status, parse_treesitter

__all__ = ["ParseResult", "Symbol", "grammar_status", "parse_file", "line_chunks"]

FALLBACK_CHUNK_LINES = 60
FALLBACK_OVERLAP_LINES = 10
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,63}")


def _module_path(path: str) -> str:
    if path.endswith((".py", ".pyi")):
        return module_path_for(path)
    stem = path.rsplit(".", 1)[0] if "." in path.rsplit("/", 1)[-1] else path
    return stem.replace("/", ".")


def line_chunks(path: str, source: str, language: str, reason: str) -> ParseResult:
    """Fixed-size overlapping line windows for files without AST support."""
    lines = source.splitlines()
    total = max(1, len(lines))
    symbols: list[Symbol] = []
    step = FALLBACK_CHUNK_LINES - FALLBACK_OVERLAP_LINES
    start = 0
    while True:
        end = min(start + FALLBACK_CHUNK_LINES, total)
        window = lines[start:end]
        first = next((ln.strip() for ln in window if ln.strip()), "")
        sym = Symbol(
            name=f"{path.rsplit('/', 1)[-1]}:{start + 1}-{end}",
            qualified_name=f"{path}:{start + 1}-{end}",
            kind="block",
            start_line=start + 1,
            end_line=end,
            signature=first[:200],
        )
        for ident in _IDENT_RE.findall("\n".join(window)):
            sym.add_identifier(ident)
        symbols.append(sym)
        if end >= total:
            break
        start += step
    return ParseResult(
        language=language,
        parser="line-fallback",
        symbols=symbols,
        fallback_reason=reason,
    )


def parse_file(path: str, source: str) -> ParseResult | None:
    """Parse ``source`` (the content of repository-relative ``path``).

    Returns None for files that are not indexable source code.
    """
    spec = detect_language(path)
    if spec is None:
        return None

    if spec.parser == "python-ast":
        result = parse_python(path, source)
        return result if result is not None else line_chunks(path, source, spec.name, "syntax_error")

    if spec.parser == "tree-sitter":
        try:
            result = parse_treesitter(path, source, spec.name, spec.grammar, _module_path(path))
        except ImportError as exc:
            return line_chunks(path, source, spec.name, str(exc))
        if len(result.symbols) <= 1 and result.partial:
            # Only the module symbol and the tree is broken: line chunks
            # retrieve better than one opaque whole-file chunk.
            return line_chunks(path, source, spec.name, "parse_error")
        return result

    return line_chunks(path, source, spec.name, "unsupported_language")
