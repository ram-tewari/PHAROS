"""File classification logic for code intelligence pipeline."""

from pathlib import Path
from typing import Optional
import re


# File extension mappings for classification
CODE_EXTENSIONS = {
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
    ".scala",
    ".sh",
    ".bash",
}

THEORY_EXTENSIONS = {
    ".pdf",
    ".md",
    ".rst",
    ".tex",
    ".txt",
}

# Academic keywords for THEORY classification
ACADEMIC_KEYWORDS = [
    "abstract",
    "introduction",
    "methodology",
    "results",
    "discussion",
    "conclusion",
    "references",
    "bibliography",
    "citation",
    "research",
    "study",
    "analysis",
    "experiment",
    "hypothesis",
    "theorem",
    "proof",
    "algorithm",
    "dataset",
]

# Governance file patterns
GOVERNANCE_PATTERNS = [
    r"^CONTRIBUTING\.md$",
    r"^CODE_OF_CONDUCT\.md$",
    r"^GOVERNANCE\.md$",
    r"^LICENSE$",
    r"^LICENSE\..*$",
    r"^\.eslintrc.*$",
    r"^\.prettierrc.*$",
    r"^\.editorconfig$",
    r"^\.gitignore$",
    r"^\.dockerignore$",
    r"^Makefile$",
    r"^CMakeLists\.txt$",
    r"^setup\.py$",
    r"^setup\.cfg$",
    r"^pyproject\.toml$",
    r"^package\.json$",
    r"^Cargo\.toml$",
    r"^go\.mod$",
    r"^pom\.xml$",
    r"^build\.gradle$",
]

# Cache compiled regex patterns for performance
_COMPILED_GOVERNANCE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE) for pattern in GOVERNANCE_PATTERNS
]


def classify_file(file_path: Path, content: Optional[str] = None) -> str:
    """
    Classify a file as THEORY, PRACTICE, or GOVERNANCE.

    Classification rules:
    - PRACTICE: Code files (.py, .js, .ts, .rs, .go, .java, etc.)
    - THEORY: Academic documents (.pdf, .md with academic keywords)
    - GOVERNANCE: Policy files (CONTRIBUTING.md, CODE_OF_CONDUCT.md, .eslintrc, etc.)

    Args:
        file_path: Path to the file
        content: Optional file content for content-based classification

    Returns:
        Classification string: "THEORY", "PRACTICE", or "GOVERNANCE"
    """
    file_name = file_path.name
    file_extension = file_path.suffix.lower()

    # Check GOVERNANCE patterns first (most specific)
    if _is_governance_file(file_name):
        return "GOVERNANCE"

    # Check CODE extensions
    if file_extension in CODE_EXTENSIONS:
        return "PRACTICE"

    # Check THEORY extensions with content analysis
    if file_extension in THEORY_EXTENSIONS:
        if content and _has_academic_content(content):
            return "THEORY"
        # If no content provided or no academic keywords, still classify as THEORY
        # for known academic formats like .pdf
        if file_extension in {".pdf", ".tex"}:
            return "THEORY"

    # Default to PRACTICE for unknown file types
    return "PRACTICE"


def _is_governance_file(file_name: str) -> bool:
    """
    Check if a file matches governance patterns.
    Uses cached compiled regex patterns for performance.

    Args:
        file_name: Name of the file

    Returns:
        True if file matches governance patterns
    """
    for pattern in _COMPILED_GOVERNANCE_PATTERNS:
        if pattern.match(file_name):
            return True
    return False


def _has_academic_content(content: str) -> bool:
    """
    Check if content contains academic keywords.

    Args:
        content: File content to analyze

    Returns:
        True if content contains academic keywords
    """
    # Convert to lowercase for case-insensitive matching
    content_lower = content.lower()

    # Count how many academic keywords are present
    keyword_count = sum(1 for keyword in ACADEMIC_KEYWORDS if keyword in content_lower)

    # Require at least 3 academic keywords to classify as THEORY
    return keyword_count >= 3
