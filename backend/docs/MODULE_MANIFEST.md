# Pharos Module Manifest

**Last Updated**: April 10, 2026  
**Status**: Post-Reconciliation (13 Active Modules)  
**Architecture**: Vertical Slice with Event-Driven Communication

## Overview

This document is the **single source of truth** for all active modules in the Pharos backend. After the code reconciliation (April 2026), we have finalized the architecture at **13 active modules**.

## Active Modules (13)

### 1. annotations
**Purpose**: Text highlights, notes, and tags on resources  
**Location**: `app/modules/annotations/`  
**Status**: ✅ Active  
**Phase**: Core (Phase 2)

**Key Features:**
- Precise text highlighting with character offsets
- Rich notes with semantic embeddings
- Tag organization with color-coding
- Semantic search across annotations
- Export to Markdown and JSON

**Events Emitted:**
- `annotation.created`
- `annotation.updated`
- `annotation.deleted`

**Events Consumed:**
- `resource.created` (initialize annotation support)

---

### 2. authority
**Purpose**: Subject authority and classification trees  
**Location**: `app/modules/authority/`  
**Status**: ✅ Active  
**Phase**: Core (Phase 2)

**Key Features:**
- Hierarchical subject authority trees
- Creator/publisher authority management
- Authority linking and validation
- Controlled vocabulary

**Events Emitted:**
- `authority.created`
- `authority.updated`

**Events Consumed:**
- `resource.classified` (link to authority)

---

### 3. collections
**Purpose**: Collection management and resource organization  
**Location**: `app/modules/collections/`  
**Status**: ✅ Active  
**Phase**: Core (Phase 1)

**Key Features:**
- Flexible collection management
- Hierarchical organization
- Resource grouping
- Visibility control (private, shared, public)

**Events Emitted:**
- `collection.created`
- `collection.updated`
- `collection.resource_added`
- `collection.resource_removed`

**Events Consumed:**
- `resource.created` (auto-add to collections)

---

### 4. graph
**Purpose**: Knowledge graph, citations, and discovery  
**Location**: `app/modules/graph/`  
**Status**: ✅ Active  
**Phase**: Core (Phase 3) + GraphRAG (Phase 4)

**Key Features:**
- Citation extraction and resolution
- Knowledge graph construction
- Entity and relationship extraction
- Contradiction detection
- Hypothesis discovery (LBD)
- GraphRAG retrieval
- PDF-to-code linking (Phase 4)

**Events Emitted:**
- `citation.extracted`
- `graph.updated`
- `hypothesis.discovered`
- `graph.entity_extracted`
- `graph.relationship_extracted`
- `pdf.linked_to_code` (Phase 4)

**Events Consumed:**
- `resource.created` (extract citations)
- `pdf.ingested` (Phase 4: create concept entities)
- `pdf.annotated` (Phase 4: link to code)

---

### 5. mcp
**Purpose**: Context Assembly for Ronin LLM integration  
**Location**: `app/modules/mcp/`  
**Status**: ✅ Active  
**Phase**: Pharos + Ronin (Phase 7)

**Key Features:**
- Context retrieval for LLM queries
- Semantic search integration
- GraphRAG traversal
- Pattern matching
- Research paper retrieval
- Code fetching (hybrid GitHub storage)
- Context assembly pipeline (<800ms)

**API Endpoints:**
- `POST /api/context/retrieve` - Assemble context for LLM
- `GET /api/context/health` - Health check

**Events Emitted:**
- `context.retrieved`
- `context.assembly_failed`

**Events Consumed:**
- `resource.created` (index for retrieval)
- `pattern.learned` (Phase 6: use in context)

**Integration:**
- Ronin LLM assistant
- IDE plugins (Phase 12)
- CLI interface (Phase 13)

---

### 6. monitoring
**Purpose**: System health, metrics, and observability  
**Location**: `app/modules/monitoring/`  
**Status**: ✅ Active  
**Phase**: Core (Phase 1)

**Key Features:**
- Health check endpoints
- Performance metrics
- Error tracking
- Event bus monitoring
- Module dependency validation

**Events Emitted:**
- `monitoring.alert`
- `monitoring.metric_recorded`

**Events Consumed:**
- All events (for monitoring)

---

### 7. patterns
**Purpose**: Pattern Learning for Ronin integration  
**Location**: `app/modules/patterns/`  
**Status**: ✅ Active  
**Phase**: Pharos + Ronin (Phase 6)

**Key Features:**
- Extract successful patterns from code history
- Identify failed patterns (bugs, refactorings)
- Learn coding style (naming, error handling)
- Track architectural patterns
- Success/failure analysis
- Pattern recommendation

**API Endpoints:**
- `POST /api/patterns/learn` - Learn patterns from history
- `GET /api/patterns/search` - Search learned patterns
- `GET /api/patterns/stats` - Pattern statistics

**Events Emitted:**
- `pattern.learned`
- `pattern.applied`
- `pattern.failed`

**Events Consumed:**
- `resource.created` (analyze for patterns)
- `quality.computed` (identify successful patterns)

**Integration:**
- Ronin LLM assistant
- Self-improving loop (Phase 8)

---

### 8. pdf_ingestion
**Purpose**: PDF upload, extraction, and GraphRAG linking  
**Location**: `app/modules/pdf_ingestion/`  
**Status**: ✅ Active  
**Phase**: Phase 4 (Complete)

**Key Features:**
- PDF upload and extraction (PyMuPDF)
- Academic fidelity (equations, tables, figures)
- Semantic chunking
- Conceptual annotation
- GraphRAG linking to code
- Unified search (PDFs + code)

**API Endpoints:**
- `POST /api/resources/pdf/ingest` - Upload and extract PDF
- `POST /api/resources/pdf/annotate` - Annotate PDF chunk
- `POST /api/resources/pdf/search/graph` - GraphRAG search

**Events Emitted:**
- `pdf.ingested`
- `pdf.annotated`
- `pdf.linked_to_code`

**Events Consumed:**
- `graph.entity_extracted` (link concepts to code)

**Documentation:**
- Module README: `app/modules/pdf_ingestion/README.md`
- Implementation: `PHASE_4_IMPLEMENTATION.md`
- Quick Start: `PHASE_4_QUICKSTART.md`

---

### 9. quality
**Purpose**: Multi-dimensional quality assessment  
**Location**: `app/modules/quality/`  
**Status**: ✅ Active  
**Phase**: Core (Phase 2)

**Key Features:**
- Multi-dimensional scoring (accuracy, completeness, consistency, timeliness)
- Outlier detection
- Quality trends
- Automated assessment

**Events Emitted:**
- `quality.computed`
- `quality.outlier_detected`

**Events Consumed:**
- `resource.created` (compute quality)
- `resource.updated` (recompute quality)

---

### 10. resources
**Purpose**: Resource CRUD operations and metadata  
**Location**: `app/modules/resources/`  
**Status**: ✅ Active  
**Phase**: Core (Phase 1)

**Key Features:**
- Resource creation, retrieval, update, delete
- Metadata management (Dublin Core + custom)
- Embedding generation
- Chunking (parent-child)
- Ingestion workflow

**Events Emitted:**
- `resource.created`
- `resource.updated`
- `resource.deleted`
- `resource.chunked`

**Events Consumed:**
- None (root module)

---

### 11. scholarly
**Purpose**: Academic metadata extraction  
**Location**: `app/modules/scholarly/`  
**Status**: ✅ Active  
**Phase**: Core (Phase 2)

**Key Features:**
- Equation extraction and parsing
- Table extraction
- Figure detection
- Citation parsing
- Author/affiliation extraction
- DOI/PMID/arXiv ID resolution

**Events Emitted:**
- `metadata.extracted`
- `equations.parsed`
- `tables.extracted`

**Events Consumed:**
- `resource.created` (extract metadata)
- `pdf.ingested` (Phase 4: extract from PDF)

---

### 12. search
**Purpose**: Hybrid search (keyword, semantic, full-text)  
**Location**: `app/modules/search/`  
**Status**: ✅ Active (Reconciled)  
**Phase**: Core (Phase 3) + Vector Reality (April 2026)

**Key Features:**
- Full-text search (FTS5, PostgreSQL tsvector)
- Dense vector semantic search (pgvector)
- Sparse vector learned keyword search (SPLADE)
- Hybrid search with RRF fusion
- ColBERT reranking
- Query-adaptive weighting
- Parent-child retrieval
- GraphRAG retrieval
- Question-based retrieval (Reverse HyDE)

**Recent Changes (April 2026):**
- ✅ Implemented real pgvector (replaced Python cosine similarity)
- ✅ Implemented real SPLADE (replaced TF-IDF stub)
- ✅ Database-native vector operations (<->, <=>, <#>)
- ✅ HNSW and IVFFlat indexes
- ✅ 20x performance improvement

**Events Emitted:**
- `search.executed`
- `search.failed`

**Events Consumed:**
- `resource.created` (index for search)
- `resource.updated` (reindex)

**Documentation:**
- Vector Reconciliation: `docs/VECTOR_RECONCILIATION_SUMMARY.md`
- Test Suite: `tests/integration/test_hybrid_vector_search.py`

---

### 13. taxonomy
**Purpose**: ML-based classification and taxonomy management  
**Location**: `app/modules/taxonomy/`  
**Status**: ✅ Active  
**Phase**: Core (Phase 2)

**Key Features:**
- Hierarchical taxonomy trees
- ML-based auto-classification
- Model training and evaluation
- Classification confidence scoring

**Events Emitted:**
- `resource.classified`
- `taxonomy.model_trained`

**Events Consumed:**
- `resource.created` (auto-classify)

---

## Removed Modules (Ghost Protocol - April 2026)

### ❌ planning
**Status**: Removed  
**Reason**: Dead code, not in use  
**Backup**: `backups/ghost_modules_20260410/planning/`

### ❌ github (standalone)
**Status**: Removed  
**Reason**: Functionality moved to resources module  
**Backup**: `backups/ghost_modules_20260410/github/`  
**Note**: GitHub integration for hybrid storage (Phase 5) will be implemented in resources module

---

## Module Communication

All modules communicate via **event bus** (no direct imports).

**Event Bus Characteristics:**
- In-memory, async
- <1ms latency (P95)
- Pub/sub pattern
- Type-safe event schemas

**Example Flow:**
```
1. User uploads PDF → pdf_ingestion.ingest()
2. pdf_ingestion emits pdf.ingested
3. scholarly subscribes → extracts metadata
4. graph subscribes → creates concept entities
5. search subscribes → indexes for search
6. All happen asynchronously, no blocking
```

---

## Module Isolation Rules

### Allowed Imports
✅ Modules can import from:
- `app.shared.*` - Shared kernel only
- `app.events.*` - Event system
- `app.domain.*` - Domain objects
- Standard library and third-party packages

### Forbidden Imports
❌ Modules CANNOT import from:
- Other modules (`app.modules.*`)
- Legacy layers (`app.routers.*`, `app.services.*`, `app.schemas.*`)

### Validation
```bash
# Check all modules for violations
python scripts/check_module_isolation.py
```

---

## Module Startup Order

Modules are registered in `app/main.py` in dependency order:

1. monitoring (no dependencies)
2. resources (root module)
3. collections (depends on resources events)
4. annotations (depends on resources events)
5. quality (depends on resources events)
6. scholarly (depends on resources events)
7. taxonomy (depends on resources events)
8. graph (depends on resources, scholarly events)
9. search (depends on resources, graph events)
10. pdf_ingestion (depends on graph, search events)
11. authority (depends on taxonomy events)
12. patterns (depends on quality, graph events)
13. mcp (depends on search, patterns, graph events)

---

## Performance Metrics

| Module | Startup Time | Event Latency | API Response |
|--------|--------------|---------------|--------------|
| annotations | <1s | <1ms | <100ms |
| authority | <1s | <1ms | <150ms |
| collections | <1s | <1ms | <100ms |
| graph | <2s | <5ms | <200ms |
| mcp | <2s | <10ms | <800ms |
| monitoring | <0.5s | <1ms | <50ms |
| patterns | <2s | <10ms | <1000ms |
| pdf_ingestion | <2s | <50ms | <30s |
| quality | <1s | <5ms | <150ms |
| resources | <1s | <1ms | <100ms |
| scholarly | <1s | <10ms | <200ms |
| search | <2s | <5ms | <250ms |
| taxonomy | <2s | <10ms | <200ms |

**Total Startup**: <10 seconds

---

## Testing

Each module has:
- Unit tests: `tests/modules/test_{module}_*.py`
- Integration tests: `tests/integration/test_{module}_*.py`
- E2E tests: `tests/test_e2e_workflows.py`

**Test Coverage Target**: >80% per module

---

## Documentation

Each module has:
- `README.md` - Module overview and API
- `router.py` - API endpoints (docstrings)
- `service.py` - Business logic (docstrings)
- `schema.py` - Request/response models (Pydantic)
- `model.py` - Database models (SQLAlchemy)
- `handlers.py` - Event handlers

---

## Related Documentation

- [Architecture Overview](architecture/overview.md)
- [Event System](architecture/event-system.md)
- [Module Development Guide](guides/workflows.md)
- [Vector Reconciliation](VECTOR_RECONCILIATION_SUMMARY.md)
- [Phase 4 Summary](../PHASE_4_SUMMARY.md)
- [Pharos + Ronin Vision](../../PHAROS_RONIN_VISION.md)

---

**Pharos**: Your second brain for code.  
**Status**: 13 active modules, production-ready.  
**Next**: Phase 5 (Hybrid GitHub Storage), Phase 6 (Pattern Learning), Phase 7 (Ronin Integration).
