"""Code-intelligence API slice (repositories, ingestion jobs, search, context).

Thin HTTP layer over :mod:`app.codeintel`.
"""

from .router import router as code_router

__version__ = "1.0.0"
__all__ = ["code_router"]
