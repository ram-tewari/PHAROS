# Pharos Backend

**AI-powered knowledge management system for code and research papers**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue.svg)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../LICENSE)

---

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set up database
alembic upgrade head

# Start server
uvicorn app.main:app --reload
```

Visit http://localhost:8000/docs for API documentation.

### Production Deployment

Deploy to Render in 5 minutes:

```bash
# See deployment guide
cat docs/deployment/quickstart.md
```

Or read the [complete deployment guide](docs/deployment/render.md).

---

## What is Pharos?

Pharos is your second brain for code - combining intelligent code analysis with research paper management to help you understand, organize, and discover connections across your technical knowledge base.

### Core Features

- **Code Intelligence**: AST-based analysis for Python, JavaScript, TypeScript, Rust, Go, Java
- **Research Integration**: Manage papers alongside code with automatic citation extraction
- **Knowledge Graph**: Connect code, papers, and concepts through relationships
- **Semantic Search**: Hybrid search combining keyword and semantic approaches
- **Advanced RAG**: Parent-child chunking with GraphRAG retrieval; set `include_code=true` to attach source code inline
- **Hybrid Code Retrieval**: Remote code chunks fetched on demand from GitHub with Redis caching (TTL 1h)
- **Active Reading**: Precise text highlighting and rich notes with semantic search

### Architecture

- **Vertical Slice Architecture**: 14 self-contained modules
- **Event-Driven**: Modules communicate via event bus (<1ms latency)
- **Hybrid Edge-Cloud**: Optional local GPU worker for embeddings
- **API-First**: All features accessible via REST API

---

## Documentation

### 📚 Complete Documentation Hub

**Start here**: [docs/index.md](docs/index.md)

### Quick Links

| Category | Description | Link |
|----------|-------------|------|
| **API Reference** | Complete API documentation for all endpoints | [docs/api/](docs/api/) |
| **Architecture** | System design and technical decisions | [docs/architecture/](docs/architecture/) |
| **Deployment** | Production deployment guides | [docs/deployment/](docs/deployment/) |
| **Developer Guides** | Development workflows and best practices | [docs/guides/](docs/guides/) |
| **Phase Summaries** | Implementation phase documentation | [docs/phases/](docs/phases/) |
| **Reference** | Module manifest, issues, security | [docs/reference/](docs/reference/) |

### Common Tasks

- **Deploy to production**: [docs/deployment/quickstart.md](docs/deployment/quickstart.md)
- **Set up local development**: [docs/guides/setup.md](docs/guides/setup.md)
- **Understand the architecture**: [docs/architecture/overview.md](docs/architecture/overview.md)
- **Ingest a codebase**: [docs/guides/code-ingestion.md](docs/guides/code-ingestion.md)
- **Process PDF papers**: [docs/guides/document-intelligence.md](docs/guides/document-intelligence.md)
- **Troubleshoot issues**: [docs/guides/troubleshooting.md](docs/guides/troubleshooting.md)

---

## Tech Stack

### Core Framework
- **Python 3.8+** - Primary language
- **FastAPI** - Web framework
- **SQLAlchemy 2.0** - ORM with async support
- **Alembic** - Database migrations

### Database & Cache
- **PostgreSQL 15+** - Production database
- **SQLite** - Development database
- **Redis** - Cache and task queue

### AI/ML
- **Sentence-Transformers** - Embeddings (nomic-embed-text-v1)
- **Transformers (Hugging Face)** - NLP models
- **PyTorch** - Deep learning framework
- **Tree-Sitter** - Multi-language code parsing

### Deployment
- **Render** - Cloud API hosting
- **NeonDB** - Serverless PostgreSQL
- **Upstash** - Serverless Redis
- **Docker** - Containerization

---

## Project Structure

```
backend/
├── app/                    # Application code
│   ├── modules/            # 14 domain modules (vertical slices)
│   ├── shared/             # Shared kernel (database, events, AI)
│   ├── database/           # Database models and config
│   └── main.py             # FastAPI app entry point
├── tests/                  # Test suite
├── alembic/                # Database migrations
├── docs/                   # 📚 Complete documentation
│   ├── api/                # API reference (18 files)
│   ├── architecture/       # System architecture (7 files)
│   ├── deployment/         # Deployment guides (9 files)
│   ├── guides/             # Developer guides (11 files)
│   ├── phases/             # Phase summaries (5 files)
│   ├── reference/          # Reference materials (5 files)
│   └── archive/            # Historical docs (70+ files)
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container image
└── README.md               # This file
```

---

## Development

### Prerequisites

- Python 3.8+
- PostgreSQL 15+ (or SQLite for development)
- Redis (optional, for caching)

### Setup

```bash
# Clone repository
git clone https://github.com/yourusername/pharos
cd pharos/backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up database
alembic upgrade head

# Start development server
uvicorn app.main:app --reload
```

### Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html

# Run specific module tests
pytest tests/modules/test_resources_endpoints.py -v
```

### Common Commands

```bash
# Start server
uvicorn app.main:app --reload

# Run migrations
alembic upgrade head

# Create migration
alembic revision --autogenerate -m "description"

# Run tests
pytest tests/ -v

# Lint and format
ruff check .
ruff format .

# Check module isolation
python scripts/check_module_isolation.py
```

---

## Modules

Pharos uses a **vertical slice architecture** with 14 self-contained modules:

| Module | Description |
|--------|-------------|
| **annotations** | Text highlights and notes |
| **authority** | Subject authority trees |
| **collections** | Collection management |
| **curation** | Content review |
| **graph** | Knowledge graph and citations |
| **ingestion** | Code repository ingestion |
| **monitoring** | System health and metrics |
| **pdf_ingestion** | PDF upload and GraphRAG |
| **quality** | Quality assessment |
| **recommendations** | Hybrid recommendations |
| **resources** | Resource CRUD |
| **scholarly** | Academic metadata |
| **search** | Hybrid search |
| **taxonomy** | ML classification |

See [docs/reference/module-manifest.md](docs/reference/module-manifest.md) for complete details.

---

## API Documentation

### Interactive API Docs

Once the server is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### API Reference

Complete API documentation: [docs/api/overview.md](docs/api/overview.md)

Quick links:
- [Authentication](docs/api/auth.md)
- [Resources](docs/api/resources.md)
- [Search](docs/api/search.md)
- [Collections](docs/api/collections.md)
- [Graph](docs/api/graph.md)
- [Ingestion](docs/api/ingestion.md)

---

## Environment Variables

### Required

```bash
DATABASE_URL=postgresql://user:pass@host:5432/db
# Or for development:
DATABASE_URL=sqlite:///./backend.db
```

### Optional

```bash
# Redis (for caching)
REDIS_URL=redis://localhost:6379

# AI Models
EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1
SUMMARIZER_MODEL=facebook/bart-large-cnn

# Search
DEFAULT_HYBRID_SEARCH_WEIGHT=0.5

# Authentication
JWT_SECRET_KEY=your-secret-key
PHAROS_ADMIN_TOKEN=your-admin-token
```

See [docs/deployment/environment.md](docs/deployment/environment.md) for complete reference.

---

## Performance

### Targets

- API response time: P95 < 200ms
- Search latency: < 500ms
- Embedding generation: < 2s per document
- Event emission + delivery: < 1ms (p95)

### Scalability

- 100K+ resources in database
- 10K+ concurrent embeddings
- 1K+ collections per user
- 100+ requests/second

---

## Contributing

We welcome contributions! Please see:

- [Developer Setup Guide](docs/guides/setup.md)
- [Development Workflows](docs/guides/workflows.md)
- [Testing Guide](docs/guides/testing.md)
- [Architecture Overview](docs/architecture/overview.md)

---

## Support

- **Documentation**: [docs/index.md](docs/index.md)
- **Issues**: [docs/reference/issues.md](docs/reference/issues.md)
- **Troubleshooting**: [docs/guides/troubleshooting.md](docs/guides/troubleshooting.md)

---

## License

MIT License - see [LICENSE](../LICENSE) for details.

---

## Related Projects

- **Pharos + Ronin**: Self-improving coding system with LLM integration
  - [Vision Document](../PHAROS_RONIN_VISION.md)
  - [Quick Reference](../.kiro/steering/PHAROS_RONIN_QUICK_REFERENCE.md)
  - [Executive Summary](../PHAROS_RONIN_SUMMARY.md)

---

**Pharos**: Your second brain for code. Understand repositories, connect research, discover knowledge.

**Status**: Production Ready  
**Version**: 2.0.0  
**Last Updated**: 2026-04-17
