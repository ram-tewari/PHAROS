"""
Unit Tests for Architecture Parser

Tests component extraction, relationship extraction, and pattern recognition.
"""

import pytest
from uuid import uuid4

pytest.importorskip(
    "tree_sitter",
    reason="ArchitectureParser requires tree_sitter for repository parsing",
)

from backend.app.modules.planning.service import ArchitectureParser
from backend.app.database.models import Resource, DocumentChunk


@pytest.mark.asyncio
async def test_component_extraction_markdown(db_session):
    """
    Test component extraction from Markdown format.

    Validates: Requirements 8.1
    """
    # Create architecture document in Markdown format
    content = """
# System Architecture

## API Gateway
The API Gateway handles all incoming HTTP requests and routes them to appropriate services.
- Request routing
- Authentication
- Rate limiting

## Service Layer
Business logic implementation layer.
- Data processing
- Business rules validation
"""

    resource_id = uuid4()
    resource = Resource(
        id=resource_id,
        title="Architecture Document",
        description="System architecture",
        type="document",
    )
    db_session.add(resource)
    db_session.commit()

    chunk = DocumentChunk(
        id=uuid4(),
        resource_id=resource_id,
        content=content,
        chunk_index=0,
        chunk_metadata={},
    )
    db_session.add(chunk)
    db_session.commit()

    # Parse document
    parser = ArchitectureParser(db=db_session)
    result = await parser.parse_architecture_doc(resource_id=resource_id)

    # Verify components extracted
    assert len(result.components) >= 2

    component_names = [c.name for c in result.components]
    assert "API Gateway" in component_names
    assert "Service Layer" in component_names

    # Verify component details
    api_gateway = next(c for c in result.components if c.name == "API Gateway")
    assert len(api_gateway.responsibilities) > 0
    assert "Request routing" in api_gateway.responsibilities

    # Cleanup
    db_session.delete(chunk)
    db_session.delete(resource)
    db_session.commit()


@pytest.mark.asyncio
async def test_relationship_extraction(db_session):
    """
    Test relationship extraction between components.

    Validates: Requirements 8.2
    """
    # Create architecture document with relationships
    content = """
# Architecture

## Frontend
User interface layer.

## Backend API
The Backend API depends on Database Service.

## Database Service
Data persistence layer.
"""

    resource_id = uuid4()
    resource = Resource(
        id=resource_id, title="Architecture with Relationships", type="document"
    )
    db_session.add(resource)
    db_session.commit()

    chunk = DocumentChunk(
        id=uuid4(),
        resource_id=resource_id,
        content=content,
        chunk_index=0,
        chunk_metadata={},
    )
    db_session.add(chunk)
    db_session.commit()

    # Parse document
    parser = ArchitectureParser(db=db_session)
    result = await parser.parse_architecture_doc(resource_id=resource_id)

    # Verify relationships extracted
    assert len(result.relationships) > 0

    # Check for dependency relationship
    backend_deps = [r for r in result.relationships if r.source == "Backend API"]
    assert len(backend_deps) > 0

    # Cleanup
    db_session.delete(chunk)
    db_session.delete(resource)
    db_session.commit()


@pytest.mark.asyncio
async def test_pattern_recognition(db_session):
    """
    Test design pattern recognition.

    Validates: Requirements 8.3
    """
    # Create architecture document mentioning patterns
    content = """
# System Design

## Architecture Overview
The system uses a layered architecture pattern with clear separation of concerns.
We implement the facade pattern for the API layer.

## Components
- Presentation Layer
- Business Logic Layer
- Data Access Layer

The system follows microservices architecture principles.
"""

    resource_id = uuid4()
    resource = Resource(
        id=resource_id, title="Architecture with Patterns", type="document"
    )
    db_session.add(resource)
    db_session.commit()

    chunk = DocumentChunk(
        id=uuid4(),
        resource_id=resource_id,
        content=content,
        chunk_index=0,
        chunk_metadata={},
    )
    db_session.add(chunk)
    db_session.commit()

    # Parse document
    parser = ArchitectureParser(db=db_session)
    result = await parser.parse_architecture_doc(resource_id=resource_id)

    # Verify patterns identified
    assert len(result.patterns) > 0

    pattern_names = [p.pattern_name for p in result.patterns]
    assert any("Layered" in name or "layered" in name.lower() for name in pattern_names)

    # Verify pattern details
    for pattern in result.patterns:
        assert pattern.confidence > 0.0
        assert pattern.confidence <= 1.0
        assert pattern.pattern_type in ["creational", "structural", "behavioral"]

    # Cleanup
    db_session.delete(chunk)
    db_session.delete(resource)
    db_session.commit()


@pytest.mark.asyncio
async def test_empty_document(db_session):
    """
    Test parsing empty document (edge case).

    Validates: Requirements 8.1, 8.2, 8.3
    """
    resource_id = uuid4()
    resource = Resource(id=resource_id, title="Empty Document", type="document")
    db_session.add(resource)
    db_session.commit()

    # No chunks - empty document

    # Parse document
    parser = ArchitectureParser(db=db_session)
    result = await parser.parse_architecture_doc(resource_id=resource_id)

    # Verify graceful handling
    assert result is not None
    assert isinstance(result.components, list)
    assert isinstance(result.relationships, list)
    assert isinstance(result.patterns, list)
    assert isinstance(result.gaps, list)

    # Should have a gap indicating no content
    assert len(result.gaps) > 0

    # Cleanup
    db_session.delete(resource)
    db_session.commit()


@pytest.mark.asyncio
async def test_restructuredtext_format(db_session):
    """
    Test parsing reStructuredText format.

    Validates: Requirements 8.5
    """
    content = """
System Architecture
===================

API Gateway
-----------
Handles incoming requests.

* Request routing
* Authentication

Service Layer
-------------
Business logic implementation.
"""

    resource_id = uuid4()
    resource = Resource(id=resource_id, title="RST Architecture", type="document")
    db_session.add(resource)
    db_session.commit()

    chunk = DocumentChunk(
        id=uuid4(),
        resource_id=resource_id,
        content=content,
        chunk_index=0,
        chunk_metadata={},
    )
    db_session.add(chunk)
    db_session.commit()

    # Parse document
    parser = ArchitectureParser(db=db_session)
    result = await parser.parse_architecture_doc(resource_id=resource_id)

    # Verify components extracted from RST format
    assert len(result.components) >= 2

    component_names = [c.name for c in result.components]
    assert "API Gateway" in component_names
    assert "Service Layer" in component_names

    # Cleanup
    db_session.delete(chunk)
    db_session.delete(resource)
    db_session.commit()


@pytest.mark.asyncio
async def test_multiple_chunks(db_session):
    """
    Test parsing document split across multiple chunks.

    Validates: Requirements 8.1
    """
    resource_id = uuid4()
    resource = Resource(id=resource_id, title="Multi-chunk Document", type="document")
    db_session.add(resource)
    db_session.commit()

    # Create multiple chunks
    chunk1 = DocumentChunk(
        id=uuid4(),
        resource_id=resource_id,
        content="# Architecture\n\n## Component A\nFirst component.",
        chunk_index=0,
        chunk_metadata={},
    )
    chunk2 = DocumentChunk(
        id=uuid4(),
        resource_id=resource_id,
        content="## Component B\nSecond component.",
        chunk_index=1,
        chunk_metadata={},
    )
    db_session.add(chunk1)
    db_session.add(chunk2)
    db_session.commit()

    # Parse document
    parser = ArchitectureParser(db=db_session)
    result = await parser.parse_architecture_doc(resource_id=resource_id)

    # Verify components from both chunks
    assert len(result.components) >= 2

    component_names = [c.name for c in result.components]
    assert "Component A" in component_names
    assert "Component B" in component_names

    # Cleanup
    db_session.delete(chunk1)
    db_session.delete(chunk2)
    db_session.delete(resource)
    db_session.commit()
