"""Tree-sitter symbol extraction for C, C++, Go, Rust, JavaScript, TypeScript and Java.

The extractor walks the syntax tree once, iteratively (minified or deeply
nested code must not hit Python's recursion limit), tracking the innermost
enclosing definition so that calls and identifiers are attributed to the
right symbol and methods are qualified by their class / impl / receiver.

Grammars ship as separate pip packages (``tree-sitter-go`` etc.). A missing
package is reported as ``fallback_reason="grammar_unavailable:<package>"``;
it is never silently treated as a successful parse.
"""

from __future__ import annotations

import importlib
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from .base import (
    MAX_DOCSTRING_CHARS,
    MAX_SIGNATURE_CHARS,
    ParseResult,
    Symbol,
    clip,
)

logger = logging.getLogger(__name__)

# grammar key -> (pip package, module, factory function)
GRAMMAR_PACKAGES: dict[str, tuple[str, str, str]] = {
    "c": ("tree-sitter-c", "tree_sitter_c", "language"),
    "cpp": ("tree-sitter-cpp", "tree_sitter_cpp", "language"),
    "go": ("tree-sitter-go", "tree_sitter_go", "language"),
    "rust": ("tree-sitter-rust", "tree_sitter_rust", "language"),
    "javascript": ("tree-sitter-javascript", "tree_sitter_javascript", "language"),
    "typescript": ("tree-sitter-typescript", "tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree-sitter-typescript", "tree_sitter_typescript", "language_tsx"),
    "java": ("tree-sitter-java", "tree_sitter_java", "language"),
}

_COMMENT_TYPES = {"comment", "line_comment", "block_comment"}
_IDENT_TYPES = {
    "identifier",
    "type_identifier",
    "field_identifier",
    "property_identifier",
    "shorthand_property_identifier",
    "package_identifier",
}
_DOC_WRAPPERS = {
    "export_statement",
    "lexical_declaration",
    "variable_declaration",
    "type_declaration",
    "template_declaration",
}
_FUNCTION_VALUE_TYPES = {"arrow_function", "function_expression", "function", "generator_function"}


# ── Language tables ─────────────────────────────────────────────────────────


@dataclass
class _Def:
    kind: str
    # Extract the symbol name from the definition node (None = not a symbol).
    name: Callable[[object, bytes], str | None]
    container: bool = False  # can hold methods (class / impl / interface / trait)


@dataclass
class _Lang:
    defs: dict[str, _Def]
    # node type -> function returning the callee simple name
    calls: dict[str, Callable[[object, bytes], str | None]]
    # node type -> function returning the import target text
    imports: dict[str, Callable[[object, bytes], str | None]]
    # node types that qualify names but are not emitted (C++ namespaces)
    namespaces: dict[str, Callable[[object, bytes], str | None]] = field(default_factory=dict)


def _text(node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _field_text(name: str):
    def get(node, src):
        child = node.child_by_field_name(name)
        return _text(child, src) if child is not None else None

    return get


def _last_segment(text: str | None) -> str | None:
    if not text:
        return None
    for sep in ("::", ".", "->"):
        text = text.rsplit(sep, 1)[-1]
    return text.strip() or None


def _callee(field_name: str):
    """Callee of a call node: identifier, or the last segment of a member access."""

    def get(node, src):
        fn = node.child_by_field_name(field_name)
        if fn is None:
            return None
        for attr in ("property", "field", "name"):
            inner = fn.child_by_field_name(attr)
            if inner is not None:
                return _text(inner, src)
        return _last_segment(_text(fn, src))

    return get


def _c_declarator_name(node, src):
    """Walk a C/C++ declarator chain down to the function name."""
    decl = node.child_by_field_name("declarator")
    depth = 0
    while decl is not None and depth < 16:
        if decl.type in ("identifier", "field_identifier", "qualified_identifier",
                         "destructor_name", "operator_name"):
            return _last_segment(_text(decl, src))
        decl = decl.child_by_field_name("declarator")
        depth += 1
    return None


def _named_with_body(node, src):
    """struct/enum/class specifiers only count as definitions when they have a body."""
    if node.child_by_field_name("body") is None:
        return None
    return _field_text("name")(node, src)


def _js_variable_function(node, src):
    """``const handler = () => {}`` at module or class level."""
    value = node.child_by_field_name("value")
    if value is None or value.type not in _FUNCTION_VALUE_TYPES:
        return None
    return _field_text("name")(node, src)


def _go_type_spec(node, src):
    return _field_text("name")(node, src)


def _rust_impl_name(node, src):
    type_text = _field_text("type")(node, src)
    if not type_text:
        return None
    trait_text = _field_text("trait")(node, src)
    return f"impl {trait_text} for {type_text}" if trait_text else f"impl {type_text}"


def _rust_impl_type(node, src) -> str | None:
    text = _field_text("type")(node, src)
    return text.split("<", 1)[0].strip() if text else None


def _strip_quotes(text: str | None) -> str | None:
    if text and len(text) >= 2 and text[0] in "\"'`<" and text[-1] in "\"'`>":
        return text[1:-1]
    return text


def _js_require(node, src):
    fn = node.child_by_field_name("function")
    if fn is None or _text(fn, src) != "require":
        return None
    args = node.child_by_field_name("arguments")
    if args is None or args.named_child_count == 0:
        return None
    first = args.named_children[0]
    return _strip_quotes(_text(first, src)) if first.type == "string" else None


def _string_field(name: str):
    def get(node, src):
        return _strip_quotes(_field_text(name)(node, src))

    return get


_JS_DEFS = {
    "function_declaration": _Def("function", _field_text("name")),
    "generator_function_declaration": _Def("function", _field_text("name")),
    "class_declaration": _Def("class", _field_text("name"), container=True),
    "method_definition": _Def("method", _field_text("name")),
    "variable_declarator": _Def("function", _js_variable_function),
}
_JS_CALLS = {
    "call_expression": _callee("function"),
    "new_expression": _callee("constructor"),
}
_JS_IMPORTS = {
    "import_statement": _string_field("source"),
    "call_expression": _js_require,
}

_TS_DEFS = {
    **_JS_DEFS,
    "abstract_class_declaration": _Def("class", _field_text("name"), container=True),
    "interface_declaration": _Def("interface", _field_text("name"), container=True),
    "type_alias_declaration": _Def("type", _field_text("name")),
    "enum_declaration": _Def("enum", _field_text("name")),
    "public_field_definition": _Def("method", _js_variable_function),
}

LANGUAGES: dict[str, _Lang] = {
    "javascript": _Lang(_JS_DEFS, _JS_CALLS, _JS_IMPORTS),
    "typescript": _Lang(_TS_DEFS, _JS_CALLS, _JS_IMPORTS),
    "tsx": _Lang(_TS_DEFS, _JS_CALLS, _JS_IMPORTS),
    "go": _Lang(
        defs={
            "function_declaration": _Def("function", _field_text("name")),
            "method_declaration": _Def("method", _field_text("name")),
            "type_spec": _Def("type", _go_type_spec, container=True),
        },
        calls={"call_expression": _callee("function")},
        imports={"import_spec": _string_field("path")},
    ),
    "rust": _Lang(
        defs={
            "function_item": _Def("function", _field_text("name")),
            "struct_item": _Def("struct", _field_text("name")),
            "enum_item": _Def("enum", _field_text("name")),
            "trait_item": _Def("trait", _field_text("name"), container=True),
            "impl_item": _Def("impl", _rust_impl_name, container=True),
        },
        calls={
            "call_expression": _callee("function"),
            "macro_invocation": _callee("macro"),
        },
        imports={"use_declaration": _field_text("argument")},
    ),
    "c": _Lang(
        defs={
            "function_definition": _Def("function", _c_declarator_name),
            "struct_specifier": _Def("struct", _named_with_body),
            "enum_specifier": _Def("enum", _named_with_body),
        },
        calls={"call_expression": _callee("function")},
        imports={"preproc_include": _string_field("path")},
    ),
    "cpp": _Lang(
        defs={
            "function_definition": _Def("function", _c_declarator_name),
            "class_specifier": _Def("class", _named_with_body, container=True),
            "struct_specifier": _Def("struct", _named_with_body, container=True),
            "enum_specifier": _Def("enum", _named_with_body),
        },
        calls={"call_expression": _callee("function")},
        imports={"preproc_include": _string_field("path")},
        namespaces={"namespace_definition": _field_text("name")},
    ),
    "java": _Lang(
        defs={
            "class_declaration": _Def("class", _field_text("name"), container=True),
            "interface_declaration": _Def("interface", _field_text("name"), container=True),
            "enum_declaration": _Def("enum", _field_text("name"), container=True),
            "record_declaration": _Def("class", _field_text("name"), container=True),
            "method_declaration": _Def("method", _field_text("name")),
            "constructor_declaration": _Def("method", _field_text("name")),
        },
        calls={
            "method_invocation": _field_text("name"),
            "object_creation_expression": lambda n, s: _last_segment(_field_text("type")(n, s)),
        },
        imports={
            "import_declaration": lambda n, s: _text(n, s)
            .removeprefix("import").removesuffix(";").replace("static ", "").strip()
        },
    ),
}


# ── Grammar loading ─────────────────────────────────────────────────────────

_cache_lock = threading.Lock()
_parsers: dict[str, object] = {}
_load_errors: dict[str, str] = {}


def _get_parser(grammar: str):
    """Return a tree-sitter Parser for ``grammar`` or raise ImportError."""
    with _cache_lock:
        if grammar in _parsers:
            return _parsers[grammar]
        if grammar in _load_errors:
            raise ImportError(_load_errors[grammar])
        package, module_name, factory = GRAMMAR_PACKAGES[grammar]
        try:
            from tree_sitter import Language, Parser

            module = importlib.import_module(module_name)
            parser = Parser(Language(getattr(module, factory)()))
        except Exception as exc:  # ImportError, ABI mismatch, ...
            msg = f"grammar_unavailable:{package}"
            _load_errors[grammar] = msg
            logger.warning(
                "tree-sitter grammar %r unavailable (%s: %s); %s files will be "
                "indexed as line chunks. Install with: pip install %s",
                grammar, type(exc).__name__, exc, grammar, package,
            )
            raise ImportError(msg) from exc
        _parsers[grammar] = parser
        return parser


def grammar_status() -> dict[str, str]:
    """``{grammar: "ok" | "grammar_unavailable:<pkg>"}`` for health checks."""
    status = {}
    for grammar in GRAMMAR_PACKAGES:
        try:
            _get_parser(grammar)
            status[grammar] = "ok"
        except ImportError as exc:
            status[grammar] = str(exc)
    return status


# ── Extraction ──────────────────────────────────────────────────────────────


def _clean_comment(text: str) -> str:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        for prefix in ("///", "//!", "//", "/**", "/*!", "/*", "*/", "*"):
            if line.startswith(prefix):
                line = line[len(prefix):]
                break
        line = line.removesuffix("*/").strip()
        if line:
            lines.append(line)
    return " ".join(lines)


def _leading_comment(node, src: bytes) -> str:
    """Contiguous comment block directly above ``node`` (doc comments)."""
    target = node
    # Wrapper nodes (`export function f`, `const f = () => …`, Go
    # `type X struct`, C++ templates): the comment precedes the wrapper.
    parent = node.parent
    while parent is not None and parent.type in _DOC_WRAPPERS and parent.start_point[0] >= target.start_point[0] - 1:
        target = parent
        parent = parent.parent
    comments = []
    expected_end_row = target.start_point[0]
    sibling = target.prev_sibling
    while sibling is not None and sibling.type in _COMMENT_TYPES:
        if sibling.end_point[0] < expected_end_row - 1:
            break  # a blank line separates the comment from the definition
        comments.append(_text(sibling, src))
        expected_end_row = sibling.start_point[0]
        sibling = sibling.prev_sibling
    if not comments:
        return ""
    return clip(_clean_comment("\n".join(reversed(comments))), MAX_DOCSTRING_CHARS)


def _signature(node, src: bytes) -> str:
    """Definition header: text from the node start up to its body."""
    body = node.child_by_field_name("body")
    end = body.start_byte if body is not None else node.end_byte
    header = src[node.start_byte:end].decode("utf-8", errors="replace")
    if body is None:
        header = header.split("\n", 1)[0]
    return clip(header.rstrip().rstrip("{").rstrip(), MAX_SIGNATURE_CHARS)


def _go_receiver_type(node, src: bytes) -> str | None:
    receiver = node.child_by_field_name("receiver")
    if receiver is None:
        return None
    for param in receiver.named_children:
        type_node = param.child_by_field_name("type")
        if type_node is not None:
            return _text(type_node, src).lstrip("*").split("[", 1)[0]
    return None


def parse_treesitter(path: str, source: str, language: str, grammar: str, module_path: str) -> ParseResult:
    """Extract symbols. Raises ImportError when the grammar is unavailable."""
    parser = _get_parser(grammar)
    spec = LANGUAGES[grammar]
    src = source.encode("utf-8", errors="replace")
    tree = parser.parse(src)
    root = tree.root_node

    line_count = max(1, source.count("\n") + (0 if source.endswith("\n") else 1))
    module = Symbol(
        name=path.rsplit("/", 1)[-1],
        qualified_name=module_path,
        kind="module",
        start_line=1,
        end_line=line_count,
        signature=f"file {path}",
        docstring=_file_comment(root, src),
    )
    symbols: list[Symbol] = [module]
    imports: list[str] = []
    by_qualified: dict[str, Symbol] = {module.qualified_name: module}

    # Iterative DFS. Each frame: (node, enclosing symbol, qualifier prefix).
    stack: list[tuple[object, Symbol, str]] = [(root, module, module_path)]
    while stack:
        node, owner, prefix = stack.pop()
        ntype = node.type
        child_owner, child_prefix = owner, prefix

        if ntype in spec.namespaces:
            ns = spec.namespaces[ntype](node, src)
            if ns:
                child_prefix = f"{prefix}.{ns}" if prefix else ns

        definition = spec.defs.get(ntype)
        name = definition.name(node, src) if definition else None
        if (
            definition
            and name
            and definition.kind in ("function", "method")
            and owner.kind in ("function", "method")
        ):
            # Nested functions / closures belong to the enclosing function's
            # chunk (same rule as the Python extractor).
            owner.add_identifier(name)
            name = None
        if definition and name:
            kind = definition.kind
            parent_qual = owner.qualified_name
            qual_prefix = prefix
            if grammar == "go" and ntype == "method_declaration":
                receiver = _go_receiver_type(node, src)
                if receiver:
                    qual_prefix = f"{module_path}.{receiver}" if module_path else receiver
                    parent_qual = qual_prefix
            elif kind == "function" and owner.kind in ("class", "impl", "trait", "interface", "struct", "type"):
                kind = "method"
            if grammar == "go" and ntype == "type_spec":
                type_node = node.child_by_field_name("type")
                kind = {"struct_type": "struct", "interface_type": "interface"}.get(
                    getattr(type_node, "type", ""), "type"
                )
            qualified = f"{qual_prefix}.{name}" if qual_prefix else name
            impl_type = _rust_impl_type(node, src) if ntype == "impl_item" else None
            if impl_type:
                # Methods are qualified by the type, not by "impl X for Y".
                qualified = f"{qual_prefix}.{name}" if qual_prefix else name
            # Overloads / repeated impl blocks: keep names unique.
            if qualified in by_qualified:
                qualified = f"{qualified}@{node.start_point[0] + 1}"
            sym = Symbol(
                name=name,
                qualified_name=qualified,
                kind=kind,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                signature=_signature(node, src),
                docstring=_leading_comment(node, src),
                parent=parent_qual,
            )
            symbols.append(sym)
            by_qualified[qualified] = sym
            child_owner = sym
            if impl_type:
                child_prefix = f"{prefix}.{impl_type}" if prefix else impl_type
            elif definition.container or kind == "class":
                child_prefix = qualified
            else:
                child_prefix = prefix

        if ntype in spec.calls:
            callee = spec.calls[ntype](node, src)
            if callee:
                owner.add_call(callee)
        if ntype in spec.imports:
            target = spec.imports[ntype](node, src)
            if target:
                imports.append(target)
        if ntype in _IDENT_TYPES:
            child_owner.add_identifier(_text(node, src))

        # Push children in reverse so they are visited in source order.
        children = node.named_children
        for child in reversed(children):
            stack.append((child, child_owner, child_prefix))

    # Order symbols by position (DFS already does, but keep it explicit).
    symbols[1:] = sorted(symbols[1:], key=lambda s: (s.start_line, s.end_line))
    return ParseResult(
        language=language,
        parser="tree-sitter",
        symbols=symbols,
        imports=list(dict.fromkeys(imports)),
        partial=bool(root.has_error),
    )


def _file_comment(root, src: bytes) -> str:
    """Leading comment block at the top of a file (package / module docs)."""
    comments = []
    following = None
    for child in root.children:
        if child.type in _COMMENT_TYPES:
            comments.append(child)
            continue
        following = child
        break
    if not comments:
        return ""
    # A comment glued to the next definition documents that definition, not
    # the file — unless it is Go's package doc comment.
    if (
        following is not None
        and following.type != "package_clause"
        and following.start_point[0] <= comments[-1].end_point[0] + 1
    ):
        return ""
    text = "\n".join(_text(c, src) for c in comments)
    return clip(_clean_comment(text), MAX_DOCSTRING_CHARS)
