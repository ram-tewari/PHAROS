# Pharos Documentation

Comprehensive documentation for the Pharos code intelligence backend — the memory and knowledge layer that powers the Ronin LLM assistant.

---

## API Reference (`docs/api/`)

| Document | Description |
|----------|-------------|
| [Overview](api/overview.md) | Base URL, authentication, error codes, rate limiting |
| [Resources](api/resources.md) | Resource CRUD, repository ingestion, PDF upload |
| [Ingestion](api/ingestion.md) | Edge Worker ingestion pipeline and job management |
| [Search](api/search.md) | Hybrid search (keyword + semantic + sparse), faceted filtering |
| [Graph](api/graph.md) | Knowledge graph traversal, citations, PageRank, contradiction detection |
| [Collections](api/collections.md) | Collection management and aggregate embeddings |
| [Annotations](api/annotations.md) | Character-offset highlights, rich notes, semantic search |
| [Scholarly](api/scholarly.md) | Academic metadata, equations, tables, citation extraction |
| [Quality](api/quality.md) | Multi-dimensional quality assessment and outlier detection |
| [Recommendations](api/recommendations.md) | Hybrid recommendation engine (NCF, content, graph) |
| [Taxonomy](api/taxonomy.md) | ML-based classification and hierarchical category trees |
| [Curation](api/curation.md) | Content review, batch operations, approval workflows |
| [Authority](api/authority.md) | Subject authority trees and classification hierarchies |
| [Auth](api/auth.md) | JWT authentication, OAuth2, token lifecycle |
| [Monitoring](api/monitoring.md) | Health checks, system metrics, event bus diagnostics |
| [MCP](api/mcp.md) | Model Context Protocol sessions and tool management |
| [Planning](api/planning.md) | AI-assisted planning sessions |

## Architecture (`docs/architecture/`)

| Document | Description |
|----------|-------------|
| [Overview](architecture/overview.md) | System architecture, data flow, the two core use cases, and defense of key engineering decisions |
| [Database Schema](architecture/database.md) | SQLAlchemy models, pgvector indexes, migration strategy |
| [Event System](architecture/event-system.md) | Async Event Bus internals, event types, handler registration |
| [Modules](architecture/modules.md) | Vertical slice architecture — module boundaries and isolation rules |
| [Decision Records](architecture/decisions.md) | ADRs including Local-Heavy Edge Inference and Hybrid Code Storage |
| [Hybrid Deployment](architecture/phase19-hybrid.md) | Cloud API + Edge Worker split architecture |
| [Phase 20 Features](architecture/phase20-features.md) | Pattern Learning Engine, Ronin integration endpoints |

## Developer Guides (`docs/guides/`)

| Guide | Description |
|-------|-------------|
| [Quick Start](guides/QUICK_START.md) | Fastest path to a running Pharos instance |
| [Setup](guides/setup.md) | Full installation, environment configuration, prerequisites |
| [Docker Setup](guides/DOCKER_SETUP_GUIDE.md) | Docker Compose for PostgreSQL + Redis backing services |
| [Development Workflows](guides/workflows.md) | Common development tasks, module creation, code quality |
| [Testing](guides/testing.md) | Test strategy, fixtures, property-based and golden-data testing |
| [Deployment](guides/deployment.md) | Production deployment to Render + Edge Worker setup |
| [Edge Worker Setup](guides/phase19-edge-setup.md) | Local GPU worker installation and configuration |
| [Code Ingestion](guides/code-ingestion.md) | Repository parsing, AST extraction, dependency graphs |
| [Code Intelligence](guides/code-intelligence.md) | How Pharos understands code structure |
| [Document Intelligence](guides/document-intelligence.md) | PDF, HTML, and Markdown processing |
| [Graph Intelligence](guides/graph-intelligence.md) | Knowledge graph construction and traversal |
| [Advanced RAG](guides/advanced-rag.md) | GraphRAG, hybrid retrieval, context assembly |
| [AI Planning](guides/ai-planning.md) | Planning session workflows |
| [MCP Integration](guides/mcp-integration.md) | Model Context Protocol setup for Ronin |
| [Troubleshooting](guides/troubleshooting.md) | Common issues and resolutions |

## Other Documentation

| Document | Description |
|----------|-------------|
| [Changelog](CHANGELOG.md) | Release history and feature timeline |
| [Ronin Integration Guide](RONIN_INTEGRATION_GUIDE.md) | How the Ronin LLM queries Pharos for context and patterns |
| [Hybrid Deployment](HYBRID_DEPLOYMENT.md) | Cloud/Edge deployment topology and cost analysis |
| [Security Audit](SECURITY_AUDIT_2026-02-16.md) | Security assessment and findings |

---

## Quick Commands

```bash
# Start dev server
cd backend && uvicorn app.main:app --reload

# Run tests
pytest tests/ -v

# Run migrations
alembic upgrade head -c config/alembic.ini

# Check module isolation
python scripts/check_module_isolation.py
```
