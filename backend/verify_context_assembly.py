#!/usr/bin/env python3
"""
Verification Script for Context Assembly Pipeline

Checks that all components are properly integrated and ready for Phase 5.

Usage:
    python verify_context_assembly.py
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))


def check_imports():
    """Check that all modules can be imported"""
    print("=" * 60)
    print("CHECKING IMPORTS")
    print("=" * 60)

    checks = []

    # Check context schema
    try:
        from app.modules.mcp.context_schema import (
            AssembledContext,
            CodeChunk,
            ContextAssemblyMetrics,
            ContextRetrievalRequest,
            ContextRetrievalResponse,
            DeveloperPattern,
            format_context_for_llm,
            GraphDependency,
            PDFAnnotation,
        )

        checks.append(("✅", "context_schema.py imports successfully"))
    except Exception as e:
        checks.append(("❌", f"context_schema.py import failed: {e}"))

    # Check context service
    try:
        from app.modules.mcp.context_service import ContextAssemblyService

        checks.append(("✅", "context_service.py imports successfully"))
    except Exception as e:
        checks.append(("❌", f"context_service.py import failed: {e}"))

    # Check router updates
    try:
        from app.modules.mcp.router import router, mcp_router

        checks.append(("✅", "router.py imports successfully"))
    except Exception as e:
        checks.append(("❌", f"router.py import failed: {e}"))

    # Print results
    for status, message in checks:
        print(f"{status} {message}")

    return all(status == "✅" for status, _ in checks)


def check_schemas():
    """Check Pydantic schema validation"""
    print("\n" + "=" * 60)
    print("CHECKING SCHEMAS")
    print("=" * 60)

    checks = []

    try:
        from app.modules.mcp.context_schema import (
            CodeChunk,
            ContextRetrievalRequest,
            DeveloperPattern,
            GraphDependency,
            PDFAnnotation,
        )

        # Test request schema
        request = ContextRetrievalRequest(
            query="Test query", codebase="test-repo", max_code_chunks=10
        )
        checks.append(("✅", "ContextRetrievalRequest validation works"))

        # Test code chunk schema
        chunk = CodeChunk(
            chunk_id="test",
            content="code",
            file_path="test.py",
            language="python",
            start_line=1,
            end_line=10,
            similarity_score=0.95,
        )
        checks.append(("✅", "CodeChunk validation works"))

        # Test graph dependency schema
        dep = GraphDependency(
            source_chunk_id="chunk1",
            target_chunk_id="chunk2",
            relationship_type="imports",
            weight=0.8,
            hops=1,
        )
        checks.append(("✅", "GraphDependency validation works"))

        # Test developer pattern schema
        pattern = DeveloperPattern(
            pattern_type="async_style",
            description="Prefers async/await",
            examples=[],
            frequency=0.8,
        )
        checks.append(("✅", "DeveloperPattern validation works"))

        # Test PDF annotation schema
        annotation = PDFAnnotation(
            annotation_id="ann1",
            pdf_title="Test PDF",
            chunk_content="Content",
            concept_tags=["Test"],
            page_number=1,
            relevance_score=0.9,
        )
        checks.append(("✅", "PDFAnnotation validation works"))

    except Exception as e:
        checks.append(("❌", f"Schema validation failed: {e}"))

    # Print results
    for status, message in checks:
        print(f"{status} {message}")

    return all(status == "✅" for status, _ in checks)


def check_xml_formatting():
    """Check XML formatting function"""
    print("\n" + "=" * 60)
    print("CHECKING XML FORMATTING")
    print("=" * 60)

    checks = []

    try:
        from app.modules.mcp.context_schema import (
            AssembledContext,
            CodeChunk,
            ContextAssemblyMetrics,
            format_context_for_llm,
        )

        # Create test context
        metrics = ContextAssemblyMetrics(
            total_time_ms=500,
            semantic_search_ms=100,
            graphrag_ms=150,
            pattern_learning_ms=50,
            pdf_memory_ms=80,
        )

        context = AssembledContext(
            query="Test query",
            codebase="test-repo",
            code_chunks=[
                CodeChunk(
                    chunk_id="chunk1",
                    content="def test(): pass",
                    file_path="test.py",
                    language="python",
                    start_line=1,
                    end_line=1,
                    similarity_score=0.95,
                )
            ],
            graph_dependencies=[],
            developer_patterns=[],
            pdf_annotations=[],
            metrics=metrics,
        )

        # Format to XML
        formatted = format_context_for_llm(context)

        # Check XML structure
        if "<context_assembly>" in formatted:
            checks.append(("✅", "XML root element present"))
        else:
            checks.append(("❌", "XML root element missing"))

        if "<query>Test query</query>" in formatted:
            checks.append(("✅", "Query element formatted correctly"))
        else:
            checks.append(("❌", "Query element missing or malformed"))

        if "<relevant_code>" in formatted:
            checks.append(("✅", "Code section present"))
        else:
            checks.append(("❌", "Code section missing"))

        if "def test(): pass" in formatted:
            checks.append(("✅", "Code content included"))
        else:
            checks.append(("❌", "Code content missing"))

        if "</context_assembly>" in formatted:
            checks.append(("✅", "XML properly closed"))
        else:
            checks.append(("❌", "XML not properly closed"))

    except Exception as e:
        checks.append(("❌", f"XML formatting failed: {e}"))

    # Print results
    for status, message in checks:
        print(f"{status} {message}")

    return all(status == "✅" for status, _ in checks)


def check_router_integration():
    """Check router endpoint registration"""
    print("\n" + "=" * 60)
    print("CHECKING ROUTER INTEGRATION")
    print("=" * 60)

    checks = []

    try:
        from app.modules.mcp.router import mcp_router, router

        # Check router has routes
        router_routes = [route.path for route in router.routes]
        mcp_router_routes = [route.path for route in mcp_router.routes]

        if "/context/retrieve" in router_routes:
            checks.append(("✅", "Context endpoint registered on /mcp router"))
        else:
            checks.append(("❌", "Context endpoint NOT registered on /mcp router"))

        if "/context/retrieve" in mcp_router_routes:
            checks.append(("✅", "Context endpoint registered on /api/v1/mcp router"))
        else:
            checks.append(
                ("❌", "Context endpoint NOT registered on /api/v1/mcp router")
            )

        # Check other expected routes
        if "/tools" in router_routes:
            checks.append(("✅", "Tools endpoint present"))
        else:
            checks.append(("❌", "Tools endpoint missing"))

    except Exception as e:
        checks.append(("❌", f"Router check failed: {e}"))

    # Print results
    for status, message in checks:
        print(f"{status} {message}")

    return all(status == "✅" for status, _ in checks)


def check_test_suite():
    """Check test suite exists and is valid"""
    print("\n" + "=" * 60)
    print("CHECKING TEST SUITE")
    print("=" * 60)

    checks = []

    test_file = Path(__file__).parent / "tests" / "test_context_assembly_integration.py"

    if test_file.exists():
        checks.append(("✅", "Test file exists"))

        # Check test file can be imported
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "test_context_assembly", test_file
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Check for test classes
            test_classes = [
                "TestContextAssemblyService",
                "TestSchemaValidation",
                "TestXMLFormatting",
                "TestContextRetrievalEndpoint",
                "TestPerformance",
                "TestMockLLMIntegration",
            ]

            for test_class in test_classes:
                if hasattr(module, test_class):
                    checks.append(("✅", f"{test_class} test class present"))
                else:
                    checks.append(("❌", f"{test_class} test class missing"))

        except Exception as e:
            checks.append(("❌", f"Test file import failed: {e}"))
    else:
        checks.append(("❌", "Test file does not exist"))

    # Print results
    for status, message in checks:
        print(f"{status} {message}")

    return all(status == "✅" for status, _ in checks)


def check_documentation():
    """Check documentation exists"""
    print("\n" + "=" * 60)
    print("CHECKING DOCUMENTATION")
    print("=" * 60)

    checks = []

    readme_file = (
        Path(__file__).parent
        / "app"
        / "modules"
        / "mcp"
        / "CONTEXT_ASSEMBLY_README.md"
    )

    if readme_file.exists():
        checks.append(("✅", "README documentation exists"))

        # Check README content
        content = readme_file.read_text(encoding='utf-8')

        required_sections = [
            "## Overview",
            "## Architecture",
            "## API Endpoint",
            "## Implementation Details",
            "## Intelligence Layer Integration",
            "## Testing",
            "## Usage Examples",
            "## Performance Optimization",
        ]

        for section in required_sections:
            if section in content:
                checks.append(("✅", f"README has {section} section"))
            else:
                checks.append(("❌", f"README missing {section} section"))
    else:
        checks.append(("❌", "README documentation does not exist"))

    # Print results
    for status, message in checks:
        print(f"{status} {message}")

    return all(status == "✅" for status, _ in checks)


def main():
    """Run all verification checks"""
    print("\n" + "=" * 60)
    print("CONTEXT ASSEMBLY PIPELINE VERIFICATION")
    print("Phase 5: Ronin Integration & Context Assembly")
    print("=" * 60 + "\n")

    results = []

    # Run checks
    results.append(("Imports", check_imports()))
    results.append(("Schemas", check_schemas()))
    results.append(("XML Formatting", check_xml_formatting()))
    results.append(("Router Integration", check_router_integration()))
    results.append(("Test Suite", check_test_suite()))
    results.append(("Documentation", check_documentation()))

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    for check_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {check_name}")

    all_passed = all(passed for _, passed in results)

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL CHECKS PASSED - Ready for Phase 5")
    else:
        print("❌ SOME CHECKS FAILED - Review errors above")
    print("=" * 60 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
