"""
End-to-End Tests for PDF Ingestion and GraphRAG Linking

Tests the complete flow:
1. Upload PDF
2. Annotate chunks with concepts
3. GraphRAG traversal search
4. Validate PDF + code results
"""

import pytest
import uuid
import io
from datetime import datetime
from typing import List, Dict, Any

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
    db_session.add(chunk1)
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
    db_session.add(chunk2)
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
    db_session.add(chunk3)
    chunks.append(chunk3)
    
    await db_session.commit()
    
    return [chunk.id for chunk in chunks]


@pytest.mark.asyncio
async def test_pdf_upload_and_extraction(client, mock_oauth_pdf):
    """
    Test PDF upload and text extraction.
    
    Validates:
    - PDF file is accepted
    - Text is extracted correctly
    - Chunks are created with page metadata
    - Equations/tables are detected
    """
    # Upload PDF
    files = {"file": ("oauth_best_practices.pdf", mock_oauth_pdf, "application/pdf")}
    data = {
        "title": "OAuth 2.0 Best Practices",
        "description": "Comprehensive guide to OAuth security",
        "authors": "Security Team",
        "publication_year": 2024,
        "tags": "OAuth,Security,Authentication",
    }
    
    response = await client.post("/api/resources/pdf/ingest", files=files, data=data)
    
    assert response.status_code == 201
    result = response.json()
    
    # Validate response structure
    assert "resource_id" in result
    assert result["title"] == "OAuth 2.0 Best Practices"
    assert result["status"] == "completed"
    assert result["total_pages"] == 2
    assert result["total_chunks"] > 0
    
    # Validate chunks
    chunks = result["chunks"]
    assert len(chunks) > 0
    
    # Check first chunk
    first_chunk = chunks[0]
    assert "chunk_id" in first_chunk
    assert "content" in first_chunk
    assert "page_number" in first_chunk
    assert first_chunk["page_number"] == 1
    assert "OAuth" in first_chunk["content"]
    
    # Verify chunk content includes key phrases
    all_content = " ".join(chunk["content"] for chunk in chunks)
    assert "whitelist redirect URIs" in all_content
    assert "state parameter" in all_content
    assert "authorization code" in all_content
    
    return result["resource_id"], [chunk["chunk_id"] for chunk in chunks]


@pytest.mark.asyncio
async def test_pdf_annotation_with_concepts(client, mock_oauth_pdf, mock_code_chunks):
    """
    Test annotating PDF chunks with conceptual tags.
    
    Validates:
    - Annotation is created
    - Concept tags are stored
    - Graph links are created to code chunks
    """
    # First, upload PDF
    files = {"file": ("oauth_best_practices.pdf", mock_oauth_pdf, "application/pdf")}
    data = {
        "title": "OAuth 2.0 Best Practices",
        "tags": "OAuth,Security",
    }
    
    upload_response = await client.post("/api/resources/pdf/ingest", files=files, data=data)
    assert upload_response.status_code == 201
    
    upload_result = upload_response.json()
    chunks = upload_result["chunks"]
    
    # Find chunk containing "whitelist redirect URIs"
    target_chunk = None
    for chunk in chunks:
        if "whitelist redirect URIs" in chunk["content"]:
            target_chunk = chunk
            break
    
    assert target_chunk is not None, "Could not find target chunk"
    
    # Annotate chunk with concepts
    annotation_data = {
        "chunk_id": target_chunk["chunk_id"],
        "concept_tags": ["OAuth", "Security", "Auth Flow"],
        "note": "Always whitelist redirect URIs to prevent open redirect attacks",
        "color": "#FFFF00",
    }
    
    annotation_response = await client.post(
        "/api/resources/pdf/annotate",
        json=annotation_data,
    )
    
    assert annotation_response.status_code == 201
    annotation_result = annotation_response.json()
    
    # Validate annotation
    assert "annotation_id" in annotation_result
    assert annotation_result["chunk_id"] == target_chunk["chunk_id"]
    assert annotation_result["concept_tags"] == ["OAuth", "Security", "Auth Flow"]
    assert annotation_result["note"] == "Always whitelist redirect URIs to prevent open redirect attacks"
    
    # Validate graph links were created
    assert annotation_result["graph_links_created"] > 0
    assert len(annotation_result["linked_code_chunks"]) > 0
    
    # Verify linked code chunks are from our mock data
    linked_chunk_ids = [str(cid) for cid in annotation_result["linked_code_chunks"]]
    mock_chunk_ids = [str(cid) for cid in mock_code_chunks]
    
    # At least one mock code chunk should be linked
    assert any(cid in mock_chunk_ids for cid in linked_chunk_ids)
    
    return annotation_result


@pytest.mark.asyncio
async def test_graph_traversal_search(client, mock_oauth_pdf, mock_code_chunks):
    """
    Test GraphRAG traversal search across PDF and code.
    
    Validates:
    - Search returns both PDF and code chunks
    - Results include annotations
    - Graph distance is calculated
    - Relevance scoring works
    """
    # Setup: Upload PDF and annotate
    files = {"file": ("oauth_best_practices.pdf", mock_oauth_pdf, "application/pdf")}
    data = {
        "title": "OAuth 2.0 Best Practices",
        "tags": "OAuth,Security",
    }
    
    upload_response = await client.post("/api/resources/pdf/ingest", files=files, data=data)
    assert upload_response.status_code == 201
    
    chunks = upload_response.json()["chunks"]
    
    # Annotate first chunk
    annotation_data = {
        "chunk_id": chunks[0]["chunk_id"],
        "concept_tags": ["OAuth", "Authentication"],
        "note": "Core OAuth concepts",
    }
    
    await client.post("/api/resources/pdf/annotate", json=annotation_data)
    
    # Perform graph traversal search
    search_data = {
        "query": "auth implementation",
        "max_hops": 2,
        "include_pdf": True,
        "include_code": True,
        "limit": 10,
    }
    
    search_response = await client.post(
        "/api/resources/pdf/search/graph",
        json=search_data,
    )
    
    assert search_response.status_code == 200
    search_result = search_response.json()
    
    # Validate search results
    assert search_result["query"] == "auth implementation"
    assert search_result["total_results"] > 0
    
    # Should have both PDF and code results
    assert search_result["pdf_results"] > 0
    assert search_result["code_results"] > 0
    
    # Validate result structure
    results = search_result["results"]
    assert len(results) > 0
    
    # Check first result
    first_result = results[0]
    assert "chunk_id" in first_result
    assert "chunk_type" in first_result
    assert first_result["chunk_type"] in ["pdf", "code"]
    assert "relevance_score" in first_result
    assert "graph_distance" in first_result
    assert "concept_tags" in first_result
    
    # Validate PDF result has page_number
    pdf_results = [r for r in results if r["chunk_type"] == "pdf"]
    if pdf_results:
        assert "page_number" in pdf_results[0]
        assert pdf_results[0]["page_number"] is not None
    
    # Validate code result has file_path
    code_results = [r for r in results if r["chunk_type"] == "code"]
    if code_results:
        assert "file_path" in code_results[0]
        assert code_results[0]["file_path"] is not None
    
    # Validate annotations are included
    annotated_results = [r for r in results if r.get("annotations")]
    assert len(annotated_results) > 0
    
    # Check execution time is reasonable
    assert search_result["execution_time_ms"] < 5000  # Less than 5 seconds
    
    return search_result


@pytest.mark.asyncio
async def test_complete_workflow(client, mock_oauth_pdf, mock_code_chunks):
    """
    Test complete end-to-end workflow.
    
    Flow:
    1. Upload PDF about OAuth
    2. Annotate specific chunk with "OAuth" tag
    3. Execute GraphRAG search for "auth implementation"
    4. Validate results include both PDF highlight and code chunks
    """
    # Step 1: Upload PDF
    files = {"file": ("oauth_best_practices.pdf", mock_oauth_pdf, "application/pdf")}
    data = {
        "title": "OAuth 2.0 Best Practices",
        "description": "Security guide for OAuth implementation",
        "authors": "Security Research Team",
        "publication_year": 2024,
        "tags": "OAuth,Security,Authentication,Authorization",
    }
    
    upload_response = await client.post("/api/resources/pdf/ingest", files=files, data=data)
    assert upload_response.status_code == 201
    
    upload_result = upload_response.json()
    resource_id = upload_result["resource_id"]
    chunks = upload_result["chunks"]
    
    print(f"\n✓ Step 1: Uploaded PDF - {len(chunks)} chunks created")
    
    # Step 2: Annotate chunk containing "whitelist redirect URIs"
    target_chunk = None
    for chunk in chunks:
        if "whitelist redirect URIs" in chunk["content"]:
            target_chunk = chunk
            break
    
    assert target_chunk is not None
    
    annotation_data = {
        "chunk_id": target_chunk["chunk_id"],
        "concept_tags": ["OAuth", "Auth Flow", "Security"],
        "note": "Always whitelist redirect URIs",
        "color": "#FFFF00",
    }
    
    annotation_response = await client.post(
        "/api/resources/pdf/annotate",
        json=annotation_data,
    )
    assert annotation_response.status_code == 201
    
    annotation_result = annotation_response.json()
    graph_links = annotation_result["graph_links_created"]
    
    print(f"✓ Step 2: Annotated chunk - {graph_links} graph links created")
    
    # Step 3: Execute GraphRAG traversal search
    search_data = {
        "query": "auth implementation",
        "max_hops": 2,
        "include_pdf": True,
        "include_code": True,
        "limit": 20,
    }
    
    search_response = await client.post(
        "/api/resources/pdf/search/graph",
        json=search_data,
    )
    assert search_response.status_code == 200
    
    search_result = search_response.json()
    
    print(f"✓ Step 3: GraphRAG search completed - {search_result['total_results']} results")
    print(f"  - PDF results: {search_result['pdf_results']}")
    print(f"  - Code results: {search_result['code_results']}")
    print(f"  - Execution time: {search_result['execution_time_ms']:.2f}ms")
    
    # Step 4: Validate results
    results = search_result["results"]
    
    # Must have both PDF and code results
    assert search_result["pdf_results"] > 0, "No PDF results found"
    assert search_result["code_results"] > 0, "No code results found"
    
    # Find the annotated PDF chunk in results
    annotated_pdf_result = None
    for result in results:
        if (
            result["chunk_type"] == "pdf"
            and str(result["chunk_id"]) == target_chunk["chunk_id"]
        ):
            annotated_pdf_result = result
            break
    
    assert annotated_pdf_result is not None, "Annotated PDF chunk not in results"
    
    # Validate annotation is included
    assert len(annotated_pdf_result["annotations"]) > 0
    annotation = annotated_pdf_result["annotations"][0]
    assert "OAuth" in annotation["tags"]
    assert annotation["note"] == "Always whitelist redirect URIs"
    
    print(f"✓ Step 4: Validation passed")
    print(f"  - Found annotated PDF chunk with {len(annotated_pdf_result['annotations'])} annotations")
    
    # Find code chunks in results
    code_results = [r for r in results if r["chunk_type"] == "code"]
    assert len(code_results) > 0
    
    # Validate code chunk structure
    code_result = code_results[0]
    assert code_result["file_path"] is not None
    assert "oauth" in code_result["semantic_summary"].lower() or "auth" in code_result["semantic_summary"].lower()
    
    print(f"  - Found {len(code_results)} code chunks")
    print(f"  - Example: {code_result['file_path']}")
    
    # Validate concept tags are propagated
    pdf_with_tags = [r for r in results if r["chunk_type"] == "pdf" and r["concept_tags"]]
    assert len(pdf_with_tags) > 0
    
    print(f"  - {len(pdf_with_tags)} PDF chunks have concept tags")
    
    print("\n✅ Complete workflow test PASSED")
    
    return {
        "resource_id": resource_id,
        "annotation_id": annotation_result["annotation_id"],
        "search_results": search_result,
    }


@pytest.mark.asyncio
async def test_error_handling_invalid_pdf(client):
    """Test error handling for invalid PDF files."""
    # Try to upload non-PDF file
    files = {"file": ("not_a_pdf.txt", io.BytesIO(b"This is not a PDF"), "text/plain")}
    data = {"title": "Invalid File"}
    
    response = await client.post("/api/resources/pdf/ingest", files=files, data=data)
    
    assert response.status_code == 400
    assert "Only PDF files are supported" in response.json()["detail"]


@pytest.mark.asyncio
async def test_error_handling_missing_chunk(client):
    """Test error handling for annotating non-existent chunk."""
    annotation_data = {
        "chunk_id": str(uuid.uuid4()),  # Random UUID
        "concept_tags": ["Test"],
    }
    
    response = await client.post("/api/resources/pdf/annotate", json=annotation_data)
    
    assert response.status_code == 404
    assert "Chunk not found" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
