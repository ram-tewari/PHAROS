#!/usr/bin/env python3
"""
Module Isolation Checker

This script validates that modules follow the vertical slice architecture rules:
1. Modules can only import from the shared kernel (app.shared)
2. Modules cannot directly import from other modules
3. No circular dependencies exist
4. Cross-module communication must use events

Checks all 11 modules:
- admin, github, graph, ingestion, mcp, monitoring
- patterns, pdf_ingestion, planning, resources, search

Usage:
    python scripts/check_module_isolation.py
    python scripts/check_module_isolation.py --verbose
    python scripts/check_module_isolation.py --graph
    python scripts/check_module_isolation.py --export-graph graph.txt
"""

import ast
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict
import argparse


class ImportVisitor(ast.NodeVisitor):
    """Collect absolute import paths, resolving relative imports.

    ``package`` is the dotted package of the file being visited (for
    ``app/modules/mcp/router.py`` that is ``app.modules.mcp``). Resolving
    ``from ..graph.service import X`` to ``app.modules.graph.service`` matters:
    the previous version ignored relative imports entirely, so cross-module
    imports written relatively were never reported.
    """

    def __init__(self, package: str = ""):
        self.package = package
        self.imports: List[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.level:
            base = self.package.split(".") if self.package else []
            if node.level > 1:
                base = base[: len(base) - (node.level - 1)]
            target = ".".join(base + ([node.module] if node.module else []))
            if node.module is None:
                # "from .. import a, b": each name may be a module.
                self.imports.extend(f"{target}.{a.name}" for a in node.names)
            else:
                self.imports.append(target)
        elif node.module:
            self.imports.append(node.module)
        self.generic_visit(node)


# Cross-module imports that existed when relative imports started being
# checked (2026-10). They are reported but do not fail the check; any NEW
# cross-module import does. An entry that no longer occurs also fails, so
# this list can only shrink. Remove entries as the coupling is untangled.
KNOWN_VIOLATIONS: Dict[Tuple[str, str], str] = {
    ("mcp", "search"): "legacy REST tool registry (mcp/tools.py) wraps search handlers",
    ("mcp", "graph"): "legacy REST tool registry (mcp/tools.py) wraps graph handlers",
    ("mcp", "planning"): "legacy REST tool registry (mcp/tools.py) wraps planning handlers",
    ("mcp", "resources"): "legacy REST tool registry (mcp/tools.py) wraps resource handlers",
    ("resources", "search"): "legacy URL-ingestion pipeline calls search indexing helpers",
    ("search", "resources"): "legacy search router/schemas reuse resource schemas (cycle)",
}


class ModuleIsolationChecker:
    """Checks module isolation rules for vertical slice architecture."""

    # Expected modules in the system
    EXPECTED_MODULES = {
        "admin",
        "code",
        "github",
        "graph",
        "mcp",
        "monitoring",
        "patterns",
        "pdf_ingestion",
        "planning",
        "resources",
        "search",
    }

    def __init__(self, app_root: Path, verbose: bool = False):
        self.app_root = app_root
        self.modules_root = app_root / "modules"
        self.shared_root = app_root / "shared"
        self.verbose = verbose

        # Track violations
        self.direct_imports: List[
            Tuple[str, str, str]
        ] = []  # (from_module, to_module, file)
        self.circular_deps: List[List[str]] = []
        self.non_shared_imports: List[
            Tuple[str, str, str]
        ] = []  # (module, import, file)

        # Dependency graph
        self.dependencies: Dict[str, Set[str]] = defaultdict(set)

        # Track discovered modules
        self.discovered_modules: Set[str] = set()

    def log(self, message: str):
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(f"[DEBUG] {message}")

    def get_module_name(self, file_path: Path) -> str:
        """Extract module name from file path."""
        try:
            relative = file_path.relative_to(self.modules_root)
            parts = relative.parts
            if parts:
                return parts[0]
        except ValueError:
            pass
        return ""

    def is_module_import(self, import_path: str) -> Tuple[bool, str]:
        """
        Check if an import is from a module.
        Returns (is_module_import, module_name)
        """
        # Check for app.modules.X imports
        if import_path.startswith("app.modules."):
            parts = import_path.split(".")
            if len(parts) >= 3:
                return True, parts[2]

        # Check for relative imports within modules
        if import_path.startswith("modules."):
            parts = import_path.split(".")
            if len(parts) >= 2:
                return True, parts[1]

        return False, ""

    def is_shared_import(self, import_path: str) -> bool:
        """Check if an import is from the shared kernel."""
        # app.codeintel is a framework-free library consumed by modules, like
        # the shared kernel.
        return import_path.startswith(("app.shared", "shared.", "app.codeintel"))

    def extract_imports(self, file_path: Path) -> List[str]:
        """Extract all imports from a Python file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content, filename=str(file_path))
            rel = file_path.relative_to(self.app_root.parent).with_suffix("")
            parts = list(rel.parts)
            package_parts = parts[:-1] if parts[-1] != "__init__" else parts[:-1]
            visitor = ImportVisitor(".".join(package_parts))
            visitor.visit(tree)
            return visitor.imports
        except SyntaxError as e:
            self.log(f"Syntax error in {file_path}: {e}")
            return []
        except Exception as e:
            self.log(f"Error parsing {file_path}: {e}")
            return []

    def check_file(self, file_path: Path):
        """Check a single Python file for isolation violations."""
        module_name = self.get_module_name(file_path)
        if not module_name:
            return

        # Track discovered module
        self.discovered_modules.add(module_name)

        self.log(f"Checking {file_path}")

        imports = self.extract_imports(file_path)

        for import_path in imports:
            # Check if it's a module import
            is_module, target_module = self.is_module_import(import_path)

            if is_module:
                # Shared kernel imports are allowed
                if self.is_shared_import(import_path):
                    self.log(f"  ✓ Allowed shared import: {import_path}")
                    continue

                # Self-imports are allowed
                if target_module == module_name:
                    self.log(f"  ✓ Self import: {import_path}")
                    continue

                # Direct import from another module - VIOLATION
                self.log(f"  ✗ Direct module import: {import_path}")
                self.direct_imports.append(
                    (
                        module_name,
                        target_module,
                        str(file_path.relative_to(self.app_root)),
                    )
                )

                # Track dependency for circular detection
                self.dependencies[module_name].add(target_module)

            # Check for non-shared kernel imports from app.*
            elif import_path.startswith("app.") and not self.is_shared_import(
                import_path
            ):
                # Allow imports from app.database.models (shared models)
                if import_path.startswith("app.database.models"):
                    self.log(f"  ✓ Allowed database models import: {import_path}")
                    continue

                # Allow imports from app.events (event system)
                if import_path.startswith("app.events"):
                    self.log(f"  ✓ Allowed events import: {import_path}")
                    continue

                # Allow imports from app.config (configuration)
                if import_path.startswith("app.config"):
                    self.log(f"  ✓ Allowed config import: {import_path}")
                    continue

                # Check if it's importing from old structure (routers, services, schemas)
                if any(
                    part in import_path
                    for part in [".routers.", ".services.", ".schemas."]
                ):
                    self.log(f"  ⚠ Legacy import detected: {import_path}")
                    self.non_shared_imports.append(
                        (
                            module_name,
                            import_path,
                            str(file_path.relative_to(self.app_root)),
                        )
                    )

    def check_all_modules(self):
        """Check all modules for isolation violations."""
        if not self.modules_root.exists():
            print(f"Error: Modules directory not found: {self.modules_root}")
            sys.exit(1)

        # Find all Python files in modules
        python_files = list(self.modules_root.rglob("*.py"))

        self.log(f"Found {len(python_files)} Python files in modules")

        for file_path in python_files:
            # Skip __pycache__ and test files
            if "__pycache__" in str(file_path) or "test_" in file_path.name:
                continue

            self.check_file(file_path)

    def detect_circular_dependencies(self):
        """Find cycles in the module dependency graph (three-colour DFS)."""
        WHITE, GRAY, BLACK = 0, 1, 2
        colour: Dict[str, int] = defaultdict(int)
        seen_cycles: Set[Tuple[str, ...]] = set()

        def dfs(node: str, path: List[str]) -> None:
            colour[node] = GRAY
            path.append(node)
            for neighbor in sorted(self.dependencies.get(node, ())):
                if colour[neighbor] == GRAY:
                    cycle = path[path.index(neighbor):] + [neighbor]
                    key = tuple(sorted(set(cycle)))
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        self.circular_deps.append(cycle)
                elif colour[neighbor] == WHITE:
                    dfs(neighbor, path)
            path.pop()
            colour[node] = BLACK

        for module in sorted(self.dependencies):
            if colour[module] == WHITE:
                dfs(module, [])

    def generate_dependency_graph(self) -> str:
        """Generate a text representation of the dependency graph."""
        if not self.dependencies:
            return "No dependencies found."

        lines = ["Module Dependency Graph:", "=" * 50]

        # Show all discovered modules
        lines.append(f"\nDiscovered Modules ({len(self.discovered_modules)}):")
        for module in sorted(self.discovered_modules):
            lines.append(f"  • {module}")

        # Show dependencies
        lines.append("\nModule Dependencies:")
        for module, deps in sorted(self.dependencies.items()):
            if deps:
                lines.append(f"\n{module}:")
                for dep in sorted(deps):
                    lines.append(f"  → {dep}")

        # Show modules with no dependencies
        no_deps = self.discovered_modules - set(self.dependencies.keys())
        if no_deps:
            lines.append("\nModules with no dependencies:")
            for module in sorted(no_deps):
                lines.append(f"  • {module}")

        return "\n".join(lines)

    def export_dependency_graph(self, output_file: Path):
        """Export dependency graph to a file."""
        graph_text = self.generate_dependency_graph()

        # Add DOT format for visualization tools
        dot_lines = ["", "", "DOT Format (for Graphviz):", "=" * 50, ""]
        dot_lines.append("digraph ModuleDependencies {")
        dot_lines.append("  rankdir=LR;")
        dot_lines.append("  node [shape=box, style=rounded];")
        dot_lines.append("")

        # Add all modules as nodes
        for module in sorted(self.discovered_modules):
            dot_lines.append(f'  "{module}";')

        dot_lines.append("")

        # Add dependencies as edges
        for module, deps in sorted(self.dependencies.items()):
            for dep in sorted(deps):
                dot_lines.append(f'  "{module}" -> "{dep}";')

        dot_lines.append("}")

        full_output = graph_text + "\n" + "\n".join(dot_lines)

        with open(output_file, "w") as f:
            f.write(full_output)

        print(f"\n✓ Dependency graph exported to: {output_file}")
        print(f"  To visualize: dot -Tpng {output_file} -o graph.png")

    def print_report(self, show_graph: bool = False):
        """Print the isolation check report."""
        print("\n" + "=" * 70)
        print("MODULE ISOLATION CHECK REPORT")
        print("=" * 70)

        # Module discovery
        print(f"\n📦 DISCOVERED MODULES: {len(self.discovered_modules)}")
        print("-" * 70)

        missing_modules = self.EXPECTED_MODULES - self.discovered_modules
        extra_modules = self.discovered_modules - self.EXPECTED_MODULES

        if self.discovered_modules == self.EXPECTED_MODULES:
            print("✅ All expected modules found")
            for module in sorted(self.discovered_modules):
                print(f"  • {module}")
        else:
            print("Found modules:")
            for module in sorted(self.discovered_modules):
                marker = "✓" if module in self.EXPECTED_MODULES else "?"
                print(f"  {marker} {module}")

            if missing_modules:
                print(
                    f"\n⚠ Missing expected modules: {', '.join(sorted(missing_modules))}"
                )

            if extra_modules:
                print(f"\n⚠ Unexpected modules: {', '.join(sorted(extra_modules))}")

        # Direct import violations
        if self.direct_imports:
            print(f"\n❌ DIRECT IMPORT VIOLATIONS: {len(self.direct_imports)}")
            print("-" * 70)

            # Group by source module
            by_module = defaultdict(list)
            for from_mod, to_mod, file in self.direct_imports:
                by_module[from_mod].append((to_mod, file))

            for from_mod, violations in sorted(by_module.items()):
                print(f"\nModule '{from_mod}' imports from:")
                for to_mod, file in violations:
                    print(f"  → {to_mod} (in {file})")
        else:
            print("\n✅ NO DIRECT IMPORT VIOLATIONS")

        # Legacy imports
        if self.non_shared_imports:
            print(f"\n⚠ LEGACY IMPORTS DETECTED: {len(self.non_shared_imports)}")
            print("-" * 70)

            by_module = defaultdict(list)
            for module, import_path, file in self.non_shared_imports:
                by_module[module].append((import_path, file))

            for module, imports in sorted(by_module.items()):
                print(f"\nModule '{module}' has legacy imports:")
                for import_path, file in imports:
                    print(f"  → {import_path} (in {file})")

        # Circular dependencies
        if self.circular_deps:
            print(f"\n❌ CIRCULAR DEPENDENCIES: {len(self.circular_deps)}")
            print("-" * 70)
            for i, cycle in enumerate(self.circular_deps, 1):
                print(f"\nCycle {i}: {' → '.join(cycle)}")
        else:
            print("\n✅ NO CIRCULAR DEPENDENCIES")

        # Dependency graph
        if show_graph:
            print("\n" + "=" * 70)
            print(self.generate_dependency_graph())

        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(
            f"Modules discovered: {len(self.discovered_modules)}/{len(self.EXPECTED_MODULES)}"
        )
        print(f"Direct import violations: {len(self.direct_imports)}")
        print(f"Legacy imports: {len(self.non_shared_imports)}")
        print(f"Circular dependencies: {len(self.circular_deps)}")

        new_violations = [v for v in self.direct_imports if (v[0], v[1]) not in KNOWN_VIOLATIONS]
        seen_pairs = {(v[0], v[1]) for v in self.direct_imports}
        stale = sorted(set(KNOWN_VIOLATIONS) - seen_pairs)
        new_cycles = [
            c for c in self.circular_deps
            if not all((a, b) in KNOWN_VIOLATIONS for a, b in zip(c, c[1:]))
        ]
        if self.direct_imports:
            print(f"Known (allowlisted) cross-module imports: {len(self.direct_imports) - len(new_violations)}")
        if stale:
            print("\n❌ STALE ALLOWLIST ENTRIES (remove from KNOWN_VIOLATIONS):")
            for a, b in stale:
                print(f"  {a} → {b}")
        total_violations = len(new_violations) + len(new_cycles) + len(stale)

        if total_violations == 0 and not missing_modules:
            known = len(self.direct_imports)
            if known:
                print(f"\n✅ NO NEW VIOLATIONS ({known} known cross-module imports allowlisted in KNOWN_VIOLATIONS)")
            else:
                print("\n✅ ALL CHECKS PASSED - Modules are properly isolated!")
            if self.non_shared_imports:
                print("⚠ Note: Legacy imports detected but not blocking")
            return 0
        else:
            print(f"\n❌ FAILED - {total_violations} violation(s) found")
            if missing_modules:
                print(f"⚠ Missing modules: {', '.join(sorted(missing_modules))}")
            print("\nModules must communicate through events, not direct imports.")
            print("Allowed imports: app.shared.* (shared kernel only)")
            return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check module isolation for vertical slice architecture"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--graph", "-g", action="store_true", help="Show dependency graph"
    )
    parser.add_argument(
        "--export-graph",
        type=Path,
        metavar="FILE",
        help="Export dependency graph to file (includes DOT format)",
    )
    parser.add_argument(
        "--app-root",
        type=Path,
        default=Path(__file__).parent.parent / "app",
        help="Path to app root directory (default: ../app)",
    )

    args = parser.parse_args()

    # Resolve app root
    app_root = args.app_root.resolve()

    if not app_root.exists():
        print(f"Error: App root not found: {app_root}")
        sys.exit(1)

    print(f"Checking module isolation in: {app_root}")
    print(
        f"Expected modules: {', '.join(sorted(ModuleIsolationChecker.EXPECTED_MODULES))}"
    )

    # Run checker
    checker = ModuleIsolationChecker(app_root, verbose=args.verbose)
    checker.check_all_modules()
    checker.detect_circular_dependencies()

    # Export graph if requested
    if args.export_graph:
        checker.export_dependency_graph(args.export_graph)

    # Print report and exit with appropriate code
    exit_code = checker.print_report(show_graph=args.graph)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
