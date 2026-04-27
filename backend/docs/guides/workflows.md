# Development Workflows

Common development tasks and patterns for Pharos.

> **Phase 14 Complete**: This guide reflects the fully modular vertical slice architecture with 13 self-contained modules, enhanced shared kernel, and event-driven communication patterns.

## Quick Reference

### Worker Commands
```bash
# Start unified edge worker (GPU-accelerated)
bash start_worker.sh    # Linux/WSL/Git Bash
python start_worker.py  # Windows

# Check worker status
ps aux | grep main_worker  # Linux/WSL
tasklist | findstr python  # Windows
```

**See [Worker Architecture](../WORKER_ARCHITECTURE.md) for complete worker documentation.**

### Module Structure
All modules follow a standard structure:
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

### Current Modules (13 Total)
1. **collections** - Collection management
2. **resources** - Resource CRUD operations
3. **search** - Hybrid search (keyword + semantic)
4. **annotations** - Text highlights and notes
5. **scholarly** - Academic metadata extraction
6. **authority** - Subject authority control
7. **curation** - Content review and batch operations
8. **quality** - Multi-dimensional quality assessment
9. **taxonomy** - ML-based classification
10. **graph** - Knowledge graph and citations
11. **recommendations** - Hybrid recommendation engine
12. **monitoring** - System health and metrics

### Shared Kernel Services
- **database.py** - Database session management
- **event_bus.py** - Event-driven communication
- **base_model.py** - Base SQLAlchemy model
- **embeddings.py** - Embedding generation (dense & sparse)
- **ai_core.py** - AI/ML operations (summarization, entity extraction)
- **cache.py** - Caching service with TTL support

## Code Quality

### Formatting

```bash
# Format with Black
black backend/

# Sort imports
isort backend/

# Both at once
black backend/ && isort backend/
```

### Linting

```bash
# Lint with Ruff
ruff check backend/

# Auto-fix issues
ruff check backend/ --fix

# Type checking
mypy backend/app/
```

### Pre-commit Hooks

Install pre-commit hooks:
```bash
pre-commit install
```

Run manually:
```bash
pre-commit run --all-files
```

## Database Management

### Create Migration

```bash
cd backend
alembic revision --autogenerate -m "Add new field to resources"
```

### Apply Migrations

```bash
alembic upgrade head
```

### Rollback Migration

```bash
# Rollback one step
alembic downgrade -1

# Rollback to specific revision
alembic downgrade abc123
```

### Check Current Version

```bash
alembic current
```

### View Migration History

```bash
alembic history
```

## Module Development Patterns

### Using Shared Kernel Services

#### Embedding Generation

```python
# In your module service
from app.shared.embeddings import EmbeddingService

class MyModuleService:
    def __init__(self, db: Session):
        self.db = db
        self.embedding_service = EmbeddingService()
    
    def process_text(self, text: str):
        # Generate dense embedding
        embedding = self.embedding_service.generate_embedding(text)
        
        # Generate sparse embedding (SPLADE)
        sparse_embedding = self.embedding_service.generate_sparse_embedding(text)
        
        # Batch generation
        embeddings = self.embedding_service.batch_generate([text1, text2, text3])
```

#### AI/ML Operations

```python
# In your module service
from app.shared.ai_core import AICore

class MyModuleService:
    def __init__(self, db: Session):
        self.db = db
        self.ai_core = AICore()
    
    def process_content(self, text: str):
        # Generate summary
        summary = self.ai_core.summarize(text)
        
        # Extract entities
        entities = self.ai_core.extract_entities(text)
        
        # Zero-shot classification
        labels = ["science", "technology", "business"]
        scores = self.ai_core.classify_text(text, labels)
```

#### Caching

```python
# In your module service
from app.shared.cache import CacheService

class MyModuleService:
    def __init__(self, db: Session):
        self.db = db
        self.cache = CacheService()
    
    def get_expensive_data(self, key: str):
        # Try cache first
        cached = self.cache.get(f"mymodule:{key}")
        if cached:
            return cached
        
        # Compute if not cached
        data = self._compute_expensive_operation(key)
        
        # Cache with TTL (seconds)
        self.cache.set(f"mymodule:{key}", data, ttl=3600)
        return data
    
    def invalidate_cache(self, pattern: str):
        # Invalidate by pattern
        self.cache.invalidate(f"mymodule:{pattern}*")
```

### Event-Driven Communication

#### Emitting Events

```python
# In your module service
from app.shared.event_bus import event_bus

class MyModuleService:
    def create_item(self, db: Session, data: ItemCreate):
        # Create item
        item = MyItem(**data.dict())
        db.add(item)
        db.commit()
        db.refresh(item)
        
        # Emit event for other modules
        event_bus.emit("mymodule.item_created", {
            "item_id": str(item.id),
            "name": item.name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return item
```

#### Subscribing to Events

```python
# In your module handlers.py
from app.shared.event_bus import event_bus
from app.shared.database import SessionLocal
from .service import MyModuleService

def handle_resource_created(payload: dict):
    """Handle resource creation event."""
    resource_id = payload.get("resource_id")
    
    # Create fresh database session
    db = SessionLocal()
    try:
        service = MyModuleService(db)
        service.process_new_resource(resource_id)
    except Exception as e:
        logger.error(f"Error handling resource.created: {e}", exc_info=True)
    finally:
        db.close()

def register_handlers():
    """Register all event handlers for this module."""
    event_bus.subscribe("resource.created", handle_resource_created)
    event_bus.subscribe("resource.updated", handle_resource_updated)
```

#### Event Handler Best Practices

1. **Always create fresh database sessions** in handlers
2. **Always close sessions** in finally block
3. **Catch exceptions** - don't let one handler break others
4. **Log errors** with full traceback
5. **Keep handlers fast** (<100ms) - offload heavy work to Celery
6. **Make handlers idempotent** - safe to run multiple times

```python
def handle_event(payload: dict):
    """Example handler with best practices."""
    from app.shared.database import SessionLocal
    
    db = SessionLocal()
    try:
        # Process event
        service = MyService(db)
        service.process(payload)
        
        logger.info(f"Successfully processed event: {payload}")
    except Exception as e:
        logger.error(f"Error processing event: {e}", exc_info=True)
        # Don't re-raise - let other handlers continue
    finally:
        db.close()
```

## Adding New Features

### 1. Create Module (Vertical Slice)

```bash
mkdir -p app/modules/new_feature
touch app/modules/new_feature/__init__.py
touch app/modules/new_feature/router.py
touch app/modules/new_feature/service.py
touch app/modules/new_feature/schema.py
touch app/modules/new_feature/model.py
touch app/modules/new_feature/handlers.py
touch app/modules/new_feature/README.md
```

### 2. Define Model

```python
# app/modules/new_feature/model.py
from app.shared.base_model import BaseModel
from sqlalchemy import Column, String, Text

class NewFeature(BaseModel):
    __tablename__ = "new_features"
    
    name = Column(String(255), nullable=False)
    description = Column(Text)
```

### 3. Create Schema

```python
# app/modules/new_feature/schema.py
from pydantic import BaseModel
from typing import Optional
from uuid import UUID

class NewFeatureCreate(BaseModel):
    name: str
    description: Optional[str] = None

class NewFeatureResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    
    class Config:
        from_attributes = True
```

### 4. Implement Service

```python
# app/modules/new_feature/service.py
from sqlalchemy.orm import Session
from .model import NewFeature
from .schema import NewFeatureCreate
from app.shared.event_bus import event_bus

class NewFeatureService:
    def __init__(self, db: Session):
        self.db = db
    
    def create_feature(self, data: NewFeatureCreate) -> NewFeature:
        feature = NewFeature(**data.dict())
        self.db.add(feature)
        self.db.commit()
        self.db.refresh(feature)
        
        # Publish event
        event_bus.emit("new_feature.created", {
            "id": str(feature.id),
            "name": feature.name
        })
        
        return feature
```

### 5. Create Router

```python
# app/modules/new_feature/router.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.shared.database import get_db
from .service import NewFeatureService
from .schema import NewFeatureCreate, NewFeatureResponse

router = APIRouter(prefix="/new-features", tags=["new-features"])

@router.post("/", response_model=NewFeatureResponse)
def create(data: NewFeatureCreate, db: Session = Depends(get_db)):
    service = NewFeatureService(db)
    return service.create_feature(data)
```

### 6. Create Event Handlers

```python
# app/modules/new_feature/handlers.py
from app.shared.event_bus import event_bus
from app.shared.database import SessionLocal
from .service import NewFeatureService

def handle_external_event(payload: dict):
    """Handle events from other modules."""
    db = SessionLocal()
    try:
        service = NewFeatureService(db)
        service.process_event(payload)
    except Exception as e:
        logger.error(f"Error handling event: {e}", exc_info=True)
    finally:
        db.close()

def register_handlers():
    """Register all event handlers for this module."""
    event_bus.subscribe("external.event", handle_external_event)
```

### 7. Create Public Interface

```python
# app/modules/new_feature/__init__.py
"""New Feature Module - Public Interface"""

__version__ = "1.0.0"
__domain__ = "new_feature"

from .router import router as new_feature_router
from .service import NewFeatureService
from .schema import NewFeatureCreate, NewFeatureResponse
from .handlers import register_handlers

__all__ = [
    "new_feature_router",
    "NewFeatureService",
    "NewFeatureCreate",
    "NewFeatureResponse",
    "register_handlers",
]
```

### 8. Register Module

Add to `app/__init__.py`:

```python
modules = [
    # Existing modules
    ("collections", "backend.app.modules.collections", "collections_router"),
    ("resources", "backend.app.modules.resources", "resources_router"),
    ("search", "backend.app.modules.search", "search_router"),
    
    # New module
    ("new_feature", "backend.app.modules.new_feature", "new_feature_router"),
]
```

### 9. Create Migration

```bash
alembic revision --autogenerate -m "Add new_features table"
alembic upgrade head
```

### 10. Write Tests

```python
# app/modules/new_feature/tests/test_service.py
import pytest
from app.modules.new_feature.service import NewFeatureService
from app.modules.new_feature.schema import NewFeatureCreate

def test_create_feature(db_session):
    service = NewFeatureService(db_session)
    data = NewFeatureCreate(name="Test", description="Test description")
    
    feature = service.create_feature(data)
    
    assert feature.name == "Test"
    assert feature.description == "Test description"
    assert feature.id is not None
```

## Adding API Endpoints

### GET Endpoint

```python
@router.get("/{item_id}", response_model=ItemResponse)
def get_item(item_id: UUID, db: Session = Depends(get_db)):
    service = ItemService(db)
    item = service.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
```

### POST Endpoint

```python
@router.post("/", response_model=ItemResponse, status_code=201)
def create_item(data: ItemCreate, db: Session = Depends(get_db)):
    service = ItemService(db)
    return service.create_item(data)
```

### PUT Endpoint

```python
@router.put("/{item_id}", response_model=ItemResponse)
def update_item(
    item_id: UUID,
    data: ItemUpdate,
    db: Session = Depends(get_db)
):
    service = ItemService(db)
    item = service.update_item(item_id, data)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
```

### DELETE Endpoint

```python
@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: UUID, db: Session = Depends(get_db)):
    service = ItemService(db)
    success = service.delete_item(item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found")
```

## Debugging

### Enable Debug Logging

```bash
LOG_LEVEL=DEBUG uvicorn app.main:app --reload
```

### Database Query Logging

```python
# In settings or main.py
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

### Event Bus Debugging

Check event metrics:
```bash
curl http://localhost:8000/monitoring/events
```

View event history:
```bash
curl http://localhost:8000/monitoring/events/history
```

### Interactive Debugging

```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use VS Code debugger with launch.json
```

### Module Isolation Validation

Check for circular dependencies:
```bash
python backend/scripts/check_module_isolation.py
```

This will detect:
- Direct imports between modules
- Circular dependencies
- Violations of module boundaries

## Common Patterns

### Annotation Workflow

```python
# 1. Create annotation on resource
from app.modules.annotations.service import AnnotationService
from app.modules.annotations.schema import AnnotationCreate

service = AnnotationService(db)

# Create highlight with note
annotation_data = AnnotationCreate(
    resource_id=resource_id,
    user_id=user_id,
    start_offset=100,
    end_offset=250,
    highlighted_text="Important concept for my research",
    note="This relates to my hypothesis about X",
    tags=["research", "hypothesis"],
    color="#FFFF00"
)

annotation = service.create_annotation(annotation_data)
# → Emits annotation.created event
# → Recommendations module updates user profile

# 2. Search annotations semantically
results = service.search_annotations_semantic(
    user_id=user_id,
    query="machine learning concepts",
    limit=10
)

# 3. Export annotations
markdown_export = service.export_annotations(
    user_id=user_id,
    resource_id=resource_id,
    format="markdown"
)
```

### Classification Workflow

```python
# 1. Auto-classify resource on creation
from app.modules.taxonomy.classification_service import ClassificationService

classifier = ClassificationService(db)

# Classify using hybrid approach (rules + ML)
result = classifier.classify_resource(
    resource_id=resource_id,
    use_ml=True,
    use_rules=True,
    confidence_threshold=0.7
)
# → Emits resource.classified event
# → Search module updates index with classification

# 2. Train ML model with new data
from app.modules.taxonomy.ml_service import MLClassificationService

ml_service = MLClassificationService(db)

# Fine-tune model with labeled data
training_result = ml_service.fine_tune(
    labeled_data=training_samples,
    epochs=3,
    batch_size=16,
    learning_rate=2e-5
)
# → Emits taxonomy.model_trained event

# 3. Active learning for model improvement
uncertain_samples = ml_service.active_learning_uncertainty_sampling(
    unlabeled_pool=unlabeled_resources,
    n_samples=50,
    strategy="least_confident"
)
# Returns resources that need manual labeling
```

### Curation Workflow

```python
# 1. Quality outlier triggers review
# (Automatic via quality.outlier_detected event)

# 2. Curator reviews flagged resource
from app.modules.curation.service import CurationService
from app.modules.curation.schema import ReviewCreate

curation_service = CurationService(db)

# Create review record
review_data = ReviewCreate(
    resource_id=resource_id,
    reviewer_id=curator_id,
    status="pending",
    priority="high"
)

review = curation_service.create_review(review_data)

# 3. Approve or reject resource
approved_review = curation_service.update_review_status(
    review_id=review.id,
    status="approved",
    notes="High quality content, approved for publication"
)
# → Emits curation.approved event

# 4. Batch operations on multiple resources
batch_result = curation_service.batch_approve(
    resource_ids=[id1, id2, id3],
    reviewer_id=curator_id,
    notes="Batch approval for verified sources"
)
```

### Literature-Based Discovery (LBD) Workflow

```python
# 1. Extract citations from new resource
from app.modules.graph.service import GraphService

graph_service = GraphService(db)

# Automatic citation extraction on resource.created event
# Manual trigger:
citations = graph_service.extract_citations(resource_id)
# → Emits citation.extracted event
# → Updates knowledge graph

# 2. Discover hidden connections (ABC pattern)
from app.modules.graph.discovery import LBDService

lbd_service = LBDService(db)

# Find bridging concepts between A and C
hypotheses = lbd_service.discover_hypotheses(
    concept_a="machine learning",
    concept_c="drug discovery",
    max_bridging_concepts=5,
    min_plausibility=0.6
)
# → Emits hypothesis.discovered event

# Returns list of hypotheses with:
# - Bridging concepts (B)
# - Plausibility scores
# - Evidence chains
# - Supporting resources

# 3. Traverse citation network
path = graph_service.find_shortest_path(
    source_resource_id=resource_a_id,
    target_resource_id=resource_c_id,
    max_depth=4
)

# 4. Compute resource importance
pagerank_scores = graph_service.compute_pagerank(
    damping_factor=0.85,
    max_iterations=100
)
```

### Async Background Tasks

For long-running operations, use Celery:

```python
# In your service
from app.tasks.celery_tasks import process_heavy_task

def trigger_processing(self, item_id: str):
    # Queue task for background processing
    process_heavy_task.delay(item_id)
    return {"status": "queued"}
```

### Pagination

```python
from fastapi import Query

@router.get("/items")
def list_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db)
):
    service = ItemService(db)
    items = service.list_items(skip=skip, limit=limit)
    total = service.count_items()
    
    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit
    }
```

### Error Handling

```python
from fastapi import HTTPException

def get_item(self, item_id: str):
    item = self.db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=404,
            detail=f"Item {item_id} not found"
        )
    return item
```

## Related Documentation

- [Worker Architecture](../WORKER_ARCHITECTURE.md) - Unified edge worker design and operation
- [Setup Guide](setup.md) - Installation
- [Testing Guide](testing.md) - Running tests
- [Architecture](../architecture/) - System design
- [Migration Guide](../MIGRATION_GUIDE.md) - Understanding the modular architecture
- [Event System](../architecture/event-system.md) - Event-driven patterns

