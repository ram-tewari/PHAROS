# Phase 4: PDF Ingestion & GraphRAG - Quick Reference

## What is Phase 4?

Phase 4 adds **research paper management** to Pharos, enabling automatic linking between PDF concepts and code implementations through GraphRAG.

## Three Core Features

### 1. PDF Ingestion
**Upload PDFs and extract with academic fidelity**

```bash
POST /api/resources/pdf/ingest
```

- Extracts text, equations, tables, figures
- Preserves page coordinates
- Creates semantic chunks
- Generates embeddings

### 2. Conceptual Annotation
**Tag PDF chunks with concepts**

```bash
POST /api/resources/pdf/annotate
```

- Tag chunks with concepts (OAuth, ML, Security)
- Add notes and highlights
- Automatic graph entity creation
- Links to related code

### 3. Unified Search
**Search across PDFs and code simultaneously**

```bash
POST /api/resources/pdf/search/graph
```

- Multi-hop graph traversal
- Returns both PDF sections and code
- Relevance scoring
- Includes annotations

## Quick Start

### 1. Upload a PDF
```bash
curl -X POST http://localhost:8000/api/resources/pdf/ingest \
  -F "file=@paper.pdf" \
  -F "title=Research Paper" \
  -F "tags=ML,AI"
```

### 2. Annotate a Chunk
```bash
curl -X POST http://localhost:8000/api/resources/pdf/annotate \
  -H "Content-Type: application/json" \
  -d '{
    "chunk_id": "uuid",
    "concept_tags": ["Machine Learning"],
    "note": "Key concept"
  }'
```

### 3. Search
```bash
curl -X POST http://localhost:8000/api/resources/pdf/search/graph \
  -H "Content-Type: application/json" \
  -d '{
    "query": "machine learning",
    "max_hops": 2,
    "limit": 10
  }'
```

## How GraphRAG Linking Works

```
1. Upload PDF about OAuth
   ↓
2. Annotate section with "OAuth" tag
   ↓
3. System creates graph entity: OAuth (Concept)
   ↓
4. System finds code chunks mentioning "oauth"
   ↓
5. System creates relationships:
   - PDF chunk → OAuth concept
   - OAuth concept → Code chunks
   ↓
6. Search "oauth" returns both PDF and code
```

## Key Concepts

### Concept Tags
Labels that describe what a PDF chunk is about:
- **Technical**: OAuth, REST API, GraphQL, JWT
- **Domain**: Machine Learning, Security, Authentication
- **Pattern**: Factory Pattern, Observer Pattern, MVC

### Graph Entities
Nodes in the knowledge graph:
- **Type**: Concept, Person, Organization, Method
- **Name**: OAuth, Security, Machine Learning
- **Relationships**: MENTIONS, IMPLEMENTS, CONTRADICTS

### GraphRAG
Graph-based Retrieval Augmented Generation:
- Uses graph relationships for context
- Multi-hop traversal finds related content
- Combines semantic search with graph structure

## Performance

| Operation | Time |
|-----------|------|
| PDF Upload (10 pages) | ~30 seconds |
| Annotation | ~200ms |
| Search (2 hops) | <1 second |

## Use Cases

### 1. Security Audit
Upload security papers → Annotate requirements → Verify code implements them

### 2. Onboarding
New developer searches "authentication" → Sees both papers and code

### 3. Research Implementation
Upload ML paper → Annotate algorithms → Link to implementation code

### 4. Best Practices
Link OAuth RFC to authentication code → Future developers see the standard

## Module Location

```
backend/app/modules/pdf_ingestion/
├── __init__.py
├── router.py      # 3 API endpoints
├── service.py     # Business logic
├── schema.py      # Request/response models
└── README.md      # Complete documentation
```

## Documentation

- **Module README**: `backend/app/modules/pdf_ingestion/README.md`
- **Implementation**: `backend/PHASE_4_IMPLEMENTATION.md`
- **Quick Start**: `backend/PHASE_4_QUICKSTART.md`
- **Integration**: `backend/PHASE_4_INTEGRATION_COMPLETE.md`

## Verification

Check integration status:
```bash
cd backend
python verify_pdf_integration.py
```

Expected: ✅ 6/6 checks passed

## API Documentation

View in browser:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

Look for "PDF Ingestion" section.

## Common Commands

### Start Server
```bash
cd backend
uvicorn app.main:app --reload
```

### Run Tests
```bash
pytest tests/test_pdf_ingestion_e2e_fixed.py -v
```

### Verify Integration
```bash
python verify_pdf_integration.py
```

## Troubleshooting

### PyMuPDF not found
```bash
pip install PyMuPDF
```

### Routes not appearing
```bash
# Check registration
python -c "from app import create_app; app = create_app(); print([r.path for r in app.routes if 'pdf' in r.path])"
```

### No graph links created
- Ensure code chunks exist in database
- Check concept tags match code content
- Verify semantic_summary field is populated

## Key Files

- `app/modules/pdf_ingestion/router.py` - API endpoints
- `app/modules/pdf_ingestion/service.py` - Core logic
- `app/modules/pdf_ingestion/schema.py` - Data models
- `verify_pdf_integration.py` - Integration checker
- `PHASE_4_SUMMARY.md` - Executive summary

## Status

✅ **INTEGRATED AND OPERATIONAL**

- 3 API endpoints registered
- PyMuPDF installed
- Database models ready
- Event bus connected
- Documentation complete

## Next Steps

1. Upload test PDFs
2. Create annotations
3. Test search
4. Build frontend UI (Phase 5)

---

**Quick Reference Version**: 1.0  
**Last Updated**: 2026-04-10  
**Status**: Production Ready
