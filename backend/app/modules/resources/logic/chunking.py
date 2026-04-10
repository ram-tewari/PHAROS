"""Code chunking logic using Tree-Sitter AST parsing."""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid as uuid_module

try:
    from tree_sitter import Language, Parser
    import tree_sitter_python, tree_sitter_javascript, tree_sitter_typescript
    import tree_sitter_rust, tree_sitter_go, tree_sitter_java

    TREE_SITTER_AVAILABLE = True
    LANGUAGE_MODULES = {
        "python": tree_sitter_python,
        "javascript": tree_sitter_javascript,
        "typescript": tree_sitter_typescript,
        "rust": tree_sitter_rust,
        "go": tree_sitter_go,
        "java": tree_sitter_java,
    }
except ImportError:
    TREE_SITTER_AVAILABLE = False
    Language = Parser = None
    LANGUAGE_MODULES = {}

from ....database import models as db_models

logger = logging.getLogger(__name__)
_PARSER_CACHE: Dict[str, Tuple[Optional[Any], Optional[Any]]] = {}

LANGUAGE_EXTENSIONS = {
    "python": [".py", ".pyw", ".pyi"],
    "javascript": [".js", ".jsx", ".mjs"],
    "typescript": [".ts", ".tsx"],
    "rust": [".rs"],
    "go": [".go"],
    "java": [".java"],
}
EXTENSION_TO_LANGUAGE = {
    ext: lang for lang, exts in LANGUAGE_EXTENSIONS.items() for ext in exts
}


@dataclass
class LogicalUnit:
    type: str
    name: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    parent_class: Optional[str] = None
    parent_type: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    is_async: bool = False
    is_exported: bool = False
    visibility: Optional[str] = None
    parameters: List[str] = field(default_factory=list)
    return_type: Optional[str] = None


@dataclass
class ChunkMetadata:
    language: str
    type: str
    start_line: int
    end_line: int
    function_name: Optional[str] = None
    class_name: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    is_async: bool = False
    is_exported: bool = False
    visibility: Optional[str] = None
    parameters: List[str] = field(default_factory=list)
    return_type: Optional[str] = None
    file_path: Optional[str] = None
    parent_class: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "language": self.language,
            "type": self.type,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }
        if self.function_name:
            result["function_name"] = self.function_name
        if self.class_name:
            result["class_name"] = self.class_name
        if self.decorators:
            result["decorators"] = self.decorators
        if self.docstring:
            result["docstring"] = self.docstring
        if self.is_async:
            result["is_async"] = self.is_async
        if self.is_exported:
            result["is_exported"] = self.is_exported
        if self.visibility:
            result["visibility"] = self.visibility
        if self.parameters:
            result["parameters"] = self.parameters
        if self.return_type:
            result["return_type"] = self.return_type
        if self.file_path:
            result["file_path"] = self.file_path
        if self.parent_class:
            result["parent_class"] = self.parent_class
        return result


class CodeChunkingStrategy:
    def __init__(self, language: str, chunk_size: int = 1000, overlap: int = 200):
        self.language = language.lower()
        self.chunk_size = chunk_size
        self.overlap = overlap
        if self.language in _PARSER_CACHE:
            self.parser, self.ts_language = _PARSER_CACHE[self.language]
        else:
            self.parser = self.ts_language = None
            if TREE_SITTER_AVAILABLE and self.language in LANGUAGE_MODULES:
                try:
                    mod = LANGUAGE_MODULES[self.language]
                    self.ts_language = Language(
                        mod.language_typescript()
                        if self.language == "typescript"
                        else mod.language()
                    )
                    self.parser = Parser(self.ts_language)
                    _PARSER_CACHE[self.language] = (self.parser, self.ts_language)
                except Exception as e:
                    logger.warning(f"Failed to create parser for {self.language}: {e}")
                    _PARSER_CACHE[self.language] = (None, None)

    def chunk(
        self,
        content: str,
        resource_id: uuid_module.UUID,
        file_path: Optional[str] = None,
    ) -> List[db_models.DocumentChunk]:
        if self.parser:
            try:
                return self._chunk_with_ast(content, resource_id, file_path)
            except Exception as e:
                logger.warning(f"AST chunking failed: {e}")
        return self._chunk_character_based(content, resource_id, file_path)

    def _parse_ast(self, content: str) -> Optional[Any]:
        if not self.parser:
            return None
        try:
            return self.parser.parse(content.encode("utf-8"))
        except:
            return None

    def _extract_logical_units(self, tree: Any, content: str) -> List[LogicalUnit]:
        if not tree:
            return []
        r = tree.root_node
        if self.language == "python":
            return self._extract_python_units(r, content)
        elif self.language in ["javascript", "jsx"]:
            return self._extract_javascript_units(r, content)
        elif self.language in ["typescript", "tsx"]:
            return self._extract_typescript_units(r, content)
        elif self.language == "rust":
            return self._extract_rust_units(r, content)
        elif self.language == "go":
            return self._extract_go_units(r, content)
        elif self.language == "java":
            return self._extract_java_units(r, content)
        return []

    def _extract_python_units(self, root_node: Any, content: str) -> List[LogicalUnit]:
        units = []

        def traverse(node, parent_class=None):
            if node.type == "function_definition":
                n = node.child_by_field_name("name")
                if n:
                    units.append(
                        LogicalUnit(
                            type="method" if parent_class else "function",
                            name=content[n.start_byte : n.end_byte],
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            parent_class=parent_class,
                        )
                    )
            elif node.type == "class_definition":
                n = node.child_by_field_name("name")
                if n:
                    cn = content[n.start_byte : n.end_byte]
                    units.append(
                        LogicalUnit(
                            type="class",
                            name=cn,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                        )
                    )
                    body = node.child_by_field_name("body")
                    if body:
                        for c in body.children:
                            traverse(c, cn)
                    return
            for c in node.children:
                traverse(c, parent_class)

        traverse(root_node)
        return units

    def _extract_javascript_units(
        self, root_node: Any, content: str
    ) -> List[LogicalUnit]:
        units = []

        def traverse(node, parent_class=None):
            if node.type == "function_declaration":
                n = node.child_by_field_name("name")
                if n:
                    units.append(
                        LogicalUnit(
                            type="function",
                            name=content[n.start_byte : n.end_byte],
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                        )
                    )
            elif node.type == "class_declaration":
                n = node.child_by_field_name("name")
                if n:
                    cn = content[n.start_byte : n.end_byte]
                    units.append(
                        LogicalUnit(
                            type="class",
                            name=cn,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                        )
                    )
                    body = node.child_by_field_name("body")
                    if body:
                        for c in body.children:
                            if c.type == "method_definition":
                                mn = c.child_by_field_name("name")
                                if mn:
                                    units.append(
                                        LogicalUnit(
                                            type="method",
                                            name=content[mn.start_byte : mn.end_byte],
                                            start_line=c.start_point[0] + 1,
                                            end_line=c.end_point[0] + 1,
                                            start_byte=c.start_byte,
                                            end_byte=c.end_byte,
                                            parent_class=cn,
                                        )
                                    )
                    return
            for c in node.children:
                traverse(c, parent_class)

        traverse(root_node)
        return units

    def _extract_typescript_units(
        self, root_node: Any, content: str
    ) -> List[LogicalUnit]:
        units = []

        def traverse(node, parent_class=None):
            if node.type == "function_declaration":
                n = node.child_by_field_name("name")
                if n:
                    units.append(
                        LogicalUnit(
                            type="function",
                            name=content[n.start_byte : n.end_byte],
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                        )
                    )
            elif node.type == "class_declaration":
                n = node.child_by_field_name("name")
                if n:
                    cn = content[n.start_byte : n.end_byte]
                    units.append(
                        LogicalUnit(
                            type="class",
                            name=cn,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                        )
                    )
                    body = node.child_by_field_name("body")
                    if body:
                        for c in body.children:
                            if c.type in [
                                "method_definition",
                                "public_field_definition",
                            ]:
                                mn = c.child_by_field_name("name")
                                if mn:
                                    units.append(
                                        LogicalUnit(
                                            type="method",
                                            name=content[mn.start_byte : mn.end_byte],
                                            start_line=c.start_point[0] + 1,
                                            end_line=c.end_point[0] + 1,
                                            start_byte=c.start_byte,
                                            end_byte=c.end_byte,
                                            parent_class=cn,
                                        )
                                    )
                    return
            elif node.type == "interface_declaration":
                n = node.child_by_field_name("name")
                if n:
                    units.append(
                        LogicalUnit(
                            type="interface",
                            name=content[n.start_byte : n.end_byte],
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                        )
                    )
                    return
            for c in node.children:
                traverse(c, parent_class)

        traverse(root_node)
        return units

    def _extract_rust_units(self, root_node: Any, content: str) -> List[LogicalUnit]:
        units = []

        def traverse(node, parent_name=None, parent_type=None):
            if node.type == "function_item":
                n = node.child_by_field_name("name")
                if n:
                    units.append(
                        LogicalUnit(
                            type="method" if parent_type == "impl" else "function",
                            name=content[n.start_byte : n.end_byte],
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            parent_class=parent_name,
                            parent_type=parent_type,
                        )
                    )
            elif node.type == "struct_item":
                n = node.child_by_field_name("name")
                if n:
                    units.append(
                        LogicalUnit(
                            type="struct",
                            name=content[n.start_byte : n.end_byte],
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                        )
                    )
            elif node.type == "impl_item":
                t = node.child_by_field_name("type")
                impl_name = content[t.start_byte : t.end_byte] if t else "impl"
                units.append(
                    LogicalUnit(
                        type="impl",
                        name=impl_name,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        start_byte=node.start_byte,
                        end_byte=node.end_byte,
                    )
                )
                body = node.child_by_field_name("body")
                if body:
                    for c in body.children:
                        traverse(c, impl_name, "impl")
                return
            elif node.type == "trait_item":
                n = node.child_by_field_name("name")
                if n:
                    tn = content[n.start_byte : n.end_byte]
                    units.append(
                        LogicalUnit(
                            type="trait",
                            name=tn,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                        )
                    )
                    body = node.child_by_field_name("body")
                    if body:
                        for c in body.children:
                            traverse(c, tn, "trait")
                    return
            for c in node.children:
                traverse(c, parent_name, parent_type)

        traverse(root_node)
        return units

    def _extract_go_units(self, root_node: Any, content: str) -> List[LogicalUnit]:
        units = []

        def get_receiver(node):
            r = node.child_by_field_name("receiver")
            if r:
                for c in r.children:
                    if c.type == "parameter_declaration":
                        for pc in c.children:
                            if pc.type in ["type_identifier", "pointer_type"]:
                                return content[pc.start_byte : pc.end_byte].lstrip("*")
            return None

        def traverse(node):
            if node.type == "function_declaration":
                n = node.child_by_field_name("name")
                if n:
                    fn = content[n.start_byte : n.end_byte]
                    recv = get_receiver(node)
                    units.append(
                        LogicalUnit(
                            type="method" if recv else "function",
                            name=fn,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            parent_class=recv,
                            is_exported=fn[0].isupper() if fn else False,
                        )
                    )
            elif node.type == "method_declaration":
                n = None
                for c in node.children:
                    if c.type == "field_identifier":
                        n = c
                        break
                if n:
                    mn = content[n.start_byte : n.end_byte]
                    recv = get_receiver(node)
                    units.append(
                        LogicalUnit(
                            type="method",
                            name=mn,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            parent_class=recv,
                            is_exported=mn[0].isupper() if mn else False,
                        )
                    )
            elif node.type == "type_declaration":
                for c in node.children:
                    if c.type == "type_spec":
                        nn = c.child_by_field_name("name")
                        tn = c.child_by_field_name("type")
                        if nn and tn:
                            name = content[nn.start_byte : nn.end_byte]
                            t = (
                                "struct"
                                if tn.type == "struct_type"
                                else "interface"
                                if tn.type == "interface_type"
                                else None
                            )
                            if t:
                                units.append(
                                    LogicalUnit(
                                        type=t,
                                        name=name,
                                        start_line=node.start_point[0] + 1,
                                        end_line=node.end_point[0] + 1,
                                        start_byte=node.start_byte,
                                        end_byte=node.end_byte,
                                        is_exported=name[0].isupper()
                                        if name
                                        else False,
                                    )
                                )
            for c in node.children:
                traverse(c)

        traverse(root_node)
        return units

    def _extract_java_units(self, root_node: Any, content: str) -> List[LogicalUnit]:
        units = []

        def get_visibility(node):
            for c in node.children:
                if c.type == "modifiers":
                    for m in c.children:
                        t = content[m.start_byte : m.end_byte]
                        if t in ["public", "private", "protected"]:
                            return t
            return None

        def traverse(node, parent_class=None):
            if node.type == "class_declaration":
                n = node.child_by_field_name("name")
                if n:
                    cn = content[n.start_byte : n.end_byte]
                    units.append(
                        LogicalUnit(
                            type="class",
                            name=cn,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            parent_class=parent_class,
                            visibility=get_visibility(node),
                        )
                    )
                    body = node.child_by_field_name("body")
                    if body:
                        for c in body.children:
                            traverse(c, cn)
                    return
            elif node.type == "interface_declaration":
                n = node.child_by_field_name("name")
                if n:
                    in_ = content[n.start_byte : n.end_byte]
                    units.append(
                        LogicalUnit(
                            type="interface",
                            name=in_,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            parent_class=parent_class,
                            visibility=get_visibility(node),
                        )
                    )
                    body = node.child_by_field_name("body")
                    if body:
                        for c in body.children:
                            traverse(c, in_)
                    return
            elif node.type == "method_declaration":
                n = node.child_by_field_name("name")
                if n:
                    units.append(
                        LogicalUnit(
                            type="method",
                            name=content[n.start_byte : n.end_byte],
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            parent_class=parent_class,
                            visibility=get_visibility(node),
                        )
                    )
            elif node.type == "constructor_declaration":
                n = node.child_by_field_name("name")
                if n:
                    units.append(
                        LogicalUnit(
                            type="constructor",
                            name=content[n.start_byte : n.end_byte],
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            parent_class=parent_class,
                            visibility=get_visibility(node),
                        )
                    )
            for c in node.children:
                traverse(c, parent_class)

        traverse(root_node)
        return units

    def _chunk_with_ast(
        self,
        content: str,
        resource_id: uuid_module.UUID,
        file_path: Optional[str] = None,
    ) -> List[db_models.DocumentChunk]:
        if not content or not content.strip():
            return []
        tree = self._parse_ast(content)
        if not tree:
            return self._chunk_character_based(content, resource_id, file_path)
        units = self._extract_logical_units(tree, content)
        if not units:
            return self._chunk_character_based(content, resource_id, file_path)
        chunks = []
        for i, u in enumerate(units):
            meta = ChunkMetadata(
                language=self.language,
                type=u.type,
                start_line=u.start_line,
                end_line=u.end_line,
                file_path=file_path,
            )
            if u.type in ["function", "method", "constructor"]:
                meta.function_name = u.name
                if u.parent_class:
                    meta.class_name = u.parent_class
            elif u.type in ["class", "struct", "interface", "enum", "trait", "impl"]:
                meta.class_name = u.name
            if u.parent_class:
                meta.parent_class = u.parent_class
            if u.visibility:
                meta.visibility = u.visibility
            if u.is_exported:
                meta.is_exported = u.is_exported
            chunks.append(
                db_models.DocumentChunk(
                    id=uuid_module.uuid4(),
                    resource_id=resource_id,
                    content=content[u.start_byte : u.end_byte],
                    chunk_index=i,
                    chunk_metadata=meta.to_dict(),
                    created_at=datetime.now(timezone.utc),
                )
            )
        return chunks

    def _chunk_character_based(
        self,
        content: str,
        resource_id: uuid_module.UUID,
        file_path: Optional[str] = None,
    ) -> List[db_models.DocumentChunk]:
        if not content or not content.strip():
            return []
        chunks, start, idx = [], 0, 0
        while start < len(content):
            end = min(start + self.chunk_size, len(content))
            if end < len(content):
                nl = content.rfind("\n", start + self.chunk_size - self.overlap, end)
                if nl > start:
                    end = nl + 1
            cc = content[start:end]
            if cc.strip():
                meta = {
                    "language": self.language,
                    "type": "character_based",
                    "start_line": content[:start].count("\n") + 1,
                    "end_line": content[:end].count("\n") + 1,
                    "start_char": start,
                    "end_char": end,
                }
                if file_path:
                    meta["file_path"] = file_path
                chunks.append(
                    db_models.DocumentChunk(
                        id=uuid_module.uuid4(),
                        resource_id=resource_id,
                        content=cc,
                        chunk_index=idx,
                        chunk_metadata=meta,
                        created_at=datetime.now(timezone.utc),
                    )
                )
                idx += 1
            start = end - self.overlap if end < len(content) else end
        return chunks


def detect_language(file_path: str) -> Optional[str]:
    from pathlib import Path

    return EXTENSION_TO_LANGUAGE.get(Path(file_path).suffix.lower())


def is_code_file(file_path: str) -> bool:
    return detect_language(file_path) is not None


def get_chunking_strategy(
    file_path: str, chunk_size: int = 1000, overlap: int = 200
) -> Optional[CodeChunkingStrategy]:
    lang = detect_language(file_path)
    return CodeChunkingStrategy(lang, chunk_size, overlap) if lang else None
