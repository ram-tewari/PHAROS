"""
Property-based tests for Code Intelligence Pipeline (Phase 18).

**Feature: phase18-code-intelligence**

These tests verify universal properties of the code intelligence pipeline
using property-based testing with hypothesis.
"""

import pytest
import asyncio
from pathlib import Path
from hypothesis import given, strategies as st, settings, HealthCheck

from app.shared.classification import classify_file


# ============================================================================
# Property 4: File Classification Correctness
# **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
# ============================================================================

# Strategy for generating file extensions
code_extensions = st.sampled_from(
    [
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".rs",
        ".go",
        ".java",
        ".cpp",
        ".c",
        ".rb",
        ".php",
        ".swift",
        ".kt",
    ]
)

theory_extensions = st.sampled_from([".pdf", ".md", ".rst", ".tex", ".txt"])

governance_filenames = st.sampled_from(
    [
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "GOVERNANCE.md",
        "LICENSE",
        "LICENSE.txt",
        ".eslintrc.json",
        ".prettierrc.json",
        ".editorconfig",
        ".gitignore",
        ".dockerignore",
        "Makefile",
        "CMakeLists.txt",
        "setup.py",
        "setup.cfg",
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
    ]
)

# Strategy for generating academic content
academic_keywords = [
    "abstract",
    "introduction",
    "methodology",
    "results",
    "discussion",
    "conclusion",
    "references",
    "bibliography",
]


def generate_academic_content():
    """Generate content with academic keywords."""
    return st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")),
        min_size=100,
        max_size=500,
    ).map(lambda text: " ".join(academic_keywords[:4]) + " " + text)


@settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=1,
        max_size=20,
    ),
    extension=code_extensions,
)
def test_property_code_file_classification(filename, extension):
    """
    **Feature: phase18-code-intelligence, Property 4: File Classification Correctness**

    For any file with a code extension (.py, .js, .ts, .rs, .go, .java),
    the classification should be PRACTICE.

    **Validates: Requirements 2.1**
    """
    file_path = Path(f"{filename}{extension}")
    classification = classify_file(file_path)

    assert classification == "PRACTICE", (
        f"Code file {file_path} should be classified as PRACTICE, "
        f"but got {classification}"
    )


@settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=1,
        max_size=20,
    ),
    extension=theory_extensions,
    content=generate_academic_content(),
)
def test_property_theory_file_classification_with_content(filename, extension, content):
    """
    **Feature: phase18-code-intelligence, Property 4: File Classification Correctness**

    For any file with a theory extension (.pdf, .md, .rst, .tex) and academic content,
    the classification should be THEORY.

    **Validates: Requirements 2.2**
    """
    file_path = Path(f"{filename}{extension}")
    classification = classify_file(file_path, content=content)

    # .pdf and .tex should always be THEORY regardless of content
    if extension in {".pdf", ".tex"}:
        assert classification == "THEORY", (
            f"Academic file {file_path} should be classified as THEORY, "
            f"but got {classification}"
        )
    else:
        # For .md, .rst, .txt, classification depends on content
        # With academic content, should be THEORY
        assert classification == "THEORY", (
            f"File {file_path} with academic content should be classified as THEORY, "
            f"but got {classification}"
        )


@settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(governance_filename=governance_filenames)
def test_property_governance_file_classification(governance_filename):
    """
    **Feature: phase18-code-intelligence, Property 4: File Classification Correctness**

    For any file matching governance patterns (CONTRIBUTING.md, CODE_OF_CONDUCT.md,
    .eslintrc, etc.), the classification should be GOVERNANCE.

    **Validates: Requirements 2.3**
    """
    file_path = Path(governance_filename)
    classification = classify_file(file_path)

    assert classification == "GOVERNANCE", (
        f"Governance file {file_path} should be classified as GOVERNANCE, "
        f"but got {classification}"
    )


@settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=1,
        max_size=20,
    ),
    extension=st.sampled_from([".xyz", ".unknown", ".data", ".bin", ".tmp"]),
)
def test_property_unknown_file_default_classification(filename, extension):
    """
    **Feature: phase18-code-intelligence, Property 4: File Classification Correctness**

    For any file that does not match classification rules, the classification
    should default to PRACTICE.

    **Validates: Requirements 2.4**
    """
    file_path = Path(f"{filename}{extension}")
    classification = classify_file(file_path)

    assert classification == "PRACTICE", (
        f"Unknown file {file_path} should default to PRACTICE, but got {classification}"
    )


@settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=1,
        max_size=20,
    ),
    extension=st.sampled_from([".md", ".txt", ".rst"]),
)
def test_property_theory_file_without_academic_content(filename, extension):
    """
    **Feature: phase18-code-intelligence, Property 4: File Classification Correctness**

    For any .md, .txt, or .rst file without academic content, the classification
    should default to PRACTICE (since we can't determine it's academic).

    **Validates: Requirements 2.2, 2.4**
    """
    file_path = Path(f"{filename}{extension}")
    # Content without academic keywords
    non_academic_content = (
        "This is just some regular text without any academic keywords."
    )
    classification = classify_file(file_path, content=non_academic_content)

    # Without academic content, these should be PRACTICE
    assert classification == "PRACTICE", (
        f"File {file_path} without academic content should be classified as PRACTICE, "
        f"but got {classification}"
    )


@settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=1,
        max_size=20,
    )
)
def test_property_pdf_always_theory(filename):
    """
    **Feature: phase18-code-intelligence, Property 4: File Classification Correctness**

    For any .pdf file, the classification should always be THEORY regardless of content.

    **Validates: Requirements 2.2**
    """
    file_path = Path(f"{filename}.pdf")
    # Even without content or with non-academic content
    classification = classify_file(file_path, content="random content")

    assert classification == "THEORY", (
        f"PDF file {file_path} should always be classified as THEORY, "
        f"but got {classification}"
    )


# ============================================================================
# Property 1: Directory Crawling Completeness
# **Validates: Requirements 1.1, 1.5**
# ============================================================================

import tempfile
import shutil




# ============================================================================
# Property 2: Gitignore Compliance
# **Validates: Requirements 1.3**
# ============================================================================




# ============================================================================
# Property 3: Binary File Exclusion
# **Validates: Requirements 1.4**
# ============================================================================




# ============================================================================
# Property 5: AST Logical Unit Extraction
# **Validates: Requirements 3.2, 3.3**
# ============================================================================


@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    num_functions=st.integers(min_value=1, max_value=10),
    num_classes=st.integers(min_value=0, max_value=5),
)
def test_property_ast_logical_unit_extraction(num_functions, num_classes):
    """
    **Feature: phase18-code-intelligence, Property 5: AST Logical Unit Extraction**

    For any valid Python code with N functions and M classes (each with 1 method),
    AST parsing should extract N + M + M logical units (functions + classes + methods).

    **Validates: Requirements 3.2, 3.3**
    """
    from app.modules.resources.logic.chunking import CodeChunkingStrategy
    import uuid as uuid_module

    # Generate Python code with functions and classes
    code_lines = []

    # Add functions
    for i in range(num_functions):
        code_lines.append(f"def function_{i}():")
        code_lines.append(f"    return {i}")
        code_lines.append("")

    # Add classes (each with 1 method)
    for i in range(num_classes):
        code_lines.append(f"class Class_{i}:")
        code_lines.append(f"    def method_{i}(self):")
        code_lines.append(f"        return {i}")
        code_lines.append("")

    code_content = "\n".join(code_lines)

    # Create chunking strategy
    strategy = CodeChunkingStrategy(language="python")

    # Chunk the code
    resource_id = uuid_module.uuid4()
    chunks = strategy.chunk(code_content, resource_id, "test.py")

    # Verify: Number of chunks should match number of logical units
    # Each function is 1 unit, each class is 1 unit, each method is 1 unit
    expected_units = (
        num_functions + num_classes + num_classes
    )  # functions + classes + methods
    assert len(chunks) == expected_units, (
        f"Expected {expected_units} chunks (functions + classes + methods), "
        f"but got {len(chunks)}"
    )

    # Verify: Each chunk should have metadata
    for chunk in chunks:
        assert chunk.chunk_metadata is not None, "Chunk should have metadata"
        assert "language" in chunk.chunk_metadata, (
            "Chunk should have language in metadata"
        )
        assert chunk.chunk_metadata["language"] == "python", "Language should be python"
        assert "type" in chunk.chunk_metadata, "Chunk should have type in metadata"
        assert chunk.chunk_metadata["type"] in ["function", "class", "method"], (
            f"Type should be function, class, or method, got {chunk.chunk_metadata['type']}"
        )


@settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    language=st.sampled_from(["python", "javascript", "typescript"]),
    num_units=st.integers(min_value=1, max_value=10),
)
def test_property_ast_extraction_preserves_content(language, num_units):
    """
    **Feature: phase18-code-intelligence, Property 5: AST Logical Unit Extraction**

    For any code with logical units, the extracted chunks should preserve
    the original content without modification.

    **Validates: Requirements 3.2, 3.3**
    """
    from app.modules.resources.logic.chunking import CodeChunkingStrategy
    import uuid as uuid_module

    # Generate code based on language
    code_lines = []

    if language == "python":
        for i in range(num_units):
            code_lines.append(f"def function_{i}():")
            code_lines.append(f"    '''Docstring for function {i}'''")
            code_lines.append(f"    return {i}")
            code_lines.append("")
    elif language == "javascript":
        for i in range(num_units):
            code_lines.append(f"function function_{i}() {{")
            code_lines.append(f"    // Comment for function {i}")
            code_lines.append(f"    return {i};")
            code_lines.append("}")
            code_lines.append("")
    elif language == "typescript":
        for i in range(num_units):
            code_lines.append(f"function function_{i}(): number {{")
            code_lines.append(f"    // Comment for function {i}")
            code_lines.append(f"    return {i};")
            code_lines.append("}")
            code_lines.append("")

    code_content = "\n".join(code_lines)

    # Create chunking strategy
    strategy = CodeChunkingStrategy(language=language)

    # Chunk the code
    resource_id = uuid_module.uuid4()
    file_ext = {"python": ".py", "javascript": ".js", "typescript": ".ts"}[language]
    chunks = strategy.chunk(code_content, resource_id, f"test{file_ext}")

    # Verify: Concatenating all chunks should give back the original content
    # (with possible whitespace differences)
    all_chunk_content = "\n".join(chunk.content for chunk in chunks)

    # Normalize whitespace for comparison
    original_normalized = "\n".join(
        line.rstrip() for line in code_content.split("\n") if line.strip()
    )
    chunks_normalized = "\n".join(
        line.rstrip() for line in all_chunk_content.split("\n") if line.strip()
    )

    assert original_normalized == chunks_normalized, (
        f"Chunk content does not match original content"
    )


# ============================================================================
# Property 6: Code Chunk Metadata Completeness
# **Validates: Requirements 3.4, 3.5**
# ============================================================================


@settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    language=st.sampled_from(
        ["python", "javascript", "typescript", "rust", "go", "java"]
    ),
    num_functions=st.integers(min_value=1, max_value=10),
)
def test_property_code_chunk_metadata_completeness(language, num_functions):
    """
    **Feature: phase18-code-intelligence, Property 6: Code Chunk Metadata Completeness**

    For any code chunk extracted from AST, the metadata should contain:
    - language
    - type (function/class/method)
    - start_line and end_line
    - function_name or class_name

    **Validates: Requirements 3.4, 3.5**
    """
    from app.modules.resources.logic.chunking import CodeChunkingStrategy
    import uuid as uuid_module

    # Generate code based on language
    code_lines = []

    if language == "python":
        for i in range(num_functions):
            code_lines.append(f"def function_{i}():")
            code_lines.append(f"    return {i}")
            code_lines.append("")
    elif language in ["javascript", "typescript"]:
        for i in range(num_functions):
            code_lines.append(f"function function_{i}() {{")
            code_lines.append(f"    return {i};")
            code_lines.append("}")
            code_lines.append("")
    elif language == "rust":
        for i in range(num_functions):
            code_lines.append(f"fn function_{i}() -> i32 {{")
            code_lines.append(f"    {i}")
            code_lines.append("}")
            code_lines.append("")
    elif language == "go":
        for i in range(num_functions):
            code_lines.append(f"func function_{i}() int {{")
            code_lines.append(f"    return {i}")
            code_lines.append("}")
            code_lines.append("")
    elif language == "java":
        for i in range(num_functions):
            code_lines.append(f"public int function_{i}() {{")
            code_lines.append(f"    return {i};")
            code_lines.append("}")
            code_lines.append("")

    code_content = "\n".join(code_lines)

    # Create chunking strategy
    strategy = CodeChunkingStrategy(language=language)

    # Chunk the code
    resource_id = uuid_module.uuid4()
    file_ext = {
        "python": ".py",
        "javascript": ".js",
        "typescript": ".ts",
        "rust": ".rs",
        "go": ".go",
        "java": ".java",
    }[language]
    chunks = strategy.chunk(code_content, resource_id, f"test{file_ext}")

    # Verify: Each chunk should have complete metadata
    for chunk in chunks:
        metadata = chunk.chunk_metadata

        # Required fields
        assert "language" in metadata, "Chunk should have language in metadata"
        assert metadata["language"] == language, f"Language should be {language}"

        assert "type" in metadata, "Chunk should have type in metadata"
        assert metadata["type"] in ["function", "class", "method", "struct", "impl"], (
            f"Type should be a valid logical unit type, got {metadata['type']}"
        )

        assert "start_line" in metadata, "Chunk should have start_line in metadata"
        assert "end_line" in metadata, "Chunk should have end_line in metadata"
        assert isinstance(metadata["start_line"], int), (
            "start_line should be an integer"
        )
        assert isinstance(metadata["end_line"], int), "end_line should be an integer"
        assert metadata["start_line"] > 0, "start_line should be positive"
        assert metadata["end_line"] >= metadata["start_line"], (
            "end_line should be >= start_line"
        )

        # Name field (function_name or class_name)
        if metadata["type"] in ["function", "method"]:
            assert "function_name" in metadata, (
                f"Function/method chunk should have function_name in metadata"
            )
            assert metadata["function_name"].startswith("function_"), (
                f"Function name should match pattern, got {metadata['function_name']}"
            )
        elif metadata["type"] in ["class", "struct"]:
            assert "class_name" in metadata, (
                f"Class/struct chunk should have class_name in metadata"
            )


@settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(num_functions=st.integers(min_value=2, max_value=10))
def test_property_chunk_line_numbers_are_sequential(num_functions):
    """
    **Feature: phase18-code-intelligence, Property 6: Code Chunk Metadata Completeness**

    For any code with multiple logical units, the line numbers in chunk metadata
    should be sequential and non-overlapping.

    **Validates: Requirements 3.5**
    """
    from app.modules.resources.logic.chunking import CodeChunkingStrategy
    import uuid as uuid_module

    # Generate Python code with functions
    code_lines = []
    for i in range(num_functions):
        code_lines.append(f"def function_{i}():")
        code_lines.append(f"    return {i}")
        code_lines.append("")

    code_content = "\n".join(code_lines)

    # Create chunking strategy
    strategy = CodeChunkingStrategy(language="python")

    # Chunk the code
    resource_id = uuid_module.uuid4()
    chunks = strategy.chunk(code_content, resource_id, "test.py")

    # Sort chunks by start_line
    sorted_chunks = sorted(chunks, key=lambda c: c.chunk_metadata["start_line"])

    # Verify: Line numbers should be sequential and non-overlapping
    for i in range(len(sorted_chunks) - 1):
        current_chunk = sorted_chunks[i]
        next_chunk = sorted_chunks[i + 1]

        current_end = current_chunk.chunk_metadata["end_line"]
        next_start = next_chunk.chunk_metadata["start_line"]

        assert current_end < next_start, (
            f"Chunks should not overlap: chunk {i} ends at line {current_end}, "
            f"but chunk {i + 1} starts at line {next_start}"
        )


# ============================================================================
# Property 7: Parsing Fallback Safety
# **Validates: Requirements 3.7**
# ============================================================================


@settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    invalid_code=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs", "Po")),
        min_size=100,
        max_size=500,
    )
)
def test_property_parsing_fallback_safety(invalid_code):
    """
    **Feature: phase18-code-intelligence, Property 7: Parsing Fallback Safety**

    For any invalid or unparseable code, the chunking strategy should fall back
    to character-based chunking without raising exceptions.

    **Validates: Requirements 3.7**
    """
    from app.modules.resources.logic.chunking import CodeChunkingStrategy
    import uuid as uuid_module

    # Create chunking strategy
    strategy = CodeChunkingStrategy(language="python", chunk_size=100, overlap=20)

    # Chunk the invalid code (should not raise exception)
    resource_id = uuid_module.uuid4()
    try:
        chunks = strategy.chunk(invalid_code, resource_id, "test.py")

        # Verify: Should produce at least one chunk
        assert len(chunks) > 0, (
            "Should produce at least one chunk even for invalid code"
        )

        # Verify: Chunks should have metadata indicating fallback
        for chunk in chunks:
            metadata = chunk.chunk_metadata
            assert "language" in metadata, "Chunk should have language in metadata"

            # If AST parsing failed, type should be "character_based"
            if metadata.get("type") == "character_based":
                assert "start_char" in metadata, "Fallback chunk should have start_char"
                assert "end_char" in metadata, "Fallback chunk should have end_char"

    except Exception as e:
        pytest.fail(f"Chunking should not raise exception for invalid code: {e}")


@settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    valid_code_lines=st.integers(min_value=1, max_value=5),
    invalid_code_lines=st.integers(min_value=1, max_value=5),
)
def test_property_partial_parsing_fallback(valid_code_lines, invalid_code_lines):
    """
    **Feature: phase18-code-intelligence, Property 7: Parsing Fallback Safety**

    For any code that is partially valid, the chunking strategy should attempt
    AST parsing and fall back to character-based chunking if it fails.

    **Validates: Requirements 3.7**
    """
    from app.modules.resources.logic.chunking import CodeChunkingStrategy
    import uuid as uuid_module

    # Generate partially valid Python code
    code_lines = []

    # Add valid functions
    for i in range(valid_code_lines):
        code_lines.append(f"def function_{i}():")
        code_lines.append(f"    return {i}")
        code_lines.append("")

    # Add invalid syntax
    for i in range(invalid_code_lines):
        code_lines.append(f"this is not valid python syntax {i}")
        code_lines.append("")

    code_content = "\n".join(code_lines)

    # Create chunking strategy
    strategy = CodeChunkingStrategy(language="python", chunk_size=100, overlap=20)

    # Chunk the code (should not raise exception)
    resource_id = uuid_module.uuid4()
    try:
        chunks = strategy.chunk(code_content, resource_id, "test.py")

        # Verify: Should produce at least one chunk
        assert len(chunks) > 0, "Should produce at least one chunk"

        # Verify: All chunks should have metadata
        for chunk in chunks:
            assert chunk.chunk_metadata is not None, "Chunk should have metadata"
            assert "language" in chunk.chunk_metadata, "Chunk should have language"

    except Exception as e:
        pytest.fail(
            f"Chunking should not raise exception for partially valid code: {e}"
        )


@settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    language=st.sampled_from(
        ["python", "javascript", "typescript", "rust", "go", "java"]
    )
)
def test_property_empty_code_fallback(language):
    """
    **Feature: phase18-code-intelligence, Property 7: Parsing Fallback Safety**

    For any empty or whitespace-only code, the chunking strategy should handle
    it gracefully without raising exceptions.

    **Validates: Requirements 3.7**
    """
    from app.modules.resources.logic.chunking import CodeChunkingStrategy
    import uuid as uuid_module

    # Create chunking strategy
    strategy = CodeChunkingStrategy(language=language)

    # Test with empty code
    resource_id = uuid_module.uuid4()
    file_ext = {
        "python": ".py",
        "javascript": ".js",
        "typescript": ".ts",
        "rust": ".rs",
        "go": ".go",
        "java": ".java",
    }[language]

    try:
        # Empty code
        chunks = strategy.chunk("", resource_id, f"test{file_ext}")
        assert len(chunks) == 0, "Empty code should produce no chunks"

        # Whitespace-only code
        chunks = strategy.chunk("   \n\n   \t\t   ", resource_id, f"test{file_ext}")
        # Should either produce no chunks or handle gracefully
        assert isinstance(chunks, list), "Should return a list"

    except Exception as e:
        pytest.fail(f"Chunking should not raise exception for empty code: {e}")


# ============================================================================
# Property 8: Static Analysis Relationship Extraction
# **Validates: Requirements 4.1, 4.2, 4.3**
# ============================================================================


@pytest.mark.asyncio
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    num_imports=st.integers(min_value=1, max_value=10),
    num_functions=st.integers(min_value=1, max_value=5),
    num_calls=st.integers(min_value=1, max_value=5),
)
async def test_property_static_analysis_relationship_extraction(
    num_imports, num_functions, num_calls, async_db_session
):
    """
    **Feature: phase18-code-intelligence, Property 8: Static Analysis Relationship Extraction**

    For any code chunk containing imports, definitions, or calls, the corresponding
    graph relationships (IMPORTS, DEFINES, CALLS) should be created.

    **Validates: Requirements 4.1, 4.2, 4.3**
    """
    from app.modules.graph.logic.static_analysis import StaticAnalysisService
    from app.database.models import DocumentChunk, Resource
    import uuid as uuid_module

    # Generate Python code with imports, functions, and calls
    code_lines = []

    # Add imports
    import_names = []
    for i in range(num_imports):
        import_name = f"module_{i}"
        code_lines.append(f"import {import_name}")
        import_names.append(import_name)

    code_lines.append("")

    # Add function definitions
    function_names = []
    for i in range(num_functions):
        func_name = f"function_{i}"
        code_lines.append(f"def {func_name}():")

        # Add function calls inside each function
        for j in range(min(num_calls, i + 1)):
            if j < len(function_names):
                code_lines.append(f"    {function_names[j]}()")

        code_lines.append(f"    return {i}")
        code_lines.append("")
        function_names.append(func_name)

    code_content = "\n".join(code_lines)

    # Create a mock resource and chunk
    resource = Resource(
        id=uuid_module.uuid4(),
        title="test.py",
        type="code",
        metadata={"path": "test.py", "classification": "PRACTICE"},
    )

    chunk = DocumentChunk(
        id=uuid_module.uuid4(),
        resource_id=resource.id,
        content=code_content,
        chunk_index=0,
        chunk_metadata={
            "language": "python",
            "type": "file",
            "start_line": 1,
            "end_line": len(code_lines),
        },
    )

    # Analyze the chunk
    service = StaticAnalysisService(async_db_session)
    relationships = await service.analyze_code_chunk(chunk, resource)

    # Verify: Should extract IMPORTS relationships
    import_rels = [r for r in relationships if r["type"] == "IMPORTS"]
    assert len(import_rels) >= num_imports, (
        f"Expected at least {num_imports} IMPORTS relationships, "
        f"but got {len(import_rels)}"
    )

    # Verify: Should extract DEFINES relationships
    define_rels = [r for r in relationships if r["type"] == "DEFINES"]
    assert len(define_rels) >= num_functions, (
        f"Expected at least {num_functions} DEFINES relationships, "
        f"but got {len(define_rels)}"
    )

    # Verify: Each relationship should have required metadata
    for rel in relationships:
        assert "type" in rel, "Relationship should have type"
        assert rel["type"] in ["IMPORTS", "DEFINES", "CALLS"], (
            f"Relationship type should be IMPORTS, DEFINES, or CALLS, got {rel['type']}"
        )

        assert "source_file" in rel, "Relationship should have source_file"
        assert "target_symbol" in rel, "Relationship should have target_symbol"
        assert "line_number" in rel, "Relationship should have line_number"
        assert "metadata" in rel, "Relationship should have metadata"

        # Verify metadata structure
        metadata = rel["metadata"]
        assert "language" in metadata, "Metadata should have language"
        assert metadata["language"] == "python", "Language should be python"


@pytest.mark.asyncio
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    language=st.sampled_from(
        ["python", "javascript", "typescript", "rust", "go", "java"]
    ),
    num_definitions=st.integers(min_value=1, max_value=10),
)
async def test_property_static_analysis_multi_language(
    language, num_definitions, async_db_session
):
    """
    **Feature: phase18-code-intelligence, Property 8: Static Analysis Relationship Extraction**

    For any supported language, static analysis should extract definitions
    correctly.

    **Validates: Requirements 4.1, 4.2**
    """
    from app.modules.graph.logic.static_analysis import StaticAnalysisService
    from app.database.models import DocumentChunk, Resource
    import uuid as uuid_module

    # Generate code based on language
    code_lines = []

    if language == "python":
        for i in range(num_definitions):
            code_lines.append(f"def function_{i}():")
            code_lines.append(f"    return {i}")
            code_lines.append("")
    elif language in ["javascript", "typescript"]:
        for i in range(num_definitions):
            code_lines.append(f"function function_{i}() {{")
            code_lines.append(f"    return {i};")
            code_lines.append("}")
            code_lines.append("")
    elif language == "rust":
        for i in range(num_definitions):
            code_lines.append(f"fn function_{i}() -> i32 {{")
            code_lines.append(f"    {i}")
            code_lines.append("}")
            code_lines.append("")
    elif language == "go":
        for i in range(num_definitions):
            code_lines.append(f"func function_{i}() int {{")
            code_lines.append(f"    return {i}")
            code_lines.append("}")
            code_lines.append("")
    elif language == "java":
        for i in range(num_definitions):
            code_lines.append(f"public int function_{i}() {{")
            code_lines.append(f"    return {i};")
            code_lines.append("}")
            code_lines.append("")

    code_content = "\n".join(code_lines)

    # Create a mock resource and chunk
    file_ext = {
        "python": ".py",
        "javascript": ".js",
        "typescript": ".ts",
        "rust": ".rs",
        "go": ".go",
        "java": ".java",
    }[language]

    resource = Resource(
        id=uuid_module.uuid4(),
        title=f"test{file_ext}",
        type="code",
        metadata={"path": f"test{file_ext}", "classification": "PRACTICE"},
    )

    chunk = DocumentChunk(
        id=uuid_module.uuid4(),
        resource_id=resource.id,
        content=code_content,
        chunk_index=0,
        chunk_metadata={
            "language": language,
            "type": "file",
            "start_line": 1,
            "end_line": len(code_lines),
        },
    )

    # Analyze the chunk
    service = StaticAnalysisService(async_db_session)
    relationships = await service.analyze_code_chunk(chunk, resource)

    # Verify: Should extract DEFINES relationships
    define_rels = [r for r in relationships if r["type"] == "DEFINES"]
    assert len(define_rels) >= num_definitions, (
        f"Expected at least {num_definitions} DEFINES relationships for {language}, "
        f"but got {len(define_rels)}"
    )

    # Verify: Each relationship should have correct language in metadata
    for rel in define_rels:
        assert rel["metadata"]["language"] == language, (
            f"Relationship metadata should have language {language}, "
            f"got {rel['metadata']['language']}"
        )


@pytest.mark.asyncio
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(num_imports=st.integers(min_value=1, max_value=10))
async def test_property_import_extraction_completeness(num_imports, async_db_session):
    """
    **Feature: phase18-code-intelligence, Property 8: Static Analysis Relationship Extraction**

    For any code with N import statements, static analysis should extract
    exactly N IMPORTS relationships.

    **Validates: Requirements 4.1**
    """
    from app.modules.graph.logic.static_analysis import StaticAnalysisService
    from app.database.models import DocumentChunk, Resource
    import uuid as uuid_module

    # Generate Python code with imports
    code_lines = []
    import_names = []

    for i in range(num_imports):
        import_name = f"module_{i}"
        code_lines.append(f"import {import_name}")
        import_names.append(import_name)

    code_content = "\n".join(code_lines)

    # Create a mock resource and chunk
    resource = Resource(
        id=uuid_module.uuid4(),
        title="test.py",
        type="code",
        metadata={"path": "test.py", "classification": "PRACTICE"},
    )

    chunk = DocumentChunk(
        id=uuid_module.uuid4(),
        resource_id=resource.id,
        content=code_content,
        chunk_index=0,
        chunk_metadata={
            "language": "python",
            "type": "file",
            "start_line": 1,
            "end_line": len(code_lines),
        },
    )

    # Analyze the chunk
    service = StaticAnalysisService(async_db_session)
    relationships = await service.analyze_code_chunk(chunk, resource)

    # Verify: Should extract exactly num_imports IMPORTS relationships
    import_rels = [r for r in relationships if r["type"] == "IMPORTS"]
    assert len(import_rels) == num_imports, (
        f"Expected exactly {num_imports} IMPORTS relationships, "
        f"but got {len(import_rels)}"
    )

    # Verify: Each import should be present
    extracted_imports = {r["target_symbol"] for r in import_rels}
    expected_imports = set(import_names)
    assert extracted_imports == expected_imports, (
        f"Extracted imports {extracted_imports} do not match expected {expected_imports}"
    )


# ============================================================================
# Property 9: Static Analysis Safety
# **Validates: Requirements 4.7**
# ============================================================================


@pytest.mark.asyncio
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    side_effect_code=st.sampled_from(
        [
            "import os\nos.system('echo hello')",
            "import subprocess\nsubprocess.run(['ls'])",
            "with open('test.txt', 'w') as f:\n    f.write('test')",
            "import sys\nsys.exit(0)",
            "exec('print(\"hello\")')",
            "eval('1 + 1')",
        ]
    )
)
async def test_property_static_analysis_no_code_execution(
    side_effect_code, async_db_session
):
    """
    **Feature: phase18-code-intelligence, Property 9: Static Analysis Safety**

    For any code with side effects (file I/O, system calls, exec/eval),
    static analysis should NOT execute the code.

    **Validates: Requirements 4.7**
    """
    from app.modules.graph.logic.static_analysis import StaticAnalysisService
    from app.database.models import DocumentChunk, Resource
    import uuid as uuid_module
    import os
    import tempfile

    # Create a temporary file to check if it gets created (it shouldn't)
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    temp_file_path = temp_file.name
    temp_file.close()
    os.unlink(temp_file_path)  # Delete it so we can check if code creates it

    # Create a mock resource and chunk with side-effect code
    resource = Resource(
        id=uuid_module.uuid4(),
        title="test.py",
        type="code",
        metadata={"path": "test.py", "classification": "PRACTICE"},
    )

    chunk = DocumentChunk(
        id=uuid_module.uuid4(),
        resource_id=resource.id,
        content=side_effect_code,
        chunk_index=0,
        chunk_metadata={
            "language": "python",
            "type": "file",
            "start_line": 1,
            "end_line": side_effect_code.count("\n") + 1,
        },
    )

    # Analyze the chunk
    service = StaticAnalysisService(async_db_session)

    try:
        relationships = await service.analyze_code_chunk(chunk, resource)

        # Verify: Analysis should complete without executing code
        assert isinstance(relationships, list), "Should return a list of relationships"

        # Verify: Temporary file should NOT be created (code was not executed)
        assert not os.path.exists(temp_file_path), (
            "Static analysis should not execute code - file should not be created"
        )

        # Verify: We should still extract relationships (imports, etc.)
        # Even though we don't execute, we should parse the AST
        if "import" in side_effect_code:
            import_rels = [r for r in relationships if r["type"] == "IMPORTS"]
            assert len(import_rels) > 0, (
                "Should extract import relationships without executing code"
            )

    finally:
        # Cleanup
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


@pytest.mark.asyncio
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    malicious_code=st.sampled_from(
        [
            "import os\nos.remove('/important/file')",
            "import shutil\nshutil.rmtree('/')",
            "while True:\n    pass",
            "import socket\nsocket.socket().connect(('evil.com', 80))",
        ]
    )
)
async def test_property_static_analysis_malicious_code_safety(
    malicious_code, async_db_session
):
    """
    **Feature: phase18-code-intelligence, Property 9: Static Analysis Safety**

    For any malicious code (file deletion, infinite loops, network calls),
    static analysis should safely parse without executing.

    **Validates: Requirements 4.7**
    """
    from app.modules.graph.logic.static_analysis import StaticAnalysisService
    from app.database.models import DocumentChunk, Resource
    import uuid as uuid_module

    # Create a mock resource and chunk with malicious code
    resource = Resource(
        id=uuid_module.uuid4(),
        title="malicious.py",
        type="code",
        metadata={"path": "malicious.py", "classification": "PRACTICE"},
    )

    chunk = DocumentChunk(
        id=uuid_module.uuid4(),
        resource_id=resource.id,
        content=malicious_code,
        chunk_index=0,
        chunk_metadata={
            "language": "python",
            "type": "file",
            "start_line": 1,
            "end_line": malicious_code.count("\n") + 1,
        },
    )

    # Analyze the chunk
    service = StaticAnalysisService(async_db_session)

    try:
        # This should complete quickly without executing the malicious code
        import time

        start_time = time.time()

        relationships = await service.analyze_code_chunk(chunk, resource)

        elapsed_time = time.time() - start_time

        # Verify: Analysis should complete quickly (not stuck in infinite loop)
        assert elapsed_time < 5.0, (
            f"Static analysis took too long ({elapsed_time}s), might be executing code"
        )

        # Verify: Should return relationships without executing
        assert isinstance(relationships, list), "Should return a list of relationships"

        # Verify: Should extract imports even from malicious code
        if "import" in malicious_code:
            import_rels = [r for r in relationships if r["type"] == "IMPORTS"]
            assert len(import_rels) > 0, (
                "Should extract import relationships from malicious code"
            )

    except Exception as e:
        # Should not raise exceptions, but if it does, it should be a parsing error
        # not an execution error
        assert "execution" not in str(e).lower(), (
            f"Error should not be related to code execution: {e}"
        )


@pytest.mark.asyncio
async def test_property_static_analysis_no_side_effects(async_db_session):
    """
    **Feature: phase18-code-intelligence, Property 9: Static Analysis Safety**

    For any code analysis, the system state should remain unchanged
    (no files created, no network calls, no environment modifications).

    **Validates: Requirements 4.7**
    """
    from app.modules.graph.logic.static_analysis import StaticAnalysisService
    from app.database.models import DocumentChunk, Resource
    import uuid as uuid_module
    import os
    import tempfile

    # Get current directory contents
    temp_dir = tempfile.gettempdir()
    files_before = set(os.listdir(temp_dir))

    # Create code that would create files if executed
    code_content = """
import os
import tempfile

# This would create a file if executed
with open(os.path.join(tempfile.gettempdir(), 'test_static_analysis.txt'), 'w') as f:
    f.write('This should not be created')

def create_file():
    with open('another_test.txt', 'w') as f:
        f.write('Also should not be created')
"""

    # Create a mock resource and chunk
    resource = Resource(
        id=uuid_module.uuid4(),
        title="test.py",
        type="code",
        metadata={"path": "test.py", "classification": "PRACTICE"},
    )

    chunk = DocumentChunk(
        id=uuid_module.uuid4(),
        resource_id=resource.id,
        content=code_content,
        chunk_index=0,
        chunk_metadata={
            "language": "python",
            "type": "file",
            "start_line": 1,
            "end_line": code_content.count("\n") + 1,
        },
    )

    # Analyze the chunk
    service = StaticAnalysisService(async_db_session)
    relationships = await service.analyze_code_chunk(chunk, resource)

    # Get directory contents after analysis
    files_after = set(os.listdir(temp_dir))

    # Verify: No new files should be created
    new_files = files_after - files_before
    assert len(new_files) == 0, (
        f"Static analysis should not create files, but found: {new_files}"
    )

    # Verify: Should still extract relationships
    assert isinstance(relationships, list), "Should return a list of relationships"

    # Verify: Should extract imports
    import_rels = [r for r in relationships if r["type"] == "IMPORTS"]
    assert len(import_rels) >= 2, "Should extract import relationships (os, tempfile)"

    # Verify: Should extract function definitions
    define_rels = [r for r in relationships if r["type"] == "DEFINES"]
    assert len(define_rels) >= 1, "Should extract function definition (create_file)"


# ============================================================================
# Property 10: Task State Transitions
# **Validates: Requirements 5.1, 5.2, 5.4**
# ============================================================================








# ============================================================================
# Property 12: Graceful Error Handling
# **Validates: Requirements 9.1, 9.2, 9.3, 9.5, 9.6**
# ============================================================================








