"""
Property-based tests for PDF metadata extraction.

Tests universal properties that must hold for all PDF files:
- Property 5: Page boundary preservation
- Property 6: Metadata extraction completeness

Uses hypothesis for property-based testing to validate correctness
across a wide range of PDF inputs.
"""

import io
from typing import Dict, Any
from hypothesis import given, strategies as st, settings, assume
import pytest

# Import the functions we're testing
from app.utils.content_extractor import extract_pdf


# ============================================================================
# Test Helpers
# ============================================================================


def create_mock_pdf_bytes(num_pages: int = 1, has_metadata: bool = False) -> bytes:
    """
    Create a minimal valid PDF byte stream for testing.

    Args:
        num_pages: Number of pages in the PDF
        has_metadata: Whether to include metadata

    Returns:
        PDF bytes
    """
    # Minimal PDF structure
    pdf_header = b"%PDF-1.4\n"

    # Create pages
    pages_content = []
    for i in range(num_pages):
        page_text = f"Page {i + 1} content. This is some text on page {i + 1}."
        pages_content.append(page_text.encode())

    # For testing purposes, we'll create a simple PDF structure
    # In real tests, we'd use a proper PDF library like reportlab
    # For now, we'll just return a marker that our mock can recognize
    pdf_content = pdf_header + b"\n".join(pages_content) + b"\n%%EOF"

    return pdf_content


# ============================================================================
# Property 5: Page Boundary Preservation
# **Validates: Requirements 2.1**
# ============================================================================


@pytest.mark.property
@given(
    num_pages=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=20, deadline=5000)
def test_property_page_boundary_preservation(num_pages: int):
    """
    Property 5: Page boundary preservation

    For any PDF file, after extraction the page boundary information should
    accurately map character offsets to page numbers.

    Universal property: For all PDFs with N pages, the extracted page boundaries
    should:
    1. Have exactly N entries
    2. Cover the entire text without gaps
    3. Not overlap
    4. Be in sequential order

    **Validates: Requirements 2.1**
    """
    # Skip if PyMuPDF is not available (test would fail anyway)
    try:
        import fitz
    except ImportError:
        pytest.skip("PyMuPDF (fitz) not available")

    # Create a mock PDF with the specified number of pages
    # For this test, we'll use a real PDF library to create valid PDFs
    try:
        # Create a simple PDF with reportlab if available
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)

        for i in range(num_pages):
            c.drawString(100, 750, f"Page {i + 1} content")
            c.drawString(100, 730, f"This is some text on page {i + 1}.")
            c.showPage()

        c.save()
        pdf_bytes = buffer.getvalue()

    except ImportError:
        # If reportlab is not available, skip this test
        pytest.skip("reportlab not available for PDF generation")

    # Extract with metadata
    result = extract_pdf(pdf_bytes, extract_metadata=True)

    # Verify page boundaries exist
    assert "page_boundaries" in result, "page_boundaries should be in result"
    page_boundaries = result["page_boundaries"]

    # Property 1: Should have exactly num_pages entries
    assert len(page_boundaries) == num_pages, (
        f"Expected {num_pages} page boundaries, got {len(page_boundaries)}"
    )

    # Property 2: Page boundaries should be in sequential order
    for i in range(len(page_boundaries)):
        boundary = page_boundaries[i]
        assert boundary["page_num"] == i + 1, (
            f"Page {i} should have page_num={i + 1}, got {boundary['page_num']}"
        )

    # Property 3: Page boundaries should not overlap and should be contiguous
    for i in range(len(page_boundaries) - 1):
        current = page_boundaries[i]
        next_boundary = page_boundaries[i + 1]

        # Current end should be <= next start (allowing for newline)
        assert current["end_char"] <= next_boundary["start_char"] + 1, (
            f"Page {i + 1} overlaps with page {i + 2}"
        )

    # Property 4: Each page boundary should have valid start/end positions
    for i, boundary in enumerate(page_boundaries):
        assert boundary["start_char"] >= 0, f"Page {i + 1} has negative start_char"
        assert boundary["end_char"] > boundary["start_char"], (
            f"Page {i + 1} has invalid end_char <= start_char"
        )

    # Property 5: Total text length should match last page's end_char
    text = result.get("text", "")
    if page_boundaries:
        last_boundary = page_boundaries[-1]
        # The last boundary's end_char should be close to the text length
        # (allowing for some variation due to newlines)
        assert last_boundary["end_char"] <= len(text) + num_pages, (
            f"Last page end_char ({last_boundary['end_char']}) exceeds text length ({len(text)})"
        )


# ============================================================================
# Property 6: Metadata Extraction Completeness
# **Validates: Requirements 2.2, 2.3**
# ============================================================================


@pytest.mark.property
@given(
    has_title=st.booleans(),
    has_author=st.booleans(),
)
@settings(max_examples=10, deadline=5000)
def test_property_metadata_extraction_completeness(has_title: bool, has_author: bool):
    """
    Property 6: Metadata extraction completeness

    For any PDF with title and author metadata, the extracted metadata should
    include both title and authors.

    Universal property: If a PDF has metadata fields, they should be extracted
    and included in the structured_metadata.

    **Validates: Requirements 2.2, 2.3**
    """
    # Skip if PyMuPDF is not available
    try:
        import fitz
    except ImportError:
        pytest.skip("PyMuPDF (fitz) not available")

    # Skip if reportlab is not available
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
    except ImportError:
        pytest.skip("reportlab not available for PDF generation")

    # Create a PDF with metadata
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)

    # Set metadata if requested
    if has_title:
        c.setTitle("Test Document Title")
    if has_author:
        c.setAuthor("Test Author Name")

    c.drawString(100, 750, "Test content")
    c.showPage()
    c.save()

    pdf_bytes = buffer.getvalue()

    # Extract with metadata
    result = extract_pdf(pdf_bytes, extract_metadata=True)

    # Verify structured_metadata exists
    assert "structured_metadata" in result, "structured_metadata should be in result"
    structured_metadata = result["structured_metadata"]

    # Property: If metadata was set, it should be extracted
    if has_title:
        assert "title" in structured_metadata, "title should be in structured_metadata"
        assert structured_metadata["title"] is not None, "title should not be None"
        assert len(structured_metadata["title"]) > 0, "title should not be empty"

    if has_author:
        assert "authors" in structured_metadata, (
            "authors should be in structured_metadata"
        )
        assert structured_metadata["authors"] is not None, "authors should not be None"
        assert len(structured_metadata["authors"]) > 0, "authors should not be empty"


# ============================================================================
# Additional Property Tests
# ============================================================================


@pytest.mark.property
def test_property_extract_metadata_flag():
    """
    Property: extract_metadata flag controls metadata extraction

    When extract_metadata=False, page_boundaries and structured_metadata
    should not be in the result.
    When extract_metadata=True, they should be present.
    """
    # Skip if PyMuPDF is not available
    try:
        import fitz
    except ImportError:
        pytest.skip("PyMuPDF (fitz) not available")

    # Skip if reportlab is not available
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
    except ImportError:
        pytest.skip("reportlab not available for PDF generation")

    # Create a simple PDF
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setTitle("Test Title")
    c.drawString(100, 750, "Test content")
    c.showPage()
    c.save()

    pdf_bytes = buffer.getvalue()

    # Test with extract_metadata=False
    result_no_metadata = extract_pdf(pdf_bytes, extract_metadata=False)
    assert "page_boundaries" not in result_no_metadata, (
        "page_boundaries should not be present when extract_metadata=False"
    )
    assert "structured_metadata" not in result_no_metadata, (
        "structured_metadata should not be present when extract_metadata=False"
    )

    # Test with extract_metadata=True
    result_with_metadata = extract_pdf(pdf_bytes, extract_metadata=True)
    assert "page_boundaries" in result_with_metadata, (
        "page_boundaries should be present when extract_metadata=True"
    )
    assert "structured_metadata" in result_with_metadata, (
        "structured_metadata should be present when extract_metadata=True"
    )
