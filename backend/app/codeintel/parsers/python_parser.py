"""Python symbol extraction with the standard-library ``ast`` module."""

from __future__ import annotations

import ast

from .base import (
    MAX_DOCSTRING_CHARS,
    MAX_SIGNATURE_CHARS,
    ParseResult,
    Symbol,
    clip,
)


def module_path_for(path: str) -> str:
    """``pkg/sub/mod.py`` -> ``pkg.sub.mod``; ``pkg/__init__.py`` -> ``pkg``.

    A leading ``src/`` (the PyPA "src layout") is not part of the import
    path: ``src/flask/app.py`` is ``flask.app``, which is also what other
    files import, so call/import resolution can match it.
    """
    parts = path.split("/")
    if len(parts) > 2 and parts[0] == "src":
        parts = parts[1:]
    last = parts[-1]
    for suffix in (".pyi", ".py"):
        if last.endswith(suffix):
            last = last[: -len(suffix)]
            break
    parts[-1] = last
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(p for p in parts if p)


def _resolve_relative(module_path: str, is_package: bool, level: int, module: str | None) -> str:
    """Absolute module name for ``from <level dots><module> import …``."""
    base = module_path.split(".") if module_path else []
    # For a module, level 1 means "my package" (drop the module itself);
    # for a package's __init__, level 1 means the package itself.
    drop = level - 1 if is_package else level
    if drop > len(base):
        base = []
    elif drop:
        base = base[: len(base) - drop]
    if module:
        base = base + module.split(".")
    return ".".join(base)


def _signature(node: ast.AST) -> str:
    if isinstance(node, ast.ClassDef):
        bases = [ast.unparse(b) for b in node.bases]
        bases += [f"{k.arg}={ast.unparse(k.value)}" for k in node.keywords if k.arg]
        return f"class {node.name}({', '.join(bases)}):" if bases else f"class {node.name}:"

    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    a = node.args

    def fmt(arg: ast.arg) -> str:
        return f"{arg.arg}: {ast.unparse(arg.annotation)}" if arg.annotation else arg.arg

    params: list[str] = [fmt(x) for x in a.posonlyargs]
    if a.posonlyargs:
        params.append("/")
    params += [fmt(x) for x in a.args]
    if a.vararg:
        params.append("*" + fmt(a.vararg))
    elif a.kwonlyargs:
        params.append("*")
    params += [fmt(x) for x in a.kwonlyargs]
    if a.kwarg:
        params.append("**" + fmt(a.kwarg))
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return clip(f"{prefix} {node.name}({', '.join(params)}){ret}:", MAX_SIGNATURE_CHARS)


def _docstring(node: ast.AST) -> str:
    try:
        doc = ast.get_docstring(node, clean=True) or ""
    except Exception:
        return ""
    return clip(doc, MAX_DOCSTRING_CHARS)


def _start_line(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", None) or []
    lines = [node.lineno] + [d.lineno for d in decorators]
    return min(lines)


class _Extractor(ast.NodeVisitor):
    def __init__(self, module_symbol: Symbol, module_path: str, is_package: bool) -> None:
        self.module_path = module_path
        self.is_package = is_package
        self.symbols: list[Symbol] = [module_symbol]
        self.stack: list[Symbol] = [module_symbol]
        self.imports: list[str] = []
        self.import_map: dict[str, str] = {}

    @property
    def current(self) -> Symbol:
        return self.stack[-1]

    # ── definitions ────────────────────────────────────────────────────
    def _enter(self, node: ast.AST, kind: str) -> None:
        parent = self.current
        name = node.name  # type: ignore[attr-defined]
        sym = Symbol(
            name=name,
            qualified_name=f"{parent.qualified_name}.{name}" if parent.qualified_name else name,
            kind=kind,
            start_line=_start_line(node),
            end_line=getattr(node, "end_lineno", None) or node.lineno,  # type: ignore[attr-defined]
            signature=_signature(node),
            docstring=_docstring(node),
            parent=parent.qualified_name,
        )
        self.symbols.append(sym)
        self.stack.append(sym)
        for deco in getattr(node, "decorator_list", []):
            self.visit(deco)
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                self.visit(base)
        else:
            for arg in ast.walk(node.args):  # type: ignore[attr-defined]
                if isinstance(arg, ast.arg):
                    sym.add_identifier(arg.arg)
        for child in node.body:  # type: ignore[attr-defined]
            self.visit(child)
        self.stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self.current.kind in ("function", "method"):
            # Classes defined inside functions are part of that function.
            self.generic_visit(node)
            return
        self._enter(node, "class")

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if self.current.kind in ("function", "method"):
            # Closures belong to the enclosing function's chunk.
            self.current.add_identifier(node.name)
            self.generic_visit(node)
            return
        self._enter(node, "method" if self.current.kind == "class" else "function")

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func

    # ── references ─────────────────────────────────────────────────────
    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name):
            self.current.add_call(func.id)
        elif isinstance(func, ast.Attribute):
            self.current.add_call(func.attr)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self.current.add_identifier(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.current.add_identifier(node.attr)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name)
            local = alias.asname or alias.name.split(".")[0]
            self.import_map[local] = alias.name if alias.asname else local
            self.current.add_identifier(local)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            base = _resolve_relative(self.module_path, self.is_package, node.level, node.module)
        else:
            base = node.module or ""
        if base:
            self.imports.append(base)
        for alias in node.names:
            if alias.name == "*":
                continue
            target = f"{base}.{alias.name}" if base else alias.name
            # "from pkg import mod" may import a submodule; record it too.
            self.imports.append(target)
            local = alias.asname or alias.name
            self.import_map[local] = target
            self.current.add_identifier(local)


def parse_python(path: str, source: str) -> ParseResult | None:
    """Parse a Python file. Returns None on a syntax error (caller falls back)."""
    try:
        tree = ast.parse(source, filename=path, type_comments=False)
    except (SyntaxError, ValueError):
        return None

    module_path = module_path_for(path)
    line_count = max(1, source.count("\n") + (0 if source.endswith("\n") else 1))
    module = Symbol(
        name=module_path.rsplit(".", 1)[-1] or path,
        qualified_name=module_path,
        kind="module",
        start_line=1,
        end_line=line_count,
        signature=f"module {module_path or path}",
        docstring=_docstring(tree),
    )
    extractor = _Extractor(module, module_path, path.endswith("__init__.py"))
    for stmt in tree.body:
        extractor.visit(stmt)

    # De-duplicate imports, preserving order.
    imports = list(dict.fromkeys(extractor.imports))
    return ParseResult(
        language="python",
        parser="python-ast",
        symbols=extractor.symbols,
        imports=imports,
        import_map=extractor.import_map,
    )
