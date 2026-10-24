"""Structural graph between the chunks of one repository.

Edges are derived purely from parse output (no code execution):

``contains``  class/impl → method, module → top-level symbol (same file)
``imports``   module chunk → module chunk of an imported file in the repo
``calls``     symbol → symbol it calls, resolved in this order:

  1. ``same_file``      exactly one symbol with that name in the caller's file
  2. ``imported_file``  Python: the name is bound by an import in the file;
                        other languages: exactly one definition in a file the
                        caller's file imports
  3. ``unique_name``    exactly one definition with that name in the repo

Anything else (stdlib calls, overloaded names, dynamic dispatch) is counted as
unresolved and **not** linked: a wrong edge feeds an assistant misleading
context, a missing edge only loses recall.
"""

from __future__ import annotations

import posixpath
from collections import defaultdict
from dataclasses import dataclass, field

# Calls to these names are almost never interesting edges even when they
# happen to resolve (constructors / dunder plumbing).
_IGNORED_CALLS = frozenset({"__init__", "super", "self", "this", "new", "main", "init"})

_JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")


@dataclass
class ChunkNode:
    id: str
    path: str
    language: str
    kind: str
    name: str
    qualified_name: str
    parent: str | None = None
    calls: list[str] = field(default_factory=list)
    # Module chunks only:
    imports: list[str] = field(default_factory=list)
    import_map: dict[str, str] = field(default_factory=dict)


@dataclass
class Edge:
    source_id: str
    target_id: str
    target_name: str
    edge_type: str
    resolution: str


@dataclass
class GraphStats:
    contains: int = 0
    imports: int = 0
    calls_resolved: int = 0
    calls_unresolved: int = 0
    calls_ambiguous: int = 0
    by_resolution: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def as_dict(self) -> dict:
        return {
            "contains": self.contains,
            "imports": self.imports,
            "calls_resolved": self.calls_resolved,
            "calls_unresolved": self.calls_unresolved,
            "calls_ambiguous": self.calls_ambiguous,
            "calls_by_resolution": dict(self.by_resolution),
        }


def _python_module_index(modules: list[ChunkNode]) -> dict[str, list[ChunkNode]]:
    """Map every dotted suffix of a module path to its module chunk(s).

    ``src.pkg.db`` is reachable as ``src.pkg.db``, ``pkg.db`` and ``db`` so
    that src-layout and namespace packages resolve.
    """
    index: dict[str, list[ChunkNode]] = defaultdict(list)
    for mod in modules:
        parts = mod.qualified_name.split(".")
        for i in range(len(parts)):
            index[".".join(parts[i:])].append(mod)
    return index


def _resolve_python_import(target: str, index: dict[str, list[ChunkNode]]) -> ChunkNode | None:
    """Longest dotted prefix of ``target`` that names exactly one module."""
    parts = target.split(".")
    for end in range(len(parts), 0, -1):
        cands = index.get(".".join(parts[:end]))
        if cands:
            return cands[0] if len(cands) == 1 else None
    return None


def _resolve_path_import(src_path: str, spec: str, language: str, files: dict[str, ChunkNode],
                         by_basename: dict[str, list[ChunkNode]]) -> list[ChunkNode]:
    """Resolve JS/TS/C/C++/Go/Rust/Java import specs to module chunks in the repo."""
    src_dir = posixpath.dirname(src_path)
    if language in ("javascript", "typescript"):
        if not spec.startswith("."):
            return []  # package import, not a repo file
        base = posixpath.normpath(posixpath.join(src_dir, spec))
        candidates = [base] + [base + ext for ext in _JS_EXTS] + [f"{base}/index{ext}" for ext in _JS_EXTS]
        for cand in candidates:
            if cand in files:
                return [files[cand]]
        return []
    if language in ("c", "cpp"):
        local = posixpath.normpath(posixpath.join(src_dir, spec))
        if local in files:
            return [files[local]]
        matches = [m for m in by_basename.get(posixpath.basename(spec), []) if m.path.endswith(spec)]
        return matches if len(matches) == 1 else []
    if language == "go":
        # Import paths name directories; match files in a directory whose
        # path is a suffix of the import path.
        hits = [m for m in files.values() if m.language == "go" and spec.endswith(posixpath.dirname(m.path) or "\0")]
        return hits[:10]
    if language == "rust":
        segs = [s for s in spec.replace("{", " ").split("::") if s and s not in ("crate", "self", "super")]
        for end in range(len(segs), 0, -1):
            stem = "/".join(segs[:end])
            for cand in (f"src/{stem}.rs", f"src/{stem}/mod.rs", f"{stem}.rs"):
                if cand in files:
                    return [files[cand]]
        return []
    if language == "java":
        suffix = spec.replace(".", "/") + ".java"
        matches = [m for p, m in files.items() if p.endswith(suffix)]
        return matches if len(matches) == 1 else []
    return []


def build_edges(nodes: list[ChunkNode]) -> tuple[list[Edge], GraphStats]:
    stats = GraphStats()
    edges: list[Edge] = []
    seen: set[tuple[str, str, str]] = set()

    def add(src: ChunkNode, dst: ChunkNode, name: str, etype: str, resolution: str) -> bool:
        if src.id == dst.id:
            return False
        key = (src.id, dst.id, etype)
        if key in seen:
            return False
        seen.add(key)
        edges.append(Edge(src.id, dst.id, name, etype, resolution))
        return True

    by_qualified: dict[str, ChunkNode] = {}
    by_file: dict[str, list[ChunkNode]] = defaultdict(list)
    modules: dict[str, ChunkNode] = {}
    by_name: dict[str, list[ChunkNode]] = defaultdict(list)
    for n in nodes:
        by_qualified.setdefault(n.qualified_name, n)
        by_file[n.path].append(n)
        if n.kind == "module":
            modules[n.path] = n
        elif n.kind != "block":
            by_name[n.name].append(n)
    by_basename: dict[str, list[ChunkNode]] = defaultdict(list)
    for path, mod in modules.items():
        by_basename[posixpath.basename(path)].append(mod)
    py_index = _python_module_index([m for m in modules.values() if m.language == "python"])

    # contains
    for file_nodes in by_file.values():
        local = {n.qualified_name: n for n in file_nodes}
        for n in file_nodes:
            if n.parent and n.parent in local:
                if add(local[n.parent], n, n.name, "contains", "same_file"):
                    stats.contains += 1

    # imports (module -> module)
    imported_files: dict[str, set[str]] = defaultdict(set)
    for path, mod in modules.items():
        targets: list[ChunkNode] = []
        for spec in mod.imports:
            if mod.language == "python":
                hit = _resolve_python_import(spec, py_index)
                targets.extend([hit] if hit else [])
            else:
                targets.extend(_resolve_path_import(path, spec, mod.language, modules, by_basename))
        for t in targets:
            if t.path != path:
                imported_files[path].add(t.path)
                if add(mod, t, t.qualified_name, "imports", "imported_file"):
                    stats.imports += 1

    # calls
    for n in nodes:
        if not n.calls or n.kind == "block":
            continue
        file_nodes = by_file[n.path]
        module = modules.get(n.path)
        import_map = module.import_map if module else {}
        for name in n.calls:
            if name in _IGNORED_CALLS or len(name) < 2:
                continue
            target, resolution = None, None
            same = [c for c in file_nodes if c.name == name and c.kind != "module"]
            if len(same) == 1:
                target, resolution = same[0], "same_file"
            elif len(same) > 1:
                stats.calls_ambiguous += 1
                continue
            if target is None and name in import_map:
                qual = import_map[name]
                hit = by_qualified.get(qual)
                if hit is None:
                    # Imported module path may carry a src/ prefix in the repo.
                    cands = [c for q, c in by_qualified.items() if q.endswith("." + qual)]
                    hit = cands[0] if len(cands) == 1 else None
                if hit is not None and hit.kind != "module":
                    target, resolution = hit, "imported_file"
            # Python has an exact import map (above); this file-level
            # heuristic is for languages without one (JS, Go, C, ...).
            if target is None and n.language != "python" and imported_files.get(n.path):
                cands = [c for c in by_name.get(name, []) if c.path in imported_files[n.path]]
                if len(cands) == 1:
                    target, resolution = cands[0], "imported_file"
            if target is None:
                cands = by_name.get(name, [])
                if len(cands) == 1:
                    target, resolution = cands[0], "unique_name"
                elif len(cands) > 1:
                    stats.calls_ambiguous += 1
                    continue
            if target is None:
                stats.calls_unresolved += 1
                continue
            if add(n, target, name, "calls", resolution):
                stats.calls_resolved += 1
                stats.by_resolution[resolution] += 1
    return edges, stats
