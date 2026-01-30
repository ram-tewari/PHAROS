"""
Planning Module API Router
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.shared.database import get_db
from app.modules.planning.service import MultiHopAgent, ArchitectureParser
from app.modules.planning.schema import (
    GeneratePlanRequest,
    RefinePlanRequest,
    PlanningResult,
    ArchitectureParseResult,
)
from app.modules.planning.model import PlanningSession

router = APIRouter(prefix="/planning", tags=["planning"])


@router.post("/generate", response_model=PlanningResult)
async def generate_plan(
    request: GeneratePlanRequest,
    db: Session = Depends(get_db)
):
    """
    Generate a multi-step implementation plan for a task.
    
    Args:
        request: Plan generation request with task description and context
        db: Database session
        
    Returns:
        PlanningResult with steps and dependencies
    """
    agent = MultiHopAgent(db=db)
    result = await agent.generate_plan(
        task_description=request.task_description,
        context=request.context
    )
    return result


@router.put("/{plan_id}/refine", response_model=PlanningResult)
async def refine_plan(
    plan_id: str,
    request: RefinePlanRequest,
    db: Session = Depends(get_db)
):
    """
    Refine an existing plan based on user feedback.
    
    Args:
        plan_id: ID of the plan to refine
        request: Refinement request with feedback
        db: Database session
        
    Returns:
        Updated PlanningResult
    """
    agent = MultiHopAgent(db=db)
    try:
        result = await agent.refine_plan(
            plan_id=plan_id,
            feedback=request.feedback
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{plan_id}", response_model=PlanningResult)
async def get_plan(
    plan_id: str,
    db: Session = Depends(get_db)
):
    """
    Retrieve an existing planning session.
    
    Args:
        plan_id: ID of the plan to retrieve
        db: Database session
        
    Returns:
        PlanningResult with current plan state
    """
    session = db.query(PlanningSession).filter(
        PlanningSession.id == plan_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail=f"Planning session {plan_id} not found")
    
    from app.modules.planning.schema import PlanningStep
    
    steps = [PlanningStep(**step) for step in session.steps]
    
    return PlanningResult(
        plan_id=session.id,
        steps=steps,
        dependencies=session.dependencies,
        estimated_duration="2-3 days",
        context_preserved=session.context
    )


@router.post("/parse-architecture", response_model=ArchitectureParseResult)
async def parse_architecture(
    resource_id: int,
    db: Session = Depends(get_db)
):
    """
    Parse an architecture document to extract components, relationships, and patterns.
    
    Args:
        resource_id: ID of the resource containing the architecture document
        db: Database session
        
    Returns:
        ArchitectureParseResult with extracted information
    """
    parser = ArchitectureParser(db=db)
    result = await parser.parse_architecture_doc(resource_id=resource_id)
    return result
