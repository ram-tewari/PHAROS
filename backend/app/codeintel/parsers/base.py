"""Parser output model shared by all extractors."""

from __future__ import annotations

from dataclasses import dataclass, field

# Per-symbol caps keep summaries and search_text bounded for huge bodies.
MAX_CALLS = 64
MAX_IDENTIFIERS = 96
MAX_DOCSTRING_CHARS = 600
MAX_SIGNATURE_CHARS = 300


@dataclass
class Symbol:
    """A retrievable unit of code: a module, class, function, method, ...

    Line numbers are 1-based and inclusive.
    """

    name: str
    qualified_name: str
    kind: str  # module | class | function | method | interface | struct | enum | trait | impl | type
    start_line: int
    end_line: int
    signature: str
    docstring: str = ""
    # Simple names of called functions / constructed types, in first-seen order.
    calls: list[str] = field(default_factory=list)
    # Identifiers referenced in the body (bounded; feeds keyword search).
    identifiers: list[str] = field(default_factory=list)
    # Qualified name of the enclosing class / impl / module symbol.
    parent: str | None = None

    def add_call(self, name: str) -> None:
        if name and name not in self.calls and len(self.calls) < MAX_CALLS:
            self.calls.append(name)

    def add_identifier(self, name: str) -> None:
        if (
            name
            and len(name) > 1
            and name not in self.identifiers
            and len(self.identifiers) < MAX_IDENTIFIERS
        ):
            self.identifiers.append(name)


@dataclass
class ParseResult:
    language: str
    # "python-ast" | "tree-sitter" | "line-fallback"
    parser: str
    symbols: list[Symbol]
    # Raw import targets: module paths, header names, package import paths.
    imports: list[str] = field(default_factory=list)
    # Local name -> fully qualified imported name (Python only), used to
    # resolve call targets across files.
    import_map: dict[str, str] = field(default_factory=dict)
    # Why AST extraction was not used (None when parser != "line-fallback").
    fallback_reason: str | None = None
    # tree-sitter reported syntax errors but still produced symbols.
    partial: bool = False


def clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
