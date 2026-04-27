#!/usr/bin/env python3
"""
Verification script for ingestion pipeline fixes (2026-04-27).

Checks:
1. Path exclusions are properly configured
2. Staleness tracking columns exist in database
3. AST density gate settings are configured
4. Search queries include staleness filter
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))


def check_path_exclusions():
    """Verify path exclusions are configured."""
    print("✓ Checking path exclusions...")
    
    try:
        from app.utils.path_exclusions import EXCLUDE_DIRS, EXCLUDE_FILE_SUFFIXES, EXCLUDE_FILENAMES
        
        # Check key exclusions
        assert "migrations" in EXCLUDE_DIRS, "migrations/ not in EXCLUDE_DIRS"
        assert "alembic" in EXCLUDE_DIRS, "alembic/ not in EXCLUDE_DIRS"
        assert "__generated__" in EXCLUDE_DIRS, "__generated__/ not in EXCLUDE_DIRS"
        
        assert any("*.lock" in s or ".lock" in s for s in EXCLUDE_FILE_SUFFIXES), "*.lock not in patterns"
        assert any(".min.js" in s for s in EXCLUDE_FILE_SUFFIXES), "*.min.js not in patterns"
        assert any("_pb2.py" in s for s in EXCLUDE_FILE_SUFFIXES), "*_pb2.py not in patterns"
        
        print(f"  ✅ Path exclusions configured: {len(EXCLUDE_DIRS)} dirs, {len(EXCLUDE_FILE_SUFFIXES)} suffixes, {len(EXCLUDE_FILENAMES)} filenames")
        return True
    except Exception as e:
        print(f"  ❌ Path exclusions check failed: {e}")
        return False


def check_staleness_columns():
    """Verify staleness tracking columns exist in Resource model."""
    print("✓ Checking staleness tracking columns...")
    
    try:
        from app.database.models import Resource
        from sqlalchemy import inspect
        
        # Check that columns are defined
        mapper = inspect(Resource)
        columns = {col.key for col in mapper.columns}
        
        assert "is_stale" in columns, "is_stale column not found"
        assert "last_indexed_sha" in columns, "last_indexed_sha column not found"
        assert "last_indexed_at" in columns, "last_indexed_at column not found"
        
        print(f"  ✅ Staleness columns exist: is_stale, last_indexed_sha, last_indexed_at")
        return True
    except Exception as e:
        print(f"  ❌ Staleness columns check failed: {e}")
        return False


def check_staleness_helpers():
    """Verify staleness helper functions exist."""
    print("✓ Checking staleness helper functions...")
    
    try:
        from app.modules.resources.logic.staleness import (
            mark_repo_stale_by_sha,
            mark_resources_fresh,
        )
        
        print(f"  ✅ Staleness helpers exist: mark_repo_stale_by_sha, mark_resources_fresh")
        return True
    except Exception as e:
        print(f"  ❌ Staleness helpers check failed: {e}")
        return False


def check_ast_density_settings():
    """Verify AST density gate settings are configured."""
    print("✓ Checking AST density gate settings...")
    
    try:
        from app.config.settings import Settings
        
        settings = Settings()
        
        assert hasattr(settings, "FEEDBACK_MIN_CONTROL_FLOW_NODES"), "FEEDBACK_MIN_CONTROL_FLOW_NODES not found"
        assert hasattr(settings, "FEEDBACK_MIN_AST_DENSITY"), "FEEDBACK_MIN_AST_DENSITY not found"
        
        min_nodes = settings.FEEDBACK_MIN_CONTROL_FLOW_NODES
        min_density = settings.FEEDBACK_MIN_AST_DENSITY
        
        print(f"  ✅ AST density settings: min_nodes={min_nodes}, min_density={min_density}")
        return True
    except Exception as e:
        print(f"  ❌ AST density settings check failed: {e}")
        return False


def check_search_filters():
    """Verify search queries include staleness filter."""
    print("✓ Checking search staleness filters...")
    
    try:
        # Check service.py
        service_path = Path(__file__).parent / "app" / "modules" / "search" / "service.py"
        service_code = service_path.read_text()
        
        assert "(r.is_stale IS NULL OR r.is_stale = FALSE)" in service_code, \
            "Staleness filter not found in service.py"
        
        # Check vector_search_real.py
        vector_path = Path(__file__).parent / "app" / "modules" / "search" / "vector_search_real.py"
        vector_code = vector_path.read_text()
        
        assert "(r.is_stale IS NULL OR r.is_stale = FALSE)" in vector_code, \
            "Staleness filter not found in vector_search_real.py"
        
        print(f"  ✅ Search filters include staleness check")
        return True
    except Exception as e:
        print(f"  ❌ Search filters check failed: {e}")
        return False


def check_ingestion_integration():
    """Verify staleness tracking is integrated into ingestion pipeline."""
    print("✓ Checking ingestion pipeline integration...")
    
    try:
        ast_pipeline_path = Path(__file__).parent / "app" / "modules" / "ingestion" / "ast_pipeline.py"
        ast_code = ast_pipeline_path.read_text(encoding="utf-8")
        
        assert "mark_repo_stale_by_sha" in ast_code, "mark_repo_stale_by_sha not called in ast_pipeline.py"
        assert "mark_resources_fresh" in ast_code, "mark_resources_fresh not called in ast_pipeline.py"
        assert "resource_ids" in ast_code, "resource_ids tracking not found in ast_pipeline.py"
        
        print(f"  ✅ Staleness tracking integrated into ingestion pipeline")
        return True
    except Exception as e:
        print(f"  ❌ Ingestion integration check failed: {e}")
        return False


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("Ingestion Pipeline Fixes Verification (2026-04-27)")
    print("=" * 60)
    print()
    
    checks = [
        ("Path Exclusions", check_path_exclusions),
        ("Staleness Columns", check_staleness_columns),
        ("Staleness Helpers", check_staleness_helpers),
        ("AST Density Settings", check_ast_density_settings),
        ("Search Filters", check_search_filters),
        ("Ingestion Integration", check_ingestion_integration),
    ]
    
    results = []
    for name, check_fn in checks:
        try:
            result = check_fn()
            results.append((name, result))
        except Exception as e:
            print(f"  ❌ Unexpected error in {name}: {e}")
            results.append((name, False))
        print()
    
    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print()
    print(f"Total: {passed}/{total} checks passed")
    
    if passed == total:
        print()
        print("🎉 All checks passed! Ingestion fixes are properly configured.")
        return 0
    else:
        print()
        print("⚠️  Some checks failed. Review the output above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
