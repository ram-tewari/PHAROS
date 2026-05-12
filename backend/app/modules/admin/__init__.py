"""Admin module — operational endpoints (backfills, housekeeping).

Exposed as `admin_router` so app/__init__.py can register it via the
same dynamic-include path used by every other module.
"""
from .router import router as admin_router  # noqa: F401

__version__ = "1.0.0"
