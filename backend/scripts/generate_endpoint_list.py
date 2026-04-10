#!/usr/bin/env python3
"""
Generate complete endpoint list from actual code.

This script extracts all endpoints from router files and generates
a comprehensive list with their full paths, methods, and descriptions.
"""

import re
from pathlib import Path
from typing import List, Tuple


def extract_router_prefix(router_file: Path) -> str:
    """Extract router prefix from router file."""
    with open(router_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Find APIRouter(prefix="...")
    match = re.search(r'APIRouter\(prefix=["\']([^"\']*)["\']', content)
    if match:
        return match.group(1)
    return ""


def extract_endpoints(
    router_file: Path, prefix: str
) -> List[Tuple[str, str, str, str]]:
    """Extract all endpoints from a router file."""
    with open(router_file, "r", encoding="utf-8") as f:
        content = f.read()

    endpoints = []

    # Find all @router.method("path") decorators
    pattern = r'@router\.(get|post|put|delete|patch)\(["\']([^"\']*)["\']'
    matches = re.finditer(pattern, content, re.IGNORECASE)

    for match in matches:
        method = match.group(1).upper()
        path = match.group(2)

        # Build full path
        full_path = f"{prefix}{path}" if prefix else path

        # Try to extract summary from next lines
        start_pos = match.end()
        next_lines = content[start_pos : start_pos + 500]

        # Look for summary= or description= in decorator
        summary_match = re.search(r'summary=["\']([^"\']+)["\']', next_lines)
        desc_match = re.search(r'description=["\']([^"\']+)["\']', next_lines)

        summary = summary_match.group(1) if summary_match else ""
        description = desc_match.group(1) if desc_match else ""

        # If no summary in decorator, try to get from docstring
        if not summary:
            func_match = re.search(r"def\s+(\w+)\s*\(", next_lines)
            if func_match:
                func_name = func_match.group(1)
                # Look for docstring
                docstring_match = re.search(r'"""([^"]+)"""', next_lines)
                if docstring_match:
                    summary = docstring_match.group(1).split("\n")[0].strip()

        endpoints.append((method, full_path, summary, description))

    return endpoints


def main():
    """Generate endpoint list."""
    backend_dir = Path(__file__).parent.parent
    modules_dir = backend_dir / "app" / "modules"

    print("# Neo Alexandria 2.0 - Complete API Endpoint List")
    print()
    print("Generated from actual router code.")
    print()

    # Find all router files
    router_files = sorted(modules_dir.glob("*/router.py"))

    total_endpoints = 0

    for router_file in router_files:
        module_name = router_file.parent.name
        prefix = extract_router_prefix(router_file)
        endpoints = extract_endpoints(router_file, prefix)

        if endpoints:
            print(f"## {module_name.title()} Module")
            print()
            print(f"**Router Prefix**: `{prefix or '(none)'}`")
            print(f"**Endpoints**: {len(endpoints)}")
            print()

            for method, path, summary, description in endpoints:
                print(f"### {method} {path}")
                if summary:
                    print(f"{summary}")
                if description and description != summary:
                    print(f"\n{description}")
                print()

            total_endpoints += len(endpoints)
            print("---")
            print()

    # Also check ingestion router
    ingestion_router = backend_dir / "app" / "routers" / "ingestion.py"
    if ingestion_router.exists():
        prefix = "/api/v1/ingestion"
        endpoints = extract_endpoints(ingestion_router, prefix)

        if endpoints:
            print(f"## Ingestion Module (Cloud API)")
            print()
            print(f"**Router Prefix**: `{prefix}`")
            print(f"**Endpoints**: {len(endpoints)}")
            print()

            for method, path, summary, description in endpoints:
                print(f"### {method} {path}")
                if summary:
                    print(f"{summary}")
                if description and description != summary:
                    print(f"\n{description}")
                print()

            total_endpoints += len(endpoints)

    print("---")
    print()
    print(f"**Total Endpoints**: {total_endpoints}")


if __name__ == "__main__":
    main()
