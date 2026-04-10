"""
Planning Module Database Models

Note: PlanningSession model is defined in app.database.models
to avoid circular imports and ensure proper SQLAlchemy registration.
"""

# Import from main models file for convenience
from app.database.models import PlanningSession

__all__ = ["PlanningSession"]
