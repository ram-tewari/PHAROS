# Pharos - Technical Stack

## Architecture

**Type**: Hybrid Edge-Cloud with Modular Monolith + LLM Memory Layer
**Pattern**: Vertical slices with shared kernel
**Deployment**: Cloud API (Render) + Edge Worker (Local GPU) + LLM Integration (Ronin)
**Status**: Production (Phases 5-8 Complete, 21+ phases total)
**Focus**: Code intelligence, research management, and LLM context provision for developers

### Architectural Principles

1. **Vertical Slice Architecture**: Each module is self-contained with its own models, schemas, services, and routes
2. **Event-Driven Communication**: Modules communicate via event bus (no direct imports)
3. **Shared Kernel**: Cross-cutting concerns (database, cache, embeddings, AI) in shared layer
4. **Zero Circular Dependencies**: Enforced by module isolation rules
5. **API-First Design**: All functionality exposed via REST API for LLM and IDE integration
6. **Hybrid Storage**: Metadata + embeddings local, code fetched from GitHub on-demand (17x storage reduction)
7. **Self-Improving**: Pattern learning engine extracts knowledge from code history

### Module Structure

**14 Domain Modules** (Production-Ready):
- Annotations, Authority, Collections, Curation, Graph
- Monitoring, Quality, Recommendations, Resources, Scholarly
- Search, Taxonomy, GitHub (Phase 5), Patterns (Phase 6 + 8)

**Each Module Contains**:
- `router.py` - FastAPI endpoints
- `service.py` - Business logic
- `schema.py` - Pydantic models
- `model.py` - SQLAlchemy models
- `handlers.py` - Event handlers
- `README.md` - Documentation

**Shared Kernel**:
- Database session management
- Event bus (in-memory, async)
- Vector embeddings
- AI operations (summarization, extraction)
- Redis caching
- GitHub API client (Phase 5)

### Event-Driven Communication

**Event Bus**: In-memory, async, <1ms latency (p95)

**Event Categories**:
- Resource lifecycle: `resource.created`, `resource.updated`, `resource.deleted`, `resource.chunked`
- Collections: `collection.created`, `collection.resource_added`
- Annotations: `annotation.created`, `annotation.updated`, `annotation.deleted`
- Quality: `quality.computed`, `quality.outlier_detected`
- Classification: `resource.classified`, `taxonomy.model_trained`
- Graph: `citation.extracted`, `graph.updated`, `hypothesis.discovered`, `graph.entity_extracted`, `graph.relationship_extracted`
- Recommendations: `recommendation.generated`, `user.profile_updated`
- Curation: `curation.reviewed`, `curation.approved`
- Metadata: `metadata.extracted`, `equations.parsed`, `tables.extracted`
- Advanced RAG: `resource.chunked`, `resource.chunking_failed`
- **PDF Ingestion** (Phase 4): `pdf.ingested`, `pdf.annotated`, `pdf.linked_to_code`
- **Pattern Learning** (Phase 6): `pattern.extracted`, `profile.updated`
- **Self-Improving** (Phase 8): `rule.proposed`, `rule.accepted`, `rule.rejected`

**Event Flow Example**:
```
1. User creates resource → resources module emits resource.created
2. Quality module subscribes → computes quality scores
3. Taxonomy module subscribes → auto-classifies resource
4. Scholarly module subscribes → extracts metadata
5. Graph module subscribes → extracts citations
6. All happen asynchronously, no blocking

Phase 4 Example:
1. User uploads PDF → pdf_ingestion module emits pdf.ingested
2. User annotates chunk → emits pdf.annotated
3. Graph module subscribes → creates concept entities
4. Graph module links PDF to code → emits pdf.linked_to_code
```

## Backend Stack

### Core Framework
- **Python 3.8+** - Primary language
- **FastAPI** - Web framework for REST API
- **Uvicorn** - ASGI server
- **Pydantic** - Data validation and serialization

### Pharos + Ronin Integration Stack

**LLM Integration**:
- **API-First Design**: All Pharos features accessible via REST API
- **Context Assembly**: Package code + papers + patterns for LLM consumption
- **Pattern Learning**: Extract successful patterns from code history
- **Hybrid Storage**: Metadata local, code fetched from GitHub on-demand

**GitHub Integration** (Phase 5):
- **PyGithub** - GitHub API client for code fetching
- **GitHub REST API** - Fetch file contents, repository metadata
- **Rate Limiting**: 5000 requests/hour (authenticated)
- **Caching**: Redis cache for fetched code (1 hour TTL)

**Pattern Learning Engine** (Phase 6):
- **AST Analysis**: Extract structural patterns from code
- **Style Profiler**: Learn naming conventions, error handling, preferences
- **Success Tracking**: Identify high-quality code patterns (quality > 0.8)
- **Failure Analysis**: Track bugs, refactorings, and fixes

**Context Retrieval Pipeline** (Phase 7):
- **Semantic Search**: HNSW vector search (<250ms)
- **GraphRAG Traversal**: Multi-hop graph queries (<200ms)
- **Pattern Matching**: Find similar code from history (<100ms)
- **Research Retrieval**: Relevant papers with annotations (<150ms)
- **Code Fetching**: On-demand from GitHub (<100ms, cached)
- **Total Time**: <800ms for complete context assembly

### Database
- **SQLite** - Development and small deployments
- **PostgreSQL 15+** - Production deployments
- **Alembic** - Database migrations
- **SQLAlchemy 2.0** - ORM with async support

### AI/ML
- **Transformers (Hugging Face)** - NLP models for summarization and classification
- **PyTorch** - Deep learning framework
- **Sentence-Transformers** - Embedding generation (nomic-embed-text-v1)
- **FAISS** - Vector similarity search
- **spaCy** - NLP processing
- **Tree-Sitter** - Multi-language code parsing (AST generation)
- **PyMuPDF** (Phase 4) - PDF extraction with academic fidelity

### Document Processing (Phase 4)
- **PyMuPDF (fitz)** - PDF text extraction preserving structure
- **Equation Detection** - Heuristic detection of mathematical equations
- **Table Detection** - Grid structure and table extraction
- **Figure Detection** - Image block identification
- **Coordinate Preservation** - Page-level bounding boxes for all elements

### Task Processing
- **Celery** - Async task queue
- **Redis** - Cache and message broker

### Testing
- **pytest** - Test framework
- **pytest-asyncio** - Async test support
- **pytest-cov** - Coverage reporting
- **hypothesis** - Property-based testing
- **Golden Data Pattern** - Immutable test expectations in JSON files
- **Protocol-Based Testing** - Anti-gaslighting test framework

## Frontend Stack

### Core Framework
- **React 18** - UI library
- **TypeScript 5** - Type safety
- **Vite 5** - Build tool and dev server

### Routing & State
- **React Router 6** - Client-side routing
- **Zustand** - Lightweight state management
- **React Query** - Server state management

### Styling
- **CSS Modules** - Component styling
- **Tailwind CSS** - Utility-first CSS
- **Framer Motion** - Animations

### Testing
- **Vitest** - Unit testing
- **React Testing Library** - Component testing

## Development Tools

### Code Quality
- **Ruff** - Python linter and formatter
- **ESLint** - JavaScript/TypeScript linter
- **Prettier** - Code formatter
- **pre-commit** - Git hooks for quality checks

### Version Control
- **Git** - Source control
- **GitHub** - Repository hosting
- **GitHub Actions** - CI/CD pipelines

### Containerization
- **Docker** - Container runtime
- **Docker Compose** - Multi-container orchestration

## Key Constraints

### Performance Requirements
- API response time: P95 < 200ms
- Search latency: < 500ms for hybrid search
- Embedding generation: < 2s per document
- Database queries: < 100ms for most operations
- Event emission + delivery: < 1ms (p95)
- Module startup: < 10 seconds total

### Scalability Targets
- 100K+ resources in database
- 10K+ concurrent embeddings
- 1K+ collections per user
- 100+ requests/second
- **1000+ codebases indexed** (Pharos + Ronin) ✅ ACHIEVED
- **10K+ codebases supported** (with hybrid GitHub storage)
- **<1s context retrieval** for LLM queries ✅ ACHIEVED (~800ms)
- **<2s pattern learning** from code history ✅ ACHIEVED (~1-2s)

### Resource Limits
- Memory: 4GB minimum, 8GB recommended
- Storage: 10GB minimum for models and data
- **Storage (Hybrid)**: 2GB for 1000 codebases (metadata + embeddings only) ✅ ACHIEVED
- CPU: 2+ cores recommended
- GPU: Optional, improves ML performance 10x (RTX 4070 used in production)
- **Network**: Required for GitHub API access (hybrid storage mode)
- **Cost**: $7/mo production (Render Starter) ✅ ACHIEVED

## Database Strategy

### PostgreSQL (Production - NeonDB)
```bash
DATABASE_URL=postgresql://user:pass@host:5432/db
```
- High concurrency
- JSONB support
- Full-text search
- Advanced indexing
- Connection pooling
- **Current**: Used by https://pharos-cloud-api.onrender.com

### SQLite (Development Only)
```bash
DATABASE_URL=sqlite:///./backend.db
```
- Zero configuration
- File-based, portable
- Limited concurrency
- **Status**: Local development only

### Migration Path
- Maintain SQLite compatibility
- Test against both databases
- Use Alembic for schema changes
- Provide migration scripts

## Common Commands

### Backend Development (Cloud API)
```bash
# Production API: https://pharos-cloud-api.onrender.com
# Database: PostgreSQL (NeonDB)
# Authentication: Required (PHAROS_ADMIN_TOKEN)

# Test API health
curl https://pharos-cloud-api.onrender.com/health

# Test with authentication
curl -H "Authorization: Bearer $PHAROS_ADMIN_TOKEN" \
  https://pharos-cloud-api.onrender.com/api/github/health

# Local development (if needed)
cd backend
uvicorn app.main:app --reload
```

### Testing Patterns

```bash
# Protocol-based testing (Golden Data pattern)
# Tests load expectations from immutable JSON files
# Never modify tests to match implementation - fix implementation instead

# Run tests with Golden Data validation
pytest tests/modules/quality/test_scoring.py -v

# Run all module tests
pytest tests/modules/ -v

# Run tests for specific module
pytest tests/modules/search/ -v

# Run property-based tests (hypothesis)
pytest tests/properties/ -v

# Check test infrastructure
pytest tests/test_infrastructure_checkpoint.py -v
```

### Module Development
```bash
# Create new module structure
mkdir -p app/modules/mymodule
touch app/modules/mymodule/{__init__.py,router.py,service.py,schema.py,model.py,handlers.py,README.md}

# Register module in main.py
# Add to register_all_modules() function

# Test module endpoints
pytest tests/modules/test_mymodule_endpoints.py -v

# Verify module isolation
python scripts/check_module_isolation.py
```

### Frontend Development
```bash
# Start dev server
cd frontend
npm run dev

# Build for production
npm run build

# Run tests
npm test

# Lint
npm run lint
```

### Docker
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Rebuild
docker-compose up -d --build
```

### Database
```bash
# Create migration
cd backend
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Backup SQLite
cp backend.db backend.db.backup

# Backup PostgreSQL
pg_dump -U user -d database > backup.sql
```

## Environment Variables

### Required
```bash
DATABASE_URL=sqlite:///./backend.db
```

### Optional (with defaults)
```bash
# AI Models
EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1
SUMMARIZER_MODEL=facebook/bart-large-cnn

# Search
DEFAULT_HYBRID_SEARCH_WEIGHT=0.5
EMBEDDING_CACHE_SIZE=1000

# Graph
GRAPH_WEIGHT_VECTOR=0.6
GRAPH_WEIGHT_TAGS=0.3
GRAPH_WEIGHT_CLASSIFICATION=0.1

# Testing
TEST_DATABASE_URL=sqlite:///:memory:

# Pharos + Ronin Integration (Phase 5+)
GITHUB_TOKEN=ghp_xxxxxxxxxxxxx  # For hybrid storage
GITHUB_CACHE_TTL=3600  # 1 hour
CONTEXT_RETRIEVAL_TIMEOUT=1000  # 1 second
PATTERN_LEARNING_TIMEOUT=2000  # 2 seconds
MAX_CODEBASES=1000  # Limit for hybrid storage
```

## API Standards

### REST Conventions
- Use standard HTTP methods (GET, POST, PUT, DELETE)
- Return appropriate status codes (200, 201, 400, 404, 500)
- Use JSON for request/response bodies
- Include pagination for list endpoints
- Provide filtering and sorting options

### Response Format
```json
{
  "data": {},
  "meta": {
    "total": 100,
    "page": 1,
    "per_page": 25
  }
}
```

### Error Format
```json
{
  "detail": "Error description",
  "error_code": "VALIDATION_ERROR",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## Security Considerations

- Input validation with Pydantic
- SQL injection prevention via ORM
- XSS protection in frontend
- CORS configuration for API
- Rate limiting (planned)
- API key authentication (planned)

## Monitoring & Observability

- Structured logging with JSON format
- Health check endpoints per module
- Database connection pool monitoring
- ML model performance tracking
- Event bus metrics (throughput, latency)
- Module dependency graph validation
- Error tracking and alerting (planned)

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

### Communication Pattern
- **Direct calls**: Use shared kernel services
- **Cross-module**: Use event bus only
- **Example**: Quality module needs resource data → subscribe to `resource.created` event

### Validation
```bash
# Check all modules for violations
python scripts/check_module_isolation.py

# Generates dependency graph
# Fails if circular dependencies or direct module imports found
```

### CI/CD Integration
- Module isolation checker runs on every commit
- Build fails if violations detected
- Dependency graph generated and archived
