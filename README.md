# Pharos

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Coverage](https://img.shields.io/badge/coverage-85%25-yellowgreen)
![API Endpoints](https://img.shields.io/badge/endpoints-97%2B-blue)

Your second brain for code. An AI-powered knowledge management system that understands code repositories, research papers, and technical documentation through intelligent analysis, semantic search, and knowledge graphs.

> **📚 Canonical documentation lives in [`notebooklm/`](notebooklm/)** — start with [`01_PHAROS_OVERVIEW.md`](notebooklm/01_PHAROS_OVERVIEW.md). Those six files are the single source of truth for what Pharos is and how it works.
>
> Historical, point-in-time status reports (`*_COMPLETE.md`, `*_STATUS.md`, phase summaries, etc.) have been moved to [`docs/archive/`](docs/archive/). They are kept for provenance but are **not** maintained — do not treat them as current.

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage Examples](#usage-examples)
- [Documentation](#documentation)
- [Project Structure](#project-structure)
- [Development](#development)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [License](#license)

## Overview

Pharos is your second brain for code - a production-ready knowledge management platform designed specifically for developers, researchers, and technical teams. It transforms how you organize, discover, and interact with code repositories, research papers, and technical documentation.

**What makes Pharos different:**

- **Code-First Intelligence**: AST-based code analysis that understands Python, JavaScript, TypeScript, Rust, Go, and Java at a structural level
- **Repository Understanding**: Ingest entire codebases, extract dependencies, build call graphs, and navigate code semantically
- **Research Integration**: Manage research papers alongside code with automatic citation extraction, metadata parsing, and quality assessment
- **Knowledge Graph**: Connect code, papers, and concepts through citation networks, entity relationships, and semantic links
- **Semantic Search**: Find code and documentation by meaning, not just keywords - powered by hybrid search with sub-500ms latency
- **Active Reading**: Annotate code and papers with precise highlights, notes, and tags that are semantically searchable
- **Production Ready**: JWT authentication, OAuth2 social login, tiered rate limiting, and comprehensive monitoring

## Key Features

### Authentication and Security
- JWT-based authentication with access and refresh tokens
- OAuth2 integration (Google, GitHub)
- Tiered rate limiting (Free: 100/hr, Premium: 1,000/hr, Admin: 10,000/hr)
- Bcrypt password hashing and token revocation

### Code Repository Analysis
- **AST-based chunking**: Parse code into logical units (functions, classes, methods) using Tree-Sitter
- **Multi-language support**: Python, JavaScript, TypeScript, Rust, Go, Java with extensible parser architecture
- **Dependency graphs**: Automatically extract IMPORTS, DEFINES, and CALLS relationships
- **Static analysis**: Understand code structure without execution - safe for any codebase
- **Performance**: Sub-2s per file parsing (P95), handles repositories with 10K+ files
- **Smart filtering**: Respects .gitignore, excludes binaries, focuses on source code

### Intelligent Content Processing
- **Multi-format ingestion**: HTML, PDF, plain text, Markdown, and entire Git repositories
- **AI-powered analysis**: Automatic summarization, tagging, and classification using transformer models
- **Quality assessment**: Multi-dimensional scoring (completeness, accuracy, relevance, clarity)
- **Metadata extraction**: Equations, tables, citations, and scholarly metadata from papers

### Advanced Search and Discovery
- **Hybrid search**: Configurable weighting between keyword and semantic search
- **Vector embeddings**: Semantic similarity using nomic-embed-text-v1
- **Full-text search**: SQLite FTS5 with PostgreSQL fallback
- **Faceted filtering**: By classification, language, quality, and subjects
- **GraphRAG retrieval**: Entity-based graph traversal for context-aware search

### Code Repository Analysis
- **AST-based chunking**: Parse code into logical units (functions, classes, methods)
- **Multi-language support**: Python, JavaScript, TypeScript, Rust, Go, Java
- **Dependency graphs**: IMPORTS, DEFINES, and CALLS relationships
- **Static analysis**: Extract structure without code execution
- **Performance**: Sub-2s per file parsing (P95)

### Knowledge Graph for Code and Research
- **Citation networks**: Automatic extraction and resolution from papers and documentation
- **Code dependency graphs**: Visualize how functions, classes, and modules connect
- **PageRank scoring**: Compute importance of code modules and research papers
- **Entity relationships**: Semantic triple storage linking concepts, code, and papers
- **Contradiction detection**: Identify conflicting information across documentation
- **Graph visualization**: Interactive mind-map and network views

### Personalized Recommendations
- **Content-based filtering**: Learn from user library
- **Hybrid scoring**: Combine content, graph, and collaborative signals
- **Fresh discovery**: Source new content from external providers
- **Explainable AI**: Transparent recommendation reasoning

### Collection Management
- **Hierarchical organization**: Nested collections with descriptions
- **Visibility controls**: Private, shared, or public
- **Aggregate embeddings**: Semantic collection representation
- **Batch operations**: Add/remove up to 100 resources at once

### Annotation System for Code and Papers
- **Precise highlighting**: Character-offset-based text selection in code and documents
- **Rich notes**: Personal annotations with semantic embeddings for intelligent search
- **Tag organization**: Custom tags with color-coding for categorization
- **Semantic search**: Find conceptually related annotations across your entire knowledge base
- **Export**: Markdown and JSON formats for integration with other tools
- **Code context**: Annotations preserve surrounding code context for better understanding

## Architecture

Pharos uses a **Vertical Slice Architecture** with event-driven communication:

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Application                  │
├─────────────────────────────────────────────────────────┤
│  13 Domain Modules (Self-Contained Vertical Slices)     │
│  ├── Resources      ├── Search          ├── Graph       │
│  ├── Collections    ├── Recommendations ├── Quality     │
│  ├── Annotations    ├── Taxonomy        ├── Scholarly   │
│  ├── Authority      ├── Curation        ├── Monitoring  │
│  └── Auth                                               │
├─────────────────────────────────────────────────────────┤
│              Shared Kernel (Cross-Cutting)              │
│  ├── Database Sessions    ├── Vector Embeddings         │
│  ├── Event Bus (<1ms)     ├── AI Operations             │
│  └── Redis Cache           └── Security                 │
├─────────────────────────────────────────────────────────┤
│              Data Layer (SQLite / PostgreSQL)           │
└─────────────────────────────────────────────────────────┘
```

**Key Architectural Principles:**
- **Zero circular dependencies**: Modules communicate via event bus only
- **API-first design**: All functionality exposed via REST API
- **Event-driven**: <1ms event emission and delivery (P95)
- **Modular monolith**: Easy to understand, deploy, and scale

## Quick Start

### Prerequisites

- Python 3.8+
- Docker Desktop (optional, for PostgreSQL/Redis)
- 4GB RAM minimum (8GB recommended)

### 5-Minute Setup (SQLite)

```bash
# Clone the repository
git clone https://github.com/yourusername/pharos.git
cd pharos/backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r config/requirements.txt

# Configure environment
cp config/.env.example .env

# Run migrations
alembic upgrade head -c config/alembic.ini

# Start the server
uvicorn app.main:app --reload
```

The API is now running at `http://127.0.0.1:8000`

### Verify Installation

```bash
# Check health
curl http://127.0.0.1:8000/health

# View API documentation
open http://127.0.0.1:8000/docs
```

## Installation

### Option 1: Docker Development (Recommended)

Use Docker for backing services while running the app locally:

```bash
# Start PostgreSQL and Redis
cd backend/deployment
docker-compose -f docker-compose.dev.yml up -d

# Install and run application
cd ..
python -m venv .venv
source .venv/bin/activate
pip install -r config/requirements.txt
cp config/.env.development .env
alembic upgrade head -c config/alembic.ini
uvicorn app.main:app --reload
```

### Option 2: Full Docker Stack

Run everything in containers:

```bash
cd backend/deployment
docker-compose up -d
```

### Option 3: Production Deployment

Deploy to cloud platforms:

```bash
# Render (Cloud API)
# See docs/guides/phase19-deployment.md

# Edge Worker (Local GPU)
cd backend/deployment
./setup_edge.sh  # Linux/macOS
# or
.\setup_edge.ps1  # Windows
```

## Usage Examples

### Ingest a Web Resource

```bash
curl -X POST http://127.0.0.1:8000/resources \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://arxiv.org/abs/2301.00001",
    "title": "Attention Is All You Need"
  }'
```

### Search with Hybrid Mode

```bash
curl -X GET "http://127.0.0.1:8000/search?query=machine+learning&mode=hybrid&limit=10"
```

### Create an Annotation

```bash
curl -X POST http://127.0.0.1:8000/annotations \
  -H "Content-Type: application/json" \
  -d '{
    "resource_id": 1,
    "start_offset": 100,
    "end_offset": 250,
    "highlighted_text": "Key insight from the paper",
    "note": "This explains the core concept",
    "tags": ["important", "concept"]
  }'
```

### Ingest a Code Repository

```bash
curl -X POST http://127.0.0.1:8000/resources/ingest-repository \
  -H "Content-Type: application/json" \
  -d '{
    "repo_path": "/path/to/local/repo",
    "title": "My Python Project"
  }'
```

### Get Citation Network

```bash
curl -X GET "http://127.0.0.1:8000/graph/citations/1?depth=2"
```

## Documentation

📖 **[Complete Documentation Index](docs/README.md)** - Start here for all documentation

### Quick Links

**Getting Started**:
- [Product Vision](.kiro/steering/product.md) - What we're building and why
- [Quick Start Guide](backend/docs/guides/QUICK_START.md) - Get up and running in 5 minutes
- [API Reference](backend/docs/index.md) - Complete endpoint documentation

**Development**:
- [Tech Stack](.kiro/steering/tech.md) - Technologies and tools
- [Repository Structure](.kiro/steering/structure.md) - Where things are located
- [Developer Setup](backend/docs/guides/setup.md) - Detailed installation guide
- [Architecture Overview](backend/docs/architecture/overview.md) - System design
- [Testing Guide](backend/docs/guides/testing.md) - Testing strategies

**Deployment**:
- [Deploy Now](backend/docs/deployment/DEPLOY_NOW.md) - Quick deployment (30 min)
- [Render Free Tier](backend/RENDER_FREE_DEPLOYMENT.md) - Free tier deployment guide
- [Pre-Flight Checklist](backend/docs/deployment/PRE_FLIGHT_CHECKLIST.md) - Deployment verification
- [Docker Setup](backend/docs/guides/DOCKER_SETUP_GUIDE.md) - Container orchestration

**Vision & Roadmap**:
- [Pharos + Ronin Vision](docs/vision/PHAROS_RONIN_VISION.md) - Complete technical vision
- [Quick Reference](.kiro/steering/PHAROS_RONIN_QUICK_REFERENCE.md) - Quick reference card
- [Future Steps](docs/PHAROS_future_steps.md) - Development roadmap

## Project Structure

```
pharos/
├── backend/                    # Python/FastAPI backend
│   ├── app/
│   │   ├── modules/            # 13 domain modules
│   │   ├── shared/             # Shared kernel
│   │   ├── database/           # Database models
│   │   └── main.py             # Application entry
│   ├── tests/                  # Test suite
│   ├── docs/                   # Technical documentation
│   ├── scripts/                # Utility scripts
│   └── alembic/                # Database migrations
├── frontend/                   # React/TypeScript frontend
│   ├── src/
│   │   ├── components/         # React components
│   │   ├── lib/                # Utilities and API client
│   │   └── App.tsx             # Application entry
│   └── package.json
├── .kiro/                      # Project configuration
│   ├── steering/               # High-level documentation
│   └── specs/                  # Feature specifications
└── docs/                       # User documentation
```

## Development

### Running Tests

```bash
# All tests
pytest backend/tests/ -v

# With coverage
pytest backend/tests/ --cov=app --cov-report=html

# Specific module
pytest backend/tests/modules/test_resources_endpoints.py -v

# Property-based tests
pytest backend/tests/properties/ -v
```

### Code Quality

```bash
# Lint and format
ruff check backend/
ruff format backend/

# Check module isolation
python backend/scripts/check_module_isolation.py

# Verify startup
python backend/test_app_startup.py
```

### Database Migrations

```bash
# Create migration
cd backend
alembic revision --autogenerate -m "description" -c config/alembic.ini

# Apply migrations
alembic upgrade head -c config/alembic.ini

# Rollback
alembic downgrade -1 -c config/alembic.ini
```

## Deployment

### Cloud Deployment (Render)

```bash
# Deploy via render.yaml
git push origin main
# Render auto-deploys from main branch
```

### Edge Worker (Local GPU)

```bash
cd backend/deployment
./setup_edge.sh  # Configures local GPU worker
```

### Docker Production

```bash
cd backend/deployment
docker-compose -f docker-compose.yml up -d
```

See [Deployment Guide](backend/docs/guides/deployment.md) for detailed instructions.

## Contributing

We welcome contributions! Here's how to get started:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes** and add tests
4. **Run tests**: `pytest backend/tests/ -v`
5. **Check code quality**: `ruff check backend/`
6. **Commit**: `git commit -m "Add amazing feature"`
7. **Push**: `git push origin feature/amazing-feature`
8. **Open a Pull Request**

### Development Guidelines

- Follow the vertical slice architecture pattern
- Use event bus for cross-module communication
- Add tests for new features (aim for 85%+ coverage)
- Update documentation for API changes
- Run `check_module_isolation.py` to verify no circular dependencies

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) - SQL toolkit and ORM
- [Transformers](https://huggingface.co/transformers/) - State-of-the-art NLP
- [React](https://react.dev/) - UI library
- [Vite](https://vitejs.dev/) - Frontend build tool

## Support

- **Documentation**: [backend/docs/index.md](backend/docs/index.md)
- **Issues**: [GitHub Issues](https://github.com/yourusername/pharos/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/pharos/discussions)

---

**Status**: Production (Phase 19 Complete)  
**API**: https://pharos.onrender.com  
**Coverage**: 88.9% endpoint coverage, 85%+ code coverage
