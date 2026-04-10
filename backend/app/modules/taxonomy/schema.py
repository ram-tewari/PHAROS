"""
Taxonomy Schemas

Pydantic schemas for taxonomy and classification requests/responses.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# Taxonomy Node Schemas
class TaxonomyNodeCreate(BaseModel):
    """Schema for creating a taxonomy node."""

    name: str = Field(..., description="Node name")
    description: Optional[str] = Field(None, description="Node description")
    parent_id: Optional[str] = Field(None, description="Parent node ID")
    allow_resources: bool = Field(
        True, description="Whether resources can be assigned to this node"
    )


class TaxonomyNodeUpdate(BaseModel):
    """Schema for updating a taxonomy node."""

    name: Optional[str] = Field(None, description="Node name")
    description: Optional[str] = Field(None, description="Node description")
    parent_id: Optional[str] = Field(None, description="Parent node ID")
    allow_resources: Optional[bool] = Field(
        None, description="Whether resources can be assigned to this node"
    )


class TaxonomyNodeResponse(BaseModel):
    """Schema for taxonomy node response."""

    id: str
    name: str
    slug: str
    parent_id: Optional[str] = None
    level: int
    path: str
    description: Optional[str] = None
    allow_resources: bool
    resource_count: int = 0


class TaxonomyTreeResponse(BaseModel):
    """Schema for taxonomy tree response."""

    nodes: List[TaxonomyNodeResponse]
    total: int


# Classification Schemas
class ClassificationRequest(BaseModel):
    """Schema for classification request."""

    resource_id: str = Field(..., description="Resource ID to classify")
    text: Optional[str] = Field(None, description="Text content for classification")


class ClassificationResponse(BaseModel):
    """Schema for classification response."""

    resource_id: str
    predicted_category: str
    confidence: float
    alternatives: List[Dict[str, Any]] = []


# Training Schemas
class TrainingRequest(BaseModel):
    """Schema for training request."""

    force_retrain: bool = Field(False, description="Force model retraining")


class TrainingResponse(BaseModel):
    """Schema for training response."""

    status: str
    accuracy: Optional[float] = None
    samples_trained: int = 0
    message: str


# Active Learning Schemas
class ActiveLearningRequest(BaseModel):
    """Schema for active learning request."""

    threshold: float = Field(
        0.7, description="Confidence threshold for uncertain predictions"
    )
    limit: int = Field(
        10, description="Maximum number of uncertain predictions to return"
    )


class ActiveLearningResponse(BaseModel):
    """Schema for active learning response."""

    uncertain_predictions: List[Dict[str, Any]]
    count: int


# Legacy schemas for backward compatibility
class CategoryCreate(BaseModel):
    """Schema for creating a category."""

    name: str
    description: Optional[str] = None
    parent_id: Optional[str] = None
    allow_resources: bool = True


class CategoryResponse(BaseModel):
    """Schema for category response."""

    id: str
    name: str
    slug: str
    parent_id: Optional[str] = None
    level: int
    path: str
    description: Optional[str] = None
    allow_resources: bool


class ClassifyRequest(BaseModel):
    """Schema for classification request."""

    resource_id: str
    text: str


class UncertaintyResponse(BaseModel):
    """Schema for uncertain predictions response."""

    threshold: float
    count: int
    resource_ids: List[str]
