"""
Pattern Learning Engine — API Router

Exposes /api/patterns/learn endpoint that accepts a repository URI,
orchestrates AST parsing and Git history analysis, and returns the
aggregated DeveloperProfile JSON.

Also exposes Phase 6 feedback-loop endpoints:
  POST /api/patterns/propose  — receive rule proposals from local workers
  GET  /api/patterns/rules    — list proposed rules (with optional status filter)
  PATCH /api/patterns/rules/{rule_id} — accept or reject a rule
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.shared.database import get_sync_db
from .schema import (
    CodingProfileCreate,
    CodingProfileResponse,
    LearnRequest,
    LearnResponse,
    ProposeRuleRequest,
    ProposeRuleResponse,
    RuleReviewItem,
)
from .service import learn_patterns, persist_profile

logger = logging.getLogger(__name__)

patterns_router = APIRouter(prefix="/api/patterns", tags=["patterns"])


@patterns_router.post("/learn", response_model=LearnResponse)
async def learn_endpoint(
    request_body: LearnRequest,
    request: Request,
    db: Session = Depends(get_sync_db),
) -> LearnResponse:
    """
    Analyze a repository to build a developer coding profile.

    Accepts a local path or remote Git URL, runs AST parsing and
    Git history analysis, and returns the aggregated JSON profile.
    The profile is persisted to the database for the authenticated user.
    """
    try:
        response = learn_patterns(request_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Persist to database if user is authenticated
    if hasattr(request.state, "user") and request.state.user:
        try:
            user_id = UUID(request.state.user.user_id)
            persist_profile(db, user_id, response)
            logger.info(
                "Profile persisted for user %s, repo %s",
                user_id,
                request_body.repository_uri,
            )
        except Exception as exc:
            logger.warning("Failed to persist profile: %s", exc)
            response.warnings.append(
                "Profile generated but failed to persist to database."
            )

    return response


@patterns_router.get("/profiles", response_model=list)
async def list_profiles(
    request: Request,
    db: Session = Depends(get_sync_db),
) -> list:
    """List all developer profiles for the authenticated user."""
    from .model import DeveloperProfileRecord

    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = UUID(request.state.user.user_id)
    records = (
        db.query(DeveloperProfileRecord)
        .filter(DeveloperProfileRecord.user_id == user_id)
        .order_by(DeveloperProfileRecord.updated_at.desc())
        .all()
    )

    return [
        {
            "id": str(r.id),
            "repository_url": r.repository_url,
            "repository_name": r.repository_name,
            "total_files_analyzed": r.total_files_analyzed,
            "total_commits_analyzed": r.total_commits_analyzed,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in records
    ]


# ============================================================================
# Coding Profiles (Master Programmer Personalities)
# NOTE: These must be registered BEFORE /profiles/{profile_id} to avoid
#       the path parameter catching "coding" as an ID.
# ============================================================================


@patterns_router.get(
    "/profiles/coding",
    response_model=list[CodingProfileResponse],
    summary="List all coding profiles for Ronin's personality selector",
)
async def list_coding_profiles(
    db: Session = Depends(get_sync_db),
) -> list[CodingProfileResponse]:
    """
    Return all available CodingProfile records so Ronin can render a
    personality selection UI.  No authentication required — profiles are
    public, curated knowledge.
    """
    from app.database.models import CodingProfile

    records = (
        db.query(CodingProfile)
        .order_by(CodingProfile.name)
        .all()
    )

    return [
        CodingProfileResponse(
            id=r.id,
            name=r.name,
            description=r.description,
            best_suited_for=r.best_suited_for or {},
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in records
    ]


@patterns_router.post(
    "/profiles/coding",
    response_model=CodingProfileResponse,
    status_code=201,
    summary="Create or update a coding profile",
)
async def create_coding_profile(
    body: CodingProfileCreate,
    db: Session = Depends(get_sync_db),
) -> CodingProfileResponse:
    """
    Create a new CodingProfile or update an existing one (upsert by id).

    Called by the local extraction worker after analyzing a master repository.
    """
    from app.database.models import CodingProfile

    existing = db.query(CodingProfile).filter(CodingProfile.id == body.id).first()

    if existing:
        existing.name = body.name
        existing.description = body.description
        existing.best_suited_for = body.best_suited_for
        db.commit()
        db.refresh(existing)
        record = existing
    else:
        record = CodingProfile(
            id=body.id,
            name=body.name,
            description=body.description,
            best_suited_for=body.best_suited_for,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    logger.info("CodingProfile upserted: %s (%s)", record.name, record.id)

    return CodingProfileResponse(
        id=record.id,
        name=record.name,
        description=record.description,
        best_suited_for=record.best_suited_for or {},
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@patterns_router.get("/profiles/{profile_id}")
async def get_profile(
    profile_id: str,
    request: Request,
    db: Session = Depends(get_sync_db),
) -> dict:
    """Retrieve a specific developer profile by ID."""
    from .model import DeveloperProfileRecord

    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = UUID(request.state.user.user_id)
    record = (
        db.query(DeveloperProfileRecord)
        .filter(
            DeveloperProfileRecord.id == profile_id,
            DeveloperProfileRecord.user_id == user_id,
        )
        .first()
    )

    if not record:
        raise HTTPException(status_code=404, detail="Profile not found")

    return record.profile_data


# ============================================================================
# Phase 6: Feedback Loop — Rule Proposal & Triage
# ============================================================================


@patterns_router.post("/propose", response_model=ProposeRuleResponse)
async def propose_rule(
    body: ProposeRuleRequest,
    db: Session = Depends(get_sync_db),
) -> ProposeRuleResponse:
    """
    Receive a rule proposal from the local extraction worker.

    The worker posts a diff + LLM-extracted JSON schema here after
    consuming a job from the ``pharos_extraction_jobs`` Redis queue.
    The rule is persisted with status=PENDING_REVIEW for human triage.
    """
    from app.database.models import ProposedRule

    rule = ProposedRule(
        repository=body.repository,
        commit_sha=body.commit_sha,
        file_path=body.file_path,
        diff_payload=body.diff_payload,
        rule_name=body.rule_name,
        rule_description=body.rule_description,
        rule_schema=body.rule_schema,
        confidence=body.confidence,
        profile_id=body.profile_id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    logger.info("Proposed rule stored: %s (id=%s)", rule.rule_name, rule.id)

    return ProposeRuleResponse(
        id=str(rule.id),
        status=rule.status,
        message="Rule proposal accepted for review.",
    )


@patterns_router.get("/rules", response_model=list[RuleReviewItem])
async def list_rules(
    status: Optional[str] = Query(None, description="Filter by status: PENDING_REVIEW, ACTIVE, REJECTED"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_sync_db),
) -> list[RuleReviewItem]:
    """List proposed rules, optionally filtered by status."""
    from app.database.models import ProposedRule

    query = db.query(ProposedRule)
    if status:
        query = query.filter(ProposedRule.status == status)
    query = query.order_by(ProposedRule.created_at.desc()).limit(limit)

    return [
        RuleReviewItem(
            id=str(r.id),
            repository=r.repository,
            commit_sha=r.commit_sha,
            file_path=r.file_path,
            diff_payload=r.diff_payload,
            rule_name=r.rule_name,
            rule_description=r.rule_description,
            rule_schema=r.rule_schema,
            confidence=r.confidence,
            status=r.status,
            created_at=r.created_at,
        )
        for r in query.all()
    ]


@patterns_router.patch("/rules/{rule_id}")
async def update_rule_status(
    rule_id: str,
    action: str = Query(..., description="'accept' or 'reject'"),
    db: Session = Depends(get_sync_db),
) -> dict:
    """Accept or reject a proposed rule."""
    from app.database.models import ProposedRule, RuleStatus

    rule = db.query(ProposedRule).filter(ProposedRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    if action == "accept":
        rule.status = RuleStatus.ACTIVE.value
    elif action == "reject":
        rule.status = RuleStatus.REJECTED.value
    else:
        raise HTTPException(status_code=400, detail="action must be 'accept' or 'reject'")

    rule.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    return {"id": str(rule.id), "status": rule.status}
