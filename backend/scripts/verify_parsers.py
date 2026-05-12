"""Verify tree-sitter language bindings for Pharos polyglot AST.

Run on the edge worker before re-ingest; exits non-zero with a single
pip-install command if anything is missing. Bindings are pure-Python
wrappers around precompiled C, so this is a <1s check.

Usage (WSL/edge):
    python backend/scripts/verify_parsers.py
"""
from __future__ import annotations

import importlib
import sys
from typing import List, Tuple

REQUIRED: List[Tuple[str, str]] = [
    ("tree_sitter",            "tree-sitter"),
    ("tree_sitter_go",         "tree-sitter-go"),
    ("tree_sitter_rust",       "tree-sitter-rust"),
    ("tree_sitter_c",          "tree-sitter-c"),
    ("tree_sitter_cpp",        "tree-sitter-cpp"),
    ("tree_sitter_typescript", "tree-sitter-typescript"),
    ("tree_sitter_javascript", "tree-sitter-javascript"),
]


def main() -> int:
    missing: List[str] = []
    ok: List[str] = []
    for mod, dist in REQUIRED:
        try:
            importlib.import_module(mod)
            ok.append(mod)
        except ImportError:
            missing.append(dist)

    for mod in ok:
        print(f"  OK   {mod}")
    for dist in missing:
        print(f"  MISS {dist}")

    if missing:
        print("\nInstall the missing bindings with:\n")
        print(f"  pip install {' '.join(missing)}\n")
        return 1

    print(f"\nAll {len(REQUIRED)} parsers importable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
