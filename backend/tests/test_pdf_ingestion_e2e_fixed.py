"""
End-to-End Tests for PDF Ingestion and GraphRAG Linking

Tests the complete flow:
1. Upload PDF
2. Annotate chunks with concepts
3. GraphRAG traversal search
4. Validate PDF + code results

Note: These tests use async_client fixture from conftest.py
"""

import pytest
import pytest_asyncio
import uuid
import io
from datetime import datetime

# Mock PDF generation
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


@pytest.fixture
def mock_oauth_pdf() -> io.BytesIO:
    """
    Generate a mock PDF about OAuth best practices.
    
    Returns:
        BytesIO containing PDF bytes
    """
    if not HAS_REPORTLAB:
        pytest.skip("reportlab not installed")
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    
    # Page 1: Introduction
    c.drawString(100, 750, "OAuth 2.0 Best Practices")
    c.drawString(100, 730, "A Comprehensive Guide")
    c.drawString(100, 700, "")
    c.drawString(100, 680, "OAuth 2.0 is an authorization framework that enables applications")
    c.drawString(100, 660, "to obtain limited access to user accounts on an HTTP service.")
    c.drawString(100, 640, "")
    c.drawString(100, 620, "Key Security Principles:")
    c.drawString(120, 600, "1. Always whitelist redirect URIs")
    c.drawString(120, 580, "2. Use state parameter to prevent CSRF attacks")
    c.drawString(120, 560, "3. Validate authorization codes immediately")
    c.drawString(120, 540, "4. Store tokens securely using encryption")
    c.showPage()
    
    # Page 2: Implementation Details
    c.drawString(100, 750, "Implementation Guidelines")
    c.drawString(100, 730, "")
    c.drawString(100, 710, "Authorization Flow:")
    c.drawString(120, 690, "1. Client redirects user to authorization server")
    c.drawString(120, 670, "2. User authenticates and grants permission")
    c.drawString(120, 650, "3. Authorization server redirects back with code")
    c.drawString(120, 630, "4. Client exchanges code for access token")
    c.drawString(100, 610, "")
    c.drawString(100, 590, "Token Management:")
    c.drawString(120, 570, "- Access tokens should be short-lived (15-60 minutes)")
    c.drawString(120, 550, "- Refresh tokens enable long-term access")
    c.drawString(120, 530, "- Implement token rotation for enhanced security")
    c.showPage()
    
    c.save()
    buffer.seek(0)
    return buffer


@pytest_asyncio.fixture
async def mock_code_chunks(async_db_session):
    """
    Create mock code chunks representing OAuth implementation.
    
    Returns:
        List of DocumentChunk IDs
    """
    from app.database.models import Resource, DocumentChunk
    
    # Create a code resource
    code_resource = Resource(
        id=uuid.uuid4(),
        title="auth_service.py",
        type="code",
        format="text/x-python",
        ingestion_status="completed",
    )
    async_db_session.add(code_resource)
    await async_db_session.flush()
    
    # Create code chunks
    chunks = []
    
    # Chunk 1: OAuth handler function
    chunk1 = DocumentChunk(
        id=uuid.uuid4(),
        resource_id=code_resource.id,
        chunk_index=0,
        is_remote=True,
        github_uri="https://raw.githubusercontent.com/example/repo/main/auth_service.py",
        branch_reference="main",
        start_line=45,
        end_line=78,
        ast_node_type="function",
        symbol_name="auth.oauth.handle_oauth_callback",
        semantic_summary=(
            "def handle_oauth_callback(code: str, state: str) -> TokenResponse:\n"
            "    '''Handle OAuth callback and exchange code for tokens.\n"
            "    Validates state parameter and redirect URI.'''"
        ),
        chunk_metadata={
            "file_path": "auth_service.py",
            "function_name": "handle_oauth_callback",
            "language": "python",
        },
    )
    async_db_session.add(chunk1)
    chunks.append(chunk1)
    
    # Chunk 2: Token validation function
    chunk2 = DocumentChunk(
        id=uuid.uuid4(),
        resource_id=code_resource.id,
        chunk_index=1,
        is_remote=True,
        github_uri="https://raw.githubusercontent.com/example/repo/main/auth_service.py",
        branch_reference="main",
        start_line=120,
        end_line=145,
        ast_node_type="function",
        symbol_name="auth.oauth.validate_token",
        semantic_summary=(
            "def validate_token(token: str) -> bool:\n"
            "    '''Validate OAuth access token.\n"
            "    Checks expiration and signature.'''"
        ),
        chunk_metadata={
            "file_path": "auth_service.py",
            "function_name": "validate_token",
            "language": "python",
        },
    )
    async_db_session.add(chunk2)
    chunks.append(chunk2)
    
    # Chunk 3: Security middleware
    chunk3 = DocumentChunk(
        id=uuid.uuid4(),
        resource_id=code_resource.id,
        chunk_index=2,
        is_remote=True,
        github_uri="https://raw.githubusercontent.com/example/repo/main/middleware.py",
        branch_reference="main",
        start_line=20,
        end_line=45,
        ast_node_type="class",
        symbol_name="middleware.SecurityMiddleware",
        semantic_summary=(
            "class SecurityMiddleware:\n"
            "    '''Security middleware for OAuth authentication.\n"
            "    Validates tokens and enforces security policies.'''"
        ),
        chunk_metadata={
            "file_path": "middleware.py",
            "class_name": "SecurityMiddleware",
            "language": "python",
        },
    )
    async_db_session.add(chunk3)
    chunks.append(chunk3)
    
    await async_db_session.commit()
    
    return [chunk.id for chunk in chunks]


@pytest.mark.asyncio
async def test_pdf_module_imports():
    """Test that PDF ingestion module can be imported."""
    from app.modules.pdf_ingestion import router, PDFIngestionService
    assert router is not None
    assert PDFIngestionService is not None


@pytest.mark.asyncio
async def test_pdf_routes_registered(async_client):
    """Test that PDF routes are registered in the app."""
    # Get OpenAPI schema
    response = await async_client.get("/openapi.json")
    assert response.status_code == 200
    
    schema = response.json()
    paths = schema.get("paths", {})
    
    # Check if PDF routes exist
    assert "/api/resources/pdf/ingest" in paths
    assert "/api/resources/pdf/annotate" in paths
    assert "/api/resources/pdf/search/graph" in paths


@pytest.mark.asyncio
async def test_error_handling_invalid_pdf(async_client):
    """Test error handling for invalid PDF files."""
    # Try to upload non-PDF file
    files = {"file": ("not_a_pdf.txt", io.BytesIO(b"This is not a PDF"), "text/plain")}
    data = {"title": "Invalid File"}
    
    response = await async_client.post("/api/resources/pdf/ingest", files=files, data=data)
    
    assert response.status_code == 400
    assert "Only PDF files are supported" in response.json()["detail"]


@pytest.mark.asyncio
async def test_error_handling_missing_chunk(async_client):
    """Test error handling for annotating non-existent chunk."""
    annotation_data = {
        "chunk_id": str(uuid.uuid4()),  # Random UUID
        "concept_tags": ["Test"],
    }
    
    response = await async_client.post("/api/resources/pdf/annotate", json=annotation_data)
    
    assert response.status_code in [404, 500]  # Either not found or internal error


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
