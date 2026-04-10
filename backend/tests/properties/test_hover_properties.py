"""
Property-based tests for Hover Information API (Phase 20).

**Feature: phase20-frontend-backend-infrastructure**

These tests verify universal properties of the hover information API
using property-based testing with hypothesis.
"""

import pytest
import time
from uuid import uuid4
from hypothesis import given, strategies as st, settings, HealthCheck
from fastapi.testclient import TestClient

from app.database.models import Resource, DocumentChunk


# ============================================================================
# Code Sample Generators for Different Languages
# ============================================================================


def generate_python_code(function_name: str) -> str:
    """Generate valid Python code with a function."""
    return f'''def {function_name}(a, b):
    """Calculate the sum of two numbers.
    
    Args:
        a: First number
        b: Second number
    
    Returns:
        Sum of a and b
    """
    return a + b

class Calculator:
    """A simple calculator class."""
    
    def multiply(self, x, y):
        """Multiply two numbers."""
        return x * y
'''


def generate_javascript_code(function_name: str) -> str:
    """Generate valid JavaScript code with a function."""
    return f"""/**
 * Calculate the sum of two numbers
 * @param {{number}} a - First number
 * @param {{number}} b - Second number
 * @returns {{number}} Sum of a and b
 */
function {function_name}(a, b) {{
    return a + b;
}}

class Calculator {{
    /**
     * Multiply two numbers
     */
    multiply(x, y) {{
        return x * y;
    }}
}}
"""


def generate_typescript_code(function_name: str) -> str:
    """Generate valid TypeScript code with a function."""
    return f"""/**
 * Calculate the sum of two numbers
 * @param a - First number
 * @param b - Second number
 * @returns Sum of a and b
 */
function {function_name}(a: number, b: number): number {{
    return a + b;
}}

class Calculator {{
    /**
     * Multiply two numbers
     */
    multiply(x: number, y: number): number {{
        return x * y;
    }}
}}
"""


def generate_java_code(function_name: str) -> str:
    """Generate valid Java code with a method."""
    # Java requires PascalCase for class names
    class_name = function_name.capitalize() + "Util"
    return f"""/**
 * Utility class for calculations
 */
public class {class_name} {{
    /**
     * Calculate the sum of two numbers
     * @param a First number
     * @param b Second number
     * @return Sum of a and b
     */
    public static int {function_name}(int a, int b) {{
        return a + b;
    }}
    
    /**
     * Multiply two numbers
     */
    public static int multiply(int x, int y) {{
        return x * y;
    }}
}}
"""


def generate_cpp_code(function_name: str) -> str:
    """Generate valid C++ code with a function."""
    return f"""/**
 * Calculate the sum of two numbers
 * @param a First number
 * @param b Second number
 * @return Sum of a and b
 */
int {function_name}(int a, int b) {{
    return a + b;
}}

class Calculator {{
public:
    /**
     * Multiply two numbers
     */
    int multiply(int x, int y) {{
        return x * y;
    }}
}};
"""


def generate_go_code(function_name: str) -> str:
    """Generate valid Go code with a function."""
    # Go requires PascalCase for exported functions
    exported_name = function_name.capitalize()
    return f"""package main

// {exported_name} calculates the sum of two numbers
func {exported_name}(a int, b int) int {{
    return a + b
}}

// Calculator is a simple calculator struct
type Calculator struct {{}}

// Multiply multiplies two numbers
func (c *Calculator) Multiply(x int, y int) int {{
    return x * y
}}
"""


def generate_rust_code(function_name: str) -> str:
    """Generate valid Rust code with a function."""
    return f"""/// Calculate the sum of two numbers
///
/// # Arguments
/// * `a` - First number
/// * `b` - Second number
///
/// # Returns
/// Sum of a and b
pub fn {function_name}(a: i32, b: i32) -> i32 {{
    a + b
}}

/// A simple calculator struct
pub struct Calculator;

impl Calculator {{
    /// Multiply two numbers
    pub fn multiply(&self, x: i32, y: i32) -> i32 {{
        x * y
    }}
}}
"""


# Language configuration mapping
LANGUAGE_CONFIG = {
    "python": {
        "extension": ".py",
        "generator": generate_python_code,
        "function_line": 1,  # Line where function definition starts
        "function_column": 4,  # Column where function name starts
    },
    "javascript": {
        "extension": ".js",
        "generator": generate_javascript_code,
        "function_line": 7,
        "function_column": 9,
    },
    "typescript": {
        "extension": ".ts",
        "generator": generate_typescript_code,
        "function_line": 7,
        "function_column": 9,
    },
    "java": {
        "extension": ".java",
        "generator": generate_java_code,
        "function_line": 10,
        "function_column": 23,
    },
    "cpp": {
        "extension": ".cpp",
        "generator": generate_cpp_code,
        "function_line": 6,
        "function_column": 4,
    },
    "go": {
        "extension": ".go",
        "generator": generate_go_code,
        "function_line": 4,
        "function_column": 5,
    },
    "rust": {
        "extension": ".rs",
        "generator": generate_rust_code,
        "function_line": 9,
        "function_column": 7,
    },
}


# ============================================================================
# Property 1: Hover Response Time
# **Validates: Requirements 1.1**
# ============================================================================


@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    language=st.sampled_from(
        ["python", "javascript", "typescript", "java", "cpp", "go", "rust"]
    ),
    function_name=st.text(
        alphabet=st.characters(whitelist_categories=("Ll",)), min_size=5, max_size=15
    ).filter(lambda x: x.isidentifier() and not x.startswith("_")),
    line_offset=st.integers(min_value=0, max_value=5),
    column_offset=st.integers(min_value=0, max_value=10),
)
def test_property_hover_response_time(
    client, db_session, language, function_name, line_offset, column_offset
):
    """
    **Feature: phase20-frontend-backend-infrastructure, Property 1: Hover response time**

    For any valid code position (file path, line, column), requesting hover information
    should return a response within 100ms.

    **Validates: Requirements 1.1**
    """
    # Get language configuration
    config = LANGUAGE_CONFIG[language]

    # Generate code sample for the language
    code_content = config["generator"](function_name)

    # Create test resource
    file_name = f"test_{function_name}{config['extension']}"
    resource = Resource(
        id=uuid4(),
        title=file_name,
        type="code",
        metadata={"language": language, "path": file_name},
    )
    db_session.add(resource)
    db_session.flush()

    # Create document chunk with the code
    chunk = DocumentChunk(
        id=uuid4(),
        resource_id=resource.id,
        content=code_content,
        chunk_index=0,
        chunk_metadata={
            "start_line": 1,
            "end_line": code_content.count("\n") + 1,
            "language": language,
        },
    )
    db_session.add(chunk)
    db_session.commit()

    # Calculate valid position within the code
    # Use the known function line from config, with small random offsets
    target_line = config["function_line"] + line_offset
    target_column = config["function_column"] + column_offset

    # Ensure line is within bounds
    total_lines = code_content.count("\n") + 1
    if target_line > total_lines:
        target_line = config["function_line"]

    # Measure response time
    start_time = time.time()

    response = client.get(
        "/api/graph/code/hover",
        params={
            "file_path": file_name,
            "line": target_line,
            "column": target_column,
            "resource_id": str(resource.id),
        },
    )

    elapsed_time = time.time() - start_time

    # Verify: Response should be successful
    assert response.status_code == 200, (
        f"Hover request failed with status {response.status_code} for {language} "
        f"at line {target_line}, column {target_column}"
    )

    # Verify: Response time should be under 100ms (0.1 seconds)
    assert elapsed_time < 0.1, (
        f"Hover response time exceeded 100ms: {elapsed_time * 1000:.1f}ms "
        f"for {language} file at line {target_line}, column {target_column}. "
        f"Target: <100ms"
    )

    # Verify: Response should have valid structure
    data = response.json()
    assert data is not None, "Hover response should not be None"
    assert "symbol_name" in data, "Response should have symbol_name field"
    assert "symbol_type" in data, "Response should have symbol_type field"
    assert "definition_location" in data, (
        "Response should have definition_location field"
    )
    assert "documentation" in data, "Response should have documentation field"
    assert "context_lines" in data, "Response should have context_lines field"
    assert "related_chunks" in data, "Response should have related_chunks field"


@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    language=st.sampled_from(
        ["python", "javascript", "typescript", "java", "cpp", "go", "rust"]
    ),
    line=st.integers(min_value=1, max_value=100),
    column=st.integers(min_value=0, max_value=200),
)
def test_property_hover_response_time_random_positions(
    client, db_session, language, line, column
):
    """
    **Feature: phase20-frontend-backend-infrastructure, Property 1: Hover response time**

    For any valid code position with random line and column numbers,
    requesting hover information should return a response within 100ms.

    This test validates performance across a wider range of positions,
    including positions that may not contain symbols.

    **Validates: Requirements 1.1**
    """
    # Get language configuration
    config = LANGUAGE_CONFIG[language]

    # Generate code sample with a standard function name
    code_content = config["generator"]("calculate")

    # Create test resource
    file_name = f"test_perf{config['extension']}"
    resource = Resource(
        id=uuid4(),
        title=file_name,
        type="code",
        metadata={"language": language, "path": file_name},
    )
    db_session.add(resource)
    db_session.flush()

    # Create document chunk with the code
    total_lines = code_content.count("\n") + 1
    chunk = DocumentChunk(
        id=uuid4(),
        resource_id=resource.id,
        content=code_content,
        chunk_index=0,
        chunk_metadata={"start_line": 1, "end_line": total_lines, "language": language},
    )
    db_session.add(chunk)
    db_session.commit()

    # Constrain line to be within the actual code bounds
    target_line = min(line, total_lines)

    # Measure response time
    start_time = time.time()

    response = client.get(
        "/api/graph/code/hover",
        params={
            "file_path": file_name,
            "line": target_line,
            "column": column,
            "resource_id": str(resource.id),
        },
    )

    elapsed_time = time.time() - start_time

    # Verify: Response should be successful
    assert response.status_code == 200, (
        f"Hover request failed with status {response.status_code} for {language} "
        f"at line {target_line}, column {column}"
    )

    # Verify: Response time should be under 100ms (0.1 seconds)
    # This is the critical property being tested
    assert elapsed_time < 0.1, (
        f"Hover response time exceeded 100ms: {elapsed_time * 1000:.1f}ms "
        f"for {language} file at line {target_line}, column {column}. "
        f"Target: <100ms. This violates the performance requirement."
    )

    # Verify: Response should be valid JSON with expected structure
    data = response.json()
    assert data is not None, "Hover response should not be None"
    assert isinstance(data, dict), "Hover response should be a dictionary"


# ============================================================================
# Property 4: Multi-language Support
# **Validates: Requirements 1.5**
# ============================================================================


@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    language=st.sampled_from(
        ["python", "javascript", "typescript", "java", "cpp", "go", "rust"]
    ),
    function_name=st.text(
        alphabet=st.characters(whitelist_categories=("Ll",)), min_size=5, max_size=15
    ).filter(lambda x: x.isidentifier() and not x.startswith("_")),
)
def test_property_multi_language_support(client, db_session, language, function_name):
    """
    **Feature: phase20-frontend-backend-infrastructure, Property 4: Multi-language support**

    For any code file in Python, JavaScript, TypeScript, Java, C++, Go, or Rust,
    hover information should be successfully extracted.

    **Validates: Requirements 1.5**
    """
    # Get language configuration
    config = LANGUAGE_CONFIG[language]

    # Generate code sample for the language
    code_content = config["generator"](function_name)

    # Create test resource
    file_name = f"test_{function_name}{config['extension']}"
    resource = Resource(
        id=uuid4(),
        title=file_name,
        type="code",
        metadata={"language": language, "path": file_name},
    )
    db_session.add(resource)
    db_session.flush()

    # Create document chunk with the code
    chunk = DocumentChunk(
        id=uuid4(),
        resource_id=resource.id,
        content=code_content,
        chunk_index=0,
        chunk_metadata={
            "start_line": 1,
            "end_line": code_content.count("\n") + 1,
            "language": language,
        },
    )
    db_session.add(chunk)
    db_session.commit()

    # Request hover info for function definition
    response = client.get(
        "/api/graph/code/hover",
        params={
            "file_path": file_name,
            "line": config["function_line"],
            "column": config["function_column"],
            "resource_id": str(resource.id),
        },
    )

    # Verify: Response should be successful
    assert response.status_code == 200, (
        f"Hover request for {language} file failed with status {response.status_code}"
    )

    data = response.json()

    # Verify: Symbol information should be extracted
    # For all languages, we should at least get some hover information
    # The symbol_name might vary based on language parsing, but we should get a response
    assert data is not None, f"Hover response should not be None for {language}"

    # Verify: Response has the expected structure
    assert "symbol_name" in data, (
        f"Response should have symbol_name field for {language}"
    )
    assert "symbol_type" in data, (
        f"Response should have symbol_type field for {language}"
    )
    assert "definition_location" in data, (
        f"Response should have definition_location field for {language}"
    )
    assert "documentation" in data, (
        f"Response should have documentation field for {language}"
    )
    assert "context_lines" in data, (
        f"Response should have context_lines field for {language}"
    )
    assert "related_chunks" in data, (
        f"Response should have related_chunks field for {language}"
    )

    # Verify: If symbol was found, it should have meaningful data
    if data["symbol_name"] is not None:
        # Symbol name should be a non-empty string
        assert isinstance(data["symbol_name"], str), (
            f"Symbol name should be a string for {language}"
        )
        assert len(data["symbol_name"]) > 0, (
            f"Symbol name should not be empty for {language}"
        )

        # Symbol type should be a valid type
        if data["symbol_type"] is not None:
            assert isinstance(data["symbol_type"], str), (
                f"Symbol type should be a string for {language}"
            )
            assert data["symbol_type"] in [
                "function",
                "class",
                "method",
                "variable",
                "struct",
                "interface",
            ], (
                f"Symbol type should be a valid type for {language}, got {data['symbol_type']}"
            )

        # Definition location should have line number
        if data["definition_location"] is not None:
            assert "line" in data["definition_location"], (
                f"Definition location should have line number for {language}"
            )
            assert isinstance(data["definition_location"]["line"], int), (
                f"Definition line should be an integer for {language}"
            )
            assert data["definition_location"]["line"] > 0, (
                f"Definition line should be positive for {language}"
            )

    # Verify: Context lines should be provided
    assert isinstance(data["context_lines"], list), (
        f"Context lines should be a list for {language}"
    )

    # Verify: Related chunks should be a list (may be empty)
    assert isinstance(data["related_chunks"], list), (
        f"Related chunks should be a list for {language}"
    )


@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    language=st.sampled_from(
        ["python", "javascript", "typescript", "java", "cpp", "go", "rust"]
    )
)
def test_property_multi_language_class_support(client, db_session, language):
    """
    **Feature: phase20-frontend-backend-infrastructure, Property 4: Multi-language support**

    For any code file with class definitions in supported languages,
    hover information should successfully extract class information.

    **Validates: Requirements 1.5**
    """
    # Get language configuration
    config = LANGUAGE_CONFIG[language]

    # Generate code sample with a standard function name
    code_content = config["generator"]("calculate")

    # Create test resource
    file_name = f"test_class{config['extension']}"
    resource = Resource(
        id=uuid4(),
        title=file_name,
        type="code",
        metadata={"language": language, "path": file_name},
    )
    db_session.add(resource)
    db_session.flush()

    # Create document chunk with the code
    chunk = DocumentChunk(
        id=uuid4(),
        resource_id=resource.id,
        content=code_content,
        chunk_index=0,
        chunk_metadata={
            "start_line": 1,
            "end_line": code_content.count("\n") + 1,
            "language": language,
        },
    )
    db_session.add(chunk)
    db_session.commit()

    # Find the line with class/struct definition
    lines = code_content.split("\n")
    class_line = None
    class_column = 0

    for i, line in enumerate(lines, start=1):
        if language in ["python", "javascript", "typescript", "cpp"]:
            if "class Calculator" in line or "class {" in line:
                class_line = i
                class_column = (
                    line.index("Calculator")
                    if "Calculator" in line
                    else line.index("class") + 6
                )
                break
        elif language == "java":
            if "class" in line and "public" in line:
                class_line = i
                class_column = line.index("class") + 6
                break
        elif language == "go":
            if "type Calculator" in line:
                class_line = i
                class_column = line.index("Calculator")
                break
        elif language == "rust":
            if "struct Calculator" in line:
                class_line = i
                class_column = line.index("Calculator")
                break

    # If we found a class definition, test hover on it
    if class_line is not None:
        response = client.get(
            "/api/graph/code/hover",
            params={
                "file_path": file_name,
                "line": class_line,
                "column": class_column,
                "resource_id": str(resource.id),
            },
        )

        # Verify: Response should be successful
        assert response.status_code == 200, (
            f"Hover request for {language} class failed with status {response.status_code}"
        )

        data = response.json()

        # Verify: Response structure is valid
        assert data is not None, (
            f"Hover response should not be None for {language} class"
        )
        assert "symbol_name" in data, (
            f"Response should have symbol_name field for {language} class"
        )
        assert "symbol_type" in data, (
            f"Response should have symbol_type field for {language} class"
        )


@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    language=st.sampled_from(
        ["python", "javascript", "typescript", "java", "cpp", "go", "rust"]
    )
)
def test_property_multi_language_invalid_position(client, db_session, language):
    """
    **Feature: phase20-frontend-backend-infrastructure, Property 4: Multi-language support**

    For any code file in supported languages, requesting hover at an invalid position
    should return empty context gracefully (not error).

    **Validates: Requirements 1.4, 1.5**
    """
    # Get language configuration
    config = LANGUAGE_CONFIG[language]

    # Generate code sample
    code_content = config["generator"]("calculate")

    # Create test resource
    file_name = f"test_invalid{config['extension']}"
    resource = Resource(
        id=uuid4(),
        title=file_name,
        type="code",
        metadata={"language": language, "path": file_name},
    )
    db_session.add(resource)
    db_session.flush()

    # Create document chunk with the code
    chunk = DocumentChunk(
        id=uuid4(),
        resource_id=resource.id,
        content=code_content,
        chunk_index=0,
        chunk_metadata={
            "start_line": 1,
            "end_line": code_content.count("\n") + 1,
            "language": language,
        },
    )
    db_session.add(chunk)
    db_session.commit()

    # Request hover info at an invalid position (way beyond the file)
    response = client.get(
        "/api/graph/code/hover",
        params={
            "file_path": file_name,
            "line": 9999,  # Invalid line
            "column": 0,
            "resource_id": str(resource.id),
        },
    )

    # Verify: Response should still be successful (200), not error
    assert response.status_code == 200, (
        f"Hover request at invalid position for {language} should return 200, "
        f"got {response.status_code}"
    )

    data = response.json()

    # Verify: Should return empty context
    assert data["symbol_name"] is None, (
        f"Symbol name should be None for invalid position in {language}"
    )
    assert data["symbol_type"] is None, (
        f"Symbol type should be None for invalid position in {language}"
    )
    assert data["definition_location"] is None, (
        f"Definition location should be None for invalid position in {language}"
    )
