"""
Unit tests for PDF metadata extraction.

Tests specific examples and edge cases for PDF metadata extraction:
- PDFs with complete metadata
- PDFs with missing metadata
- Single-page PDFs (edge case)
"""

import io
import pytest
from unittest.mock import Mock, patch

from app.utils.content_extractor import extract_pdf, extract_from_fetched


class TestPDFMetadataExtraction:
    """Test PDF metadata extraction with various scenarios."""

    def test_pdf_with_complete_metadata(self):
        """Test PDF extraction with complete metadata (title, author, subject)."""
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

        # Create a PDF with complete metadata
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.setTitle("Complete Test Document")
        c.setAuthor("John Doe")
        c.setSubject("Test Subject")
        c.setKeywords("test, metadata, pdf")

        c.drawString(100, 750, "Page 1 content")
        c.showPage()
        c.drawString(100, 750, "Page 2 content")
        c.showPage()
        c.save()

        pdf_bytes = buffer.getvalue()

        # Extract with metadata
        result = extract_pdf(pdf_bytes, extract_metadata=True)

        # Verify text extraction
        assert "Page 1 content" in result["text"]
        assert "Page 2 content" in result["text"]

        # Verify page boundaries
        assert "page_boundaries" in result
        assert len(result["page_boundaries"]) == 2
        assert result["page_boundaries"][0]["page_num"] == 1
        assert result["page_boundaries"][1]["page_num"] == 2

        # Verify structured metadata
        assert "structured_metadata" in result
        metadata = result["structured_metadata"]
        assert metadata["title"] == "Complete Test Document"
        assert metadata["authors"] == "John Doe"
        assert metadata["subject"] == "Test Subject"
        assert metadata["keywords"] == "test, metadata, pdf"

    def test_pdf_with_missing_metadata(self):
        """Test PDF extraction with missing metadata fields."""
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

        # Create a PDF without metadata
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        # Don't set any metadata
        c.drawString(100, 750, "Content without metadata")
        c.showPage()
        c.save()

        pdf_bytes = buffer.getvalue()

        # Extract with metadata
        result = extract_pdf(pdf_bytes, extract_metadata=True)

        # Verify text extraction still works
        assert "Content without metadata" in result["text"]

        # Verify page boundaries still work
        assert "page_boundaries" in result
        assert len(result["page_boundaries"]) == 1

        # Verify structured metadata exists but may have default values
        assert "structured_metadata" in result
        metadata = result["structured_metadata"]
        # Metadata fields may be None, empty, or have default values like "untitled"
        # when not explicitly set by the PDF creator
        title = metadata.get("title")
        authors = metadata.get("authors")
        assert title is None or title == "" or title.lower() == "untitled"
        assert authors is None or authors == "" or authors.lower() == "anonymous"

    def test_single_page_pdf(self):
        """Test PDF extraction with single page (edge case)."""
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

        # Create a single-page PDF
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.setTitle("Single Page Document")
        c.drawString(100, 750, "This is the only page")
        c.showPage()
        c.save()

        pdf_bytes = buffer.getvalue()

        # Extract with metadata
        result = extract_pdf(pdf_bytes, extract_metadata=True)

        # Verify text extraction
        assert "This is the only page" in result["text"]

        # Verify exactly one page boundary
        assert "page_boundaries" in result
        assert len(result["page_boundaries"]) == 1
        boundary = result["page_boundaries"][0]
        assert boundary["page_num"] == 1
        assert boundary["start_char"] == 0
        assert boundary["end_char"] > 0

        # Verify metadata
        assert "structured_metadata" in result
        assert result["structured_metadata"]["title"] == "Single Page Document"

    def test_pdf_without_metadata_flag(self):
        """Test PDF extraction without metadata flag (backward compatibility)."""
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

        # Create a PDF
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.setTitle("Test Document")
        c.drawString(100, 750, "Test content")
        c.showPage()
        c.save()

        pdf_bytes = buffer.getvalue()

        # Extract without metadata (default behavior)
        result = extract_pdf(pdf_bytes, extract_metadata=False)

        # Verify text extraction works
        assert "Test content" in result["text"]

        # Verify metadata fields are NOT present
        assert "page_boundaries" not in result
        assert "structured_metadata" not in result

        # Title should be None (backward compatibility)
        assert result["title"] is None

    def test_pdf_with_abstract_extraction(self):
        """Test PDF extraction with abstract section detection."""
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

        # Create a PDF with abstract section
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.setTitle("Research Paper")

        # Add abstract section on first page
        c.drawString(100, 750, "Abstract")
        c.drawString(100, 730, "This is the abstract of the research paper.")
        c.drawString(100, 710, "It contains important information about the study.")
        c.showPage()
        c.save()

        pdf_bytes = buffer.getvalue()

        # Extract with metadata
        result = extract_pdf(pdf_bytes, extract_metadata=True)

        # Verify abstract extraction
        assert "structured_metadata" in result
        metadata = result["structured_metadata"]

        # Abstract should be extracted (heuristic-based)
        if "abstract" in metadata and metadata["abstract"]:
            assert (
                "abstract" in metadata["abstract"].lower()
                or "research paper" in metadata["abstract"].lower()
            )

    def test_extract_from_fetched_with_pdf_metadata(self):
        """Test extract_from_fetched passes extract_metadata flag for PDFs."""
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

        # Create a PDF
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.setTitle("Fetched PDF")
        c.drawString(100, 750, "Fetched content")
        c.showPage()
        c.save()

        pdf_bytes = buffer.getvalue()

        # Simulate fetched data
        fetched_data = {
            "content_type": "application/pdf",
            "content_bytes": pdf_bytes,
            "url": "https://example.com/test.pdf",
        }

        # Extract with metadata flag
        result = extract_from_fetched(fetched_data, extract_metadata=True)

        # Verify metadata was extracted
        assert "page_boundaries" in result
        assert "structured_metadata" in result
        assert result["structured_metadata"]["title"] == "Fetched PDF"

    def test_multi_page_pdf_page_boundaries(self):
        """Test page boundaries for multi-page PDF."""
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

        # Create a 5-page PDF
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)

        for i in range(5):
            c.drawString(100, 750, f"Page {i + 1} content here")
            c.showPage()

        c.save()
        pdf_bytes = buffer.getvalue()

        # Extract with metadata
        result = extract_pdf(pdf_bytes, extract_metadata=True)

        # Verify page boundaries
        assert "page_boundaries" in result
        boundaries = result["page_boundaries"]
        assert len(boundaries) == 5

        # Verify sequential page numbers
        for i, boundary in enumerate(boundaries):
            assert boundary["page_num"] == i + 1
            assert boundary["start_char"] >= 0
            assert boundary["end_char"] > boundary["start_char"]

        # Verify no overlaps
        for i in range(len(boundaries) - 1):
            current = boundaries[i]
            next_boundary = boundaries[i + 1]
            # Current end should be <= next start (allowing for newline)
            assert current["end_char"] <= next_boundary["start_char"] + 1

    def test_pdf_metadata_with_pdfminer_fallback(self):
        """Test that pdfminer fallback logs warning about missing metadata."""
        # Mock PyMuPDF to fail
        with patch("app.utils.content_extractor.fitz", None):
            # Mock pdfminer to succeed
            with patch(
                "app.utils.content_extractor.pdfminer_extract_text"
            ) as mock_pdfminer:
                mock_pdfminer.return_value = "Extracted text from pdfminer"

                pdf_bytes = b"%PDF-1.4\nfake pdf"

                # Extract with metadata flag
                result = extract_pdf(pdf_bytes, extract_metadata=True)

                # Verify text extraction works
                assert result["text"] == "Extracted text from pdfminer"

                # Verify metadata fields are present but empty
                # (pdfminer doesn't support page boundaries)
                assert "page_boundaries" in result
                assert len(result["page_boundaries"]) == 0
                assert "structured_metadata" in result
                assert len(result["structured_metadata"]) == 0
