# Resources Module

## Overview

The Resources module is the core domain module responsible for managing resource entities in Pharos. It handles URL ingestion, content processing, metadata extraction, and the complete resource lifecycle from creation to deletion.

## Purpose

This module provides:
- **URL Ingestion**: Asynchronous processing of web resources with content extraction
- **CRUD Operations**: Create, read, update, and delete resources
- **Metadata Management**: Dublin Core metadata with scholarly extensions
- **Quality Assessment**: Automated quality scoring and classification
- **Search Integration**: Dense and sparse embeddings for hybrid search
- **Content Processing**: HTML, PDF, and plain text extraction
- **Status Tracking**: Ingestion status and error handling

## Module Structure

```
resources/
├── __init__.py          # Public interface and module metadata
├── router.py            # FastAPI endpoints (15+ endpoints)
├── service.py           # Business logic and orchestration
├── model.py             # SQLAlchemy Resource model
├── schema.py            # Pydantic schemas for validation
├── handlers.py          # Event handlers (future)
├── README.md            # This file
└── tests/
    ├── test_service.py
    ├── test_router.py
    └── test_handlers.py
```

## Public Interface

### Router
```python
from app.modules.resources import resources_router

# Endpoints:
# POST /resources - Create resource
# POST /resources/ingest - Ingest from URL
# GET /resources - List resources
# GET /resources/{id} - Get resource
# PUT /resources/{id} - Update resource
# DELETE /resources/{id} - Delete resource
# GET /resources/{id}/content - Get content
# GET /resources/{id}/metadata - Get metadata
# POST /resources/{id}/reprocess - Reprocess resource
# GET /resources/status/{id} - Get ingestion status
```

### Service
```python
from app.modules.resources import ResourceService

service = ResourceService(db)
# Methods:
# - create_resource(data: ResourceCreate) -> Resource
# - get_resource(resource_id: UUID) -> Resource
# - list_resources(filters, pagination) -> List[Resource]
# - update_resource(resource_id: UUID, data: ResourceUpdate) -> Resource
# - delete_resource(resource_id: UUID) -> None
# - ingest_from_url(url: str) -> Resource
# - get_content(resource_id: UUID) -> str
# - reprocess_resource(resource_id: UUID) -> Resource
```

### Schemas
```python
from app.modules.resources import (
    ResourceCreate,
    ResourceUpdate,
    ResourceRead,
    ResourceResponse,
    ResourceListResponse,
    ResourceStatus,
    IngestionRequest,
    IngestionResponse
)
```

### Models
```python
from app.modules.resources import Resource

# Resource model fields:
# - id: UUID
# - url: str
# - title: str
# - content: str
# - summary: str
# - tags: List[str]
# - embedding: vector
# - sparse_embedding: vector
# - quality_score: float
# - status: ResourceStatus enum
# - created_at, updated_at: datetime
```

## Events

### Emitted Events

#### resource.created
Emitted when a new resource is successfully created.
```python
{
    "resource_id": str,
    "url": str,
    "title": str,
    "user_id": str,
    "timestamp": datetime
}
```

#### resource.updated
Emitted when a resource is modified.
```python
{
    "resource_id": str,
    "updated_fields": List[str],
    "user_id": str,
    "timestamp": datetime
}
```

#### resource.deleted
Emitted when a resource is deleted.
```python
{
    "resource_id": str,
    "user_id": str,
    "timestamp": datetime
}
```

#### resource.content_changed
Emitted when resource content is modified.
```python
{
    "resource_id": str,
    "content_length": int,
    "timestamp": datetime
}
```

#### ingestion.started
Emitted when URL ingestion begins.
```python
{
    "resource_id": str,
    "url": str,
    "timestamp": datetime
}
```

#### ingestion.completed
Emitted when ingestion completes successfully.
```python
{
    "resource_id": str,
    "url": str,
    "duration_seconds": float,
    "timestamp": datetime
}
```

#### ingestion.failed
Emitted when ingestion fails.
```python
{
    "resource_id": str,
    "url": str,
    "error": str,
    "timestamp": datetime
}
```

### Subscribed Events
None currently. Future events may include:
- `quality.computed` - Update quality score
- `taxonomy.classified` - Update classification

## Dependencies

### Shared Kernel
- `shared.database`: Database session management
- `shared.event_bus`: Event-driven communication
- `shared.base_model`: Base SQLAlchemy model
- `shared.embeddings`: Embedding generation
- `shared.ai_core`: AI operations (summarization)

### External Libraries
- `requests`: HTTP requests for URL ingestion
- `beautifulsoup4`: HTML parsing
- `PyPDF2`: PDF extraction
- `sqlalchemy`: ORM

## Usage Examples

### Create Resource from URL
```python
from app.modules.resources import ResourceService

service = ResourceService(db)
resource = await service.ingest_from_url(
    url="https://arxiv.org/abs/2301.00001"
)
print(f"Created resource: {resource.id}")
```

### Update Resource Metadata
```python
from app.modules.resources import ResourceUpdate

update_data = ResourceUpdate(
    title="Updated Title",
    tags=["machine-learning", "nlp"]
)
updated = await service.update_resource(resource.id, update_data)
```

### Delete Resource (Cascades to Related Data)
```python
await service.delete_resource(resource.id)
# Triggers resource.deleted event
# Other modules clean up related data via event handlers
```

### Get Resource with Content
```python
resource = await service.get_resource(resource_id)
content = await service.get_content(resource_id)
```

## Integration Patterns

### Event-Driven Integration
```python
from app.shared.event_bus import event_bus

# Other modules subscribe to resource events
@event_bus.subscribe("resource.created")
async def handle_new_resource(payload):
    resource_id = payload["resource_id"]
    # Process new resource (quality assessment, classification, etc.)
```

### Service-to-Service (via Events Only)
```python
# Resources module emits events
await event_bus.emit("resource.created", {
    "resource_id": str(resource.id),
    "url": resource.url
})

# Other modules react asynchronously
# No direct service dependencies
```

## Testing

### Unit Tests
```bash
pytest backend/tests/modules/test_resources_endpoints.py -v
```

### Integration Tests
```bash
pytest backend/tests/integration/ -k resources -v
```

### Test Coverage
- Resource CRUD operations
- URL ingestion workflow
- Content extraction
- Event emission
- Error handling
- Status tracking

## Performance Considerations

- **Async Ingestion**: URL ingestion runs asynchronously via Celery
- **Caching**: Frequently accessed resources cached in Redis
- **Batch Operations**: Support for bulk resource creation
- **Pagination**: List endpoints support cursor-based pagination
- **Indexing**: Database indexes on url, created_at, quality_score

## Troubleshooting

### Issue: Ingestion Fails with Timeout
**Solution**: Check network connectivity and increase timeout in settings.

### Issue: Duplicate Resources Created
**Solution**: Use unique constraint on URL field. Check for existing resource before creating.

### Issue: Content Extraction Returns Empty
**Solution**: Verify content type is supported (HTML, PDF, TXT). Check for JavaScript-rendered content.

### Issue: Events Not Emitted
**Solution**: Verify event bus is initialized. Check event handler registration in main.py.

## Related Modules

- **Collections**: Resources can be organized into collections
- **Search**: Resources are indexed for search
- **Quality**: Resources have quality scores computed
- **Taxonomy**: Resources are automatically classified
- **Annotations**: Users can annotate resource content
- **Graph**: Resources are connected via citations
- **Scholarly**: Academic metadata is extracted

## Version History

- **1.0.0** (Phase 14): Initial extraction from layered architecture
  - Moved from `routers/resources.py` and `services/resource_service.py`
  - Implemented event-driven communication
  - Added module isolation

## Module Metadata

- **Version**: 1.0.0
- **Domain**: resources
- **Phase**: 14 (Complete Vertical Slice Refactor)
