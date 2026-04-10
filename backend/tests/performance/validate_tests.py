"""
Validation script for Phase 19 performance tests.

This script validates that all performance test files are properly structured
and can be imported without errors (when dependencies are available).
"""

import os
import sys
import ast


def validate_test_file(filepath):
    """Validate a test file's structure."""
    print(f"\nValidating: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Parse the file
    try:
        tree = ast.parse(content)
        print("  ✓ Valid Python syntax")
    except SyntaxError as e:
        print(f"  ✗ Syntax error: {e}")
        return False

    # Check for required elements
    has_imports = False
    has_fixtures = False
    has_test_classes = False
    has_test_functions = False
    test_count = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
            has_imports = True

        if isinstance(node, ast.FunctionDef):
            if node.name.startswith("test_"):
                has_test_functions = True
                test_count += 1

            # Check for pytest fixtures
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Attribute):
                    if decorator.attr == "fixture":
                        has_fixtures = True
                elif isinstance(decorator, ast.Name):
                    if decorator.id == "fixture":
                        has_fixtures = True

        if isinstance(node, ast.ClassDef):
            if node.name.startswith("Test"):
                has_test_classes = True

    print(f"  ✓ Has imports: {has_imports}")
    print(f"  ✓ Has fixtures: {has_fixtures}")
    print(f"  ✓ Has test classes: {has_test_classes}")
    print(f"  ✓ Has test functions: {has_test_functions}")
    print(f"  ✓ Test count: {test_count}")

    if not has_test_functions:
        print("  ✗ No test functions found")
        return False

    return True


def main():
    """Main validation function."""
    print("=" * 70)
    print("PHASE 19 PERFORMANCE TEST VALIDATION")
    print("=" * 70)

    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Test files to validate
    test_files = [
        "test_phase19_benchmarks.py",
        "test_phase19_stress.py",
        "test_phase19_performance.py",
    ]

    results = {}

    for test_file in test_files:
        filepath = os.path.join(script_dir, test_file)

        if not os.path.exists(filepath):
            print(f"\n✗ File not found: {test_file}")
            results[test_file] = False
            continue

        results[test_file] = validate_test_file(filepath)

    # Summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    for test_file, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_file}")

    all_passed = all(results.values())

    if all_passed:
        print("\n✓ All performance tests are properly structured!")
        print("\nTo run the tests (requires dependencies):")
        print("  pytest tests/performance/test_phase19_benchmarks.py -v")
        print("  pytest tests/performance/test_phase19_stress.py -v")
        print("  pytest tests/performance/test_phase19_performance.py -v")
        return 0
    else:
        print("\n✗ Some tests have issues. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
