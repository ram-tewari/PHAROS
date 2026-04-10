# Pharos - Backend API

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-009688)
![Coverage](https://img.shields.io/badge/coverage-85%25-yellowgreen)
![Endpoints](https://img.shields.io/badge/endpoints-97%2B-blue)

Your second brain for code. AI-powered knowledge management API that understands code repositories, research papers, and technical documentation through intelligent analysis and semantic search.

## Quick Navigation

- [Product Vision & Goals](../.kiro/steering/product.md) - What we're building and why
- [Tech Stack & Architecture](../.kiro/steering/tech.md) - How we're building it
- [Repository Structure](../.kiro/steering/structure.md) - Where things are located
- [API Documentation](docs/index.md) - Complete API reference
- [Architecture Guide](docs/architecture/overview.md) - System architecture details
- [Developer Setup](docs/guides/setup.md) - Getting started guide
- [Deployment Guide](docs/guides/deployment.md) - Cloud & edge deployment

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [API Usage](#api-usage)
- [Development](#development)
- [Testing](#testing)
- [Deployment](#deployment)
- [Documentation](#documentation)

## Overview

Pharos is a production-ready knowledge management API designed specifically for developers and researchers. Built on a vertical slice architecture with event-driven communication, it delivers code intelligence, semantic search, and knowledge graph capabilities with enterprise-grade features and self-hosting flexibility.

**Core Focus:**
- **Code Understanding**: AST-based analysis of entire repositories with dependency extraction
- **Research Management**: Papers, documentation, and technical articles with citation networks
- **Semantic Search**: Find code and concepts by meaning, not just keywords
- **Knowledge Graphs**: Connect code, papers, and ideas through intelligent relationships

**Performance Targets:**
- API response time: P95 < 200ms
- Search latency: < 500ms for hybrid search
- Event emission: < 1ms (P95)
- Database queries: < 100ms for most operations

**Scalability:**
- 100K+ resources supported
- 10K+ concurrent embeddings
- 1K+ collections per user
- 100+ requests/second

## Key Features

### Code Intelligence & Repository Analysis
- **AST-Based Parsing**: Understand code structure through Tree-Sitter parsing (Python, JavaScript, TypeScript, Rust, Go, Java)
- **Dependency Extraction**: Automatically build IMPORTS, DEFINES, and CALLS relationship graphs
- **Repository Ingestion**: Analyze entire codebases from local directories or Git URLs (HTTPS/SSH)
- **Smart Filtering**: Respects .gitignore, excludes binaries, focuses on source code
- **Performance**: Sub-2s per file parsing (P95), handles repositories with 10K+ files
- **Static Analysis**: Safe code understanding without execution

### Semantic Search & Discovery
- **Hybrid Search**: Configurable weighting between keyword, semantic, and code-specific search
- **Vector Embeddings**: Semantic similarity using nomic-embed-text-v1 for code and documentation
- **Full-Text Search**: SQLite FTS5 with PostgreSQL fallback for fast keyword matching
- **Code Search**: Find functions, classes, and patterns across repositories
- **Faceted Filtering**: Filter by language, quality, classification, and file type
- **GraphRAG Retrieval**: Entity-based graph traversal for context-aware search

### Knowledge Graph & Relationships
- **Code Dependency Graphs**: Visualize how functions, classes, and modules connect
- **Citation Networks**: Automatic extraction and resolution from papers and documentation
- **PageRank Scoring**: Compute importance of code modules and research papers
- **Entity Relationships**: Semantic triple storage linking concepts, code, and papers
- **Contradiction Detection**: Identify conflicting information across documentation
- **Graph Visualization**: Interactive mind-map and network views

### Research Paper Integration (Phase 4 ✅)
- **PDF Ingestion**: Upload and extract academic PDFs with PyMuPDF
- **Academic Fidelity**: Preserves equations, tables, figures with page coordinates
- **Semantic Chunking**: Intelligent chunking respecting document structure (max 512 tokens)
- **Conceptual Annotation**: Tag PDF chunks with concepts (OAuth, Security, ML, etc.)
- **GraphRAG Linking**: Automatic bidirectional links between PDF concepts and code implementations
- **Unified Search**: Single query returns both PDF sections and related code chunks
- **Multi-Format Ingestion**: HTML, PDF, Markdown, and plain text
- **Scholarly Metadata**: Automatic extraction of equations, tables, citations, and references
- **Quality Assessment**: Multi-dimensional scoring (completeness, accuracy, relevance, clarity)
- **Citation Resolution**: Link papers to existing resources in your library
- **Academic Classification**: Automatic categorization using ML models

**Phase 4 API Endpoints:**
- `POST /api/resources/pdf/ingest` - Upload and extract PDF with academic fidelity
- `POST /api/resources/pdf/annotate` - Annotate chunks with conceptual tags
- `POST /api/resources/pdf/search/graph` - GraphRAG traversal search across PDFs and code

### Active Reading & Annotation
- **Precise Highlighting**: Character-offset-based text selection in code and documents
- **Rich Notes**: Personal annotations with semantic embeddings for intelligent search
- **Tag Organization**: Custom tags with color-coding for categorization
- **Semantic Search**: Find conceptually related annotations across your entire knowledge base
- **Code Context**: Annotations preserve surrounding code context
- **Export**: Markdown and JSON formats for integration with other tools

### Authentication & Security
- **JWT Authentication**: Secure token-based authentication with access and refresh tokens
- **OAuth2 Integration**: Social login via Google and GitHub
- **Tiered Rate Limiting**: Free (100/hr), Premium (1,000/hr), and Admin (10,000/hr) tiers
- **Token Revocation**: Redis-backed token blacklist for secure logout
- **Password Security**: Bcrypt password hashing with automatic salt generation

### ML-Powered Features
- **Transformer-Based Classification**: Fine-tuned BERT/DistilBERT models for categorization
- **Hierarchical Taxonomy**: Multi-level category trees with parent-child relationships
- **Active Learning**: System identifies uncertain predictions for targeted review
- **Model Versioning**: Track and manage multiple model versions with rollback capability
- **GPU Acceleration**: Automatic GPU utilization with graceful CPU fallback

## Architecture

Pharos uses a **Vertical Slice Architecture** with **Event-Driven Communication**:

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Application                  │
├─────────────────────────────────────────────────────────┤
│  13 Domain Modules (Self-Contained Vertical Slices)     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  Resources   │  │    Search    │  │    Graph     │   │
│  │  Collections │  │ Recommend... │  │   Quality    │   │
│  │  Annotations │  │   Taxonomy   │  │  Scholarly   │   │
│  │  Authority   │  │   Curation   │  │  Monitoring  │   │ 
│  │     Auth     │  │              │  │              │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                         │
│  Each module contains:                                  │
│  • router.py - API endpoints                            │
│  • service.py - Business logic                          │
│  • schema.py - Pydantic models                          │
│  • model.py - Database models                           │
│  • handlers.py - Event handlers                         │
├─────────────────────────────────────────────────────────┤
│              Shared Kernel (Cross-Cutting)              │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Database • Event Bus • Embeddings • AI • Cache   │   │
│  └──────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────┤
│              Data Layer (SQLite / PostgreSQL)           │
└─────────────────────────────────────────────────────────┘
```

**Key Architectural Principles:**

1. **Vertical Slice Architecture**: Each module is self-contained with its own models, schemas, services, and routes
2. **Event-Driven Communication**: Modules communicate via event bus (no direct imports)
3. **Shared Kernel**: Cross-cutting concerns (database, cache, embeddings, AI) in shared layer
4. **Zero Circular Dependencies**: Enforced by module isolation rules
5. **API-First Design**: All functionality exposed via REST API

**Event Bus Performance:**
- In-memory, async event system
- <1ms latency (P95) for event emission and delivery
- 20+ event types across resource lifecycle, quality, classification, graph, and recommendations

## API-First Architecture

Pharos is built with an API-first approach, enabling seamless integration with IDEs, editors, and development workflows. The RESTful API provides comprehensive endpoints for code analysis, semantic search, and knowledge management, making it suitable for both personal second-brain systems and team knowledge bases.

## Quick Start

### Prerequisites

- Python 3.8 or higher
- SQLite (default) or PostgreSQL database
- Docker Desktop (for PostgreSQL and Redis)
- 4GB RAM minimum (8GB recommended for AI features)

### Option 1: Docker Development Setup (Recommended)

Use Docker for backing services (PostgreSQL and Redis) while running the application locally:

1. **Start backing services**
```bash
cd backend/deployment
docker-compose -f docker-compose.dev.yml up -d
```

2. **Create virtual environment and install dependencies**
```bash
cd ..
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r config/requirements.txt
```

3. **Configure environment**
```bash
# Copy template and edit
cp config/.env.example .env
# Edit .env with your settings
```

4. **Run database migrations**
```bash
alembic upgrade head -c config/alembic.ini
```

5. **Start the API server**
```bash
uvicorn app.main:app --reload
```

📖 **See [docs/guides/DOCKER_SETUP_GUIDE.md](docs/guides/DOCKER_SETUP_GUIDE.md) for detailed instructions**

### Option 2: SQLite Setup (Simple)

Use SQLite for a zero-configuration setup:

1. **Create a virtual environment**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. **Install dependencies**
```bash
pip install -r config/requirements.txt
```

3. **Configure environment**
```bash
cp config/.env.example .env
```

4. **Run database migrations**
```bash
alembic upgrade head -c config/alembic.ini
```

5. **Start the API server**
```bash
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`

**Interactive API Documentation:**
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

### First API Call

Test the API by ingesting your first resource:

```bash
curl -X POST http://127.0.0.1:8000/resources \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/article"}'
```

**Expected Response:**
```json
{
  "id": 1,
  "url": "https://example.com/article",
  "title": "Example Article",
  "status": "pending",
  "created_at": "2024-01-01T00:00:00Z"
}
```

## Configuration

### Environment Variables

```bash
# Database Configuration
DATABASE_URL=sqlite:///backend.db
TEST_DATABASE_URL=sqlite:///:memory:

# Authentication and Security
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# OAuth2 Providers (Optional)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback

# Rate Limiting
REDIS_HOST=localhost
REDIS_PORT=6379
RATE_LIMIT_FREE_TIER=100
RATE_LIMIT_PREMIUM_TIER=1000
RATE_LIMIT_ADMIN_TIER=10000

# AI Model Configuration
EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1
SUMMARIZER_MODEL=facebook/bart-large-cnn

# Search Configuration
DEFAULT_HYBRID_SEARCH_WEIGHT=0.5
EMBEDDING_CACHE_SIZE=1000

# Graph Configuration
GRAPH_WEIGHT_VECTOR=0.6
GRAPH_WEIGHT_TAGS=0.3
GRAPH_WEIGHT_CLASSIFICATION=0.1
```

**Generate Secure JWT Secret:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## API Usage

### Authentication

```bash
# Register a new user
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123!",
    "full_name": "John Doe"
  }'

# Login
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123!"
  }'

# Use the access token in subsequent requests
curl -X GET http://127.0.0.1:8000/resources \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Resource Management

```bash
# Ingest a web resource
curl -X POST http://127.0.0.1:8000/resources \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://arxiv.org/abs/2301.00001",
    "title": "Attention Is All You Need"
  }'

# Get resource details
curl -X GET http://127.0.0.1:8000/resources/1 \
  -H "Authorization: Bearer YOUR_TOKEN"

# List all resources
curl -X GET "http://127.0.0.1:8000/resources?limit=10&offset=0" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Search

```bash
# Hybrid search (keyword + semantic)
curl -X GET "http://127.0.0.1:8000/search?query=machine+learning&mode=hybrid&limit=10" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Semantic search only
curl -X GET "http://127.0.0.1:8000/search?query=neural+networks&mode=semantic" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Advanced search with filters
curl -X POST http://127.0.0.1:8000/search/advanced \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "deep learning",
    "filters": {
      "classification": ["cs.AI", "cs.LG"],
      "min_quality": 0.7,
      "language": "en"
    },
    "limit": 20
  }'
```

### Collections

```bash
# Create a collection
curl -X POST http://127.0.0.1:8000/collections \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Machine Learning Papers",
    "description": "Curated ML research papers",
    "visibility": "private"
  }'

# Add resources to collection
curl -X POST http://127.0.0.1:8000/collections/1/resources \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "resource_ids": [1, 2, 3]
  }'
```

### Annotations

```bash
# Create an annotation
curl -X POST http://127.0.0.1:8000/annotations \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "resource_id": 1,
    "start_offset": 100,
    "end_offset": 250,
    "highlighted_text": "Key insight from the paper",
    "note": "This explains the core concept",
    "tags": ["important", "concept"]
  }'

# Search annotations
curl -X GET "http://127.0.0.1:8000/annotations/search?query=concept&mode=semantic" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Code Repository Ingestion

```bash
# Ingest a local repository
curl -X POST http://127.0.0.1:8000/resources/ingest-repository \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_path": "/path/to/local/repo",
    "title": "My Python Project",
    "description": "A sample Python project"
  }'

# Ingest from Git URL
curl -X POST http://127.0.0.1:8000/resources/ingest-repository \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/user/repo.git",
    "title": "Open Source Project"
  }'
```

### Knowledge Graph

```bash
# Get citation network
curl -X GET "http://127.0.0.1:8000/graph/citations/1?depth=2" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get resource neighbors (mind-map view)
curl -X GET "http://127.0.0.1:8000/graph/neighbors/1?limit=10" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Detect contradictions
curl -X GET http://127.0.0.1:8000/graph/contradictions \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Development

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=app --cov-report=html --cov-report=term

# Run specific test module
pytest tests/modules/test_resources_endpoints.py -v

# Run integration tests
pytest tests/integration/ -v

# Run property-based tests
pytest tests/properties/ -v

# Run performance tests
pytest tests/performance/ -v
```

**Test Organization:**
- `tests/modules/` - Module-specific endpoint tests
- `tests/integration/` - Cross-module integration tests
- `tests/properties/` - Property-based tests (Hypothesis)
- `tests/performance/` - Performance and load tests
- `tests/golden_data/` - Golden data for protocol-based testing

### Code Quality

```bash
# Lint code
ruff check app/

# Format code
ruff format app/

# Type checking (if using mypy)
mypy app/

# Check module isolation (no circular dependencies)
python scripts/check_module_isolation.py

# Verify all modules load correctly
python test_app_startup.py
```

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "Add new table" -c config/alembic.ini

# Apply all pending migrations
alembic upgrade head -c config/alembic.ini

# Rollback one migration
alembic downgrade -1 -c config/alembic.ini

# View migration history
alembic history -c config/alembic.ini

# View current version
alembic current -c config/alembic.ini
```

### Module Development

When creating a new module:

```bash
# Create module structure
mkdir -p app/modules/mymodule
touch app/modules/mymodule/{__init__.py,router.py,service.py,schema.py,model.py,handlers.py,README.md}

# Register module in main.py
# Add to register_all_modules() function

# Create tests
mkdir -p tests/modules/mymodule
touch tests/modules/mymodule/test_endpoints.py

# Verify module isolation
python scripts/check_module_isolation.py
```

**Module Rules:**
- Modules can import from `app.shared.*` (shared kernel)
- Modules can import from `app.events.*` (event system)
- Modules CANNOT import from other modules
- Cross-module communication via event bus only

## Testing

### Test Strategy

Pharos uses a multi-layered testing approach:

1. **Unit Tests**: Test individual functions and classes in isolation
2. **Integration Tests**: Test module interactions and database operations
3. **Property-Based Tests**: Use Hypothesis for generative testing
4. **Performance Tests**: Validate response times and throughput
5. **Golden Data Tests**: Protocol-based testing with immutable expectations

### Test Fixtures

Common fixtures are defined in `tests/conftest.py`:

```python
# Database session
def test_db():
    # Provides clean test database

# Authenticated client
def authenticated_client():
    # Provides client with valid JWT token

# Sample resources
def sample_resource():
    # Provides test resource data
```

## Deployment

### Production Checklist

Before deploying to production:

- [ ] Set strong `JWT_SECRET_KEY` (use `secrets.token_urlsafe(32)`)
- [ ] Configure OAuth2 credentials (Google, GitHub)
- [ ] Set up PostgreSQL database (not SQLite)
- [ ] Configure Redis for caching and rate limiting
- [ ] Set appropriate rate limits for tiers
- [ ] Enable HTTPS/TLS
- [ ] Configure CORS origins
- [ ] Set up monitoring and logging
- [ ] Configure backup strategy
- [ ] Test disaster recovery procedures

### Cloud Deployment (Render)

```bash
# Deploy via render.yaml
git push origin main
# Render auto-deploys from main branch
```

**Environment Variables on Render:**
- Set all required environment variables in Render dashboard
- Use Render's PostgreSQL add-on for database
- Use Render's Redis add-on for caching

### Edge Worker (Local GPU)

For ML-intensive workloads:

```bash
cd deployment
./setup_edge.sh  # Linux/macOS
# or
.\setup_edge.ps1  # Windows
```

See [Phase 19 Deployment Guide](docs/guides/phase19-deployment.md) for details.

### Docker Production

```bash
cd deployment
docker-compose -f docker-compose.yml up -d
```

**Docker Services:**
- `api`: FastAPI application
- `postgres`: PostgreSQL database
- `redis`: Redis cache
- `worker`: Celery worker (optional)

### Health Checks

```bash
# Application health
curl http://your-domain.com/health

# Database health
curl http://your-domain.com/health/db

# Module health
curl http://your-domain.com/monitoring/health
```

## Documentation

### API Documentation

- [API Index](docs/index.md) - Documentation hub and navigation
- [API Overview](docs/api/overview.md) - Base URL, authentication, errors
- [Resources API](docs/api/resources.md) - Resource CRUD endpoints
- [Search API](docs/api/search.md) - Search and hybrid search
- [Collections API](docs/api/collections.md) - Collection management
- [Annotations API](docs/api/annotations.md) - Annotation endpoints
- [Graph API](docs/api/graph.md) - Knowledge graph and citations
- [Recommendations API](docs/api/recommendations.md) - Recommendation engine
- [Quality API](docs/api/quality.md) - Quality assessment
- [Monitoring API](docs/api/monitoring.md) - Health and metrics

### Architecture Documentation

- [Architecture Overview](docs/architecture/overview.md) - System design
- [Database Schema](docs/architecture/database.md) - Models and migrations
- [Event System](docs/architecture/event-system.md) - Event bus details
- [Module Structure](docs/architecture/modules.md) - Vertical slices
- [Decision Records](docs/architecture/decisions.md) - ADRs

### Developer Guides

- [Setup Guide](docs/guides/setup.md) - Installation and configuration
- [Development Workflows](docs/guides/workflows.md) - Common tasks
- [Testing Guide](docs/guides/testing.md) - Testing strategies
- [Deployment Guide](docs/guides/deployment.md) - Production deployment
- [Troubleshooting](docs/guides/troubleshooting.md) - Common issues

## Contributing

We welcome contributions! Here's how to get started:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes** and add tests
4. **Run tests**: `pytest tests/ -v`
5. **Check code quality**: `ruff check app/`
6. **Verify module isolation**: `python scripts/check_module_isolation.py`
7. **Commit**: `git commit -m "Add amazing feature"`
8. **Push**: `git push origin feature/amazing-feature`
9. **Open a Pull Request**

### Contribution Guidelines

- Follow the vertical slice architecture pattern
- Use event bus for cross-module communication
- Add tests for new features (aim for 85%+ coverage)
- Update documentation for API changes
- Follow code style (Ruff formatting)
- No circular dependencies between modules
- Update CHANGELOG.md with your changes

## License

This project is licensed under the MIT License - see the [LICENSE](../LICENSE) file for details.

## Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) - SQL toolkit and ORM
- [Transformers](https://huggingface.co/transformers/) - State-of-the-art NLP
- [Alembic](https://alembic.sqlalchemy.org/) - Database migrations
- [Pydantic](https://docs.pydantic.dev/) - Data validation

## Support

- **Documentation**: [docs/index.md](docs/index.md)
- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **API Status**: https://pharos.onrender.com/health

---

**Status**: Production (Phase 19 Complete)  
**API**: https://pharos.onrender.com  
**Coverage**: 88.9% endpoint coverage, 85%+ code coverage
