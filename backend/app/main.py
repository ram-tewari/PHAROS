"""
Neo Alexandria 2.0 - Main Application Entry Point

This module serves as the main entry point for the Neo Alexandria 2.0 application.
It creates the FastAPI application instance using the factory pattern.

Related files:
- app/__init__.py: FastAPI application factory and configuration
- app/routers/: API endpoint definitions
- app/services/: Business logic services
- app/database/: Database models and configuration
- app/schemas/: Pydantic validation schemas

The application provides a comprehensive knowledge management system with:
- URL ingestion and content processing
- Authority control for subjects, creators, and publishers
- Personal classification system with UDC-inspired codes
- Enhanced quality control with multi-factor scoring
- Full-text search with SQLite FTS5 support
- CRUD operations and quality workflows
"""

from __future__ import annotations

import logging
import os

from . import create_app

# Configure structured JSON logging for production
if os.getenv("ENV", "dev") == "prod" or os.getenv("JSON_LOGGING", "").lower() in (
    "true",
    "1",
):
    from .ml_monitoring.json_logging import JSONFormatter

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter(include_extra=True))
    root_logger.handlers = [handler]
else:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

# Create app instance using factory pattern
# This ensures proper initialization order and avoids circular imports
app = create_app()

__all__ = ["app"]
