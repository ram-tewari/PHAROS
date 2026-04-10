"""
Resources Module - Public Interface

This module provides resource management functionality including:
- URL ingestion with content processing
- Resource CRUD operations
- Resource querying with filtering and pagination
- Quality assessment and classification

Public API:
- resources_router: FastAPI router for resource endpoints
- Service functions: Business logic for resource operations
- Schema classes: Pydantic models for validation

Version: 1.0.0
Domain: Resources
"""

__version__ = "1.0.0"
__domain__ = "resources"

# Import public components
# NOTE: Router and service imports are deferred to avoid model conflicts during migration
# from .router import router as resources_router
# from .service import (...)


# Lazy imports to avoid model conflicts
def __getattr__(name):
    """Lazy import to avoid model conflicts."""
    if name == "resources_router":
        from .router import router as resources_router

        return resources_router
    elif name == "chunking_router":
        from .router import chunking_router

        return chunking_router
    elif name == "register_handlers":
        from .handlers import register_handlers

        return register_handlers
    elif name in [
        "create_pending_resource",
        "get_resource",
        "list_resources",
        "update_resource",
        "delete_resource",
        "process_ingestion",
    ]:
        from . import service

        return getattr(service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


from .schema import (
    ResourceBase,
    ResourceCreate,
    ResourceUpdate,
    ResourceRead,
    ResourceInDB,
    ResourceStatus,
)
# NOTE: Model import commented out to avoid conflicts
# with existing database/models.py. Will be re-enabled after old models are removed.
# from .model import Resource

# Public exports
__all__ = [
    # Router
    "resources_router",
    "chunking_router",
    # Service functions
    "create_pending_resource",
    "get_resource",
    "list_resources",
    "update_resource",
    "delete_resource",
    "process_ingestion",
    # Schemas
    "ResourceBase",
    "ResourceCreate",
    "ResourceUpdate",
    "ResourceRead",
    "ResourceInDB",
    "ResourceStatus",
    # Event handlers
    "register_handlers",
    # Model (commented out during migration)
    # "Resource",
]
