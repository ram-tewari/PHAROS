"""Polyglot Tree-Sitter parser factory + tags.scm-style queries.

Produces SymbolInfo records compatible with PythonASTExtractor's output, so
HybridIngestionPipeline can plug it in without changing DocumentChunk shape.

Dependencies:
    pip install tree-sitter
    pip install tree-sitter-c tree-sitter-cpp tree-sitter-go tree-sitter-rust
    pip install tree-sitter-javascript tree-sitter-typescript
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── SymbolInfo (mirrors ast_pipeline.SymbolInfo so the pipeline accepts it) ──

@dataclass
class SymbolInfo:
    name: str
    qualified_name: str
    node_type: str          # "function" | "class" | "method" | "import" | "block"
    start_line: int
    end_line: int
    signature: str
    docstring: str = ""
    dependencies: list[str] = field(default_factory=list)


# ── Extension → tree-sitter grammar name ──────────────────────────────────────

_EXT_TO_GRAMMAR: dict[str, str] = {
    ".c":   "c",
    ".h":   "c",
    ".cc":  "cpp", ".cpp": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp",
    ".go":  "go",
    ".rs":  "rust",
    ".js":  "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts":  "typescript", ".tsx": "tsx",
}


# ── Tree-Sitter Queries (tags.scm-style) ─────────────────────────────────────
# Capture conventions:
#   @import.path   — file/module/header being imported
#   @def.full      — the full definition node (used for line span)
#   @def.name      — name node of the def (matched to enclosing @def.full)
#   @call.name     — call expression callee
#
# Languages without a "class" keyword (Go, C, Rust) reuse @def for
# struct / interface / trait / impl / enum.

QUERIES: dict[str, str] = {
    # ── C ────────────────────────────────────────────────────────────────
    "c": r"""
        (preproc_include
            path: (_) @import.path)

        (function_definition
            declarator: (function_declarator
                declarator: (identifier) @def.name)) @def.full

        (declaration
            type: (struct_specifier name: (type_identifier) @def.name)) @def.full

        (call_expression
            function: [(identifier) @call.name
                       (field_expression field: (field_identifier) @call.name)])
    """,

    # ── C++ ──────────────────────────────────────────────────────────────
    "cpp": r"""
        (preproc_include
            path: (_) @import.path)

        (function_definition
            declarator: [(function_declarator
                            declarator: [(identifier) @def.name
                                         (qualified_identifier) @def.name
                                         (field_identifier) @def.name])]) @def.full

        (class_specifier
            name: (type_identifier) @def.name) @def.full

        (struct_specifier
            name: (type_identifier) @def.name) @def.full

        (call_expression
            function: [(identifier) @call.name
                       (field_expression field: (field_identifier) @call.name)
                       (qualified_identifier) @call.name])
    """,

    # ── Go ───────────────────────────────────────────────────────────────
    "go": r"""
        (import_spec
            path: (interpreted_string_literal) @import.path)

        (function_declaration
            name: (identifier) @def.name) @def.full

        (method_declaration
            name: (field_identifier) @def.name) @def.full

        (type_declaration
            (type_spec
                name: (type_identifier) @def.name
                type: (struct_type))) @def.full

        (type_declaration
            (type_spec
                name: (type_identifier) @def.name
                type: (interface_type))) @def.full

        (call_expression
            function: [(identifier) @call.name
                       (selector_expression field: (field_identifier) @call.name)])
    """,

    # ── Rust ─────────────────────────────────────────────────────────────
    "rust": r"""
        (use_declaration
            argument: (_) @import.path)

        (function_item
            name: (identifier) @def.name) @def.full

        (struct_item
            name: (type_identifier) @def.name) @def.full

        (enum_item
            name: (type_identifier) @def.name) @def.full

        (trait_item
            name: (type_identifier) @def.name) @def.full

        (impl_item
            type: (type_identifier) @def.name) @def.full

        (call_expression
            function: [(identifier) @call.name
                       (field_expression field: (field_identifier) @call.name)
                       (scoped_identifier) @call.name])

        (macro_invocation
            macro: [(identifier) @call.name
                    (scoped_identifier) @call.name])
    """,

    # ── JavaScript ───────────────────────────────────────────────────────
    "javascript": r"""
        (import_statement
            source: (string) @import.path)

        (call_expression
            function: (identifier) @call.name
            arguments: (arguments (string) @import.path)
            (#eq? @call.name "require"))

        (function_declaration
            name: (identifier) @def.name) @def.full

        (class_declaration
            name: (identifier) @def.name) @def.full

        (method_definition
            name: (property_identifier) @def.name) @def.full

        (variable_declarator
            name: (identifier) @def.name
            value: [(arrow_function) (function_expression)]) @def.full

        (call_expression
            function: [(identifier) @call.name
                       (member_expression property: (property_identifier) @call.name)])
    """,

    # ── TypeScript ───────────────────────────────────────────────────────
    # Used for both "typescript" and "tsx" — same grammar dialects.
    "typescript": r"""
        (import_statement
            source: (string) @import.path)

        (function_declaration
            name: (identifier) @def.name) @def.full

        (class_declaration
            name: (type_identifier) @def.name) @def.full

        (interface_declaration
            name: (type_identifier) @def.name) @def.full

        (type_alias_declaration
            name: (type_identifier) @def.name) @def.full

        (method_definition
            name: (property_identifier) @def.name) @def.full

        (variable_declarator
            name: (identifier) @def.name
            value: [(arrow_function) (function_expression)]) @def.full

        (public_field_definition
            name: (property_identifier) @def.name
            value: [(arrow_function) (function_expression)]) @def.full

        (call_expression
            function: [(identifier) @call.name
                       (member_expression property: (property_identifier) @call.name)])
    """,
}
QUERIES["tsx"] = QUERIES["typescript"]


# ── Per-language node-type → SymbolInfo.node_type mapping ────────────────────

_NODE_TYPE_MAP: dict[str, str] = {
    # Functions
    "function_definition": "function",
    "function_declaration": "function",
    "function_item": "function",
    "method_declaration": "method",
    "method_definition": "method",
    "arrow_function": "function",
    "function_expression": "function",
    "variable_declarator": "function",      # const x = () => ...
    "public_field_definition": "method",
    # Classes / structs / traits / interfaces
    "class_specifier": "class",
    "class_declaration": "class",
    "struct_specifier": "class",
    "struct_item": "class",
    "type_declaration": "class",
    "type_spec": "class",
    "interface_declaration": "class",
    "type_alias_declaration": "class",
    "enum_item": "class",
    "trait_item": "class",
    "impl_item": "class",
    "declaration": "class",                 # C struct decls
}


# ── LanguageParser factory ───────────────────────────────────────────────────

class LanguageParser:
    """Lazy-loading polyglot Tree-Sitter parser.

    Usage:
        parser = LanguageParser.for_path(Path("src/foo.go"))
        if parser is not None:
            symbols = parser.extract(source, module_path="foo")
    """

    _grammar_cache: dict[str, object] = {}
    _parser_cache: dict[str, object] = {}
    _query_cache: dict[str, object] = {}

    def __init__(self, grammar_name: str):
        self.grammar_name = grammar_name
        self._lang = self._load_language(grammar_name)
        self._parser = self._load_parser(grammar_name, self._lang)
        self._query = self._load_query(grammar_name, self._lang)

    # ── Factories ─────────────────────────────────────────────────────────
    @classmethod
    def for_path(cls, path: Path) -> Optional["LanguageParser"]:
        grammar = _EXT_TO_GRAMMAR.get(path.suffix.lower())
        if not grammar:
            return None
        try:
            return cls(grammar)
        except Exception as exc:
            logger.warning("Failed to load %s grammar: %s", grammar, exc)
            return None

    @classmethod
    def supported_extensions(cls) -> set[str]:
        return set(_EXT_TO_GRAMMAR.keys())

    # ── Grammar loaders ───────────────────────────────────────────────────
    @classmethod
    def _load_language(cls, name: str):
        if name in cls._grammar_cache:
            return cls._grammar_cache[name]
        
        # Map grammar names to their tree-sitter package imports
        import_map = {
            "c": ("tree_sitter_c", "language"),
            "cpp": ("tree_sitter_cpp", "language"),
            "go": ("tree_sitter_go", "language"),
            "rust": ("tree_sitter_rust", "language"),
            "javascript": ("tree_sitter_javascript", "language"),
            "typescript": ("tree_sitter_typescript", "language_typescript"),
            "tsx": ("tree_sitter_typescript", "language_tsx"),
        }
        
        mapping = import_map.get(name)
        if not mapping:
            raise ValueError(f"No import mapping for grammar {name!r}")
        
        package_name, func_name = mapping
        
        try:
            # Import the language module dynamically
            import importlib
            from tree_sitter import Language
            
            lang_module = importlib.import_module(package_name)
            # Get the language function - returns PyCapsule
            lang_func = getattr(lang_module, func_name)
            lang_capsule = lang_func()
            # Wrap in Language object for tree-sitter 0.23+
            lang = Language(lang_capsule)
            cls._grammar_cache[name] = lang
            return lang
        except ImportError as exc:
            raise ImportError(
                f"Grammar {name!r} requires package {package_name!r}. "
                f"Install with: pip install {package_name}"
            ) from exc

    @classmethod
    def _load_parser(cls, name: str, lang):
        if name in cls._parser_cache:
            return cls._parser_cache[name]
        from tree_sitter import Parser
        parser = Parser(lang)  # tree-sitter 0.23+ takes language in constructor
        cls._parser_cache[name] = parser
        return parser

    @classmethod
    def _load_query(cls, name: str, lang):
        if name in cls._query_cache:
            return cls._query_cache[name]
        query_src = QUERIES.get(name)
        if query_src is None:
            raise ValueError(f"No tags query defined for grammar {name!r}")
        # tree-sitter < 0.25 exposes Language.query(); 0.25+ removed it in favor
        # of constructing Query(lang, src) directly. Support both.
        if hasattr(lang, "query"):
            q = lang.query(query_src)
        else:
            from tree_sitter import Query
            q = Query(lang, query_src)
        cls._query_cache[name] = q
        return q

    # ── Public API ────────────────────────────────────────────────────────
    def extract(self, source: str, module_path: str) -> list[SymbolInfo]:
        """Parse `source` and return SymbolInfo entries (defs only, plus a
        synthesized `__imports__` pseudo-symbol when imports are present)."""
        try:
            src_bytes = source.encode("utf-8", errors="replace")
            tree = self._parser.parse(src_bytes)
        except Exception as exc:
            logger.warning(
                "Parse failed (%s, %s): %s", self.grammar_name, module_path, exc,
            )
            return []

        try:
            # captures() returns dict[str, list[Node]]. Its home moved between
            # versions: Query.captures() in < 0.25, QueryCursor(query).captures()
            # in 0.25+. Detect which is available at call time.
            if hasattr(self._query, "captures"):
                captures_dict = self._query.captures(tree.root_node)
            else:
                from tree_sitter import QueryCursor
                captures_dict = QueryCursor(self._query).captures(tree.root_node)
        except Exception as exc:
            logger.warning(
                "Query.captures failed (%s, %s): %s",
                self.grammar_name, module_path, exc,
            )
            return []

        full_nodes: list[object] = []
        name_nodes: list[tuple[object, str]] = []
        imports: list[tuple[int, str]] = []
        calls: list[tuple[int, str]] = []

        # Flatten dict to (node, tag) pairs
        for tag, nodes in captures_dict.items():
            for node in nodes:
                text = src_bytes[node.start_byte:node.end_byte].decode(
                    "utf-8", errors="replace"
                )
                if tag == "def.full":
                    full_nodes.append(node)
                elif tag == "def.name":
                    name_nodes.append((node, text))
                elif tag == "import.path":
                    imports.append((node.start_point[0] + 1, _strip_quotes(text)))
                elif tag == "call.name":
                    calls.append((node.start_point[0] + 1, text))

        # Pair each name with its smallest enclosing @def.full.
        defs: list[tuple[object, str, str]] = []
        for name_node, name_text in name_nodes:
            full = _enclosing(name_node, full_nodes) or name_node
            kind = _NODE_TYPE_MAP.get(full.type, "function")
            defs.append((full, name_text, kind))

        symbols: list[SymbolInfo] = []
        for full, name, kind in defs:
            start_line = full.start_point[0] + 1
            end_line = full.end_point[0] + 1
            # Per-symbol calls = calls whose line falls inside this def's
            # line span. Cheap and avoids a second AST walk.
            local_calls = sorted({
                c_name for c_line, c_name in calls
                if start_line <= c_line <= end_line
            })
            signature = _first_line(src_bytes, full).strip().rstrip("{").rstrip()
            qualified = f"{module_path}.{name}" if module_path else name
            symbols.append(SymbolInfo(
                name=name,
                qualified_name=qualified,
                node_type=kind,
                start_line=start_line,
                end_line=end_line,
                signature=signature,
                # Comment-as-docstring extraction varies per language; left
                # empty here. For Python the stdlib ast_pipeline still owns
                # docstring extraction, so this only affects the polyglot path.
                docstring="",
                dependencies=local_calls,
            ))

        # File-level pseudo-symbol so imports survive into chunks.
        if imports:
            import_lines = [p for _, p in imports]
            symbols.insert(0, SymbolInfo(
                name="__imports__",
                qualified_name=f"{module_path}.__imports__" if module_path else "__imports__",
                node_type="import",
                start_line=imports[0][0],
                end_line=imports[-1][0],
                signature="// imports",
                docstring="",
                dependencies=import_lines[:50],
            ))

        return symbols


# ── Normalization → semantic_summary string for embeddings ───────────────────

def build_semantic_summary(sym: SymbolInfo, language: str) -> str:
    """Produce the embedding-friendly text block that matches what
    PythonASTExtractor.build_semantic_summary emits, so DocumentChunk's
    semantic_summary stays shape-consistent across languages.
    """
    parts = [f"[{language}] {sym.signature}"]
    if sym.docstring:
        doc = sym.docstring[:512]
        if len(sym.docstring) > 512:
            doc += "…"
        parts.append(f'    """{doc}"""')
    if sym.dependencies:
        deps = ", ".join(sym.dependencies[:20])
        parts.append(f"    deps: [{deps}]")
    return "\n".join(parts)


# ── helpers ──────────────────────────────────────────────────────────────────

def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] in "\"'" and s[-1] == s[0]:
        return s[1:-1]
    return s


def _first_line(src_bytes: bytes, node) -> str:
    end_byte = src_bytes.find(b"\n", node.start_byte, node.end_byte)
    if end_byte == -1:
        end_byte = node.end_byte
    return src_bytes[node.start_byte:end_byte].decode("utf-8", errors="replace")


def _enclosing(inner, candidates: list):
    """Smallest candidate whose byte range contains `inner`."""
    best = None
    best_size: int | None = None
    for c in candidates:
        if c.start_byte <= inner.start_byte and c.end_byte >= inner.end_byte:
            size = c.end_byte - c.start_byte
            if best_size is None or size < best_size:
                best, best_size = c, size
    return best
