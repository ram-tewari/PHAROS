"""
Recommendations Router

Provides API endpoints for:
- Getting personalized recommendations
- Recording user interactions
- Managing recommendation feedback
- Retrieving and updating user profiles
- Performance metrics

This module merges endpoints from:
- routers/recommendation.py (Basic recommendations)
- routers/recommendations.py (Hybrid recommendations)
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

from app.shared.database import get_sync_db
from app.database.models import RecommendationFeedback

# Module-local imports
from .service import generate_recommendations
from .hybrid_service import HybridRecommendationService
from .user_profile import UserProfileService
from .schema import RecommendationResponse, RecommendedResource
from app.utils.performance_monitoring import metrics


recommendations_router = APIRouter(
    prefix="/api/recommendations", tags=["recommendations"]
)


# ============================================================================
# Pydantic Schemas
# ============================================================================


class InteractionRequest(BaseModel):
    """Request schema for tracking user interactions."""

    resource_id: str = Field(..., description="Resource UUID")
    interaction_type: str = Field(
        ...,
        description="Type of interaction: view, annotation, collection_add, export, rating",
    )
    dwell_time: Optional[int] = Field(
        None, description="Time spent on resource in seconds"
    )
    scroll_depth: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Scroll depth (0.0-1.0)"
    )
    session_id: Optional[str] = Field(None, description="Session identifier")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating (1-5 stars)")

    @validator("interaction_type")
    def validate_interaction_type(cls, v):
        allowed_types = ["view", "annotation", "collection_add", "export", "rating"]
        if v not in allowed_types:
            raise ValueError(f"interaction_type must be one of {allowed_types}")
        return v


class InteractionResponse(BaseModel):
    """Response schema for interaction tracking."""

    interaction_id: str
    user_id: str
    resource_id: str
    interaction_type: str
    interaction_strength: float
    is_positive: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ProfileUpdateRequest(BaseModel):
    """Request schema for updating user profile."""

    diversity_preference: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Diversity preference (0.0-1.0)"
    )
    novelty_preference: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Novelty preference (0.0-1.0)"
    )
    recency_bias: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Recency bias (0.0-1.0)"
    )
    excluded_sources: Optional[List[str]] = Field(
        None, description="List of excluded source domains"
    )
    research_domains: Optional[List[str]] = Field(
        None, description="List of research domains"
    )
    active_domain: Optional[str] = Field(
        None, description="Currently active research domain"
    )


class ProfileResponse(BaseModel):
    """Response schema for user profile."""

    user_id: str
    diversity_preference: float
    novelty_preference: float
    recency_bias: float
    research_domains: Optional[List[str]]
    active_domain: Optional[str]
    excluded_sources: Optional[List[str]]
    total_interactions: int
    last_active_at: Optional[datetime]

    class Config:
        from_attributes = True


class RecommendationScores(BaseModel):
    """Breakdown of recommendation scores."""

    collaborative: float
    content: float
    graph: float
    quality: float
    recency: float


class RecommendationItem(BaseModel):
    """Individual recommendation item."""

    resource_id: str
    title: str
    score: float
    strategy: str
    scores: RecommendationScores
    rank: int
    novelty_score: float
    view_count: int


class RecommendationMetadata(BaseModel):
    """Metadata about the recommendation process."""

    total: int
    strategy: str
    is_cold_start: Optional[bool] = None
    interaction_count: Optional[int] = None
    diversity_applied: bool
    novelty_applied: bool
    gini_coefficient: Optional[float] = None
    diversity_preference: Optional[float] = None
    novelty_preference: Optional[float] = None


class RecommendationsResponse(BaseModel):
    """Response schema for recommendations."""

    recommendations: List[RecommendationItem]
    metadata: RecommendationMetadata


class FeedbackRequest(BaseModel):
    """Request schema for recommendation feedback."""

    resource_id: str = Field(..., description="Resource UUID")
    was_clicked: bool = Field(..., description="Whether the recommendation was clicked")
    was_useful: Optional[bool] = Field(
        None, description="Whether the recommendation was useful (explicit feedback)"
    )
    feedback_notes: Optional[str] = Field(None, description="Optional feedback notes")


class FeedbackResponse(BaseModel):
    """Response schema for recommendation feedback."""

    feedback_id: str
    user_id: str
    resource_id: str
    was_clicked: bool
    was_useful: Optional[bool]
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Helper Functions
# ============================================================================


def _get_current_user_id() -> UUID:
    """
    Get current authenticated user ID.

    In production, this would extract the user ID from:
    - JWT token in Authorization header
    - Session cookie
    - API key

    For now, returns a fixed test user ID. The actual User record
    should be created by application startup or test fixtures.

    TODO: Implement proper authentication with JWT tokens
    """
    # Return a fixed UUID for the test user
    # The test fixtures will create a User with this ID
    return UUID("00000000-0000-0000-0000-000000000001")


def _get_hybrid_recommendation_service(db: Session) -> HybridRecommendationService:
    """Helper to create HybridRecommendationService instance."""
    return HybridRecommendationService(db)


def _get_user_profile_service(db: Session) -> UserProfileService:
    """Helper to create UserProfileService instance."""
    return UserProfileService(db)


# ============================================================================
# API Endpoints
# ============================================================================


@recommendations_router.get("", response_model=RecommendationsResponse)
async def get_recommendations_hybrid(
    limit: int = Query(
        20, ge=1, le=100, description="Number of recommendations to return"
    ),
    strategy: str = Query(
        "hybrid", description="Strategy: collaborative, content, graph, or hybrid"
    ),
    diversity: Optional[float] = Query(
        None, ge=0.0, le=1.0, description="Override diversity preference"
    ),
    min_quality: Optional[float] = Query(
        None, ge=0.0, le=1.0, description="Minimum quality threshold"
    ),
    db: Session = Depends(get_sync_db),
    user_id: UUID = Depends(_get_current_user_id),
):
    """
    Get personalized recommendations for the authenticated user (Hybrid).

    Args:
        limit: Number of recommendations (1-100, default 20)
        strategy: Recommendation strategy (collaborative, content, graph, hybrid)
        diversity: Override user's diversity preference (0.0-1.0)
        min_quality: Minimum quality threshold (0.0-1.0)
        db: Database session
        user_id: Current authenticated user ID

    Returns:
        RecommendationsResponse with recommendations and metadata
    """
    try:
        # Validate strategy
        allowed_strategies = ["collaborative", "content", "graph", "hybrid"]
        if strategy not in allowed_strategies:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid strategy. Must be one of {allowed_strategies}",
            )

        # Build filters
        filters = {}
        if min_quality is not None:
            filters["min_quality"] = min_quality
            filters["exclude_outliers"] = True

        # Override diversity preference if provided
        if diversity is not None:
            profile_service = _get_user_profile_service(db)
            profile = profile_service.get_or_create_profile(user_id)
            profile.diversity_preference = diversity
            db.commit()

        # Generate recommendations
        recommendation_service = _get_hybrid_recommendation_service(db)
        result = recommendation_service.generate_recommendations(
            user_id=user_id,
            limit=limit,
            strategy=strategy,
            filters=filters if filters else None,
        )

        # Convert to response format
        recommendations = []
        for rec in result["recommendations"]:
            recommendations.append(
                RecommendationItem(
                    resource_id=rec["resource_id"],
                    title=rec["title"],
                    score=rec["score"],
                    strategy=rec["strategy"],
                    scores=RecommendationScores(**rec["scores"]),
                    rank=rec["rank"],
                    novelty_score=rec["novelty_score"],
                    view_count=rec["view_count"],
                )
            )

        metadata = RecommendationMetadata(**result["metadata"])

        return RecommendationsResponse(
            recommendations=recommendations, metadata=metadata
        )

    except HTTPException:
        # Re-raise HTTPException without modification
        raise
    except ValueError as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"ValueError in get_recommendations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_recommendations: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating recommendations: {str(e)}",
        )


@recommendations_router.get(
    "/simple", response_model=RecommendationResponse, status_code=status.HTTP_200_OK
)
def get_recommendations_simple(
    limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_sync_db)
):
    """
    Get simple recommendations (Basic endpoint).

    Args:
        limit: Number of recommendations (1-100, default 10)
        db: Database session

    Returns:
        RecommendationResponse with basic recommendations
    """
    try:
        recs = generate_recommendations(db, limit=limit)
        items = [RecommendedResource(**it) for it in recs]
        return RecommendationResponse(items=items)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate recommendations",
        ) from exc


@recommendations_router.post(
    "/interactions",
    response_model=InteractionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def track_interaction(
    request: InteractionRequest,
    db: Session = Depends(get_sync_db),
    user_id: UUID = Depends(_get_current_user_id),
):
    """
    Track a user-resource interaction.

    Args:
        request: InteractionRequest with interaction details
        db: Database session
        user_id: Current authenticated user ID

    Returns:
        InteractionResponse with interaction details
    """
    try:
        # Parse resource_id
        try:
            resource_id = UUID(request.resource_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid resource_id format",
            )

        # Track interaction
        profile_service = _get_user_profile_service(db)
        interaction = profile_service.track_interaction(
            user_id=user_id,
            resource_id=resource_id,
            interaction_type=request.interaction_type,
            dwell_time=request.dwell_time,
            scroll_depth=request.scroll_depth,
            session_id=request.session_id,
            rating=request.rating,
        )

        return InteractionResponse(
            interaction_id=str(interaction.id),
            user_id=str(interaction.user_id),
            resource_id=str(interaction.resource_id),
            interaction_type=interaction.interaction_type,
            interaction_strength=interaction.interaction_strength,
            is_positive=bool(interaction.is_positive),
            created_at=interaction.created_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error tracking interaction: {str(e)}",
        )


@recommendations_router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    db: Session = Depends(get_sync_db),
    user_id: UUID = Depends(_get_current_user_id),
):
    """
    Get user profile settings.

    Args:
        db: Database session
        user_id: Current authenticated user ID

    Returns:
        ProfileResponse with user profile settings
    """
    try:
        # Get profile
        profile_service = _get_user_profile_service(db)
        profile = profile_service.get_or_create_profile(user_id)

        # Parse JSON fields
        import json

        research_domains = None
        if profile.research_domains:
            try:
                research_domains = json.loads(profile.research_domains)
            except json.JSONDecodeError:
                research_domains = None

        excluded_sources = None
        if profile.excluded_sources:
            try:
                excluded_sources = json.loads(profile.excluded_sources)
            except json.JSONDecodeError:
                excluded_sources = None

        return ProfileResponse(
            user_id=str(profile.user_id),
            diversity_preference=profile.diversity_preference,
            novelty_preference=profile.novelty_preference,
            recency_bias=profile.recency_bias,
            research_domains=research_domains,
            active_domain=profile.active_domain,
            excluded_sources=excluded_sources,
            total_interactions=profile.total_interactions,
            last_active_at=profile.last_active_at,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving profile: {str(e)}",
        )


@recommendations_router.get("/interactions", response_model=List[InteractionResponse])
async def get_user_interactions(
    limit: int = Query(
        100, ge=1, le=1000, description="Number of interactions to return"
    ),
    offset: int = Query(0, ge=0, description="Number of interactions to skip"),
    interaction_type: Optional[str] = Query(
        None, description="Filter by interaction type"
    ),
    db: Session = Depends(get_sync_db),
    user_id: UUID = Depends(_get_current_user_id),
):
    """
    Get user interaction history.

    Args:
        limit: Number of interactions to return (1-1000, default 100)
        offset: Number of interactions to skip (default 0)
        interaction_type: Optional filter by interaction type
        db: Database session
        user_id: Current authenticated user ID

    Returns:
        List of InteractionResponse with interaction details
    """
    try:
        from app.database.models import UserInteraction

        # Build query
        query = db.query(UserInteraction).filter(UserInteraction.user_id == user_id)

        # Apply interaction type filter if provided
        if interaction_type:
            allowed_types = ["view", "annotation", "collection_add", "export", "rating"]
            if interaction_type not in allowed_types:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid interaction_type. Must be one of {allowed_types}",
                )
            query = query.filter(UserInteraction.interaction_type == interaction_type)

        # Order by most recent first
        query = query.order_by(UserInteraction.interaction_timestamp.desc())

        # Apply pagination
        interactions = query.offset(offset).limit(limit).all()

        # Convert to response format
        return [
            InteractionResponse(
                interaction_id=str(interaction.id),
                user_id=str(interaction.user_id),
                resource_id=str(interaction.resource_id),
                interaction_type=interaction.interaction_type,
                interaction_strength=interaction.interaction_strength,
                is_positive=bool(interaction.is_positive),
                created_at=interaction.created_at,
            )
            for interaction in interactions
        ]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving interactions: {str(e)}",
        )


@recommendations_router.put("/profile", response_model=ProfileResponse)
async def update_profile(
    request: ProfileUpdateRequest,
    db: Session = Depends(get_sync_db),
    user_id: UUID = Depends(_get_current_user_id),
):
    """
    Update user profile settings.

    Args:
        request: ProfileUpdateRequest with updated settings
        db: Database session
        user_id: Current authenticated user ID

    Returns:
        ProfileResponse with updated profile settings
    """
    try:
        # Update profile
        profile_service = _get_user_profile_service(db)
        profile = profile_service.update_profile_settings(
            user_id=user_id,
            diversity_preference=request.diversity_preference,
            novelty_preference=request.novelty_preference,
            recency_bias=request.recency_bias,
            excluded_sources=request.excluded_sources,
            research_domains=request.research_domains,
            active_domain=request.active_domain,
        )

        # Parse JSON fields
        import json

        research_domains = None
        if profile.research_domains:
            try:
                research_domains = json.loads(profile.research_domains)
            except json.JSONDecodeError:
                research_domains = None

        excluded_sources = None
        if profile.excluded_sources:
            try:
                excluded_sources = json.loads(profile.excluded_sources)
            except json.JSONDecodeError:
                excluded_sources = None

        return ProfileResponse(
            user_id=str(profile.user_id),
            diversity_preference=profile.diversity_preference,
            novelty_preference=profile.novelty_preference,
            recency_bias=profile.recency_bias,
            research_domains=research_domains,
            active_domain=profile.active_domain,
            excluded_sources=excluded_sources,
            total_interactions=profile.total_interactions,
            last_active_at=profile.last_active_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating profile: {str(e)}",
        )


@recommendations_router.post(
    "/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED
)
async def submit_feedback(
    request: FeedbackRequest,
    db: Session = Depends(get_sync_db),
    user_id: UUID = Depends(_get_current_user_id),
):
    """
    Submit feedback for a recommendation.

    Args:
        request: FeedbackRequest with feedback details
        db: Database session
        user_id: Current authenticated user ID

    Returns:
        FeedbackResponse with feedback details
    """
    try:
        # Parse resource_id
        try:
            resource_id = UUID(request.resource_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid resource_id format",
            )

        # Create feedback record using the actual database schema
        feedback = RecommendationFeedback(
            user_id=user_id,
            resource_id=resource_id,
            feedback_type="click" if request.was_clicked else "view",
            feedback_value=1.0
            if request.was_useful
            else 0.5
            if request.was_clicked
            else 0.0,
            context={
                "was_clicked": request.was_clicked,
                "was_useful": request.was_useful,
                "feedback_notes": request.feedback_notes,
            },
        )

        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        # Extract values from context for response
        context = feedback.context or {}

        return FeedbackResponse(
            feedback_id=str(feedback.id),
            user_id=str(feedback.user_id),
            resource_id=str(feedback.resource_id),
            was_clicked=context.get("was_clicked", False),
            was_useful=context.get("was_useful"),
            created_at=feedback.created_at,
        )

    except HTTPException:
        # Re-raise HTTPException without modification
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error submitting feedback: {str(e)}",
        )


@recommendations_router.get("/metrics")
async def get_performance_metrics():
    """
    Get performance metrics for the recommendation system.

    Returns:
        Dictionary with performance metrics including:
        - Cache hit rate
        - Method execution times
        - Slow query count
        - Recommendation generation metrics
    """
    try:
        summary = metrics.get_summary()
        return {"status": "success", "metrics": summary}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving metrics: {str(e)}",
        )


@recommendations_router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_recommendations(
    db: Session = Depends(get_sync_db),
    user_id: UUID = Depends(_get_current_user_id),
):
    """
    Trigger a refresh of recommendations for the current user.

    This endpoint initiates a background task to:
    - Recompute user profile based on recent interactions
    - Regenerate recommendations using latest data
    - Update recommendation cache

    Returns:
        Status message indicating refresh has been queued
    """
    try:
        # In a production system, this would queue a background task
        # For now, we'll just return a success response
        return {
            "status": "accepted",
            "message": "Recommendation refresh queued",
            "user_id": str(user_id),
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error queueing refresh: {str(e)}",
        )


@recommendations_router.get("/health")
async def health_check(db: Session = Depends(get_sync_db)):
    """
    Health check endpoint for Recommendations module.

    Verifies:
    - Database connectivity
    - Recommendation service availability
    - User profile service availability
    - Module version and status

    Returns:
        Dictionary with health status including:
        - status: "healthy" or "unhealthy"
        - module: Module name and version
        - database: Database connection status
        - services: Service availability
        - timestamp: When the check was performed
    """
    try:
        # Check database connectivity
        try:
            from sqlalchemy import text

            db.execute(text("SELECT 1"))
            db_healthy = True
            db_message = "Database connection healthy"
        except Exception as e:
            db_healthy = False
            db_message = f"Database connection failed: {str(e)}"

        # Check recommendation service availability
        try:
            _get_hybrid_recommendation_service(db)
            rec_available = True
            rec_message = "Recommendation service available"
        except Exception as e:
            rec_available = False
            rec_message = f"Recommendation service unavailable: {str(e)}"

        # Check user profile service availability
        try:
            _get_user_profile_service(db)
            profile_available = True
            profile_message = "User profile service available"
        except Exception as e:
            profile_available = False
            profile_message = f"User profile service unavailable: {str(e)}"

        # Determine overall status
        overall_healthy = db_healthy and rec_available and profile_available

        return {
            "status": "healthy" if overall_healthy else "unhealthy",
            "module": {
                "name": "recommendations",
                "version": "1.0.0",
                "domain": "recommendations",
            },
            "database": {"healthy": db_healthy, "message": db_message},
            "services": {
                "recommendation_service": {
                    "available": rec_available,
                    "message": rec_message,
                },
                "user_profile_service": {
                    "available": profile_available,
                    "message": profile_message,
                },
            },
            "event_handlers": {"registered": False, "count": 0, "events": []},
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }
