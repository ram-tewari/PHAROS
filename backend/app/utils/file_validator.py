"""
File Upload Validation for Security

This module provides file upload validation including:
- File extension allowlisting
- Content-type validation using magic numbers
- File size limits
- Metadata stripping from uploaded files

Related files:
- app/config/settings.py: Configuration for upload limits
"""

import logging
import os
import struct
from pathlib import Path
from typing import Tuple, Optional

from ..config.settings import get_settings

logger = logging.getLogger(__name__)


# Default allowed file extensions for uploads
DEFAULT_ALLOWED_EXTENSIONS = {
    # Documents
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".rtf",
    ".odt",
    # Code
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".cs",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
    # Markup
    ".html",
    ".css",
    ".scss",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".md",
    # Data
    ".csv",
    ".tsv",
    ".jsonl",
    ".parquet",
    # Images (for metadata extraction)
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".tiff",
    ".webp",
}

# Magic numbers for common file types (first bytes)
MAGIC_NUMBERS = {
    # Images
    b"\x89PNG\r\n\x1a\n": ".png",
    b"\xff\xd8\xff": ".jpg",
    b"GIF87a": ".gif",
    b"GIF89a": ".gif",
    b"BM": ".bmp",
    b"II\x2a\x00": ".tiff",
    b"MM\x00\x2a": ".tiff",
    b"RIFF": ".webp",  # Check WebP
    # Documents
    b"%PDF": ".pdf",
    b"\xd0\xcf\x11\xe0": ".doc",  # OLE compound document
    # Code/Markup (text-based, checked by extension)
    None: ".txt",  # Default for text files
}

# Default maximum file size (50MB)
DEFAULT_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


class FileUploadValidator:
    """Validator for file uploads with security checks."""

    def __init__(
        self,
        allowed_extensions: set[str] | None = None,
        max_file_size: int | None = None,
        blocked_extensions: set[str] | None = None,
    ):
        """Initialize the file upload validator.

        Args:
            allowed_extensions: Set of allowed file extensions (with dot)
            max_file_size: Maximum file size in bytes
            blocked_extensions: Set of explicitly blocked extensions
        """
        settings = get_settings()

        self.allowed_extensions = (
            allowed_extensions
            or getattr(settings, "ALLOWED_FILE_EXTENSIONS", None)
            or DEFAULT_ALLOWED_EXTENSIONS
        )

        self.max_file_size = (
            max_file_size
            or getattr(settings, "MAX_FILE_UPLOAD_SIZE", None)
            or DEFAULT_MAX_FILE_SIZE
        )

        self.blocked_extensions = (
            blocked_extensions
            or getattr(settings, "BLOCKED_FILE_EXTENSIONS", None)
            or set()
        )

    def validate_file(
        self,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> Tuple[bool, str]:
        """
        Validate a file upload.

        Args:
            filename: Original filename from upload
            content: File content bytes
            content_type: Optional content-type header

        Returns:
            Tuple of (is_valid: bool, error_message: str)
        """
        # Check file extension
        ext = Path(filename).suffix.lower()

        # Check if extension is blocked
        if ext in self.blocked_extensions:
            return False, f"File extension '{ext}' is not allowed"

        # Check if extension is allowed
        if ext not in self.allowed_extensions:
            return False, (
                f"File extension '{ext}' is not in the allowed list. "
                f"Allowed extensions: {', '.join(sorted(self.allowed_extensions))}"
            )

        # Check file size
        if len(content) > self.max_file_size:
            max_mb = self.max_file_size / (1024 * 1024)
            actual_mb = len(content) / (1024 * 1024)
            return False, (
                f"File size ({actual_mb:.1f} MB) exceeds maximum allowed "
                f"({max_mb:.1f} MB)"
            )

        # Validate content type if provided
        if content_type:
            if not self._is_content_type_allowed(content_type, ext):
                logger.warning(
                    f"Content-Type mismatch for '{filename}': "
                    f"declared={content_type}, extension={ext}"
                )
                # Warning but don't fail - rely on magic number validation

        # Validate magic number
        magic_valid, actual_ext = self._validate_magic_number(content, ext)
        if not magic_valid:
            return False, (
                f"File content does not match extension. "
                f"Expected {ext}, detected {actual_ext or 'unknown'}"
            )

        return True, ""

    def _validate_magic_number(
        self, content: bytes, expected_ext: str
    ) -> Tuple[bool, str | None]:
        """
        Validate file magic number against expected extension.

        Args:
            content: File content bytes
            expected_ext: Expected file extension

        Returns:
            Tuple of (is_valid: bool, detected_ext: str | None)
        """
        if len(content) < 4:
            # Not enough bytes for magic number check
            return True, None

        # Check against known magic numbers
        for magic, ext in MAGIC_NUMBERS.items():
            if magic is None:
                continue  # Skip text file default
            if content[: len(magic)] == magic:
                return ext == expected_ext, ext

        # No matching magic number - could be text file
        # Text files don't have magic numbers
        text_extensions = {
            ".txt",
            ".md",
            ".py",
            ".js",
            ".ts",
            ".json",
            ".yaml",
            ".yml",
            ".xml",
            ".csv",
            ".html",
            ".css",
            ".scss",
        }
        if expected_ext in text_extensions:
            return True, "text"

        return True, None  # Allow unknown files

    def _is_content_type_allowed(self, content_type: str, extension: str) -> bool:
        """
        Check if content-type is consistent with extension.

        Args:
            content_type: The content-type header value
            extension: The file extension

        Returns:
            True if content-type is consistent with extension
        """
        # Map extensions to expected content types
        expected_types = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
            ".webp": "image/webp",
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".ts": "application/typescript",
            ".json": "application/json",
            ".xml": "application/xml",
            ".csv": "text/csv",
        }

        expected = expected_types.get(extension)
        if not expected:
            return True  # No expected type for this extension

        # Check if content-type matches (allow subtypes)
        return content_type.startswith(expected.split("/")[0] + "/")

    def strip_metadata(self, content: bytes, extension: str) -> bytes:
        """
        Strip metadata from file content.

        For now, this is a placeholder. Full implementation would require
        library-specific metadata stripping (e.g., piexif for images,
        python-docx for documents).

        Args:
            content: File content bytes
            extension: File extension

        Returns:
            Content with metadata stripped (if applicable)
        """
        # TODO: Implement actual metadata stripping
        # For images: use piexif.remove(filepath)
        # For PDFs: use pypdf
        # For documents: use python-docx, openpyxl, etc.

        logger.debug(
            f"Metadata stripping requested for {extension} (not yet implemented)"
        )
        return content


# Global validator instance
file_upload_validator = FileUploadValidator()


def validate_file_upload(
    filename: str,
    content: bytes,
    content_type: str | None = None,
) -> Tuple[bool, str]:
    """
    Validate a file upload using the global validator.

    Args:
        filename: Original filename from upload
        content: File content bytes
        content_type: Optional content-type header

    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    return file_upload_validator.validate_file(filename, content, content_type)


def strip_file_metadata(content: bytes, extension: str) -> bytes:
    """
    Strip metadata from file content.

    Args:
        content: File content bytes
        extension: File extension

    Returns:
        Content with metadata stripped
    """
    return file_upload_validator.strip_metadata(content, extension)
