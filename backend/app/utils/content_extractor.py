"""
Neo Alexandria 2.0 - Content Extraction and Processing

This module provides comprehensive content extraction capabilities for Neo Alexandria 2.0.
It handles web content extraction, PDF processing, and content archiving with support
for various formats and intelligent content cleaning.

Related files:
- app/services/resource_service.py: Uses content extraction during URL ingestion
- app/utils/text_processor.py: Processes extracted text for quality analysis
- app/config/settings.py: Configuration for content extraction settings
- app/shared/circuit_breaker.py: Circuit breaker for resilience

Features:
- Web content extraction with readability processing
- PDF text extraction using multiple backends (PyMuPDF, pdfminer)
- Content archiving with metadata preservation
- Intelligent content cleaning and normalization
- Error handling and fallback mechanisms
- Circuit breaker protection for external URL fetching
- Support for various content types and formats
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlparse
from datetime import datetime, timezone

import io
import json
import logging
import httpx
from bs4 import BeautifulSoup
from slugify import slugify

# Circuit breaker for resilience
try:
    import pybreaker
    from ..shared.circuit_breaker import http_content_breaker

    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False
    http_content_breaker = None

try:
    from readability import Document  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    Document = None  # type: ignore

try:  # PDF extraction primary
    import fitz  # type: ignore  # PyMuPDF
except Exception:  # pragma: no cover - optional
    fitz = None  # type: ignore

try:  # PDF extraction fallback
    from pdfminer.high_level import extract_text as pdfminer_extract_text  # type: ignore
except Exception:  # pragma: no cover - optional
    pdfminer_extract_text = None  # type: ignore

logger = logging.getLogger(__name__)

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _do_fetch_url(url: str, timeout: float = 10.0) -> Dict[str, Any]:
    """Internal fetch implementation without circuit breaker."""
    with httpx.Client(
        headers={"User-Agent": DESKTOP_UA},
        follow_redirects=True,
        timeout=timeout,
    ) as client:
        resp = client.get(url)
        # Raise for status, but let tests capture original message
        try:
            resp.raise_for_status()
        except Exception as exc:
            raise ValueError(f"Failed to fetch URL: {exc}") from exc
        # Normalize headers to a plain dict for robustness in tests
        raw_headers = getattr(resp, "headers", None)
        if isinstance(raw_headers, dict):
            headers_norm: Dict[str, Any] = raw_headers
        else:
            try:
                headers_norm = (
                    dict(raw_headers.items()) if hasattr(raw_headers, "items") else {}
                )
            except Exception:
                headers_norm = {}
        content_type = (headers_norm.get("Content-Type") or "").lower()
        data: Dict[str, Any] = {
            "url": str(resp.url),
            "status": resp.status_code,
            "headers": headers_norm,
            "content_bytes": resp.content,
            "content_type": content_type,
        }
        # Back-compat: expose html field for HTML responses and always include for tests
        if "text/html" in content_type or content_type.startswith("text/"):
            data["html"] = resp.text
        else:
            # Always include html field even for non-HTML to avoid KeyError in tests
            data["html"] = resp.text if hasattr(resp, "text") else ""
        return data


def fetch_url(url: str, timeout: float = 10.0) -> Dict[str, Any]:
    """Fetch a URL using httpx with sane defaults and circuit breaker protection.

    Returns a dict with final URL, status code, headers, raw content bytes, and HTML text when applicable.
    Raises ValueError on network or HTTP errors.

    The circuit breaker opens after 3 consecutive failures and attempts
    recovery after 60 seconds to prevent cascading failures.
    """
    try:
        if CIRCUIT_BREAKER_AVAILABLE and http_content_breaker is not None:
            # Use circuit breaker protection
            return http_content_breaker.call(_do_fetch_url, url, timeout)
        else:
            # No circuit breaker available, call directly
            return _do_fetch_url(url, timeout)
    except (
        pybreaker.CircuitBreakerError if CIRCUIT_BREAKER_AVAILABLE else Exception
    ) as e:
        logger.error(f"Circuit breaker open for URL fetching, failing fast: {url}")
        raise ValueError(
            f"Service temporarily unavailable (circuit breaker open): {url}"
        ) from e
    except (
        httpx.HTTPError,
        httpx.RequestError,
        Exception,
    ) as exc:  # pragma: no cover - error path
        logger.warning("Fetch failed for %s: %s", url, exc)
        # Preserve message for tests expecting specific substrings
        raise ValueError(f"Failed to fetch URL: {exc}")


def _strip_scripts_and_styles(soup: BeautifulSoup) -> None:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()


def extract_text(html: str) -> Dict[str, Any]:
    """Extract title and main text content from HTML.

    Prefer readability-lxml if available; fallback to BeautifulSoup-only.
    Always strip scripts/styles and return plain text.

    If readability extracts too little content (< 500 words), fall back to
    full BeautifulSoup extraction to capture more complete content.
    """
    title: str | None = None
    text: str = ""
    readability_text: str = ""

    if Document is not None:
        try:
            doc = Document(html)
            title = doc.short_title() or None
            summary_html = doc.summary(html_partial=True)
            soup = BeautifulSoup(summary_html, "html.parser")
            _strip_scripts_and_styles(soup)
            readability_text = soup.get_text("\n", strip=True)

            # Check if readability extracted enough content
            # If less than 500 words, it might be too aggressive
            word_count = len(readability_text.split())
            if word_count >= 500:
                text = readability_text
            else:
                logger.info(
                    "Readability extracted only %d words, falling back to full extraction",
                    word_count,
                )
        except Exception as exc:
            logger.debug("Readability extraction failed: %s", exc)

    # Fallback to full BeautifulSoup extraction if:
    # - Readability is not available
    # - Readability failed
    # - Readability extracted too little content
    if not text:
        soup = BeautifulSoup(html, "html.parser")
        _strip_scripts_and_styles(soup)

        # Best-effort title
        if title is None:
            t = soup.find("title")
            if t and t.text:
                title = t.text.strip() or None

        # Extract text from main content areas
        # Try to find main content containers first
        main_content = None
        for selector in ["main", "article", '[role="main"]', ".content", "#content"]:
            main_content = soup.select_one(selector)
            if main_content:
                break

        # If we found a main content area, extract from there
        # Otherwise, extract from body
        if main_content:
            text = main_content.get_text("\n", strip=True)
        else:
            # Remove common non-content elements
            for tag in soup(["nav", "header", "footer", "aside", "form"]):
                tag.decompose()
            text = soup.get_text("\n", strip=True)

    return {"title": title, "text": text}


def _looks_like_pdf_bytes(b: Optional[bytes]) -> bool:
    if not b or len(b) < 4:
        return False
    try:
        head = b[:4]
        return head == b"%PDF"
    except Exception:
        return False


def extract_pdf(content_bytes: bytes, extract_metadata: bool = False) -> Dict[str, Any]:
    """Extract text from a PDF byte stream using PyMuPDF, fallback to pdfminer.

    Args:
        content_bytes: PDF file content as bytes
        extract_metadata: If True, extract page boundaries and structured metadata

    Returns a dict with keys:
        - title: Document title (from metadata or None)
        - text: Extracted text content
        - page_boundaries: List of (start_char, end_char, page_num) tuples (if extract_metadata=True)
        - structured_metadata: Dict with title, authors, abstract (if extract_metadata=True)
    """
    text_content = ""
    page_boundaries = []
    structured_metadata = {}

    # Primary: PyMuPDF
    if fitz is not None:  # pragma: no cover - depends on optional lib
        try:
            with fitz.open(stream=content_bytes, filetype="pdf") as doc:
                parts = []
                current_offset = 0

                # Extract metadata from PDF info dictionary
                if extract_metadata and doc.metadata:
                    metadata = doc.metadata
                    structured_metadata["title"] = metadata.get("title") or None
                    structured_metadata["authors"] = metadata.get("author") or None
                    structured_metadata["subject"] = metadata.get("subject") or None
                    structured_metadata["keywords"] = metadata.get("keywords") or None

                # Extract text page by page
                for page_num, page in enumerate(doc, start=1):
                    page_text = page.get_text("text")
                    parts.append(page_text)

                    # Track page boundaries if metadata extraction is enabled
                    if extract_metadata:
                        page_length = len(page_text)
                        if page_length > 0:
                            # Add newline between pages
                            if page_num > 1:
                                current_offset += 1  # Account for newline
                            page_boundaries.append(
                                {
                                    "start_char": current_offset,
                                    "end_char": current_offset + page_length,
                                    "page_num": page_num,
                                }
                            )
                            current_offset += page_length

                text_content = "\n".join(parts).strip()

                # Try to extract abstract from first page if not in metadata
                if (
                    extract_metadata
                    and not structured_metadata.get("abstract")
                    and len(parts) > 0
                ):
                    first_page = parts[0].lower()
                    # Look for abstract section
                    abstract_markers = ["abstract", "summary"]
                    for marker in abstract_markers:
                        if marker in first_page:
                            # Simple heuristic: extract text after abstract marker
                            marker_pos = first_page.find(marker)
                            # Find next section or take next 500 chars
                            abstract_text = parts[0][marker_pos : marker_pos + 500]
                            # Clean up
                            lines = abstract_text.split("\n")
                            if len(lines) > 1:
                                # Skip the "Abstract" header line
                                abstract_text = "\n".join(lines[1:]).strip()
                                structured_metadata["abstract"] = abstract_text[:500]
                            break

        except Exception as exc:
            logger.info("PyMuPDF failed to parse PDF: %s", exc)

    # Fallback: pdfminer (no page boundary support)
    if not text_content and pdfminer_extract_text is not None:  # pragma: no cover
        try:
            buf = io.BytesIO(content_bytes)
            text_content = (pdfminer_extract_text(buf) or "").strip()
            # pdfminer doesn't provide page boundaries or metadata
            if extract_metadata:
                logger.warning(
                    "pdfminer fallback: page boundaries and metadata not available"
                )
        except Exception as exc:
            logger.info("pdfminer failed to parse PDF: %s", exc)

    result = {
        "title": structured_metadata.get("title") if extract_metadata else None,
        "text": text_content or "",
    }

    if extract_metadata:
        result["page_boundaries"] = page_boundaries
        result["structured_metadata"] = structured_metadata

    return result


def extract_from_fetched(
    fetched: Dict[str, Any], extract_metadata: bool = False
) -> Dict[str, Any]:
    """Extract title/text from fetched response supporting HTML and PDF.

    Args:
        fetched: Dict with url, content_type, content_bytes, html
        extract_metadata: If True, extract additional metadata (page boundaries for PDFs)

    Returns:
        - For HTML: use extract_text on the HTML string
        - For PDF: use extract_pdf on the bytes with metadata extraction
        - For others: fallback to text decode if possible
    """
    content_type = (fetched.get("content_type") or "").lower()
    url = fetched.get("url") or ""
    content_bytes: Optional[bytes] = fetched.get("content_bytes")

    # Detect by header, URL extension, or signature
    is_pdf = (
        "application/pdf" in content_type
        or url.lower().endswith(".pdf")
        or _looks_like_pdf_bytes(content_bytes)
    )

    if is_pdf and content_bytes:
        return extract_pdf(content_bytes, extract_metadata=extract_metadata)

    # HTML path retains compatibility
    html = fetched.get("html")
    if isinstance(html, str):
        return extract_text(html)

    # Fallback: try to decode bytes as UTF-8 text
    if content_bytes:
        try:
            decoded = content_bytes.decode("utf-8", errors="ignore")
            return extract_text(decoded)
        except Exception:
            pass

    return {"title": None, "text": ""}


def _build_archive_folder(url: str, root: Path) -> Path:
    now = datetime.now(timezone.utc)
    y = now.strftime("%Y")
    m = now.strftime("%m")
    d = now.strftime("%d")

    parsed = urlparse(url)
    host = parsed.hostname or "unknown-host"
    path = parsed.path or "/"
    slug_source = f"{host}{path}"
    slug = slugify(slug_source, lowercase=True, separator="-")
    folder = root / y / m / d / slug
    return folder


def archive_local(
    url: str, html: str, text: str, meta: Dict[str, Any], root: Path
) -> Dict[str, Any]:
    """Archive raw HTML, extracted text, and metadata to a deterministic folder.

    Writes UTF-8 files: raw.html, text.txt, meta.json
    Returns paths for the archive and files.
    """
    folder = _build_archive_folder(url, root)
    folder.mkdir(parents=True, exist_ok=True)

    raw_path = folder / "raw.html"
    text_path = folder / "text.txt"
    meta_path = folder / "meta.json"

    # Ensure meta contains minimal required fields
    meta_to_write = dict(meta)
    meta_to_write.setdefault("url", url)
    meta_to_write.setdefault("archived_at", datetime.now(timezone.utc).isoformat())

    # Binary-safe, explicit UTF-8
    raw_path.write_text(html, encoding="utf-8")
    text_path.write_text(text, encoding="utf-8")
    meta_path.write_text(
        json.dumps(meta_to_write, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "archive_path": str(folder),
        "files": {
            "raw": str(raw_path),
            "text": str(text_path),
            "meta": str(meta_path),
        },
    }
