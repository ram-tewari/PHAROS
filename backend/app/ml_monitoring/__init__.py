"""Structured JSON logging for production observability.

The rest of the ML-ops package (PredictionMonitor, AlertManager, model
health checks) was deleted in the Phase 2 amputation; json_logging is the
only survivor and main.py imports it directly.
"""

from .json_logging import JSONFormatter, configure_json_logging, log_with_context

__all__ = [
    "JSONFormatter",
    "configure_json_logging",
    "log_with_context",
]
