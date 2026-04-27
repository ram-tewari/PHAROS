"""
Repository Parser for Hybrid Edge-Cloud Orchestration.

This module provides functionality to clone Git repositories, parse source files,
extract import statements, and build dependency graphs for neural graph learning.
"""

import logging
import os
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
import torch
from git import Repo
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript

from app.utils.path_exclusions import (
    EXCLUDE_DIRS,
    is_excluded_file,
)

logger = logging.getLogger(__name__)


class DependencyGraph:
    """Container for dependency graph data."""

    def __init__(self, edge_index: torch.Tensor, file_paths: List[str]):
        """
        Initialize a dependency graph.

        Args:
            edge_index: Edge list tensor of shape [2, num_edges]
            file_paths: List of file paths corresponding to node indices
        """
        self.edge_index = edge_index
        self.file_paths = file_paths
        self.num_nodes = len(file_paths)


class RepositoryParser:
    """Parse code repositories and build dependency graphs."""

    def __init__(self):
        """Initialize the repository parser with Tree-sitter parsers."""
        # Initialize Tree-sitter parsers for supported languages
        self._parsers = self._initialize_parsers()
        self._supported_extensions = {".py", ".js", ".ts"}

    def _initialize_parsers(self) -> Dict[str, Parser]:
        """
        Initialize Tree-sitter parsers for each supported language.

        Returns:
            Dictionary mapping file extensions to Parser instances
        """
        parsers = {}

        # Python parser
        py_parser = Parser(Language(tspython.language()))
        parsers[".py"] = py_parser

        # JavaScript/TypeScript parser (same parser for both)
        js_parser = Parser(Language(tsjavascript.language()))
        parsers[".js"] = js_parser
        parsers[".ts"] = js_parser

        return parsers

    def clone_repository(self, repo_url: str) -> str:
        """
        Clone a Git repository to an isolated temporary directory.

        Uses tempfile.mkdtemp() with unique prefixes to ensure different
        jobs use different temp directories, preventing conflicts and
        security issues (Requirement 11.5).

        Args:
            repo_url: Repository URL (e.g., github.com/user/repo or https://github.com/user/repo)

        Returns:
            Path to cloned repository

        Raises:
            Exception: If cloning fails
        """
        # Ensure URL has protocol
        if not repo_url.startswith(("http://", "https://", "git@")):
            repo_url = f"https://{repo_url}"

        # Create temp directory with unique prefix (includes timestamp and PID)
        # This ensures concurrent clones use different directories
        import time

        timestamp = int(time.time() * 1000)  # Millisecond precision
        pid = os.getpid()
        prefix = f"neo_repo_{timestamp}_{pid}_"

        temp_dir = tempfile.mkdtemp(prefix=prefix)

        try:
            print(f"📥 Cloning {repo_url}...")
            Repo.clone_from(repo_url, temp_dir, depth=1)  # Shallow clone for efficiency
            print(f"✅ Cloned to {temp_dir}")
            return temp_dir
        except Exception as e:
            # Clean up on failure
            try:
                shutil.rmtree(temp_dir)
            except Exception as cleanup_error:
                logger.error(
                    f"Failed to clean up temp directory {temp_dir}: {cleanup_error}"
                )
            raise Exception(f"Failed to clone repository: {e}")

    def _find_source_files(self, repo_path: str) -> List[str]:
        """
        Find all source files in repository.

        Args:
            repo_path: Path to repository root

        Returns:
            List of absolute paths to source files
        """
        source_files = []

        for ext in self._supported_extensions:
            for file_path in Path(repo_path).rglob(f"*{ext}"):
                if any(part in EXCLUDE_DIRS for part in file_path.parts):
                    continue
                if is_excluded_file(file_path.name):
                    continue
                source_files.append(str(file_path))

        print(f"📁 Found {len(source_files)} source files")
        return source_files

    def cleanup(self, repo_path: str):
        """
        Clean up temporary repository directory.

        Args:
            repo_path: Path to repository to remove
        """
        try:
            if os.path.exists(repo_path):
                shutil.rmtree(repo_path)
                logger.info(f"Cleaned up temporary directory: {repo_path}")
        except Exception as e:
            logger.error(f"Failed to clean up temporary directory {repo_path}: {e}")
            # Don't raise - cleanup failures shouldn't break the workflow

    def _extract_imports(self, file_path: str) -> List[str]:
        """
        Extract import statements from a source file.

        Args:
            file_path: Path to source file

        Returns:
            List of imported module/file paths
        """
        ext = Path(file_path).suffix
        parser = self._parsers.get(ext)

        if not parser:
            return []

        try:
            with open(file_path, "rb") as f:
                code = f.read()

            tree = parser.parse(code)
            imports = []

            # Language-specific import extraction
            if ext == ".py":
                imports = self._extract_python_imports(tree.root_node, code)
            elif ext in [".js", ".ts"]:
                imports = self._extract_javascript_imports(tree.root_node, code)

            return imports

        except Exception as e:
            # Log error but continue with remaining files
            print(f"WARNING: Failed to parse {file_path}: {e}")
            return []

    def _extract_python_imports(self, node, code: bytes) -> List[str]:
        """
        Extract Python import statements.

        Args:
            node: Tree-sitter root node
            code: Source code as bytes

        Returns:
            List of imported module names
        """
        imports = []

        def traverse(node):
            if node.type == "import_statement":
                # import module
                for child in node.children:
                    if child.type == "dotted_name":
                        import_name = code[child.start_byte : child.end_byte].decode(
                            "utf-8", errors="ignore"
                        )
                        imports.append(import_name)
            elif node.type == "import_from_statement":
                # from module import ...
                for child in node.children:
                    if child.type == "dotted_name":
                        import_name = code[child.start_byte : child.end_byte].decode(
                            "utf-8", errors="ignore"
                        )
                        imports.append(import_name)

            # Recursively traverse children
            for child in node.children:
                traverse(child)

        traverse(node)
        return imports

    def _extract_javascript_imports(self, node, code: bytes) -> List[str]:
        """
        Extract JavaScript/TypeScript import statements.

        Args:
            node: Tree-sitter root node
            code: Source code as bytes

        Returns:
            List of imported module/file paths
        """
        imports = []

        def traverse(node):
            if node.type == "import_statement":
                # import ... from 'module'
                for child in node.children:
                    if child.type == "string":
                        # Remove quotes
                        import_path = code[child.start_byte : child.end_byte].decode(
                            "utf-8", errors="ignore"
                        )
                        import_path = import_path.strip("\"'")
                        imports.append(import_path)

            # Recursively traverse children
            for child in node.children:
                traverse(child)

        traverse(node)
        return imports

    def build_dependency_graph(self, repo_path: str) -> DependencyGraph:
        """
        Build dependency graph from repository.

        Args:
            repo_path: Path to cloned repository

        Returns:
            DependencyGraph with edge_index and file_paths
        """
        # Find all source files
        file_paths = self._find_source_files(repo_path)

        if not file_paths:
            # Empty repository - return empty graph with self-loop
            print("WARNING: No source files found")
            edge_index = torch.tensor(  # type: ignore[attr-defined][[0], [0]], dtype=torch.long)
            return DependencyGraph(edge_index=edge_index, file_paths=["<empty>"])

        # Create file index mapping
        file_to_idx = {path: idx for idx, path in enumerate(file_paths)}

        # Extract imports and build edges
        edges = []
        for file_path in file_paths:
            imports = self._extract_imports(file_path)

            # Resolve imports to file paths
            for import_path in imports:
                resolved = self._resolve_import(import_path, file_path, repo_path)
                if resolved and resolved in file_to_idx:
                    # Add edge: file -> imported_file
                    edges.append([file_to_idx[file_path], file_to_idx[resolved]])

        # Convert to PyTorch tensor
        if edges:
            edge_index = torch.tensor(  # type: ignore[attr-defined]edges, dtype=torch.long).t()
        else:
            # Empty graph - create self-loops for all nodes
            edge_index = torch.tensor(  # type: ignore[attr-defined]
                [[i, i] for i in range(len(file_paths))], dtype=torch.long
            ).t()

        print(f"[STATS]Built graph: {len(file_paths)} nodes, {edge_index.shape[1]} edges")

        return DependencyGraph(edge_index=edge_index, file_paths=file_paths)

    def _resolve_import(
        self, import_path: str, current_file: str, repo_path: str
    ) -> Optional[str]:
        """
        Resolve import path to actual file path.

        Args:
            import_path: Import statement path (e.g., './utils' or 'app.models')
            current_file: Path to file containing the import
            repo_path: Root path of repository

        Returns:
            Resolved absolute file path or None if not found
        """
        # Handle relative imports (JavaScript/TypeScript style)
        if import_path.startswith("."):
            current_dir = Path(current_file).parent
            resolved = (current_dir / import_path).resolve()

            # Try with common extensions
            for ext in [".py", ".js", ".ts", "/index.js", "/index.ts"]:
                candidate = Path(str(resolved) + ext)
                if candidate.exists() and str(candidate) != current_file:
                    return str(candidate)

        # Handle absolute imports (Python style)
        # Convert module path to file path (e.g., 'app.models' -> 'app/models.py')
        if "." in import_path and not import_path.startswith("."):
            # Try to resolve as Python module
            module_parts = import_path.split(".")

            # Try different combinations
            for i in range(len(module_parts), 0, -1):
                module_path = Path(repo_path) / "/".join(module_parts[:i])

                # Try as file
                for ext in [".py"]:
                    candidate = Path(str(module_path) + ext)
                    if candidate.exists() and str(candidate) != current_file:
                        return str(candidate)

                # Try as package
                candidate = module_path / "__init__.py"
                if candidate.exists() and str(candidate) != current_file:
                    return str(candidate)

        # Could not resolve
        return None

    def detect_best_practices(self, repo_path: str) -> Dict[str, Any]:
        """
        Detect best practices in a repository.

        Analyzes code patterns, test coverage, documentation, and code quality
        indicators to identify best practices being followed.

        Args:
            repo_path: Path to repository root

        Returns:
            Dictionary with:
            - patterns: List of detected code patterns
            - quality_indicators: Dict of quality metrics
            - recommendations: List of improvement suggestions
        """
        from pathlib import Path

        print(f"🔍 Detecting best practices in {repo_path}...")

        # Find all source files
        source_files = self._find_source_files(repo_path)

        if not source_files:
            return {
                "patterns": [],
                "quality_indicators": {},
                "recommendations": ["No source files found in repository"],
            }

        # Initialize results
        patterns = []
        quality_indicators = {}
        recommendations = []

        # Analyze patterns across all files
        error_handling_count = 0
        docstring_count = 0
        test_file_count = 0
        total_functions = 0
        total_classes = 0

        for file_path in source_files:
            ext = Path(file_path).suffix

            # Count test files
            if "test" in Path(file_path).name.lower():
                test_file_count += 1

            # Parse file for patterns
            try:
                with open(file_path, "rb") as f:
                    code = f.read()

                parser = self._parsers.get(ext)
                if not parser:
                    continue

                tree = parser.parse(code)

                # Analyze based on language
                if ext == ".py":
                    file_patterns = self._analyze_python_patterns(tree.root_node, code)
                    error_handling_count += file_patterns.get("error_handling", 0)
                    docstring_count += file_patterns.get("docstrings", 0)
                    total_functions += file_patterns.get("functions", 0)
                    total_classes += file_patterns.get("classes", 0)
                elif ext in [".js", ".ts"]:
                    file_patterns = self._analyze_javascript_patterns(
                        tree.root_node, code
                    )
                    error_handling_count += file_patterns.get("error_handling", 0)
                    docstring_count += file_patterns.get("docstrings", 0)
                    total_functions += file_patterns.get("functions", 0)
                    total_classes += file_patterns.get("classes", 0)

            except Exception as e:
                print(f"WARNING: Error analyzing {file_path}: {e}")
                continue

        # Calculate quality indicators
        test_coverage_indicator = test_file_count / max(len(source_files), 1)
        doc_coverage = docstring_count / max(total_functions + total_classes, 1)
        error_handling_ratio = error_handling_count / max(total_functions, 1)

        quality_indicators = {
            "test_file_ratio": round(test_coverage_indicator, 2),
            "documentation_coverage": round(doc_coverage, 2),
            "error_handling_ratio": round(error_handling_ratio, 2),
            "total_files": len(source_files),
            "test_files": test_file_count,
            "total_functions": total_functions,
            "total_classes": total_classes,
        }

        # Identify patterns
        if error_handling_count > 0:
            confidence = min(error_handling_ratio, 1.0)
            patterns.append(
                {
                    "pattern_type": "error_handling",
                    "pattern_name": "Try-Catch Error Handling",
                    "examples": [f"Found {error_handling_count} error handling blocks"],
                    "confidence": round(confidence, 2),
                }
            )

        if docstring_count > 0:
            confidence = min(doc_coverage, 1.0)
            patterns.append(
                {
                    "pattern_type": "documentation",
                    "pattern_name": "Function/Class Documentation",
                    "examples": [
                        f"Found {docstring_count} documented functions/classes"
                    ],
                    "confidence": round(confidence, 2),
                }
            )

        if test_file_count > 0:
            confidence = min(
                test_coverage_indicator * 2, 1.0
            )  # Scale up for visibility
            patterns.append(
                {
                    "pattern_type": "testing",
                    "pattern_name": "Unit Testing",
                    "examples": [f"Found {test_file_count} test files"],
                    "confidence": round(confidence, 2),
                }
            )

        # Generate recommendations
        if test_coverage_indicator < 0.2:
            recommendations.append(
                "Consider adding more test files (current ratio: {:.1%})".format(
                    test_coverage_indicator
                )
            )

        if doc_coverage < 0.5:
            recommendations.append(
                "Consider adding documentation to more functions/classes (current coverage: {:.1%})".format(
                    doc_coverage
                )
            )

        if error_handling_ratio < 0.3:
            recommendations.append(
                "Consider adding error handling to more functions (current ratio: {:.1%})".format(
                    error_handling_ratio
                )
            )

        print(
            f"✅ Detected {len(patterns)} patterns, {len(recommendations)} recommendations"
        )

        return {
            "patterns": patterns,
            "quality_indicators": quality_indicators,
            "recommendations": recommendations,
        }

    def _analyze_python_patterns(self, root_node, code: bytes) -> Dict[str, int]:
        """
        Analyze Python code for best practice patterns.

        Args:
            root_node: Tree-sitter root node
            code: Source code as bytes

        Returns:
            Dictionary with pattern counts
        """
        patterns = {"error_handling": 0, "docstrings": 0, "functions": 0, "classes": 0}

        def traverse(node):
            if node.type == "try_statement":
                patterns["error_handling"] += 1

            elif node.type == "function_definition":
                patterns["functions"] += 1
                # Check for docstring
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        if child.type == "expression_statement":
                            for expr_child in child.children:
                                if expr_child.type == "string":
                                    patterns["docstrings"] += 1
                                    break
                            break

            elif node.type == "class_definition":
                patterns["classes"] += 1
                # Check for docstring
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        if child.type == "expression_statement":
                            for expr_child in child.children:
                                if expr_child.type == "string":
                                    patterns["docstrings"] += 1
                                    break
                            break

            # Traverse children
            for child in node.children:
                traverse(child)

        traverse(root_node)
        return patterns

    def _analyze_javascript_patterns(self, root_node, code: bytes) -> Dict[str, int]:
        """
        Analyze JavaScript/TypeScript code for best practice patterns.

        Args:
            root_node: Tree-sitter root node
            code: Source code as bytes

        Returns:
            Dictionary with pattern counts
        """
        patterns = {"error_handling": 0, "docstrings": 0, "functions": 0, "classes": 0}

        def traverse(node):
            if node.type == "try_statement":
                patterns["error_handling"] += 1

            elif node.type in ["function_declaration", "function"]:
                patterns["functions"] += 1
                # Check for JSDoc comment
                parent = node.parent
                if parent:
                    node_index = None
                    for i, child in enumerate(parent.children):
                        if child == node:
                            node_index = i
                            break

                    if node_index and node_index > 0:
                        prev_node = parent.children[node_index - 1]
                        if prev_node.type == "comment" and b"/**" in prev_node.text:
                            patterns["docstrings"] += 1

            elif node.type == "class_declaration":
                patterns["classes"] += 1
                # Check for JSDoc comment
                parent = node.parent
                if parent:
                    node_index = None
                    for i, child in enumerate(parent.children):
                        if child == node:
                            node_index = i
                            break

                    if node_index and node_index > 0:
                        prev_node = parent.children[node_index - 1]
                        if prev_node.type == "comment" and b"/**" in prev_node.text:
                            patterns["docstrings"] += 1

            # Traverse children
            for child in node.children:
                traverse(child)

        traverse(root_node)
        return patterns

    def extract_reusable_components(self, repo_path: str) -> List[Dict[str, Any]]:
        """
        Extract reusable components from a repository.

        Identifies utility functions, classes, and interfaces that could be
        reused in other projects.

        Args:
            repo_path: Path to repository root

        Returns:
            List of reusable component dictionaries with:
            - component_name: Name of the component
            - file_path: Path to file containing component
            - interface: Function/class signature
            - usage_examples: List of usage examples
            - dependencies: List of dependencies
        """
        from pathlib import Path

        print(f"🔍 Extracting reusable components from {repo_path}...")

        # Find all source files
        source_files = self._find_source_files(repo_path)

        if not source_files:
            return []

        components = []

        for file_path in source_files:
            ext = Path(file_path).suffix

            # Skip test files
            if "test" in Path(file_path).name.lower():
                continue

            # Parse file for reusable components
            try:
                with open(file_path, "rb") as f:
                    code = f.read()

                parser = self._parsers.get(ext)
                if not parser:
                    continue

                tree = parser.parse(code)

                # Extract components based on language
                if ext == ".py":
                    file_components = self._extract_python_components(
                        tree.root_node, code, file_path
                    )
                    components.extend(file_components)
                elif ext in [".js", ".ts"]:
                    file_components = self._extract_javascript_components(
                        tree.root_node, code, file_path
                    )
                    components.extend(file_components)

            except Exception as e:
                print(f"WARNING: Error extracting from {file_path}: {e}")
                continue

        print(f"✅ Extracted {len(components)} reusable components")

        return components

    def _extract_python_components(
        self, root_node, code: bytes, file_path: str
    ) -> List[Dict[str, Any]]:
        """
        Extract reusable Python components.

        Args:
            root_node: Tree-sitter root node
            code: Source code as bytes
            file_path: Path to source file

        Returns:
            List of component dictionaries
        """
        components = []

        def traverse(node):
            # Extract utility functions (functions not in classes)
            if node.type == "function_definition":
                # Check if this is a top-level function (not a method)
                parent = node.parent
                is_top_level = parent and parent.type == "module"

                if is_top_level:
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        func_name = name_node.text.decode("utf8", errors="ignore")

                        # Extract function signature
                        params_node = node.child_by_field_name("parameters")
                        params = (
                            params_node.text.decode("utf8", errors="ignore")
                            if params_node
                            else "()"
                        )

                        # Extract docstring
                        docstring = None
                        body = node.child_by_field_name("body")
                        if body:
                            for child in body.children:
                                if child.type == "expression_statement":
                                    for expr_child in child.children:
                                        if expr_child.type == "string":
                                            docstring = (
                                                expr_child.text.decode(
                                                    "utf8", errors="ignore"
                                                )
                                                .strip('"""')
                                                .strip("'''")
                                                .strip()
                                            )
                                            break
                                    break

                        # Extract dependencies (imports used in function)
                        dependencies = self._extract_function_dependencies(node, code)

                        components.append(
                            {
                                "component_name": func_name,
                                "file_path": file_path,
                                "interface": f"def {func_name}{params}",
                                "usage_examples": [docstring] if docstring else [],
                                "dependencies": dependencies,
                            }
                        )

            # Extract utility classes
            elif node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    class_name = name_node.text.decode("utf8", errors="ignore")

                    # Extract class docstring
                    docstring = None
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            if child.type == "expression_statement":
                                for expr_child in child.children:
                                    if expr_child.type == "string":
                                        docstring = (
                                            expr_child.text.decode(
                                                "utf8", errors="ignore"
                                            )
                                            .strip('"""')
                                            .strip("'''")
                                            .strip()
                                        )
                                        break
                                break

                    # Extract method signatures
                    methods = []
                    if body:
                        for child in body.children:
                            if child.type == "function_definition":
                                method_name_node = child.child_by_field_name("name")
                                if method_name_node:
                                    method_name = method_name_node.text.decode(
                                        "utf8", errors="ignore"
                                    )
                                    params_node = child.child_by_field_name(
                                        "parameters"
                                    )
                                    params = (
                                        params_node.text.decode("utf8", errors="ignore")
                                        if params_node
                                        else "()"
                                    )
                                    methods.append(f"{method_name}{params}")

                    # Extract dependencies
                    dependencies = self._extract_function_dependencies(node, code)

                    interface = (
                        f"class {class_name}:\n    " + "\n    ".join(methods)
                        if methods
                        else f"class {class_name}"
                    )

                    components.append(
                        {
                            "component_name": class_name,
                            "file_path": file_path,
                            "interface": interface,
                            "usage_examples": [docstring] if docstring else [],
                            "dependencies": dependencies,
                        }
                    )

            # Traverse children
            for child in node.children:
                traverse(child)

        traverse(root_node)
        return components

    def _extract_javascript_components(
        self, root_node, code: bytes, file_path: str
    ) -> List[Dict[str, Any]]:
        """
        Extract reusable JavaScript/TypeScript components.

        Args:
            root_node: Tree-sitter root node
            code: Source code as bytes
            file_path: Path to source file

        Returns:
            List of component dictionaries
        """
        components = []

        def traverse(node):
            # Extract exported functions
            if node.type in ["function_declaration", "function"]:
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = name_node.text.decode("utf8", errors="ignore")

                    # Extract function signature
                    params_node = node.child_by_field_name("parameters")
                    params = (
                        params_node.text.decode("utf8", errors="ignore")
                        if params_node
                        else "()"
                    )

                    # Check for JSDoc
                    jsdoc = None
                    parent = node.parent
                    if parent:
                        node_index = None
                        for i, child in enumerate(parent.children):
                            if child == node:
                                node_index = i
                                break

                        if node_index and node_index > 0:
                            prev_node = parent.children[node_index - 1]
                            if prev_node.type == "comment" and b"/**" in prev_node.text:
                                jsdoc = (
                                    prev_node.text.decode("utf8", errors="ignore")
                                    .strip("/*")
                                    .strip("*/")
                                    .strip()
                                )

                    # Extract dependencies
                    dependencies = self._extract_function_dependencies(node, code)

                    components.append(
                        {
                            "component_name": func_name,
                            "file_path": file_path,
                            "interface": f"function {func_name}{params}",
                            "usage_examples": [jsdoc] if jsdoc else [],
                            "dependencies": dependencies,
                        }
                    )

            # Extract exported classes
            elif node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    class_name = name_node.text.decode("utf8", errors="ignore")

                    # Check for JSDoc
                    jsdoc = None
                    parent = node.parent
                    if parent:
                        node_index = None
                        for i, child in enumerate(parent.children):
                            if child == node:
                                node_index = i
                                break

                        if node_index and node_index > 0:
                            prev_node = parent.children[node_index - 1]
                            if prev_node.type == "comment" and b"/**" in prev_node.text:
                                jsdoc = (
                                    prev_node.text.decode("utf8", errors="ignore")
                                    .strip("/*")
                                    .strip("*/")
                                    .strip()
                                )

                    # Extract method signatures
                    methods = []
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            if child.type == "method_definition":
                                method_name_node = child.child_by_field_name("name")
                                if method_name_node:
                                    method_name = method_name_node.text.decode(
                                        "utf8", errors="ignore"
                                    )
                                    params_node = child.child_by_field_name(
                                        "parameters"
                                    )
                                    params = (
                                        params_node.text.decode("utf8", errors="ignore")
                                        if params_node
                                        else "()"
                                    )
                                    methods.append(f"{method_name}{params}")

                    # Extract dependencies
                    dependencies = self._extract_function_dependencies(node, code)

                    interface = (
                        f"class {class_name} {{\n  " + "\n  ".join(methods) + "\n}}"
                        if methods
                        else f"class {class_name}"
                    )

                    components.append(
                        {
                            "component_name": class_name,
                            "file_path": file_path,
                            "interface": interface,
                            "usage_examples": [jsdoc] if jsdoc else [],
                            "dependencies": dependencies,
                        }
                    )

            # Traverse children
            for child in node.children:
                traverse(child)

        traverse(root_node)
        return components

    def _extract_function_dependencies(self, node, code: bytes) -> List[str]:
        """
        Extract dependencies (imports/calls) used within a function or class.

        Args:
            node: Tree-sitter node for function or class
            code: Source code as bytes

        Returns:
            List of dependency names
        """
        dependencies = set()

        def traverse(node):
            # Look for identifiers that might be dependencies
            if node.type == "identifier":
                identifier = node.text.decode("utf8", errors="ignore")
                # Filter out common keywords and built-ins
                if identifier not in [
                    "self",
                    "this",
                    "return",
                    "if",
                    "else",
                    "for",
                    "while",
                    "def",
                    "class",
                    "function",
                ]:
                    dependencies.add(identifier)

            # Traverse children
            for child in node.children:
                traverse(child)

        traverse(node)

        # Return sorted list (limit to reasonable size)
        return sorted(list(dependencies))[:10]
