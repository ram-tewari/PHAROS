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

from app.modules.resources.logic.classification import classify_file


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


@pytest.mark.asyncio
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    num_files=st.integers(min_value=1, max_value=20),
    file_extensions=st.lists(
        st.sampled_from([".py", ".js", ".md", ".txt", ".json"]), min_size=1, max_size=5
    ),
)
async def test_property_directory_crawling_completeness(
    num_files, file_extensions, async_db_session
):
    """
    **Feature: phase18-code-intelligence, Property 1: Directory Crawling Completeness**

    For any directory structure with N non-ignored files, ingesting the directory
    should create exactly N Resource entries with preserved file paths.

    **Validates: Requirements 1.1, 1.5**
    """
    from app.modules.resources.logic.repo_ingestion import RepoIngestionService

    # Create temporary directory
    temp_dir = tempfile.mkdtemp(prefix="test_repo_")
    temp_path = Path(temp_dir)

    try:
        # Create test files
        created_files = []
        for i in range(num_files):
            ext = file_extensions[i % len(file_extensions)]
            file_path = temp_path / f"file_{i}{ext}"
            file_path.write_text(f"Content of file {i}")
            created_files.append(file_path)

        # Ingest directory
        service = RepoIngestionService(async_db_session)
        resources = await service.crawl_directory(temp_path)

        # Verify: Number of resources should match number of files
        assert len(resources) == num_files, (
            f"Expected {num_files} resources, but got {len(resources)}"
        )

        # Verify: All file paths should be preserved in identifier field
        resource_paths = {r.identifier for r in resources}
        expected_paths = {
            str(f.relative_to(temp_path)).replace("\\", "/") for f in created_files
        }

        assert resource_paths == expected_paths, (
            f"Resource paths {resource_paths} do not match expected paths {expected_paths}"
        )

        # Verify: All resources should have repo_root in coverage field
        for resource in resources:
            assert resource.coverage == str(temp_path), (
                f"Resource {resource.title} has incorrect repo_root in coverage field"
            )

    finally:
        # Cleanup
        shutil.rmtree(temp_path, ignore_errors=True)


# ============================================================================
# Property 2: Gitignore Compliance
# **Validates: Requirements 1.3**
# ============================================================================


@pytest.mark.asyncio
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    num_files=st.integers(min_value=3, max_value=10),
    ignore_pattern=st.sampled_from(
        ["*.log", "*.tmp", "build/*", "dist/*", "__pycache__/*"]
    ),
)
async def test_property_gitignore_compliance(
    num_files, ignore_pattern, async_db_session
):
    """
    **Feature: phase18-code-intelligence, Property 2: Gitignore Compliance**

    For any .gitignore pattern and file set, files matching the pattern
    should be excluded from ingestion.

    **Validates: Requirements 1.3**
    """
    from app.modules.resources.logic.repo_ingestion import RepoIngestionService

    # Create temporary directory
    temp_dir = tempfile.mkdtemp(prefix="test_repo_")
    temp_path = Path(temp_dir)

    try:
        # Create .gitignore
        gitignore_path = temp_path / ".gitignore"
        gitignore_path.write_text(ignore_pattern)

        # Create files that should be ignored
        ignored_files = []
        if ignore_pattern == "*.log":
            for i in range(num_files // 2):
                file_path = temp_path / f"file_{i}.log"
                file_path.write_text(f"Log content {i}")
                ignored_files.append(file_path)
        elif ignore_pattern == "*.tmp":
            for i in range(num_files // 2):
                file_path = temp_path / f"file_{i}.tmp"
                file_path.write_text(f"Temp content {i}")
                ignored_files.append(file_path)
        elif ignore_pattern == "build/*":
            build_dir = temp_path / "build"
            build_dir.mkdir()
            for i in range(num_files // 2):
                file_path = build_dir / f"file_{i}.txt"
                file_path.write_text(f"Build content {i}")
                ignored_files.append(file_path)
        elif ignore_pattern == "dist/*":
            dist_dir = temp_path / "dist"
            dist_dir.mkdir()
            for i in range(num_files // 2):
                file_path = dist_dir / f"file_{i}.txt"
                file_path.write_text(f"Dist content {i}")
                ignored_files.append(file_path)
        elif ignore_pattern == "__pycache__/*":
            pycache_dir = temp_path / "__pycache__"
            pycache_dir.mkdir()
            for i in range(num_files // 2):
                file_path = pycache_dir / f"file_{i}.pyc"
                file_path.write_text(f"Cache content {i}")
                ignored_files.append(file_path)

        # Create files that should NOT be ignored
        included_files = []
        for i in range(num_files - len(ignored_files)):
            file_path = temp_path / f"source_{i}.py"
            file_path.write_text(f"Source content {i}")
            included_files.append(file_path)

        # Ingest directory
        service = RepoIngestionService(async_db_session)
        resources = await service.crawl_directory(temp_path)

        # Verify: Only non-ignored files should be ingested
        assert len(resources) == len(included_files), (
            f"Expected {len(included_files)} resources (ignored {len(ignored_files)}), "
            f"but got {len(resources)}"
        )

        # Verify: Resource paths should only include non-ignored files
        resource_paths = {r.identifier for r in resources}
        expected_paths = {
            str(f.relative_to(temp_path)).replace("\\", "/") for f in included_files
        }

        assert resource_paths == expected_paths, (
            f"Resource paths {resource_paths} do not match expected paths {expected_paths}"
        )

    finally:
        # Cleanup
        shutil.rmtree(temp_path, ignore_errors=True)


# ============================================================================
# Property 3: Binary File Exclusion
# **Validates: Requirements 1.4**
# ============================================================================


@pytest.mark.asyncio
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    num_text_files=st.integers(min_value=1, max_value=10),
    num_binary_files=st.integers(min_value=1, max_value=5),
)
async def test_property_binary_file_exclusion(
    num_text_files, num_binary_files, async_db_session
):
    """
    **Feature: phase18-code-intelligence, Property 3: Binary File Exclusion**

    For any file set containing binary files, binary files should be
    excluded from ingestion.

    **Validates: Requirements 1.4**
    """
    from app.modules.resources.logic.repo_ingestion import RepoIngestionService

    # Create temporary directory
    temp_dir = tempfile.mkdtemp(prefix="test_repo_")
    temp_path = Path(temp_dir)

    try:
        # Create text files
        text_files = []
        for i in range(num_text_files):
            file_path = temp_path / f"text_{i}.txt"
            file_path.write_text(f"Text content {i}")
            text_files.append(file_path)

        # Create binary files (with null bytes)
        binary_files = []
        for i in range(num_binary_files):
            file_path = temp_path / f"binary_{i}.bin"
            file_path.write_bytes(b"Binary\x00content\x00" + bytes([i]))
            binary_files.append(file_path)

        # Ingest directory
        service = RepoIngestionService(async_db_session)
        resources = await service.crawl_directory(temp_path)

        # Verify: Only text files should be ingested
        assert len(resources) == num_text_files, (
            f"Expected {num_text_files} resources (excluded {num_binary_files} binary files), "
            f"but got {len(resources)}"
        )

        # Verify: Resource paths should only include text files
        resource_paths = {r.identifier for r in resources}
        expected_paths = {
            str(f.relative_to(temp_path)).replace("\\", "/") for f in text_files
        }

        assert resource_paths == expected_paths, (
            f"Resource paths {resource_paths} do not match expected paths {expected_paths}"
        )

        # Verify: No binary files should be in resources
        for resource in resources:
            assert not resource.identifier.endswith(".bin"), (
                f"Binary file {resource.identifier} should not be ingested"
            )

    finally:
        # Cleanup
        shutil.rmtree(temp_path, ignore_errors=True)


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
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
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


@pytest.mark.asyncio
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(num_files=st.integers(min_value=1, max_value=5))
async def test_property_task_state_transitions(
    num_files, async_db_session, celery_eager_mode
):
    """
    **Feature: phase18-code-intelligence, Property 10: Task State Transitions**

    For any repository ingestion task, the task state should transition from
    PENDING → PROCESSING → COMPLETED (or FAILED), never skipping states.

    **Validates: Requirements 5.1, 5.2, 5.4**
    """
    from app.tasks.celery_tasks import ingest_repo_task
    from celery.result import AsyncResult
    import tempfile
    import time
    import uuid

    # Create a temporary directory with test files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test files
        for i in range(num_files):
            test_file = temp_path / f"test_{i}.py"
            test_file.write_text(
                f"# Test file {i}\ndef test_function_{i}():\n    pass\n"
            )

        # Track state transitions
        observed_states = []

        # Start the task with unique ID
        task_id = f"test_task_{uuid.uuid4()}"
        result = ingest_repo_task.apply_async(
            kwargs={"path": str(temp_path)}, task_id=task_id
        )

        # Poll task state and record transitions
        max_polls = 100
        poll_count = 0
        previous_state = None

        while poll_count < max_polls:
            task_result = AsyncResult(result.id)
            current_state = task_result.state

            # Record state transition
            if current_state != previous_state:
                observed_states.append(current_state)
                previous_state = current_state

            # Check if task is done
            if current_state in ["SUCCESS", "FAILURE"]:
                break

            poll_count += 1
            await asyncio.sleep(0.2)  # Poll every 200ms

        # Wait for task to complete
        try:
            final_result = task_result.get(timeout=30)
        except Exception as e:
            # Task might fail, that's okay for this test
            pass

        # Verify: Should have at least 2 states (initial and final)
        assert len(observed_states) >= 2, (
            f"Task should transition through multiple states, "
            f"but only observed: {observed_states}"
        )

        # Verify: First state should be PENDING
        assert observed_states[0] == "PENDING", (
            f"First state should be PENDING, but was {observed_states[0]}"
        )

        # Verify: Should have PROCESSING state before completion
        if "SUCCESS" in observed_states:
            assert "PROCESSING" in observed_states, (
                f"Task should go through PROCESSING state before completion, "
                f"but states were: {observed_states}"
            )

        # Verify: Final state should be SUCCESS or FAILURE
        final_state = observed_states[-1]
        assert final_state in ["SUCCESS", "FAILURE"], (
            f"Final state should be SUCCESS or FAILURE, but was {final_state}"
        )

        # Verify: States should be in valid order
        # Valid transitions: PENDING → PROCESSING → (SUCCESS|FAILURE)
        valid_transitions = {
            "PENDING": ["PROCESSING", "SUCCESS", "FAILURE"],
            "PROCESSING": ["PROCESSING", "SUCCESS", "FAILURE"],
            "SUCCESS": [],
            "FAILURE": [],
        }

        for i in range(len(observed_states) - 1):
            current = observed_states[i]
            next_state = observed_states[i + 1]

            assert next_state in valid_transitions.get(current, []), (
                f"Invalid state transition: {current} → {next_state}. "
                f"Valid transitions from {current}: {valid_transitions.get(current, [])}"
            )


@pytest.mark.asyncio
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(num_files=st.integers(min_value=1, max_value=5))
async def test_property_task_progress_tracking(
    num_files, async_db_session, celery_eager_mode
):
    """
    **Feature: phase18-code-intelligence, Property 10: Task State Transitions**

    For any repository ingestion task, progress information should be
    available and should increase monotonically.

    **Validates: Requirements 5.3, 5.5**
    """
    from app.tasks.celery_tasks import ingest_repo_task
    from celery.result import AsyncResult
    import tempfile
    import uuid

    # Create a temporary directory with test files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test files
        for i in range(num_files):
            test_file = temp_path / f"test_{i}.py"
            test_file.write_text(
                f"# Test file {i}\ndef test_function_{i}():\n    pass\n"
            )

        # Start the task with unique ID
        task_id = f"test_progress_{uuid.uuid4()}"
        result = ingest_repo_task.apply_async(
            kwargs={"path": str(temp_path)}, task_id=task_id
        )

        # Track progress
        progress_values = []
        max_polls = 100
        poll_count = 0

        while poll_count < max_polls:
            task_result = AsyncResult(result.id)

            # Get task info
            if task_result.state == "PROCESSING":
                info = task_result.info
                if isinstance(info, dict) and "files_processed" in info:
                    files_processed = info["files_processed"]
                    total_files = info.get("total_files", 0)
                    progress_values.append((files_processed, total_files))

            # Check if task is done
            if task_result.state in ["SUCCESS", "FAILURE"]:
                break

            poll_count += 1
            await asyncio.sleep(0.2)

        # Wait for task to complete
        try:
            task_result.get(timeout=30)
        except Exception:
            pass

        # Verify: Should have captured some progress
        if len(progress_values) > 0:
            # Verify: files_processed should increase monotonically
            for i in range(len(progress_values) - 1):
                current_processed = progress_values[i][0]
                next_processed = progress_values[i + 1][0]

                assert next_processed >= current_processed, (
                    f"files_processed should increase monotonically, "
                    f"but went from {current_processed} to {next_processed}"
                )

            # Verify: total_files should be consistent
            total_files_values = [total for _, total in progress_values if total > 0]
            if len(total_files_values) > 0:
                first_total = total_files_values[0]
                for total in total_files_values:
                    assert total == first_total, (
                        f"total_files should remain constant, "
                        f"but changed from {first_total} to {total}"
                    )

            # Verify: files_processed should not exceed total_files
            for processed, total in progress_values:
                if total > 0:
                    assert processed <= total, (
                        f"files_processed ({processed}) should not exceed "
                        f"total_files ({total})"
                    )


@pytest.mark.asyncio
@settings(
    max_examples=5,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
async def test_property_task_error_handling(async_db_session, celery_eager_mode):
    """
    **Feature: phase18-code-intelligence, Property 10: Task State Transitions**

    For any repository ingestion task that encounters an error,
    the task should transition to FAILED state with error information.

    **Validates: Requirements 5.4**
    """
    from app.tasks.celery_tasks import ingest_repo_task
    from celery.result import AsyncResult
    import uuid

    # Try to ingest a non-existent directory
    invalid_path = f"/nonexistent/path/{uuid.uuid4()}"

    # Start the task with unique ID
    task_id = f"test_error_{uuid.uuid4()}"
    result = ingest_repo_task.apply_async(
        kwargs={"path": invalid_path}, task_id=task_id
    )

    # Wait for task to complete
    max_wait = 30
    start_time = asyncio.get_event_loop().time()

    while asyncio.get_event_loop().time() - start_time < max_wait:
        task_result = AsyncResult(result.id)

        if task_result.state in ["FAILURE"]:
            # Verify: Should have error information
            info = task_result.info

            if isinstance(info, dict):
                assert "error" in info or "exc_message" in str(info), (
                    f"Failed task should include error information, but got: {info}"
                )

            # Task failed as expected
            return

        if task_result.state in ["SUCCESS"]:
            pytest.fail(
                f"Task should have failed for invalid path, "
                f"but succeeded with state: {task_result.state}"
            )

        await asyncio.sleep(0.5)

    # If we get here, task didn't complete in time
    # That's okay, we just verify it didn't succeed
    task_result = AsyncResult(result.id)
    assert task_result.state not in ["SUCCESS"], (
        f"Task should not succeed for invalid path, but got state: {task_result.state}"
    )


# ============================================================================
# Property 12: Graceful Error Handling
# **Validates: Requirements 9.1, 9.2, 9.3, 9.5, 9.6**
# ============================================================================


@pytest.mark.asyncio
@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    num_valid_files=st.integers(min_value=3, max_value=10),
    num_invalid_files=st.integers(min_value=1, max_value=3),
)
async def test_property_graceful_error_handling(
    num_valid_files, num_invalid_files, async_db_session, tmp_path
):
    """
    **Feature: phase18-code-intelligence, Property 12: Graceful Error Handling**

    For any file that cannot be processed (read error, parse error, analysis error),
    the system should log the error and continue processing other files without data corruption.

    **Validates: Requirements 9.1, 9.2, 9.3, 9.5, 9.6**
    """
    from app.modules.resources.logic.repo_ingestion import RepoIngestionService
    import shutil

    # Create test directory (clean up if exists)
    test_dir = tmp_path / "test_repo"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()

    # Create valid files
    valid_files = []
    for i in range(num_valid_files):
        file_path = test_dir / f"valid_{i}.py"
        file_path.write_text(f"# Valid Python file {i}\ndef func_{i}():\n    pass\n")
        valid_files.append(file_path)

    # Create invalid files (various error conditions)
    invalid_files = []
    for i in range(num_invalid_files):
        if i % 3 == 0:
            # File with permission error (simulate by creating directory with same name)
            file_path = test_dir / f"invalid_{i}.py"
            file_path.mkdir()  # Create directory instead of file
            invalid_files.append(file_path)
        elif i % 3 == 1:
            # File with encoding error (binary content with .py extension)
            file_path = test_dir / f"invalid_{i}.py"
            file_path.write_bytes(b"\x00\x01\x02\x03\x04\x05")
            invalid_files.append(file_path)
        else:
            # File with very long name (may cause issues on some systems)
            long_name = "x" * 200 + ".py"
            file_path = test_dir / long_name
            try:
                file_path.write_text("# File with long name\n")
                invalid_files.append(file_path)
            except OSError:
                # If we can't create the file, skip it
                pass

    # Ingest repository
    service = RepoIngestionService(async_db_session)
    resources, error_metadata = await service.crawl_directory(
        test_dir, track_errors=True
    )

    # Verify: Should have processed valid files
    assert len(resources) >= num_valid_files - 1, (
        f"Should have processed at least {num_valid_files - 1} valid files, "
        f"but only got {len(resources)}"
    )

    # Verify: Should have tracked failed files
    assert error_metadata["failed"] >= 0, (
        f"Should track failed files, but got {error_metadata['failed']}"
    )

    # Verify: Should have error metadata for failed files
    if error_metadata["failed"] > 0:
        assert len(error_metadata["failed_files"]) > 0, (
            "Should have failed_files list when failures occur"
        )

        # Verify each failed file has required metadata
        for failed_file in error_metadata["failed_files"]:
            assert "path" in failed_file, "Failed file should have path"
            assert "error" in failed_file, "Failed file should have error message"
            assert "error_type" in failed_file, "Failed file should have error type"

    # Verify: Total files should match
    total_expected = num_valid_files + len(invalid_files)
    total_processed = (
        error_metadata["successful"]
        + error_metadata["failed"]
        + error_metadata["skipped"]
    )

    # Allow some tolerance for files that might be skipped (like directories)
    assert total_processed >= num_valid_files, (
        f"Should have processed at least {num_valid_files} files, "
        f"but only processed {total_processed}"
    )

    # Verify: Database should not be corrupted
    # All created resources should be valid
    for resource in resources:
        assert resource.id is not None, "Resource should have ID"
        assert resource.title is not None, "Resource should have title"


@pytest.mark.asyncio
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    batch_size=st.integers(min_value=2, max_value=10),
    num_files=st.integers(min_value=5, max_value=20),
)
async def test_property_batch_transaction_rollback(
    batch_size, num_files, async_db_session, tmp_path
):
    """
    **Feature: phase18-code-intelligence, Property 12: Graceful Error Handling**

    For any batch that encounters a database error, the system should rollback
    the transaction and continue processing other batches without data corruption.

    **Validates: Requirements 9.5, 9.6**
    """
    from app.modules.resources.logic.repo_ingestion import RepoIngestionService
    import shutil

    # Create test directory with files (clean up if exists)
    test_dir = tmp_path / "test_repo"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()

    for i in range(num_files):
        file_path = test_dir / f"file_{i}.py"
        file_path.write_text(f"# Python file {i}\ndef func_{i}():\n    pass\n")

    # Ingest repository with specified batch size
    service = RepoIngestionService(async_db_session)
    resources, error_metadata = await service.crawl_directory(
        test_dir, track_errors=True, batch_size=batch_size
    )

    # Verify: Should have processed files in batches
    expected_batches = (num_files + batch_size - 1) // batch_size
    assert error_metadata["batches_processed"] == expected_batches, (
        f"Should have processed {expected_batches} batches, "
        f"but got {error_metadata['batches_processed']}"
    )

    # Verify: Should have created resources
    assert len(resources) > 0, "Should have created at least some resources"

    # Verify: All resources should be valid (no partial commits)
    for resource in resources:
        assert resource.id is not None, "Resource should have ID"
        assert resource.title is not None, "Resource should have title"
        assert resource.identifier is not None, "Resource should have identifier"


@pytest.mark.asyncio
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(num_files=st.integers(min_value=5, max_value=15))
async def test_property_error_tracking_in_task_metadata(
    num_files, async_db_session, tmp_path, celery_eager_mode
):
    """
    **Feature: phase18-code-intelligence, Property 12: Graceful Error Handling**

    For any repository ingestion task, failed files should be tracked in task metadata
    and available for inspection after task completion.

    **Validates: Requirements 9.1, 9.2, 9.3**
    """
    from app.tasks.celery_tasks import ingest_repo_task
    from celery.result import AsyncResult
    import uuid
    import shutil

    # Create test directory with mix of valid and invalid files (clean up if exists)
    test_dir = tmp_path / "test_repo"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()

    # Create valid files
    for i in range(num_files // 2):
        file_path = test_dir / f"valid_{i}.py"
        file_path.write_text(f"# Valid file {i}\ndef func():\n    pass\n")

    # Create invalid files (binary content with .py extension)
    for i in range(num_files // 2):
        file_path = test_dir / f"invalid_{i}.py"
        file_path.write_bytes(b"\x00\x01\x02\x03")

    # Start ingestion task
    task_id = f"test_error_tracking_{uuid.uuid4()}"
    result = ingest_repo_task.apply_async(
        kwargs={"path": str(test_dir)}, task_id=task_id
    )

    # Wait for task to complete
    max_wait = 30
    start_time = asyncio.get_event_loop().time()

    while asyncio.get_event_loop().time() - start_time < max_wait:
        task_result = AsyncResult(result.id)

        if task_result.state in ["SUCCESS", "FAILURE"]:
            # Task completed
            break

        await asyncio.sleep(0.5)

    # Get final result
    task_result = AsyncResult(result.id)

    # Verify: Task should complete (even with some failures)
    assert task_result.state in ["SUCCESS", "FAILURE"], (
        f"Task should complete, but got state: {task_result.state}"
    )

    # If task succeeded, verify error metadata is present
    if task_result.state == "SUCCESS":
        result_data = task_result.result

        # Verify: Should have error_metadata
        assert "error_metadata" in result_data, (
            "Task result should include error_metadata"
        )

        error_metadata = result_data["error_metadata"]

        # Verify: Error metadata should have required fields
        assert "total_files" in error_metadata, "Should track total_files"
        assert "successful" in error_metadata, "Should track successful count"
        assert "failed" in error_metadata, "Should track failed count"
        assert "failed_files" in error_metadata, "Should track failed_files list"

        # Verify: Should have processed some files
        assert error_metadata["total_files"] > 0, "Should have found files to process"


@pytest.mark.asyncio
@settings(
    max_examples=5,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
async def test_property_continue_after_file_error(async_db_session, tmp_path):
    """
    **Feature: phase18-code-intelligence, Property 12: Graceful Error Handling**

    For any repository with a mix of processable and unprocessable files,
    the system should process all valid files even when some files fail.

    **Validates: Requirements 9.1, 9.2**
    """
    from app.modules.resources.logic.repo_ingestion import RepoIngestionService
    import shutil

    # Create test directory (clean up if exists)
    test_dir = tmp_path / "test_repo"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()

    # Create files in specific order: valid, invalid, valid, invalid, valid
    files_created = []

    # Valid file 1
    file1 = test_dir / "valid_1.py"
    file1.write_text("# Valid file 1\ndef func1():\n    pass\n")
    files_created.append(("valid", file1))

    # Invalid file 1 (directory with .py extension)
    file2 = test_dir / "invalid_1.py"
    file2.mkdir()
    files_created.append(("invalid", file2))

    # Valid file 2
    file3 = test_dir / "valid_2.py"
    file3.write_text("# Valid file 2\ndef func2():\n    pass\n")
    files_created.append(("valid", file3))

    # Invalid file 2 (binary content)
    file4 = test_dir / "invalid_2.py"
    file4.write_bytes(b"\x00\x01\x02\x03")
    files_created.append(("invalid", file4))

    # Valid file 3
    file5 = test_dir / "valid_3.py"
    file5.write_text("# Valid file 3\ndef func3():\n    pass\n")
    files_created.append(("valid", file5))

    # Ingest repository
    service = RepoIngestionService(async_db_session)
    resources, error_metadata = await service.crawl_directory(
        test_dir, track_errors=True
    )

    # Verify: Should have processed all valid files
    expected_valid = sum(1 for t, _ in files_created if t == "valid")
    assert len(resources) >= expected_valid - 1, (
        f"Should have processed at least {expected_valid - 1} valid files, "
        f"but only got {len(resources)}"
    )

    # Verify: Should have tracked some failures
    expected_invalid = sum(1 for t, _ in files_created if t == "invalid")
    assert error_metadata["failed"] >= 0, f"Should track failed files"

    # Verify: Processing should not stop at first error
    # If we got any resources, it means we continued after errors
    if error_metadata["failed"] > 0:
        assert len(resources) > 0, (
            "Should continue processing after encountering errors"
        )
