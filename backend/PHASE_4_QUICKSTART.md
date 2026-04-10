# Phase 4: PDF Ingestion - Quick Start Guide

## Installation

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements-base.txt
```

This installs PyMuPDF (fitz) for PDF extraction.

### 2. Verify Installation

```bash
python -c "import fitz; print(f'PyMuPDF version: {fitz.version}')"
```

Expected output: `PyMuPDF version: (1, 23, ...)`

## Running the Server

### Start FastAPI Server

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

The PDF ingestion endpoints will be available at:
- `POST /api/resources/pdf/ingest`
- `POST /api/resources/pdf/annotate`
- `POST /api/resources/pdf/search/graph`

## Quick Test

### 1. Upload a PDF

```bash
# Create a test PDF (or use your own)
curl -X POST http://localhost:8000/api/resources/pdf/ingest \
  -F "file=@your_paper.pdf" \
  -F "title=Test Paper" \
  -F "tags=Test,Research"
```

**Response**:
```json
{
  "resource_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Test Paper",
  "status": "completed",
  "total_pages": 5,
  "total_chunks": 12,
  "chunks": [
    {
      "chunk_id": "660e8400-e29b-41d4-a716-446655440001",
      "chunk_index": 0,
      "content": "Introduction...",
      "page_number": 1,
      "chunk_type": "text"
    }
  ],
  "message": "PDF ingested successfully: 12 chunks created"
}
```

### 2. Annotate a Chunk

```bash
# Use a chunk_id from the upload response
curl -X POST http://localhost:8000/api/resources/pdf/annotate \
  -H "Content-Type: application/json" \
  -d '{
    "chunk_id": "660e8400-e29b-41d4-a716-446655440001",
    "concept_tags": ["Machine Learning", "Neural Networks"],
    "note": "Key concept for implementation",
    "color": "#FFFF00"
  }'
```

**Response**:
```json
{
  "annotation_id": "770e8400-e29b-41d4-a716-446655440002",
  "chunk_id": "660e8400-e29b-41d4-a716-446655440001",
  "concept_tags": ["Machine Learning", "Neural Networks"],
  "note": "Key concept for implementation",
  "color": "#FFFF00",
  "created_at": "2024-01-15T10:30:00Z",
  "graph_links_created": 2,
  "linked_code_chunks": ["880e8400-...", "990e8400-..."]
}
```

### 3. Search Across PDF + Code

```bash
curl -X POST http://localhost:8000/api/resources/pdf/search/graph \
  -H "Content-Type: application/json" \
  -d '{
    "query": "machine learning implementation",
    "max_hops": 2,
    "include_pdf": true,
    "include_code": true,
    "limit": 10
  }'
```

**Response**:
```json
{
  "query": "machine learning implementation",
  "total_results": 7,
  "pdf_results": 3,
  "code_results": 4,
  "results": [
    {
      "chunk_id": "660e8400-...",
      "chunk_type": "pdf",
      "content": "Neural networks are...",
      "relevance_score": 0.92,
      "graph_distance": 1,
      "concept_tags": ["Machine Learning", "Neural Networks"],
      "page_number": 1,
      "annotations": [...]
    },
    {
      "chunk_id": "880e8400-...",
      "chunk_type": "code",
      "semantic_summary": "class NeuralNetwork:\n    def train(self, data)...",
      "relevance_score": 0.88,
      "graph_distance": 1,
      "concept_tags": ["Machine Learning"],
      "file_path": "https://raw.githubusercontent.com/.../model.py"
    }
  ],
  "execution_time_ms": 234.5
}
```

## Running Tests

### Install Test Dependencies

```bash
pip install reportlab pytest pytest-asyncio
```

### Run End-to-End Tests

```bash
# Run all tests
pytest backend/tests/test_pdf_ingestion_e2e.py -v

# Run with output
pytest backend/tests/test_pdf_ingestion_e2e.py -v -s

# Run specific test
pytest backend/tests/test_pdf_ingestion_e2e.py::test_complete_workflow -v -s
```

### Expected Test Output

```
test_pdf_upload_and_extraction PASSED
test_pdf_annotation_with_concepts PASSED
test_graph_traversal_search PASSED
test_complete_workflow PASSED
  ✓ Step 1: Uploaded PDF - 8 chunks created
  ✓ Step 2: Annotated chunk - 3 graph links created
  ✓ Step 3: GraphRAG search completed - 8 results
  ✓ Step 4: Validation passed
  ✅ Complete workflow test PASSED
test_error_handling_invalid_pdf PASSED
test_error_handling_missing_chunk PASSED

======================== 6 passed in 5.23s ========================
```

## Python API Usage

### Example Script

```python
import asyncio
import httpx

async def test_pdf_workflow():
    async with httpx.AsyncClient() as client:
        # 1. Upload PDF
        with open("paper.pdf", "rb") as f:
            files = {"file": ("paper.pdf", f, "application/pdf")}
            data = {
                "title": "Research Paper",
                "tags": "ML,AI"
            }
            response = await client.post(
                "http://localhost:8000/api/resources/pdf/ingest",
                files=files,
                data=data
            )
            result = response.json()
            print(f"Uploaded: {result['total_chunks']} chunks")
            
            chunk_id = result["chunks"][0]["chunk_id"]
        
        # 2. Annotate
        annotation_data = {
            "chunk_id": chunk_id,
            "concept_tags": ["ML", "AI"],
            "note": "Important concept"
        }
        response = await client.post(
            "http://localhost:8000/api/resources/pdf/annotate",
            json=annotation_data
        )
        result = response.json()
        print(f"Annotated: {result['graph_links_created']} links created")
        
        # 3. Search
        search_data = {
            "query": "machine learning",
            "max_hops": 2,
            "limit": 10
        }
        response = await client.post(
            "http://localhost:8000/api/resources/pdf/search/graph",
            json=search_data
        )
        result = response.json()
        print(f"Found: {result['total_results']} results")
        print(f"  PDF: {result['pdf_results']}")
        print(f"  Code: {result['code_results']}")

asyncio.run(test_pdf_workflow())
```

## Troubleshooting

### PyMuPDF Not Found

```bash
# Install PyMuPDF
pip install PyMuPDF

# Verify
python -c "import fitz; print('OK')"
```

### PDF Extraction Fails

Check PDF file:
```bash
# Verify PDF is valid
file your_paper.pdf
# Should output: PDF document, version X.X
```

### No Graph Links Created

Ensure code chunks exist:
```bash
# Check if code chunks are in database
curl http://localhost:8000/api/resources?type=code
```

### Search Returns No Results

1. Check if annotations exist
2. Verify concept tags match code chunk content
3. Increase `max_hops` parameter

## Next Steps

1. **Frontend Integration**: Build UI for PDF upload and annotation
2. **Advanced Extraction**: Add LaTeX equation parsing
3. **Enhanced Search**: Implement hybrid search (keyword + semantic + graph)
4. **Visualization**: Create graph explorer UI

## Documentation

- **Module README**: `backend/app/modules/pdf_ingestion/README.md`
- **Implementation Details**: `backend/PHASE_4_IMPLEMENTATION.md`
- **API Reference**: See module README for detailed endpoint docs

## Support

For issues or questions:
1. Check the module README
2. Review test cases for usage examples
3. Check logs for error details
