"""
Quality Module

This module provides multi-dimensional quality assessment for resources.
It evaluates content quality, metadata completeness, and citation quality.

Public Interface:
- quality_router: FastAPI router for quality endpoints
- QualityService: Service for quality assessment operations
- SummarizationEvaluator: Service for summarization quality evaluation
- Schema classes: QualityAssessment, QualityMetrics, etc.

Events Emitted:
- quality.computed: When quality assessment is completed
- quality.outlier_detected: When a quality outlier is detected
- quality.degradation_detected: When quality degradation is detected

Events Subscribed:
- resource.created: Triggers initial quality computation
- resource.updated: Triggers quality recomputation
"""

__version__ = "1.0.0"
__domain__ = "quality"

from .router import quality_router, rag_evaluation_router
from .service import QualityService
from .evaluator import SummarizationEvaluator
from .schema import (
    QualityDetailsResponse,
    QualityRecalculateRequest,
    OutlierListResponse,
    OutlierResponse,
    DegradationReport,
    DegradationResourceReport,
    QualityDistributionResponse,
    QualityTrendsResponse,
    QualityDimensionsResponse,
    ReviewQueueResponse,
)
from .handlers import register_handlers

__all__ = [
    "quality_router",
    "rag_evaluation_router",
    "QualityService",
    "SummarizationEvaluator",
    "QualityDetailsResponse",
    "QualityRecalculateRequest",
    "OutlierListResponse",
    "OutlierResponse",
    "DegradationReport",
    "DegradationResourceReport",
    "QualityDistributionResponse",
    "QualityTrendsResponse",
    "QualityDimensionsResponse",
    "ReviewQueueResponse",
    "register_handlers",
]
