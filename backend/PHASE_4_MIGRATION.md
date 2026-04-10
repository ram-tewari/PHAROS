# Phase 4: Migration and Integration Guide

## Overview

This guide helps integrate Phase 4 (PDF Ingestion) with your existing Pharos deployment.

## Prerequisites

- Pharos Phase 17.5 (Advanced RAG) must be deployed
- PostgreSQL or SQLite database
- Python 3.8+
- FastAPI application running

## Migration Steps

### Step 1: Install Dependencies

```bash
cd backend
pip install PyMuPDF>=1.23.0
```

Verify installation:
```bash
python -c "import fitz; print(f'PyMuPDF {fitz.version} installed')"
```

### Step 2: No Database Migration Required

Phase 4 reuses existing tables from Phase 17.5:
- ✅ `document_chunks` (already exists)
- ✅ `annotations` (already exists)
- ✅ `graph_entities` (already exists)
- ✅ `graph_relationships` (already exists)

**No Alembic migration needed!**

### Step 3: Module Registration

The module is already registered in `app/__init__.py`:

```python
additional_routers: List[Tuple[str, str, List[str]]] = [
    # ... other routers
    ("pdf_ingestion", "app.modules.pdf_ingestion", ["router"]),
]
```

If you're on an older version, add this line to the `additional_routers` list.

### Step 4: Restart Application

```bash
# Development
uvicorn app.main:app --reload

# Production (Render)
# Render will automatically restart on git push
```

### Step 5: Verify Endpoints

```bash
# Check if endpoints are registered
curl http://localhost:8000/docs

# Look for:
# - POST /api/resources/pdf/ingest
# - POST /api/resources/pdf/annotate
# - POST /api/resources/pdf/search/graph
```

### Step 6: Test Upload

```bash
# Create a test PDF or use existing one
curl -X POST http://localhost:8000/api/resources/pdf/ingest \
  -F "file=@test.pdf" \
  -F "title=Test Document" \
  -F "tags=Test"
```

Expected response:
```json
{
  "resource_id": "uuid",
  "status": "completed",
  "total_chunks": 5,
  "message": "PDF ingested successfully: 5 chunks created"
}
```

## Integration with Existing Modules

### Resources Module

PDF ingestion creates `Resource` records with:
- `type="research_paper"`
- `format="application/pdf"`
- `ingestion_status="completed"`

These resources appear in existing resource endpoints:
```bash
# List all resources (includes PDFs)
GET /api/resources

# Get specific PDF resource
GET /api/resources/{resource_id}
```

### Search Module

PDF chunks are searchable via existing search endpoints:
```bash
# Hybrid search includes PDF chunks
POST /api/search/hybrid
{
  "query": "oauth security",
  "limit": 10
}
```

### Graph Module

PDF annotations create graph entities and relationships:
```bash
# View graph includes PDF nodes
GET /api/graph/view

# Citations include PDF references
GET /api/citations
```

### Annotations Module

PDF annotations are accessible via existing annotation endpoints:
```bash
# List annotations (includes PDF annotations)
GET /api/annotations

# Get annotations for specific resource
GET /api/annotations?resource_id={pdf_resource_id}
```

## Event Bus Integration

Phase 4 emits events that other modules can subscribe to:

### Emitted Events

```python
# After PDF ingestion
event_bus.emit("resource.created", {
    "resource_id": str(resource_id),
    "title": title,
    "type": "pdf",
    "chunk_count": len(chunks)
})

# After chunk creation
event_bus.emit("resource.chunked", {
    "resource_id": str(resource_id),
    "chunk_id": str(chunk_id),
    "chunk_index": chunk_index,
    "embedding": embedding_vector
})

# After annotation
event_bus.emit("annotation.created", {
    "annotation_id": str(annotation_id),
    "chunk_id": str(chunk_id),
    "concept_tags": concept_tags,
    "graph_links": len(linked_chunks)
})
```

### Subscribe to Events (Optional)

If you want to react to PDF events in other modules:

```python
# In your module's handlers.py
from app.shared.event_bus import event_bus

def handle_pdf_created(payload: dict):
    resource_id = payload["resource_id"]
    # Your custom logic here
    print(f"New PDF created: {resource_id}")

# Register handler
event_bus.subscribe("resource.created", handle_pdf_created)
```

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Optional: PDF-specific settings
PDF_MAX_FILE_SIZE_MB=50
PDF_CHUNK_SIZE_TOKENS=512
PDF_ENABLE_OCR=false  # Future feature
```

### Render Configuration

Update `render.yaml`:

```yaml
services:
  - type: web
    name: pharos-api
    env: python
    buildCommand: "pip install -r requirements-base.txt"
    startCommand: "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: pharos-db
          property: connectionString
      - key: PDF_MAX_FILE_SIZE_MB
        value: "50"
```

## Testing Integration

### Run Integration Tests

```bash
# Test PDF ingestion
pytest backend/tests/test_pdf_ingestion_e2e.py -v

# Test with existing modules
pytest backend/tests/test_integration.py -v
```

### Manual Integration Test

```bash
# 1. Upload PDF
RESOURCE_ID=$(curl -X POST http://localhost:8000/api/resources/pdf/ingest \
  -F "file=@test.pdf" \
  -F "title=Test" \
  | jq -r '.resource_id')

# 2. Verify resource exists
curl http://localhost:8000/api/resources/$RESOURCE_ID

# 3. Search for PDF content
curl -X POST http://localhost:8000/api/search/hybrid \
  -H "Content-Type: application/json" \
  -d '{"query":"test content","limit":10}'

# 4. Annotate PDF chunk
CHUNK_ID=$(curl http://localhost:8000/api/resources/$RESOURCE_ID \
  | jq -r '.chunks[0].chunk_id')

curl -X POST http://localhost:8000/api/resources/pdf/annotate \
  -H "Content-Type: application/json" \
  -d "{\"chunk_id\":\"$CHUNK_ID\",\"concept_tags\":[\"Test\"]}"

# 5. GraphRAG search
curl -X POST http://localhost:8000/api/resources/pdf/search/graph \
  -H "Content-Type: application/json" \
  -d '{"query":"test","max_hops":2,"limit":10}'
```

## Troubleshooting

### Issue: PyMuPDF Import Error

```
ImportError: No module named 'fitz'
```

**Solution**:
```bash
pip install PyMuPDF
```

### Issue: PDF Extraction Fails

```
PDFExtractionError: Failed to extract PDF content
```

**Solution**:
1. Verify PDF is valid: `file your.pdf`
2. Check file size: `ls -lh your.pdf`
3. Try with different PDF
4. Check logs for detailed error

### Issue: No Graph Links Created

```json
{
  "graph_links_created": 0,
  "linked_code_chunks": []
}
```

**Solution**:
1. Ensure code chunks exist in database
2. Check concept tags match code content
3. Verify `semantic_summary` field is populated on code chunks

### Issue: Search Returns No Results

**Solution**:
1. Check if PDF chunks were created: `GET /api/resources/{resource_id}`
2. Verify annotations exist: `GET /api/annotations?resource_id={resource_id}`
3. Increase `max_hops` parameter in search
4. Check graph entities: `GET /api/graph/entities`

## Rollback Plan

If you need to rollback Phase 4:

### Step 1: Remove Module Registration

In `app/__init__.py`, remove:
```python
("pdf_ingestion", "app.modules.pdf_ingestion", ["router"]),
```

### Step 2: Restart Application

```bash
uvicorn app.main:app --reload
```

### Step 3: Clean Up Data (Optional)

```sql
-- Remove PDF resources
DELETE FROM resources WHERE type = 'research_paper';

-- Remove PDF chunks
DELETE FROM document_chunks WHERE is_remote = false;

-- Remove PDF annotations
DELETE FROM annotations WHERE resource_id IN (
    SELECT id FROM resources WHERE type = 'research_paper'
);
```

**Note**: This is optional. Leaving the data won't cause issues.

## Performance Tuning

### Optimize PDF Extraction

```python
# In service.py, adjust chunk size
PDF_CHUNK_SIZE_TOKENS = 512  # Default
# Increase for fewer chunks: 1024
# Decrease for more granular chunks: 256
```

### Optimize Graph Traversal

```python
# In router.py, adjust default max_hops
max_hops: int = 2  # Default
# Increase for deeper search: 3
# Decrease for faster search: 1
```

### Database Indexes

Ensure indexes exist (should be automatic):
```sql
-- Check indexes
SELECT * FROM pg_indexes WHERE tablename IN (
    'document_chunks',
    'graph_entities',
    'graph_relationships'
);
```

## Monitoring

### Key Metrics to Monitor

1. **PDF Ingestion Rate**
   - Metric: `pdf_ingestion_duration_seconds`
   - Alert: > 60 seconds per PDF

2. **Graph Link Creation**
   - Metric: `graph_links_created_total`
   - Alert: 0 links for multiple PDFs

3. **Search Latency**
   - Metric: `graph_search_duration_ms`
   - Alert: > 2000ms

### Logging

Check logs for PDF ingestion:
```bash
# Development
tail -f logs/app.log | grep "PDF ingestion"

# Production (Render)
# View logs in Render dashboard
```

## Next Steps

After successful integration:

1. **Frontend Integration**: Build UI for PDF upload and annotation
2. **Advanced Features**: Add LaTeX equation parsing, table extraction
3. **Performance Optimization**: Tune chunk size, graph traversal depth
4. **User Training**: Document PDF ingestion workflow for end users

## Support

For issues:
1. Check module README: `app/modules/pdf_ingestion/README.md`
2. Review test cases: `tests/test_pdf_ingestion_e2e.py`
3. Check implementation docs: `PHASE_4_IMPLEMENTATION.md`
4. Review logs for detailed errors

## Checklist

- [ ] PyMuPDF installed
- [ ] Module registered in `app/__init__.py`
- [ ] Application restarted
- [ ] Endpoints verified in `/docs`
- [ ] Test PDF uploaded successfully
- [ ] Annotation created successfully
- [ ] GraphRAG search returns results
- [ ] Integration tests pass
- [ ] Monitoring configured
- [ ] Documentation reviewed

---

**Migration Complete!** Phase 4 is now integrated with your Pharos deployment.
