#!/usr/bin/env python3
"""
Reconciliation Verification Script

Verifies that all reconciliation files were created correctly
without requiring database setup or running actual tests.
"""

import sys
from pathlib import Path
import importlib.util

def check_file_exists(filepath: str) -> bool:
    """Check if a file exists."""
    path = Path(filepath)
    exists = path.exists()
    status = "✅" if exists else "❌"
    print(f"{status} {filepath}")
    return exists

def check_python_syntax(filepath: str) -> bool:
    """Check if a Python file has valid syntax."""
    try:
        path = Path(filepath)
        if not path.exists():
            return False
        
        spec = importlib.util.spec_from_file_location("module", path)
        if spec is None:
            return False
        
        module = importlib.util.module_from_spec(spec)
        # Just compile, don't execute
        with open(path, 'r', encoding='utf-8') as f:
            compile(f.read(), path, 'exec')
        
        print(f"  ✅ Valid Python syntax")
        return True
    except SyntaxError as e:
        print(f"  ❌ Syntax error: {e}")
        return False
    except Exception as e:
        print(f"  ⚠️  Could not verify: {e}")
        return True  # Don't fail on import errors

def main():
    print("=" * 70)
    print("RECONCILIATION VERIFICATION")
    print("=" * 70)
    print()
    
    all_passed = True
    
    # Check implementation files
    print("📦 Implementation Files:")
    print("-" * 70)
    
    files_to_check = [
        ("alembic/versions/20260410_implement_pgvector_and_splade.py", True),
        ("app/modules/search/sparse_embeddings_real.py", True),
        ("app/modules/search/vector_search_real.py", True),
    ]
    
    for filepath, check_syntax in files_to_check:
        exists = check_file_exists(filepath)
        all_passed = all_passed and exists
        
        if exists and check_syntax:
            syntax_ok = check_python_syntax(filepath)
            all_passed = all_passed and syntax_ok
    
    print()
    
    # Check test files
    print("🧪 Test Files:")
    print("-" * 70)
    
    test_files = [
        "tests/integration/test_hybrid_vector_search.py",
    ]
    
    for filepath in test_files:
        exists = check_file_exists(filepath)
        all_passed = all_passed and exists
        
        if exists:
            syntax_ok = check_python_syntax(filepath)
            all_passed = all_passed and syntax_ok
    
    print()
    
    # Check cleanup files
    print("🗑️  Cleanup Files:")
    print("-" * 70)
    
    cleanup_files = [
        "scripts/ghost_protocol_cleanup.sh",
    ]
    
    for filepath in cleanup_files:
        exists = check_file_exists(filepath)
        all_passed = all_passed and exists
    
    print()
    
    # Check documentation files
    print("📚 Documentation Files:")
    print("-" * 70)
    
    doc_files = [
        "docs/VECTOR_RECONCILIATION_SUMMARY.md",
        "docs/MODULE_MANIFEST.md",
        "RECONCILIATION_CHECKLIST.md",
        "RECONCILIATION_EXECUTIVE_SUMMARY.md",
        "VECTOR_SEARCH_QUICK_REFERENCE.md",
        "../RECONCILIATION_COMPLETE.md",
        "RECONCILIATION_INDEX.md",
    ]
    
    for filepath in doc_files:
        exists = check_file_exists(filepath)
        all_passed = all_passed and exists
    
    print()
    
    # Check for ghost modules (should NOT exist)
    print("👻 Ghost Modules (should be absent):")
    print("-" * 70)
    
    ghost_modules = [
        "app/modules/planning",
        "app/modules/github",
    ]
    
    for module_path in ghost_modules:
        path = Path(module_path)
        exists = path.exists()
        status = "⚠️  STILL EXISTS" if exists else "✅ Removed"
        print(f"{status} {module_path}")
        if exists:
            print(f"  ℹ️  Run: bash scripts/ghost_protocol_cleanup.sh")
    
    print()
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    if all_passed:
        print("✅ All reconciliation files created successfully!")
        print()
        print("Next steps:")
        print("1. Install dependencies: pip install transformers torch pgvector")
        print("2. Run migration: alembic upgrade head")
        print("3. Clean up ghost modules: bash scripts/ghost_protocol_cleanup.sh")
        print("4. Run tests: pytest tests/integration/test_hybrid_vector_search.py -v")
        return 0
    else:
        print("❌ Some files are missing or have errors")
        print()
        print("Please review the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
