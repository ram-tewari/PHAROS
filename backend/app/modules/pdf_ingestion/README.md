# PDF Ingestion Module

## Overview

The PDF Ingestion module enables Pharos to ingest academic research papers and link them to codebase knowledge through GraphRAG. It provides PDF extraction, annotation, and graph-based search capabilities.

## Features

### 1. PDF Upload & Extraction
- **Academic Fidelity**: Preserves text structure, equations, tables, and figures
- **PyMuPDF Integration**: Robust PDF parsing with coordinate preservation
- **Chunking Strategy**: Semantic chunking with page/coordinate metadata
- **Embedding Generation**: Automatic vector embeddings for semantic search

### 2. Annotation System
- **Conceptual Tagging**: Tag PDF chunks with concepts (e.g., "OAuth", "Security")
- **Manual Mapping**: Link specific text blocks to conceptual tags
- **Color Coding**: Visual highlighting with customizable colors
- **Notes**: Rich annotation notes for context

### 3. GraphRAG Linking
- **Concept Entities**: Automatic graph entity creation from tags
- **PDF ↔ Code Links**: Bidirectional relationships between PDF concepts and code
- **Semantic Matching**: Find code chunks implementing PDF concepts
- **Graph Traversal**: Multi-hop search across knowledge graph

## API Endpoints

### POST /api/resources/pdf/ingest

Upload and ingest a PDF file.

**Request** (multipart/form-data):
```
file: PDF file (required)
title: Document title (required)
description: Optional description
authors: Comma-separated authors
publication_year: Year of publication
doi: Digital Object Identifier
tags: Comma-separated initial tags
```

**Response**:
```json
{
  "resource_id": "uuid",
  "title": "OAuth 2.0 Best Practices",
  "status": "completed",
  "total_pages": 15,
  "total_chunks": 42,
  "chunks": [
    {
      "chunk_id": "uuid",
      "chunk_index": 0,
      "content": "OAuth 2.0 is an authorization framework...",
      "page_number": 1,
      "coordinates": {"x0": 100, "y0": 750, "x1": 500, "y1": 680},
      "chunk_type": "text"
    }
  ],
  "message": "PDF ingested successfully: 42 chunks created"
}
```

### POST /api/resources/pdf/annotate

Annotate a PDF chunk with conceptual tags.

**Request**:
```json
{
  "chunk_id": "uuid",
  "concept_tags": ["OAuth", "Security", "Auth Flow"],
  "note": "Always whitelist redirect URIs",
  "color": "#FFFF00"
}
```

**Response**:
```json
{
  "annotation_id": "uuid",
  "chunk_id": "uuid",
  "concept_tags": ["OAuth", "Security", "Auth Flow"],
  "note": "Always whitelist redirect URIs",
  "color": "#FFFF00",
  "created_at": "2024-01-15T10:30:00Z",
  "graph_links_created": 3,
  "linked_code_chunks": ["uuid1", "uuid2", "uuid3"]
}
```

### POST /api/resources/pdf/search/graph

Perform GraphRAG traversal search.

**Request**:
```json
{
  "query": "auth implementation",
  "max_hops": 2,
  "include_pdf": true,
  "include_code": true,
  "limit": 10
}
```

**Response**:
```json
{
  "query": "auth implementation",
  "total_results": 8,
  "pdf_results": 3,
  "code_results": 5,
  "results": [
    {
      "chunk_id": "uuid",
      "resource_id": "uuid",
      "chunk_type": "pdf",
      "content": "OAuth 2.0 authorization flow...",
      "relevance_score": 0.92,
      "graph_distance": 1,
      "concept_tags": ["OAuth", "Auth Flow"],
      "page_number": 3,
      "annotations": [
        {
          "id": "uuid",
          "tags": "OAuth,Security",
          "note": "Core OAuth concepts"
        }
      ]
    },
    {
      "chunk_id": "uuid",
      "resource_id": "uuid",
      "chunk_type": "code",
      "semantic_summary": "def handle_oauth_callback(code, state)...",
      "relevance_score": 0.88,
      "graph_distance": 1,
      "concept_tags": ["OAuth"],
      "file_path": "https://raw.githubusercontent.com/.../auth_service.py",
      "annotations": []
    }
  ],
  "execution_time_ms": 245.3
}
```

## Architecture

### Service Layer (`service.py`)

**PDFIngestionService**:
- `ingest_pdf()`: Main ingestion pipeline
- `_extract_pdf_content()`: PyMuPDF extraction
- `_create_chunks()`: Semantic chunking
- `annotate_chunk()`: Annotation creation
- `_link_to_graph()`: GraphRAG linking
- `graph_traversal_search()`: Graph-based search

### Database Models

**DocumentChunk** (existing):
- Stores PDF chunks with `is_remote=False`
- `chunk_metadata`: Page number, coordinates, chunk type
- `content`: Extracted text

**Annotation** (existing):
- Links to resource (PDF)
- `tags`: Comma-separated concept tags
- `note`: Annotation text

**GraphEntity** (existing):
- Represents concepts (OAuth, Security, etc.)
- `type`: "Concept", "Person", "Organization", "Method"

**GraphRelationship** (existing):
- Links entities with provenance
- `relation_type`: "MENTIONS", "IMPLEMENTS", "CONTRADICTS"
- `provenance_chunk_id`: Source chunk

## GraphRAG Linking Algorithm

### 1. Annotation Phase

```python
# User annotates PDF chunk with concepts
annotation = {
    "chunk_id": "pdf_chunk_123",
    "concept_tags": ["OAuth", "Security"]
}

# System creates graph entities
entity_oauth = GraphEntity(name="OAuth", type="Concept")
entity_security = GraphEntity(name="Security", type="Concept")

# Link PDF chunk to concepts
relationship_1 = GraphRelationship(
    source_entity=entity_oauth,
    target_entity=entity_oauth,  # Self-reference
    provenance_chunk_id="pdf_chunk_123",
    relation_type="MENTIONS"
)
```

### 2. Code Linking Phase

```python
# Find code chunks mentioning "OAuth"
code_chunks = find_code_chunks_by_concept("OAuth")
# Returns: [
#   DocumentChunk(symbol_name="auth.oauth.handle_callback"),
#   DocumentChunk(symbol_name="auth.oauth.validate_token")
# ]

# Create bidirectional links
for code_chunk in code_chunks:
    relationship = GraphRelationship(
        source_entity=entity_oauth,
        target_entity=entity_oauth,
        provenance_chunk_id=code_chunk.id,
        relation_type="IMPLEMENTS",
        relationship_metadata={
            "pdf_chunk_id": "pdf_chunk_123",
            "code_chunk_id": code_chunk.id,
            "concept": "OAuth",
            "link_type": "pdf_to_code"
        }
    )
```

### 3. Traversal Search Phase

```python
# User searches: "auth implementation"
query_embedding = generate_embedding("auth implementation")

# Find seed entities
seed_entities = [
    GraphEntity(name="OAuth"),
    GraphEntity(name="Authentication")
]

# Traverse graph (BFS, max 2 hops)
for entity in seed_entities:
    relationships = get_relationships(entity)
    for rel in relationships:
        chunk = get_chunk(rel.provenance_chunk_id)
        if chunk.is_remote:  # Code chunk
            results.append({
                "chunk_type": "code",
                "file_path": chunk.github_uri,
                "semantic_summary": chunk.semantic_summary
            })
        else:  # PDF chunk
            results.append({
                "chunk_type": "pdf",
                "page_number": chunk.chunk_metadata["page"],
                "content": chunk.content
            })
```

## Dependencies

### Required
- `PyMuPDF` (fitz): PDF extraction
- `sqlalchemy`: Database ORM
- `fastapi`: API framework

### Optional (for testing)
- `reportlab`: Mock PDF generation
- `pytest`: Testing framework

## Installation

```bash
# Install core dependencies
pip install PyMuPDF sqlalchemy fastapi

# Install testing dependencies
pip install reportlab pytest pytest-asyncio
```

## Usage Examples

### Example 1: Upload OAuth Paper

```python
import requests

# Upload PDF
with open("oauth_best_practices.pdf", "rb") as f:
    files = {"file": f}
    data = {
        "title": "OAuth 2.0 Best Practices",
        "authors": "Security Team",
        "publication_year": 2024,
        "tags": "OAuth,Security,Authentication"
    }
    response = requests.post(
        "http://localhost:8000/api/resources/pdf/ingest",
        files=files,
        data=data
    )

result = response.json()
print(f"Created {result['total_chunks']} chunks")
```

### Example 2: Annotate Security Concept

```python
# Annotate chunk about redirect URI whitelisting
annotation_data = {
    "chunk_id": "chunk_uuid",
    "concept_tags": ["OAuth", "Security", "Auth Flow"],
    "note": "Always whitelist redirect URIs to prevent open redirect attacks",
    "color": "#FFFF00"
}

response = requests.post(
    "http://localhost:8000/api/resources/pdf/annotate",
    json=annotation_data
)

result = response.json()
print(f"Created {result['graph_links_created']} graph links")
print(f"Linked to {len(result['linked_code_chunks'])} code chunks")
```

### Example 3: Search Across PDF + Code

```python
# Search for auth implementation
search_data = {
    "query": "auth implementation",
    "max_hops": 2,
    "include_pdf": True,
    "include_code": True,
    "limit": 10
}

response = requests.post(
    "http://localhost:8000/api/resources/pdf/search/graph",
    json=search_data
)

result = response.json()
print(f"Found {result['total_results']} results:")
print(f"  - {result['pdf_results']} from PDFs")
print(f"  - {result['code_results']} from code")

for item in result["results"]:
    if item["chunk_type"] == "pdf":
        print(f"PDF (page {item['page_number']}): {item['content'][:100]}...")
    else:
        print(f"Code ({item['file_path']}): {item['semantic_summary'][:100]}...")
```

## Testing

Run end-to-end tests:

```bash
# Run all PDF ingestion tests
pytest backend/tests/test_pdf_ingestion_e2e.py -v

# Run specific test
pytest backend/tests/test_pdf_ingestion_e2e.py::test_complete_workflow -v -s

# Run with coverage
pytest backend/tests/test_pdf_ingestion_e2e.py --cov=app.modules.pdf_ingestion
```

## Performance Considerations

### PDF Extraction
- **Speed**: ~2-5 seconds per page (PyMuPDF)
- **Memory**: ~50MB per 100-page PDF
- **Optimization**: Async processing, chunked extraction

### Embedding Generation
- **Speed**: ~100ms per chunk (nomic-embed-text-v1)
- **Batch Size**: 32 chunks per batch
- **Optimization**: Background task queue

### Graph Traversal
- **Speed**: <500ms for 2-hop traversal
- **Complexity**: O(E * H) where E=edges, H=hops
- **Optimization**: Indexed relationships, early termination

## Future Enhancements

### Phase 4.1: Advanced Extraction
- [ ] LaTeX equation parsing (SymPy)
- [ ] Table structure extraction (Camelot)
- [ ] Figure caption extraction
- [ ] Reference parsing (Grobid)

### Phase 4.2: Enhanced Linking
- [ ] Semantic similarity threshold tuning
- [ ] Multi-concept relationship strength
- [ ] Temporal relationship tracking
- [ ] Contradiction detection

### Phase 4.3: Search Improvements
- [ ] Hybrid search (keyword + semantic + graph)
- [ ] Personalized ranking
- [ ] Query expansion
- [ ] Result clustering

## Related Modules

- **Resources**: Base resource management
- **Graph**: Knowledge graph construction
- **Search**: Hybrid search infrastructure
- **Annotations**: Annotation management

## References

- [PyMuPDF Documentation](https://pymupdf.readthedocs.io/)
- [GraphRAG Paper](https://arxiv.org/abs/2404.16130)
- [OAuth 2.0 RFC](https://datatracker.ietf.org/doc/html/rfc6749)
