"""
Planning Module Pydantic Schemas
"""

from typing import List, Dict, Any, Tuple
from pydantic import BaseModel, Field


class PlanningStep(BaseModel):
    """Individual step in a multi-hop plan"""

    step_id: int
    description: str
    action_type: str = Field(
        ..., description="Type: 'code', 'test', 'document', 'review'"
    )
    required_context: List[str] = Field(default_factory=list)
    success_criteria: str


class PlanningResult(BaseModel):
    """Result of plan generation or refinement"""

    plan_id: str
    steps: List[PlanningStep]
    dependencies: List[Tuple[int, int]] = Field(
        default_factory=list, description="List of (step_id, depends_on_step_id) tuples"
    )
    estimated_duration: str
    context_preserved: Dict[str, Any] = Field(default_factory=dict)


class GeneratePlanRequest(BaseModel):
    """Request to generate a new plan"""

    task_description: str
    context: Dict[str, Any] = Field(default_factory=dict)


class RefinePlanRequest(BaseModel):
    """Request to refine an existing plan"""

    feedback: str


class Component(BaseModel):
    """Architectural component"""

    name: str
    description: str
    responsibilities: List[str] = Field(default_factory=list)
    interfaces: List[str] = Field(default_factory=list)


class Relationship(BaseModel):
    """Relationship between components"""

    source: str
    target: str
    relationship_type: str = Field(
        ..., description="Type: 'depends_on', 'implements', 'extends'"
    )
    description: str


class DesignPattern(BaseModel):
    """Identified design pattern"""

    pattern_name: str
    pattern_type: str = Field(
        ..., description="Type: 'creational', 'structural', 'behavioral'"
    )
    components_involved: List[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)


class ArchitectureGap(BaseModel):
    """Gap between documented and implemented architecture"""

    gap_type: str = Field(
        ..., description="Type: 'missing_component', 'undocumented_relationship'"
    )
    description: str
    severity: str = Field(..., description="Severity: 'low', 'medium', 'high'")


class ArchitectureParseResult(BaseModel):
    """Result of architecture document parsing"""

    components: List[Component] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    patterns: List[DesignPattern] = Field(default_factory=list)
    gaps: List[ArchitectureGap] = Field(default_factory=list)


class CodePattern(BaseModel):
    """Identified code pattern"""

    pattern_type: str = Field(
        ..., description="Type: 'error_handling', 'testing', 'documentation'"
    )
    pattern_name: str
    examples: List[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)


class ReusableComponent(BaseModel):
    """Reusable component extracted from repository"""

    component_name: str
    file_path: str
    interface: str
    usage_examples: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)


class BestPracticesResult(BaseModel):
    """Result of best practices detection"""

    patterns: List[CodePattern] = Field(default_factory=list)
    quality_indicators: Dict[str, float] = Field(default_factory=dict)
    recommendations: List[str] = Field(default_factory=list)
