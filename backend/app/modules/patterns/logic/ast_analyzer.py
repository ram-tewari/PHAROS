"""
AST-based code analysis for Python source files.

Extracts architectural patterns, style conventions, and structural fingerprints
from Python ASTs. Designed for batch processing of entire repositories.
"""

from __future__ import annotations

import ast
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..schema import (
    ArchitectureProfile,
    AsyncProfile,
    DependencyInjectionProfile,
    DocstringProfile,
    ErrorHandlingProfile,
    FrameworkProfile,
    ImportProfile,
    NamingConventions,
    ORMProfile,
    RepositoryPatternProfile,
    StyleProfile,
    StructuralFingerprint,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Helpers
# ============================================================================


def _safe_parse(source: str, filename: str = "<unknown>") -> Optional[ast.Module]:
    """Parse Python source, returning None on syntax errors."""
    try:
        return ast.parse(source, filename=filename)
    except SyntaxError:
        logger.debug("Syntax error in %s, skipping", filename)
        return None


def _classify_casing(name: str) -> str:
    """Classify a name's casing convention."""
    if name.isupper():
        return "UPPER_SNAKE"
    if "_" in name and name == name.lower():
        return "snake_case"
    if name[0].isupper() and "_" not in name:
        return "PascalCase"
    if name[0].islower() and "_" not in name and any(c.isupper() for c in name):
        return "camelCase"
    return "mixed"


def _get_nesting_depth(node: ast.AST, current: int = 0) -> int:
    """Get the maximum nesting depth of control-flow statements."""
    max_depth = current
    nested_types = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.AsyncWith, ast.AsyncFor)
    for child in ast.iter_child_nodes(node):
        if isinstance(child, nested_types):
            max_depth = max(max_depth, _get_nesting_depth(child, current + 1))
        else:
            max_depth = max(max_depth, _get_nesting_depth(child, current))
    return max_depth


# ============================================================================
# Per-file AST Visitor
# ============================================================================


class _FileVisitor(ast.NodeVisitor):
    """Collects raw metrics from a single file's AST."""

    def __init__(self, source_lines: List[str], filename: str):
        self.filename = filename
        self.source_lines = source_lines

        # Counts
        self.async_functions: int = 0
        self.sync_functions: int = 0
        self.classes: int = 0
        self.function_lengths: List[int] = []
        self.class_lengths: List[int] = []

        # Naming
        self.function_names: List[str] = []
        self.class_names: List[str] = []
        self.variable_names: List[str] = []
        self.constant_names: List[str] = []
        self.private_prefixes: Set[str] = set()

        # Type hints
        self.annotated_params: int = 0
        self.total_params: int = 0

        # Async details
        self.uses_asyncio_gather: bool = False
        self.uses_asyncio_create_task: bool = False
        self.uses_async_generators: bool = False
        self.uses_async_context_managers: bool = False

        # Error handling
        self.try_blocks: int = 0
        self.bare_excepts: int = 0
        self.typed_excepts: int = 0
        self.except_logging_styles: List[str] = []
        self.reraise_count: int = 0
        self.except_total: int = 0
        self.caught_exceptions: List[str] = []
        self.custom_exception_classes: int = 0

        # Imports
        self.imports: List[str] = []
        self.has_relative_imports: bool = False
        self.has_absolute_imports: bool = False

        # Docstrings
        self.documented_functions: int = 0
        self.total_functions: int = 0
        self.docstring_styles: List[str] = []

        # Comments
        self.comment_lines: int = 0

        # DI
        self.di_depends_count: int = 0

        # ORM
        self.orm_indicators: Dict[str, int] = defaultdict(int)
        self.raw_sql_count: int = 0

        # Framework
        self.framework_indicators: Dict[str, int] = defaultdict(int)

        # Structural fingerprints
        self.fingerprints: List[StructuralFingerprint] = []

        # Nesting
        self.max_nesting: int = 0

        # Count comment lines
        for line in source_lines:
            stripped = line.strip()
            if stripped.startswith("#") and not stripped.startswith("#!"):
                self.comment_lines += 1

    # ------------------------------------------------------------------
    # Functions and methods
    # ------------------------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._process_function(node, is_async=False)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._process_function(node, is_async=True)
        self.generic_visit(node)

    def _process_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> None:
        if is_async:
            self.async_functions += 1
        else:
            self.sync_functions += 1

        self.function_names.append(node.name)
        self.total_functions += 1

        # Function length
        if node.end_lineno and node.lineno:
            self.function_lengths.append(node.end_lineno - node.lineno + 1)

        # Private prefix detection
        if node.name.startswith("__") and not node.name.endswith("__"):
            self.private_prefixes.add("__")
        elif node.name.startswith("_"):
            self.private_prefixes.add("_")

        # Type hint counting
        for arg in node.args.args + node.args.kwonlyargs:
            self.total_params += 1
            if arg.annotation is not None:
                self.annotated_params += 1

        # Return annotation
        if node.returns is not None:
            self.annotated_params += 1
            self.total_params += 1

        # Docstring
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, (ast.Constant, ast.Str))
        ):
            self.documented_functions += 1
            doc_val = node.body[0].value
            doc_text = doc_val.value if isinstance(doc_val, ast.Constant) else doc_val.s
            if isinstance(doc_text, str):
                self.docstring_styles.append(self._classify_docstring(doc_text))

        # DI detection: Depends() in defaults
        for default in node.args.defaults + node.args.kw_defaults:
            if default is not None and self._is_depends_call(default):
                self.di_depends_count += 1

        # Nesting depth
        depth = _get_nesting_depth(node)
        self.max_nesting = max(self.max_nesting, depth)

    def _is_depends_call(self, node: ast.AST) -> bool:
        """Check if a node is a call to Depends(...)."""
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "Depends":
                return True
            if isinstance(node.func, ast.Attribute) and node.func.attr == "Depends":
                return True
        return False

    @staticmethod
    def _classify_docstring(text: str) -> str:
        """Heuristic docstring style classification."""
        if "Args:" in text or "Returns:" in text or "Raises:" in text:
            return "google"
        if "Parameters\n" in text or "----------" in text:
            return "numpy"
        if ":param " in text or ":type " in text:
            return "sphinx"
        return "plain"

    # ------------------------------------------------------------------
    # Classes
    # ------------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes += 1
        self.class_names.append(node.name)

        if node.end_lineno and node.lineno:
            self.class_lengths.append(node.end_lineno - node.lineno + 1)

        # Detect custom exceptions
        for base in node.bases:
            base_name = self._get_name(base)
            if base_name and "Exception" in base_name or base_name and "Error" in base_name:
                self.custom_exception_classes += 1

        # Detect ORM model patterns
        for base in node.bases:
            base_name = self._get_name(base)
            if base_name in ("Base", "DeclarativeBase"):
                self.orm_indicators["sqlalchemy"] += 1
            elif base_name == "Model":
                # Could be Django or other
                self.orm_indicators["django_orm"] += 1
            elif base_name in ("db.Model",):
                self.orm_indicators["flask_sqlalchemy"] += 1

        # Detect mapped_column, Column usage inside class
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func_name = self._get_name(child.func)
                if func_name in ("mapped_column", "Column"):
                    self.orm_indicators["sqlalchemy"] += 1
                elif func_name in ("CharField", "IntegerField", "TextField"):
                    self.orm_indicators["django_orm"] += 1

        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def visit_Try(self, node: ast.Try) -> None:
        self.try_blocks += 1

        for handler in node.handlers:
            self.except_total += 1
            if handler.type is None:
                self.bare_excepts += 1
            else:
                self.typed_excepts += 1
                exc_name = self._get_name(handler.type)
                if exc_name:
                    self.caught_exceptions.append(exc_name)

            # Analyze handler body for logging style and re-raises
            for stmt in handler.body:
                if isinstance(stmt, ast.Raise):
                    self.reraise_count += 1

                # Detect logging calls
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    call = stmt.value
                    if isinstance(call.func, ast.Attribute):
                        attr_name = call.func.attr
                        if attr_name in ("error", "exception", "warning", "critical"):
                            # Check if it's logger.X
                            if isinstance(call.func.value, ast.Name):
                                self.except_logging_styles.append(
                                    f"logger.{attr_name}"
                                )
                        elif attr_name == "print" or (
                            isinstance(call.func, ast.Name) and call.func.id == "print"
                        ):
                            self.except_logging_styles.append("print")

                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    if isinstance(stmt.value.func, ast.Name) and stmt.value.func.id == "print":
                        self.except_logging_styles.append("print")

            # Build structural fingerprint for error handlers
            if handler.type is not None:
                exc_name = self._get_name(handler.type) or "Unknown"
                body_sig = self._fingerprint_handler_body(handler.body)
                sig = f"try>except({exc_name})>{body_sig}"
                self.fingerprints.append(
                    StructuralFingerprint(
                        pattern_type="error_handler",
                        signature=sig,
                        source_file=self.filename,
                        first_seen_commit="",
                    )
                )

        self.generic_visit(node)

    def _fingerprint_handler_body(self, body: List[ast.stmt]) -> str:
        """Create a normalized signature for an except block's body."""
        parts = []
        for stmt in body[:3]:  # Only first 3 statements
            if isinstance(stmt, ast.Raise):
                parts.append("raise")
            elif isinstance(stmt, ast.Return):
                parts.append("return")
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call_name = self._get_name(stmt.value.func)
                if call_name:
                    parts.append(call_name)
            elif isinstance(stmt, ast.Assign):
                parts.append("assign")
            elif isinstance(stmt, ast.Pass):
                parts.append("pass")
        return "+".join(parts) if parts else "empty"

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name.split(".")[0])
            self.has_absolute_imports = True
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level and node.level > 0:
            self.has_relative_imports = True
        else:
            self.has_absolute_imports = True
        if node.module:
            top = node.module.split(".")[0]
            self.imports.append(top)

            # Framework detection
            if top == "fastapi":
                self.framework_indicators["fastapi"] += 1
            elif top == "flask":
                self.framework_indicators["flask"] += 1
            elif top == "django":
                self.framework_indicators["django"] += 1
            elif top == "starlette":
                self.framework_indicators["starlette"] += 1

            # ORM detection
            if top == "sqlalchemy":
                self.orm_indicators["sqlalchemy"] += 1
            elif top == "tortoise":
                self.orm_indicators["tortoise"] += 1
            elif top == "peewee":
                self.orm_indicators["peewee"] += 1

        # Detect specific import patterns
        if node.module:
            for alias in node.names:
                full_name = f"{node.module}.{alias.name}" if node.module else alias.name
                if "APIRouter" in full_name or "Blueprint" in full_name:
                    self.framework_indicators.setdefault("uses_routers", 0)
                    self.framework_indicators["uses_routers"] += 1

        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Assignments (for variable/constant naming)
    # ------------------------------------------------------------------

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                name = target.id
                if name.isupper() and len(name) > 1:
                    self.constant_names.append(name)
                elif not name.startswith("_"):
                    self.variable_names.append(name)

        # Detect raw SQL
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            val = node.value.value.strip().upper()
            if val.startswith(("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "CREATE ")):
                self.raw_sql_count += 1

        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Async-specific node detection
    # ------------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        func_name = self._get_name(node.func)
        if func_name:
            if "asyncio.gather" in func_name or func_name == "gather":
                self.uses_asyncio_gather = True
            elif "asyncio.create_task" in func_name or func_name == "create_task":
                self.uses_asyncio_create_task = True
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self.uses_async_context_managers = True
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.uses_async_generators = True
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _get_name(node: ast.AST) -> Optional[str]:
        """Extract a readable name from a Name or Attribute node."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            value_name = _FileVisitor._get_name(node.value)
            if value_name:
                return f"{value_name}.{node.attr}"
            return node.attr
        return None


# ============================================================================
# Repository-level Analyzer
# ============================================================================


class ASTAnalyzer:
    """
    Analyzes all Python files in a repository to produce an ArchitectureProfile
    and a StyleProfile.
    """

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self._visitors: List[_FileVisitor] = []
        self._file_count = 0
        self._total_lines = 0

    def analyze(self) -> Tuple[ArchitectureProfile, StyleProfile, List[StructuralFingerprint], int, int]:
        """
        Walk the repository and analyze all .py files.

        Returns:
            (architecture_profile, style_profile, fingerprints, file_count, total_lines)
        """
        py_files = self._collect_python_files()
        logger.info("Found %d Python files in %s", len(py_files), self.repo_path)

        for py_file in py_files:
            self._analyze_file(py_file)

        arch = self._build_architecture_profile()
        style = self._build_style_profile()
        fingerprints = self._collect_fingerprints()

        return arch, style, fingerprints, self._file_count, self._total_lines

    def _collect_python_files(self) -> List[Path]:
        """Collect .py files, excluding typical non-source directories."""
        excludes = {
            ".git", ".tox", ".mypy_cache", "__pycache__", ".pytest_cache",
            "node_modules", ".venv", "venv", "env", ".eggs", "dist", "build",
            ".nox", "migrations", "alembic",
        }
        result = []
        for py_file in self.repo_path.rglob("*.py"):
            parts = set(py_file.relative_to(self.repo_path).parts)
            if not parts.intersection(excludes):
                result.append(py_file)
        return sorted(result)

    def _analyze_file(self, filepath: Path) -> None:
        """Parse and visit a single Python file."""
        try:
            source = filepath.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError) as exc:
            logger.debug("Cannot read %s: %s", filepath, exc)
            return

        tree = _safe_parse(source, str(filepath))
        if tree is None:
            return

        lines = source.splitlines()
        self._file_count += 1
        self._total_lines += len(lines)

        rel_path = str(filepath.relative_to(self.repo_path))
        visitor = _FileVisitor(lines, rel_path)
        visitor.visit(tree)
        self._visitors.append(visitor)

    # ------------------------------------------------------------------
    # Architecture aggregation
    # ------------------------------------------------------------------

    def _build_architecture_profile(self) -> ArchitectureProfile:
        # DI
        total_funcs = sum(v.sync_functions + v.async_functions for v in self._visitors)
        total_di = sum(v.di_depends_count for v in self._visitors)
        di = DependencyInjectionProfile(
            uses_di=total_di > 0,
            di_style="fastapi_depends" if total_di > 0 else "none",
            di_density=total_di / max(total_funcs, 1),
        )

        # ORM
        orm_counts: Counter = Counter()
        raw_sql = 0
        for v in self._visitors:
            for k, count in v.orm_indicators.items():
                orm_counts[k] += count
            raw_sql += v.raw_sql_count

        detected_orm = orm_counts.most_common(1)[0][0] if orm_counts else None
        total_db = sum(orm_counts.values()) + raw_sql

        # Detect session style
        async_count = sum(v.async_functions for v in self._visitors)
        sync_count = sum(v.sync_functions for v in self._visitors)
        if async_count > 0 and sync_count > 0:
            session_style = "mixed"
        elif async_count > 0:
            session_style = "async"
        elif sync_count > 0:
            session_style = "sync"
        else:
            session_style = None

        orm = ORMProfile(
            orm_detected=detected_orm,
            uses_raw_sql=raw_sql > 0,
            raw_sql_density=raw_sql / max(total_db, 1),
            session_style=session_style,
            model_style="declarative" if detected_orm == "sqlalchemy" else None,
        )

        # Repository pattern
        layer_files = defaultdict(int)
        for v in self._visitors:
            filename_lower = v.filename.lower()
            if "router" in filename_lower:
                layer_files["router"] += 1
            if "service" in filename_lower:
                layer_files["service"] += 1
            if "repository" in filename_lower or "repo" in filename_lower:
                layer_files["repository"] += 1
            if "schema" in filename_lower or "model" in filename_lower:
                layer_files["model/schema"] += 1

        has_repo = layer_files.get("repository", 0) > 0
        has_service = layer_files.get("service", 0) > 0
        detected_layers = [k for k, count in layer_files.items() if count > 0]

        repo_pattern = RepositoryPatternProfile(
            uses_repository_pattern=has_repo,
            uses_service_layer=has_service,
            layer_separation="strict" if has_repo and has_service else ("loose" if has_service else "none"),
            detected_layers=detected_layers,
        )

        # Framework
        fw_counts: Counter = Counter()
        for v in self._visitors:
            for k, count in v.framework_indicators.items():
                if k != "uses_routers":
                    fw_counts[k] += count

        detected_fw = fw_counts.most_common(1)[0][0] if fw_counts else None
        uses_routers = any(v.framework_indicators.get("uses_routers", 0) > 0 for v in self._visitors)

        fw = FrameworkProfile(
            framework=detected_fw,
            uses_routers=uses_routers,
            uses_blueprints=detected_fw == "flask" and uses_routers,
        )

        # Named patterns
        named_patterns = []
        if di.uses_di:
            named_patterns.append("dependency_injection")
        if has_service:
            named_patterns.append("service_layer")
        if has_repo:
            named_patterns.append("repository")
        if uses_routers:
            named_patterns.append("router")
        # Detect factory pattern
        factory_funcs = sum(
            1 for v in self._visitors
            for name in v.function_names
            if name.startswith("create_") or name.startswith("make_") or name.endswith("_factory")
        )
        if factory_funcs >= 2:
            named_patterns.append("factory")

        # Detect singleton (@lru_cache on callables)
        # (rough heuristic via function names)
        singleton_funcs = sum(
            1 for v in self._visitors
            for name in v.function_names
            if name.startswith("get_") and name.endswith("s") is False
        )
        # Not reliable enough alone, skip

        return ArchitectureProfile(
            dependency_injection=di,
            orm=orm,
            repository_pattern=repo_pattern,
            framework=fw,
            detected_patterns=named_patterns,
        )

    # ------------------------------------------------------------------
    # Style aggregation
    # ------------------------------------------------------------------

    def _build_style_profile(self) -> StyleProfile:
        total_async = sum(v.async_functions for v in self._visitors)
        total_sync = sum(v.sync_functions for v in self._visitors)
        total_funcs = total_async + total_sync

        # Async
        async_prof = AsyncProfile(
            async_function_count=total_async,
            sync_function_count=total_sync,
            async_density=total_async / max(total_funcs, 1),
            uses_asyncio_gather=any(v.uses_asyncio_gather for v in self._visitors),
            uses_asyncio_create_task=any(v.uses_asyncio_create_task for v in self._visitors),
            uses_async_generators=any(v.uses_async_generators for v in self._visitors),
            uses_async_context_managers=any(v.uses_async_context_managers for v in self._visitors),
        )

        # Error handling
        total_try = sum(v.try_blocks for v in self._visitors)
        total_bare = sum(v.bare_excepts for v in self._visitors)
        total_typed = sum(v.typed_excepts for v in self._visitors)
        total_reraise = sum(v.reraise_count for v in self._visitors)
        total_except = sum(v.except_total for v in self._visitors)
        custom_exc = sum(v.custom_exception_classes for v in self._visitors)

        # Determine dominant logging style
        all_styles: Counter = Counter()
        for v in self._visitors:
            all_styles.update(v.except_logging_styles)
        dominant_style = all_styles.most_common(1)[0][0] if all_styles else None

        # Common caught exceptions
        all_caught: Counter = Counter()
        for v in self._visitors:
            all_caught.update(v.caught_exceptions)
        common_caught = [exc for exc, _ in all_caught.most_common(5)]

        err = ErrorHandlingProfile(
            total_try_blocks=total_try,
            bare_except_count=total_bare,
            typed_except_count=total_typed,
            exception_logging_style=dominant_style,
            uses_custom_exceptions=custom_exc > 0,
            custom_exception_count=custom_exc,
            reraise_ratio=total_reraise / max(total_except, 1),
            common_caught_exceptions=common_caught,
        )

        # Naming conventions
        all_func_names = [n for v in self._visitors for n in v.function_names if not n.startswith("__")]
        all_class_names = [n for v in self._visitors for n in v.class_names]
        all_var_names = [n for v in self._visitors for n in v.variable_names]
        all_const_names = [n for v in self._visitors for n in v.constant_names]

        func_casings = Counter(_classify_casing(n) for n in all_func_names) if all_func_names else Counter()
        class_casings = Counter(_classify_casing(n) for n in all_class_names) if all_class_names else Counter()
        var_casings = Counter(_classify_casing(n) for n in all_var_names) if all_var_names else Counter()
        const_casings = Counter(_classify_casing(n) for n in all_const_names) if all_const_names else Counter()

        # Type hints
        total_annotated = sum(v.annotated_params for v in self._visitors)
        total_params = sum(v.total_params for v in self._visitors)

        # Private prefix
        all_prefixes = set()
        for v in self._visitors:
            all_prefixes.update(v.private_prefixes)
        private_prefix = "__" if "__" in all_prefixes else ("_" if "_" in all_prefixes else "none")

        naming = NamingConventions(
            function_casing=func_casings.most_common(1)[0][0] if func_casings else "snake_case",
            class_casing=class_casings.most_common(1)[0][0] if class_casings else "PascalCase",
            variable_casing=var_casings.most_common(1)[0][0] if var_casings else "snake_case",
            constant_casing=const_casings.most_common(1)[0][0] if const_casings else "UPPER_SNAKE",
            private_prefix=private_prefix,
            uses_type_hints=total_annotated > 0,
            type_hint_density=total_annotated / max(total_params, 1),
        )

        # Imports
        all_imports: Counter = Counter()
        has_relative = False
        has_absolute = False
        for v in self._visitors:
            all_imports.update(v.imports)
            has_relative = has_relative or v.has_relative_imports
            has_absolute = has_absolute or v.has_absolute_imports

        total_imports = sum(len(v.imports) for v in self._visitors)
        avg_imports = total_imports / max(self._file_count, 1)
        top_pkgs = [pkg for pkg, _ in all_imports.most_common(10)]

        imports = ImportProfile(
            uses_absolute_imports=has_absolute,
            uses_relative_imports=has_relative,
            groups_imports=False,  # Would need token-level analysis
            average_imports_per_file=round(avg_imports, 1),
            top_packages=top_pkgs,
        )

        # Docstrings
        total_documented = sum(v.documented_functions for v in self._visitors)
        all_doc_styles: Counter = Counter()
        for v in self._visitors:
            all_doc_styles.update(v.docstring_styles)
        dominant_doc = all_doc_styles.most_common(1)[0][0] if all_doc_styles else "none"

        # Comment density
        total_comments = sum(v.comment_lines for v in self._visitors)

        docstrings = DocstringProfile(
            docstring_density=total_documented / max(total_funcs, 1),
            docstring_style=dominant_doc,
            uses_inline_comments=total_comments > 0,
            avg_comment_density=total_comments / max(self._total_lines, 1),
        )

        # Function/class lengths
        all_func_lengths = [l for v in self._visitors for l in v.function_lengths]
        all_class_lengths = [l for v in self._visitors for l in v.class_lengths]
        avg_func = sum(all_func_lengths) / max(len(all_func_lengths), 1)
        avg_class = sum(all_class_lengths) / max(len(all_class_lengths), 1)
        max_nesting = max((v.max_nesting for v in self._visitors), default=0)

        return StyleProfile(
            async_patterns=async_prof,
            error_handling=err,
            naming=naming,
            imports=imports,
            docstrings=docstrings,
            avg_function_length=round(avg_func, 1),
            avg_class_length=round(avg_class, 1),
            max_nesting_depth=max_nesting,
        )

    def _collect_fingerprints(self) -> List[StructuralFingerprint]:
        """Collect all structural fingerprints from all visited files."""
        return [fp for v in self._visitors for fp in v.fingerprints]
