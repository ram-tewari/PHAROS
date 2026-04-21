"""
Static Analysis Service for Code Intelligence

Extracts code relationships (imports, definitions, calls) from code chunks
using Tree-Sitter AST parsing. This service performs static analysis only
and never executes code.

Related files:
- app/modules/resources/logic/chunking.py: Code chunking with AST metadata
- app/modules/graph/service.py: Graph extraction service integration
- app/database/models.py: GraphRelationship model
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional

try:
    import tree_sitter
    from tree_sitter import Language, Parser

    # Import individual language parsers
    try:
        import tree_sitter_python
    except ImportError:
        tree_sitter_python = None

    try:
        import tree_sitter_javascript
    except ImportError:
        tree_sitter_javascript = None

    try:
        import tree_sitter_typescript
    except ImportError:
        tree_sitter_typescript = None

    try:
        import tree_sitter_rust
    except ImportError:
        tree_sitter_rust = None

    try:
        import tree_sitter_go
    except ImportError:
        tree_sitter_go = None

    try:
        import tree_sitter_java
    except ImportError:
        tree_sitter_java = None

    TREE_SITTER_AVAILABLE = True
except ImportError:
    tree_sitter = None
    TREE_SITTER_AVAILABLE = False

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ImportRelationship:
    """Represents an import relationship extracted from code."""

    def __init__(
        self,
        source_file: str,
        target_symbol: str,
        line_number: int,
        import_type: str = "import",
    ):
        self.source_file = source_file
        self.target_symbol = target_symbol
        self.line_number = line_number
        self.import_type = import_type  # "import", "from_import", "require", etc.


class DefinitionRelationship:
    """Represents a definition relationship extracted from code."""

    def __init__(
        self,
        source_file: str,
        symbol_name: str,
        line_number: int,
        definition_type: str = "function",
    ):
        self.source_file = source_file
        self.symbol_name = symbol_name
        self.line_number = line_number
        self.definition_type = (
            definition_type  # "function", "class", "method", "variable"
        )


class CallRelationship:
    """Represents a function call relationship extracted from code."""

    def __init__(
        self,
        source_file: str,
        caller: str,
        callee: str,
        line_number: int,
        confidence: float = 0.8,
    ):
        self.source_file = source_file
        self.caller = caller
        self.callee = callee
        self.line_number = line_number
        self.confidence = confidence  # Confidence score for ambiguous calls


class StaticAnalysisService:
    """
    Service for static analysis of code chunks.

    Extracts code relationships (imports, definitions, calls) using Tree-Sitter
    AST parsing. Never executes code - all analysis is static.

    Supports multiple programming languages:
    - Python (.py)
    - JavaScript/TypeScript (.js, .ts, .jsx, .tsx)
    - Rust (.rs)
    - Go (.go)
    - Java (.java)
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the static analysis service.

        Args:
            db: Async database session
        """
        self.db = db
        self._parsers = {}  # Cache parsers by language

        if not TREE_SITTER_AVAILABLE:
            logger.warning(
                "tree-sitter not available. Static analysis will be limited."
            )

    @staticmethod
    def _iter_nodes(root_node):
        """
        Iterative pre-order DFS over a Tree-Sitter AST.

        Uses an explicit stack instead of recursion so that deeply nested
        syntax trees (long JSX, chained calls, macro-expanded Rust) cannot
        exceed Python's recursion limit. Traversal order matches the
        previous recursive implementation: parent before children,
        left-to-right siblings.

        See ADR-015 §3.
        """
        if root_node is None:
            return
        stack = [root_node]
        while stack:
            node = stack.pop()
            yield node
            # Push children in reverse so the leftmost child is popped next.
            children = node.children
            for i in range(len(children) - 1, -1, -1):
                stack.append(children[i])

    def _get_parser(self, language: str):
        """
        Get or create a Tree-Sitter parser for the given language.

        Args:
            language: Programming language (python, javascript, typescript, etc.)

        Returns:
            Tree-Sitter parser or None if language not supported
        """
        if not TREE_SITTER_AVAILABLE:
            return None

        # Check cache
        if language in self._parsers:
            return self._parsers[language]

        try:
            # Map language to tree-sitter language module
            language_func = None
            if language == "python" and tree_sitter_python:
                language_func = tree_sitter_python.language
            elif language in ["javascript", "jsx"] and tree_sitter_javascript:
                language_func = tree_sitter_javascript.language
            elif language in ["typescript", "tsx"] and tree_sitter_typescript:
                language_func = tree_sitter_typescript.language_typescript
            elif language == "rust" and tree_sitter_rust:
                language_func = tree_sitter_rust.language
            elif language == "go" and tree_sitter_go:
                language_func = tree_sitter_go.language
            elif language == "java" and tree_sitter_java:
                language_func = tree_sitter_java.language

            if not language_func:
                logger.warning(f"Language module not available for {language}")
                return None

            # Create parser with the new API
            parser = Parser(Language(language_func()))

            self._parsers[language] = parser
            logger.debug(f"Created Tree-Sitter parser for {language}")
            return parser
        except Exception as e:
            logger.warning(f"Failed to create parser for {language}: {e}")
            return None

    async def analyze_code_chunk(self, chunk, resource) -> List[Dict[str, Any]]:
        """
        Extract code relationships from a chunk.

        Analyzes the code chunk using Tree-Sitter to extract:
        - Import statements (IMPORTS relationships)
        - Class/function definitions (DEFINES relationships)
        - Function calls (CALLS relationships)

        Args:
            chunk: DocumentChunk with code content and metadata
            resource: Resource containing the chunk

        Returns:
            List of relationship dictionaries ready for GraphRelationship creation
        """
        relationships = []

        # Get language from chunk metadata
        chunk_metadata = chunk.chunk_metadata or {}
        language = chunk_metadata.get("language")

        if not language:
            logger.warning(f"No language specified for chunk {chunk.id}")
            return relationships

        # Get file path from resource metadata
        resource_metadata = resource.metadata or {}
        file_path = resource_metadata.get("path", resource.title)

        # Parse the code
        parser = self._get_parser(language)
        if not parser:
            logger.warning(f"No parser available for language: {language}")
            return relationships

        try:
            tree = parser.parse(bytes(chunk.content, "utf8"))
            root_node = tree.root_node

            # Extract imports
            imports = self._extract_imports(root_node, file_path, language)
            for imp in imports:
                relationships.append(
                    {
                        "type": "IMPORTS",
                        "source_file": imp.source_file,
                        "target_symbol": imp.target_symbol,
                        "line_number": imp.line_number,
                        "metadata": {
                            "import_type": imp.import_type,
                            "language": language,
                        },
                    }
                )

            # Extract definitions
            definitions = self._extract_definitions(root_node, file_path, language)
            for defn in definitions:
                relationships.append(
                    {
                        "type": "DEFINES",
                        "source_file": defn.source_file,
                        "target_symbol": defn.symbol_name,
                        "line_number": defn.line_number,
                        "metadata": {
                            "definition_type": defn.definition_type,
                            "language": language,
                        },
                    }
                )

            # Extract calls
            calls = self._extract_calls(root_node, file_path, language, chunk_metadata)
            for call in calls:
                relationships.append(
                    {
                        "type": "CALLS",
                        "source_file": call.source_file,
                        "source_symbol": call.caller,
                        "target_symbol": call.callee,
                        "line_number": call.line_number,
                        "metadata": {
                            "confidence": call.confidence,
                            "language": language,
                        },
                    }
                )

            logger.info(
                f"Extracted {len(relationships)} relationships from chunk {chunk.id}: "
                f"{len(imports)} imports, {len(definitions)} definitions, {len(calls)} calls"
            )

        except Exception as e:
            logger.error(f"Error analyzing code chunk {chunk.id}: {e}")

        return relationships

    def _extract_imports(
        self, root_node, file_path: str, language: str
    ) -> List[ImportRelationship]:
        """
        Extract import statements from AST.

        Supports:
        - Python: import x, from x import y
        - JavaScript/TypeScript: import x from 'y', require('x')
        - Go: import "x"
        - Java: import x.y.z
        - Rust: use x::y

        Args:
            root_node: Tree-Sitter root node
            file_path: Source file path
            language: Programming language

        Returns:
            List of ImportRelationship objects
        """
        imports = []

        if language == "python":
            imports.extend(self._extract_python_imports(root_node, file_path))
        elif language in ["javascript", "typescript", "tsx", "jsx"]:
            imports.extend(self._extract_js_imports(root_node, file_path))
        elif language == "go":
            imports.extend(self._extract_go_imports(root_node, file_path))
        elif language == "java":
            imports.extend(self._extract_java_imports(root_node, file_path))
        elif language == "rust":
            imports.extend(self._extract_rust_imports(root_node, file_path))

        return imports

    def _extract_python_imports(
        self, root_node, file_path: str
    ) -> List[ImportRelationship]:
        """Extract Python import statements."""
        imports = []

        for node in self._iter_nodes(root_node):
            if node.type == "import_statement":
                for child in node.children:
                    if child.type == "dotted_name":
                        import_name = child.text.decode("utf8")
                        imports.append(
                            ImportRelationship(
                                source_file=file_path,
                                target_symbol=import_name,
                                line_number=node.start_point[0] + 1,
                                import_type="import",
                            )
                        )

            elif node.type == "import_from_statement":
                module_name = None
                import_names = []

                for child in node.children:
                    if child.type == "dotted_name" and not module_name:
                        module_name = child.text.decode("utf8")
                    elif child.type == "dotted_name" and module_name:
                        import_names.append(child.text.decode("utf8"))
                    elif child.type == "aliased_import":
                        for subchild in child.children:
                            if subchild.type in ["identifier", "dotted_name"]:
                                import_names.append(subchild.text.decode("utf8"))
                                break

                if module_name:
                    for import_name in import_names:
                        full_name = f"{module_name}.{import_name}"
                        imports.append(
                            ImportRelationship(
                                source_file=file_path,
                                target_symbol=full_name,
                                line_number=node.start_point[0] + 1,
                                import_type="from_import",
                            )
                        )

        return imports

    def _extract_js_imports(
        self, root_node, file_path: str
    ) -> List[ImportRelationship]:
        """Extract JavaScript/TypeScript import statements."""
        imports = []

        for node in self._iter_nodes(root_node):
            if node.type == "import_statement":
                for child in node.children:
                    if child.type == "string":
                        module_path = child.text.decode("utf8").strip("\"'")
                        imports.append(
                            ImportRelationship(
                                source_file=file_path,
                                target_symbol=module_path,
                                line_number=node.start_point[0] + 1,
                                import_type="import",
                            )
                        )
                        break

        return imports

    def _extract_go_imports(
        self, root_node, file_path: str
    ) -> List[ImportRelationship]:
        """Extract Go import statements."""
        imports = []

        for node in self._iter_nodes(root_node):
            if node.type == "import_declaration":
                for child in node.children:
                    if child.type == "import_spec":
                        for spec_child in child.children:
                            if spec_child.type == "interpreted_string_literal":
                                package_path = spec_child.text.decode("utf8").strip('"')
                                imports.append(
                                    ImportRelationship(
                                        source_file=file_path,
                                        target_symbol=package_path,
                                        line_number=node.start_point[0] + 1,
                                        import_type="import",
                                    )
                                )

        return imports

    def _extract_java_imports(
        self, root_node, file_path: str
    ) -> List[ImportRelationship]:
        """Extract Java import statements."""
        imports = []

        for node in self._iter_nodes(root_node):
            if node.type == "import_declaration":
                for child in node.children:
                    if child.type == "scoped_identifier":
                        import_name = child.text.decode("utf8")
                        imports.append(
                            ImportRelationship(
                                source_file=file_path,
                                target_symbol=import_name,
                                line_number=node.start_point[0] + 1,
                                import_type="import",
                            )
                        )

        return imports

    def _extract_rust_imports(
        self, root_node, file_path: str
    ) -> List[ImportRelationship]:
        """Extract Rust use statements."""
        imports = []

        for node in self._iter_nodes(root_node):
            if node.type == "use_declaration":
                for child in node.children:
                    if child.type in [
                        "scoped_identifier",
                        "identifier",
                        "use_wildcard",
                    ]:
                        use_path = child.text.decode("utf8")
                        imports.append(
                            ImportRelationship(
                                source_file=file_path,
                                target_symbol=use_path,
                                line_number=node.start_point[0] + 1,
                                import_type="use",
                            )
                        )

        return imports

    def _extract_definitions(
        self, root_node, file_path: str, language: str
    ) -> List[DefinitionRelationship]:
        """
        Extract class and function definitions from AST.

        Args:
            root_node: Tree-Sitter root node
            file_path: Source file path
            language: Programming language

        Returns:
            List of DefinitionRelationship objects
        """
        definitions = []

        if language == "python":
            definitions.extend(self._extract_python_definitions(root_node, file_path))
        elif language in ["javascript", "typescript", "tsx", "jsx"]:
            definitions.extend(self._extract_js_definitions(root_node, file_path))
        elif language == "go":
            definitions.extend(self._extract_go_definitions(root_node, file_path))
        elif language == "java":
            definitions.extend(self._extract_java_definitions(root_node, file_path))
        elif language == "rust":
            definitions.extend(self._extract_rust_definitions(root_node, file_path))

        return definitions

    def _extract_python_definitions(
        self, root_node, file_path: str
    ) -> List[DefinitionRelationship]:
        """Extract Python function and class definitions."""
        definitions = []

        for node in self._iter_nodes(root_node):
            if node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = name_node.text.decode("utf8")
                    definitions.append(
                        DefinitionRelationship(
                            source_file=file_path,
                            symbol_name=func_name,
                            line_number=node.start_point[0] + 1,
                            definition_type="function",
                        )
                    )

            elif node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    class_name = name_node.text.decode("utf8")
                    definitions.append(
                        DefinitionRelationship(
                            source_file=file_path,
                            symbol_name=class_name,
                            line_number=node.start_point[0] + 1,
                            definition_type="class",
                        )
                    )

        return definitions

    def _extract_js_definitions(
        self, root_node, file_path: str
    ) -> List[DefinitionRelationship]:
        """Extract JavaScript/TypeScript function and class definitions."""
        definitions = []

        for node in self._iter_nodes(root_node):
            if node.type in ["function_declaration", "function"]:
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = name_node.text.decode("utf8")
                    definitions.append(
                        DefinitionRelationship(
                            source_file=file_path,
                            symbol_name=func_name,
                            line_number=node.start_point[0] + 1,
                            definition_type="function",
                        )
                    )

            elif node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    class_name = name_node.text.decode("utf8")
                    definitions.append(
                        DefinitionRelationship(
                            source_file=file_path,
                            symbol_name=class_name,
                            line_number=node.start_point[0] + 1,
                            definition_type="class",
                        )
                    )

        return definitions

    def _extract_go_definitions(
        self, root_node, file_path: str
    ) -> List[DefinitionRelationship]:
        """Extract Go function and type definitions."""
        definitions = []

        for node in self._iter_nodes(root_node):
            if node.type == "function_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = name_node.text.decode("utf8")
                    definitions.append(
                        DefinitionRelationship(
                            source_file=file_path,
                            symbol_name=func_name,
                            line_number=node.start_point[0] + 1,
                            definition_type="function",
                        )
                    )

            elif node.type == "type_declaration":
                for child in node.children:
                    if child.type == "type_spec":
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            type_name = name_node.text.decode("utf8")
                            definitions.append(
                                DefinitionRelationship(
                                    source_file=file_path,
                                    symbol_name=type_name,
                                    line_number=node.start_point[0] + 1,
                                    definition_type="type",
                                )
                            )

        return definitions

    def _extract_java_definitions(
        self, root_node, file_path: str
    ) -> List[DefinitionRelationship]:
        """Extract Java class and method definitions."""
        definitions = []

        for node in self._iter_nodes(root_node):
            if node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    class_name = name_node.text.decode("utf8")
                    definitions.append(
                        DefinitionRelationship(
                            source_file=file_path,
                            symbol_name=class_name,
                            line_number=node.start_point[0] + 1,
                            definition_type="class",
                        )
                    )

            elif node.type == "method_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    method_name = name_node.text.decode("utf8")
                    definitions.append(
                        DefinitionRelationship(
                            source_file=file_path,
                            symbol_name=method_name,
                            line_number=node.start_point[0] + 1,
                            definition_type="method",
                        )
                    )

        return definitions

    def _extract_rust_definitions(
        self, root_node, file_path: str
    ) -> List[DefinitionRelationship]:
        """Extract Rust function and struct definitions."""
        definitions = []

        for node in self._iter_nodes(root_node):
            if node.type == "function_item":
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = name_node.text.decode("utf8")
                    definitions.append(
                        DefinitionRelationship(
                            source_file=file_path,
                            symbol_name=func_name,
                            line_number=node.start_point[0] + 1,
                            definition_type="function",
                        )
                    )

            elif node.type in ["struct_item", "enum_item"]:
                name_node = node.child_by_field_name("name")
                if name_node:
                    type_name = name_node.text.decode("utf8")
                    definitions.append(
                        DefinitionRelationship(
                            source_file=file_path,
                            symbol_name=type_name,
                            line_number=node.start_point[0] + 1,
                            definition_type=node.type.replace("_item", ""),
                        )
                    )

        return definitions

    def _extract_calls(
        self, root_node, file_path: str, language: str, chunk_metadata: Dict[str, Any]
    ) -> List[CallRelationship]:
        """
        Extract function call patterns from AST.

        This is best-effort extraction - call resolution is ambiguous without
        full type information and cross-file analysis.

        Args:
            root_node: Tree-Sitter root node
            file_path: Source file path
            language: Programming language
            chunk_metadata: Chunk metadata with function/class context

        Returns:
            List of CallRelationship objects
        """
        calls = []

        # Get caller context from chunk metadata
        caller = chunk_metadata.get("function_name", "unknown")
        if chunk_metadata.get("class_name"):
            caller = f"{chunk_metadata['class_name']}.{caller}"

        if language == "python":
            calls.extend(self._extract_python_calls(root_node, file_path, caller))
        elif language in ["javascript", "typescript", "tsx", "jsx"]:
            calls.extend(self._extract_js_calls(root_node, file_path, caller))
        elif language == "go":
            calls.extend(self._extract_go_calls(root_node, file_path, caller))
        elif language == "java":
            calls.extend(self._extract_java_calls(root_node, file_path, caller))
        elif language == "rust":
            calls.extend(self._extract_rust_calls(root_node, file_path, caller))

        return calls

    def _extract_python_calls(
        self, root_node, file_path: str, caller: str
    ) -> List[CallRelationship]:
        """Extract Python function calls."""
        calls = []

        for node in self._iter_nodes(root_node):
            if node.type == "call":
                function_node = node.child_by_field_name("function")
                if function_node:
                    callee = function_node.text.decode("utf8")

                    confidence = 0.8
                    if "." in callee:
                        confidence = 0.6

                    calls.append(
                        CallRelationship(
                            source_file=file_path,
                            caller=caller,
                            callee=callee,
                            line_number=node.start_point[0] + 1,
                            confidence=confidence,
                        )
                    )

        return calls

    def _extract_js_calls(
        self, root_node, file_path: str, caller: str
    ) -> List[CallRelationship]:
        """Extract JavaScript/TypeScript function calls."""
        calls = []

        for node in self._iter_nodes(root_node):
            if node.type == "call_expression":
                function_node = node.child_by_field_name("function")
                if function_node:
                    callee = function_node.text.decode("utf8")

                    confidence = 0.8
                    if "." in callee or callee.startswith("this."):
                        confidence = 0.6

                    calls.append(
                        CallRelationship(
                            source_file=file_path,
                            caller=caller,
                            callee=callee,
                            line_number=node.start_point[0] + 1,
                            confidence=confidence,
                        )
                    )

        return calls

    def _extract_go_calls(
        self, root_node, file_path: str, caller: str
    ) -> List[CallRelationship]:
        """Extract Go function calls."""
        calls = []

        for node in self._iter_nodes(root_node):
            if node.type == "call_expression":
                function_node = node.child_by_field_name("function")
                if function_node:
                    callee = function_node.text.decode("utf8")

                    calls.append(
                        CallRelationship(
                            source_file=file_path,
                            caller=caller,
                            callee=callee,
                            line_number=node.start_point[0] + 1,
                            confidence=0.8,
                        )
                    )

        return calls

    def _extract_java_calls(
        self, root_node, file_path: str, caller: str
    ) -> List[CallRelationship]:
        """Extract Java method calls."""
        calls = []

        for node in self._iter_nodes(root_node):
            if node.type == "method_invocation":
                name_node = node.child_by_field_name("name")
                if name_node:
                    callee = name_node.text.decode("utf8")

                    object_node = node.child_by_field_name("object")
                    if object_node:
                        obj_name = object_node.text.decode("utf8")
                        callee = f"{obj_name}.{callee}"

                    calls.append(
                        CallRelationship(
                            source_file=file_path,
                            caller=caller,
                            callee=callee,
                            line_number=node.start_point[0] + 1,
                            confidence=0.7,
                        )
                    )

        return calls

    def _extract_rust_calls(
        self, root_node, file_path: str, caller: str
    ) -> List[CallRelationship]:
        """Extract Rust function calls."""
        calls = []

        for node in self._iter_nodes(root_node):
            if node.type == "call_expression":
                function_node = node.child_by_field_name("function")
                if function_node:
                    callee = function_node.text.decode("utf8")

                    calls.append(
                        CallRelationship(
                            source_file=file_path,
                            caller=caller,
                            callee=callee,
                            line_number=node.start_point[0] + 1,
                            confidence=0.8,
                        )
                    )

        return calls

    def get_symbol_at_position(
        self, code: str, language: str, line: int, column: int
    ) -> Dict[str, Any]:
        """
        Extract symbol information at a specific position in code.

        Uses Tree-Sitter AST parsing to identify the symbol at the given
        line and column position, including its type, definition location,
        and documentation.

        Args:
            code: Source code content
            language: Programming language (python, javascript, typescript, etc.)
            line: Line number (1-indexed)
            column: Column number (0-indexed)

        Returns:
            Dictionary with symbol information:
            - symbol_name: Name of the symbol
            - symbol_type: Type (function, class, variable, method, etc.)
            - definition_location: Dict with file_path, line, column
            - documentation: Docstring or comment if available
            Returns empty dict if no symbol found at position.
        """
        if not TREE_SITTER_AVAILABLE:
            logger.warning("Tree-Sitter not available for symbol extraction")
            return {}

        parser = self._get_parser(language)
        if not parser:
            logger.warning(f"No parser available for language: {language}")
            return {}

        try:
            # Parse the code
            tree = parser.parse(bytes(code, "utf8"))
            root_node = tree.root_node

            # Convert 1-indexed line to 0-indexed for Tree-Sitter
            target_line = line - 1
            target_column = column

            # Find the node at the target position
            node = root_node.descendant_for_point_range(
                (target_line, target_column), (target_line, target_column)
            )

            if not node:
                return {}

            # Walk up the tree to find a meaningful symbol node
            symbol_info = self._extract_symbol_info(node, language)

            return symbol_info

        except Exception as e:
            logger.error(f"Error extracting symbol at position: {e}")
            return {}

    def _extract_symbol_info(self, node, language: str) -> Dict[str, Any]:
        """
        Extract symbol information from a Tree-Sitter node.

        Walks up the AST from the given node to find the nearest
        meaningful symbol (function, class, variable, etc.).

        Args:
            node: Tree-Sitter node at target position
            language: Programming language

        Returns:
            Dictionary with symbol information
        """
        result = {}

        # Walk up the tree to find a definition node
        current = node
        while current:
            node_type = current.type

            # Python symbol extraction
            if language == "python":
                if node_type == "function_definition":
                    name_node = current.child_by_field_name("name")
                    if name_node:
                        result["symbol_name"] = name_node.text.decode("utf8")
                        result["symbol_type"] = "function"
                        result["definition_location"] = {
                            "line": current.start_point[0] + 1,
                            "column": current.start_point[1],
                        }
                        # Try to extract docstring
                        result["documentation"] = self._extract_python_docstring(
                            current
                        )
                        break

                elif node_type == "class_definition":
                    name_node = current.child_by_field_name("name")
                    if name_node:
                        result["symbol_name"] = name_node.text.decode("utf8")
                        result["symbol_type"] = "class"
                        result["definition_location"] = {
                            "line": current.start_point[0] + 1,
                            "column": current.start_point[1],
                        }
                        result["documentation"] = self._extract_python_docstring(
                            current
                        )
                        break

                elif node_type == "identifier":
                    # Check if this is a variable assignment
                    parent = current.parent
                    if parent and parent.type == "assignment":
                        result["symbol_name"] = current.text.decode("utf8")
                        result["symbol_type"] = "variable"
                        result["definition_location"] = {
                            "line": current.start_point[0] + 1,
                            "column": current.start_point[1],
                        }
                        break

            # JavaScript/TypeScript symbol extraction
            elif language in ["javascript", "typescript", "tsx", "jsx"]:
                if node_type in ["function_declaration", "function"]:
                    name_node = current.child_by_field_name("name")
                    if name_node:
                        result["symbol_name"] = name_node.text.decode("utf8")
                        result["symbol_type"] = "function"
                        result["definition_location"] = {
                            "line": current.start_point[0] + 1,
                            "column": current.start_point[1],
                        }
                        result["documentation"] = self._extract_js_jsdoc(current)
                        break

                elif node_type == "class_declaration":
                    name_node = current.child_by_field_name("name")
                    if name_node:
                        result["symbol_name"] = name_node.text.decode("utf8")
                        result["symbol_type"] = "class"
                        result["definition_location"] = {
                            "line": current.start_point[0] + 1,
                            "column": current.start_point[1],
                        }
                        result["documentation"] = self._extract_js_jsdoc(current)
                        break

                elif node_type == "method_definition":
                    name_node = current.child_by_field_name("name")
                    if name_node:
                        result["symbol_name"] = name_node.text.decode("utf8")
                        result["symbol_type"] = "method"
                        result["definition_location"] = {
                            "line": current.start_point[0] + 1,
                            "column": current.start_point[1],
                        }
                        result["documentation"] = self._extract_js_jsdoc(current)
                        break

                elif node_type == "variable_declarator":
                    name_node = current.child_by_field_name("name")
                    if name_node:
                        result["symbol_name"] = name_node.text.decode("utf8")
                        result["symbol_type"] = "variable"
                        result["definition_location"] = {
                            "line": current.start_point[0] + 1,
                            "column": current.start_point[1],
                        }
                        break

            # Move to parent node
            current = current.parent

        return result

    def _extract_python_docstring(self, node) -> Optional[str]:
        """
        Extract docstring from a Python function or class definition.

        Args:
            node: Tree-Sitter node for function_definition or class_definition

        Returns:
            Docstring text or None
        """
        try:
            # Look for the first string in the body
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    if child.type == "expression_statement":
                        for expr_child in child.children:
                            if expr_child.type == "string":
                                # Extract string content, removing quotes
                                docstring = expr_child.text.decode("utf8")
                                # Remove triple quotes and clean up
                                docstring = docstring.strip('"""').strip("'''")
                                docstring = docstring.strip('"').strip("'")
                                return docstring.strip()
        except Exception as e:
            logger.debug(f"Error extracting Python docstring: {e}")

        return None

    def _extract_js_jsdoc(self, node) -> Optional[str]:
        """
        Extract JSDoc comment from a JavaScript/TypeScript function or class.

        Args:
            node: Tree-Sitter node for function or class definition

        Returns:
            JSDoc text or None
        """
        try:
            # Look for a comment node immediately before this node
            parent = node.parent
            if parent:
                node_index = None
                for i, child in enumerate(parent.children):
                    if child == node:
                        node_index = i
                        break

                if node_index and node_index > 0:
                    prev_node = parent.children[node_index - 1]
                    if prev_node.type == "comment":
                        comment_text = prev_node.text.decode("utf8")
                        # Clean up JSDoc formatting
                        if comment_text.startswith("/**"):
                            comment_text = comment_text.strip("/*").strip("*/")
                            # Remove leading asterisks from each line
                            lines = [
                                line.strip().lstrip("*").strip()
                                for line in comment_text.split("\n")
                            ]
                            return "\n".join(lines).strip()
        except Exception as e:
            logger.debug(f"Error extracting JSDoc: {e}")

        return None
