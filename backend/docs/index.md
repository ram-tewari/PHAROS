# Pharos Backend Documentation

**Your second brain for code** - AI-powered knowledge management API for developers and researchers.

## What is Pharos?

Pharos is a production-ready knowledge management system designed specifically for developers. It understands code repositories at a structural level through AST-based analysis, integrates research papers and technical documentation, and provides semantic search across your entire technical knowledge base.

**Key Capabilities:**
- **Code Intelligence**: Parse and analyze Python, JavaScript, TypeScript, Rust, Go, and Java repositories
- **Semantic Search**: Find code and documentation by meaning, not just keywords
- **Knowledge Graphs**: Connect code, papers, and concepts through citation networks and dependencies
- **Active Reading**: Annotate code and papers with searchable highlights and notes
- **Research Integration**: Manage academic papers alongside code with automatic metadata extraction

## Quick Navigation

| Need | Read |
|------|------|
| Get started quickly | [Quick Start Guide](guides/QUICK_START.md) |
| API endpoints | [API Reference](api/) |
| System architecture | [Architecture](architecture/) |
| Development setup | [Developer Guides](guides/) |
| Code ingestion | [Code Intelligence Guide](guides/code-ingestion.md) |
| Database info | [Architecture: Database](architecture/database.md) |
| Testing | [Guides: Testing](guides/testing.md) |

## Documentation Structure

```
backend/docs/
├── index.md                    # This file
├── api/                        # API Reference (split by domain/module)
│   ├── overview.md             # Auth, errors, base URLs, module architecture
│   ├── auth.md                 # Authentication & authorization (Phase 17)
│   ├── resources.md            # Resource management endpoints
│   ├── search.md               # Search endpoints (hybrid, vector, FTS)
│   ├── collections.md          # Collection management
│   ├── annotations.md          # Annotation system
│   ├── taxonomy.md             # Taxonomy & classification
│   ├── graph.md                # Knowledge graph & citations
│   ├── recommendations.md      # Recommendation engine
│   ├── quality.md              # Quality assessment
│   ├── scholarly.md            # Academic metadata extraction
│   ├── authority.md            # Subject authority
│   ├── curation.md             # Content review
│   └── monitoring.md           # Monitoring & health checks
├── architecture/               # System Architecture
│   ├── overview.md             # High-level system design
│   ├── database.md             # Database schema & models
│   ├── event-system.md         # Event-driven architecture
│   ├── events.md               # Event catalog
│   ├── modules.md              # Vertical slice modules
│   └── decisions.md            # Architectural Decision Records (ADRs)
└── guides/                     # Developer Guides
    ├── setup.md                # Installation & environment
    ├── workflows.md            # Common development tasks
    ├── testing.md              # Testing strategies
    ├── deployment.md           # Docker & production
    └── troubleshooting.md      # Common issues & solutions
```

## API Reference

Complete REST API documentation organized by module:

**Core Features:**
- [API Overview](api/overview.md) - Authentication, errors, pagination, module architecture
- [Authentication API](api/auth.md) - JWT authentication, OAuth2, rate limiting
- [Resources API](api/resources.md) - Content management and ingestion

**Code Intelligence:**
- [Ingestion API](api/ingestion.md) - Repository ingestion and AST-based code analysis
- [Search API](api/search.md) - Hybrid search (keyword + semantic + code)
- [Graph API](api/graph.md) - Code dependencies, citation networks, knowledge graphs

**Organization & Discovery:**
- [Collections API](api/collections.md) - Organize code and papers into collections
- [Annotations API](api/annotations.md) - Highlight and annotate code/papers
- [Taxonomy API](api/taxonomy.md) - ML-based classification
- [Recommendations API](api/recommendations.md) - Personalized content discovery

**Quality & Metadata:**
- [Quality API](api/quality.md) - Multi-dimensional quality assessment
- [Scholarly API](api/scholarly.md) - Academic metadata extraction (equations, tables, citations)
- [Authority API](api/authority.md) - Subject authority and normalization
- [Curation API](api/curation.md) - Content review and batch operations

**System:**
- [Monitoring API](api/monitoring.md) - Health checks, metrics, and observability

## Architecture

System design and technical decisions:

- [Architecture Overview](architecture/overview.md) - High-level system design and module structure
- [Database](architecture/database.md) - Schema, models, migrations
- [Event System](architecture/event-system.md) - Event-driven communication patterns
- [Event Catalog](architecture/events.md) - Complete event reference
- [Modules](architecture/modules.md) - Vertical slice architecture
- [Design Decisions](architecture/decisions.md) - ADRs

## Developer Guides

Getting started and development workflows:

**Getting Started:**
- [Quick Start Guide](guides/QUICK_START.md) - Get up and running in 5 minutes
- [Setup Guide](guides/setup.md) - Detailed installation and environment setup
- [Deployment Guide](guides/deployment.md) - Docker deployment and production setup

**Code Intelligence:**
- [Code Ingestion Guide](guides/code-ingestion.md) - Ingest and analyze code repositories
- [Code Intelligence Guide](guides/code-intelligence.md) - AST-based code understanding

**Development:**
- [Development Workflows](guides/workflows.md) - Common development tasks
- [Testing Guide](guides/testing.md) - Testing strategies and patterns
- [Troubleshooting](guides/troubleshooting.md) - Common issues and solutions

**Advanced Features:**
- [Advanced RAG Guide](guides/advanced-rag.md) - Parent-child chunking and GraphRAG
- [Graph Intelligence Guide](guides/graph-intelligence.md) - Knowledge graph features
- [Document Intelligence Guide](guides/document-intelligence.md) - PDF and document processing

**Worker Architecture:**
- [Worker Architecture](WORKER_ARCHITECTURE.md) - Unified edge worker design and operation

### Hybrid Edge-Cloud Architecture

- [Worker Architecture](WORKER_ARCHITECTURE.md) - Unified edge worker design (updated 2026-04-27)
- [Phase 19 Cloud Deployment](guides/phase19-deployment.md) - Deploy Cloud API to Render
- [Phase 19 Edge Worker Setup](guides/phase19-edge-setup.md) - Set up local GPU worker
- [Phase 19 Monitoring](guides/phase19-monitoring.md) - Monitor hybrid system health
- [Phase 19 Architecture](architecture/phase19-hybrid.md) - Hybrid architecture overview

## Interactive Documentation

FastAPI provides interactive API documentation:

- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc

## Related Documentation

- [Steering Docs](../../.kiro/steering/) - High-level project context
- [Spec Organization](../../.kiro/specs/) - Feature specifications
- [Frontend Docs](../../frontend/README.md) - Frontend documentation
