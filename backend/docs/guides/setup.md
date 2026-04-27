# Development Setup Guide

Installation and environment configuration for Pharos.

> **Phase 14 Complete**: Neo Alexandria now uses a fully modular vertical slice architecture with 13 self-contained modules, enhanced shared kernel, and event-driven communication.

## Prerequisites

- Python 3.8 or higher
- Git
- SQLite (included with Python) or PostgreSQL 15+ (recommended for production)
- 4GB RAM minimum (8GB recommended for AI features)
- 2GB free disk space

## Installation Steps

### 1. Clone the Repository

```bash
git clone <repository-url>
cd backend
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Create a `.env` file in the backend directory:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```bash
# Database Configuration
DATABASE_URL=sqlite:///backend.db
TEST_DATABASE_URL=sqlite:///:memory:

# AI Model Configuration
EMBEDDING_MODEL_NAME=nomic-ai/nomic-embed-text-v1
SUMMARIZER_MODEL=facebook/bart-large-cnn
TAGGER_MODEL=facebook/bart-large-mnli

# Search Configuration
DEFAULT_HYBRID_SEARCH_WEIGHT=0.5
EMBEDDING_CACHE_SIZE=1000

# Graph Configuration
GRAPH_WEIGHT_VECTOR=0.6
GRAPH_WEIGHT_TAGS=0.3
GRAPH_WEIGHT_CLASSIFICATION=0.1

# Development Settings
DEBUG=true
LOG_LEVEL=INFO
```

### 5. Run Database Migrations

```bash
alembic upgrade head
```

### 6. Start Development Server

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`

### 7. Start Edge Worker (Optional)

For GPU-accelerated embeddings and repository ingestion:

```bash
# Linux/WSL/Git Bash
bash start_worker.sh

# Windows
python start_worker.py
```

**See [Worker Architecture](../WORKER_ARCHITECTURE.md) for complete worker setup and operation.**

## Verify Installation

### Check API Documentation

Open in browser:
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

### Test Health Endpoint

```bash
curl http://127.0.0.1:8000/health
```

Expected response:
```json
{"status": "healthy", "timestamp": "2024-01-01T10:00:00Z"}
```

### Verify Module Registration

Check that all 13 modules are loaded:

```bash
curl http://127.0.0.1:8000/monitoring/health
```

Expected response should show all modules as healthy:
```json
{
  "status": "healthy",
  "modules": {
    "collections": "healthy",
    "resources": "healthy",
    "search": "healthy",
    "annotations": "healthy",
    "scholarly": "healthy",
    "authority": "healthy",
    "curation": "healthy",
    "quality": "healthy",
    "taxonomy": "healthy",
    "graph": "healthy",
    "recommendations": "healthy",
    "monitoring": "healthy"
  },
  "event_bus": {
    "status": "healthy",
    "handlers_registered": 12
  }
}
```

### Run Tests

```bash
pytest tests/ -v
```

## Understanding the Module Structure

### Phase 14 Architecture

Neo Alexandria uses a **vertical slice architecture** where each feature is a self-contained module:

```
app/
├── shared/              # Shared kernel (no business logic)
│   ├── database.py      # Database session management
│   ├── event_bus.py     # Event-driven communication
│   ├── base_model.py    # Base SQLAlchemy model
│   ├── embeddings.py    # Embedding generation service
│   ├── ai_core.py       # AI/ML operations
│   └── cache.py         # Caching service
└── modules/             # 13 self-contained modules
    ├── collections/     # Collection management
    ├── resources/       # Resource CRUD
    ├── search/          # Hybrid search
    ├── annotations/     # Text highlights & notes
    ├── scholarly/       # Academic metadata
    ├── authority/       # Subject authority
    ├── curation/        # Content review
    ├── quality/         # Quality assessment
    ├── taxonomy/        # ML classification
    ├── graph/           # Knowledge graph & citations
    ├── recommendations/ # Hybrid recommendations
    └── monitoring/      # System health & metrics
```

### Module Standard Structure

Each module follows this pattern:

```
modules/{module_name}/
├── __init__.py      # Public interface
├── router.py        # API endpoints
├── service.py       # Business logic
├── schema.py        # Pydantic models
├── model.py         # SQLAlchemy models (optional)
├── handlers.py      # Event handlers
└── README.md        # Documentation
```

### Key Principles

1. **Module Independence**: Modules don't import from each other
2. **Event-Driven**: Modules communicate via events, not direct calls
3. **Shared Kernel**: Common infrastructure (database, events, cache) in `shared/`
4. **Standard Structure**: All modules follow the same layout
5. **Self-Contained**: Each module has its own router, service, schema, and tests

## Database Configuration

### SQLite (Default)

No additional setup required. Database file created automatically.

```bash
DATABASE_URL=sqlite:///backend.db
```

### PostgreSQL (Production)

1. Install PostgreSQL 15+
2. Create database:
```bash
createdb neo_alexandria
```
3. Update `.env`:
```bash
DATABASE_URL=postgresql://user:password@localhost:5432/neo_alexandria
```
4. Run migrations:
```bash
alembic upgrade head
```

## AI Model Setup

Models are downloaded automatically on first use. To pre-download:

```python
from transformers import AutoModel, AutoTokenizer

# Embedding model
AutoModel.from_pretrained("nomic-ai/nomic-embed-text-v1")
AutoTokenizer.from_pretrained("nomic-ai/nomic-embed-text-v1")

# Summarization model
AutoModel.from_pretrained("facebook/bart-large-cnn")
AutoTokenizer.from_pretrained("facebook/bart-large-cnn")
```

## IDE Setup

### VS Code

Recommended extensions:
- Python
- Pylance
- Black Formatter
- isort

Settings (`.vscode/settings.json`):
```json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "[python]": {
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  }
}
```

### PyCharm

1. Set interpreter to `.venv/bin/python`
2. Enable Black formatter
3. Configure pytest as test runner

## Common Issues

### Import Errors

Ensure virtual environment is activated:
```bash
source .venv/bin/activate
which python  # Should show .venv path
```

### Module Not Loading

Check application startup logs for module registration:
```bash
uvicorn app.main:app --reload --log-level debug
```

Look for lines like:
```
INFO: ✓ Registered router for module: collections
INFO: ✓ Registered event handlers for module: collections
```

If a module fails to load, check:
1. Module `__init__.py` exists and exports correctly
2. No circular imports within the module
3. All dependencies are installed

### Database Locked (SQLite)

SQLite doesn't support concurrent writes. For development:
- Use single process
- Or switch to PostgreSQL

### Model Download Fails

Check internet connection and disk space. Models require ~2GB.

### Memory Errors

AI models require significant RAM. Options:
- Increase system RAM to 8GB+
- Use smaller models
- Disable AI features for testing

### Event Handlers Not Firing

Check that event handlers are registered during startup:
```bash
curl http://127.0.0.1:8000/monitoring/events
```

Should show events being emitted and delivered. If not:
1. Verify `register_handlers()` is called in module `__init__.py`
2. Check application logs for handler registration errors
3. Ensure event types match exactly (case-sensitive)

## Next Steps

- [Development Workflows](workflows.md) - Common tasks and module development patterns
- [Testing Guide](testing.md) - Running tests
- [Migration Guide](../MIGRATION_GUIDE.md) - Understanding the modular architecture
- [API Documentation](../api/) - API reference

## Related Documentation

- [Worker Architecture](../WORKER_ARCHITECTURE.md) - Unified edge worker design and operation
- [Architecture Overview](../architecture/overview.md) - System architecture and module structure
- [Module Documentation](../architecture/modules.md) - Complete module reference
- [Event System](../architecture/event-system.md) - Event-driven communication patterns
- [Database Configuration](../architecture/database.md)
- [Troubleshooting](troubleshooting.md)

