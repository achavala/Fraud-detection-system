"""
/case endpoints — fraud case management and investigator workflows.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import require_role
from src.core.database import get_db
from src.models.investigation import FactFraudCase, FactCaseAction
from src.models.audit import AuditEvent
from src.schemas.investigation import (
    FraudCaseCreate,
    FraudCaseResponse,
    CaseActionCreate,
    CaseReviewRequest,
)
from src.services.copilot.service import InvestigatorCopilot

router = APIRouter(prefix="/case", tags=["cases"])


@router.post("/create", response_model=FraudCaseResponse)
async def create_case(
    request: FraudCaseCreate,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_role("admin", "investigator")),
):
    case = FactFraudCase(
        auth_event_id=request.auth_event_id,
        queue_name=request.queue_name,
        priority=request.priority,
        assigned_to=request.assigned_to,
        created_reason=request.created_reason,
    )
    db.add(case)

    db.add(AuditEvent(
        entity_type="case",
        entity_id="pending",
        event_type="case_created",
        payload_json={"auth_event_id": request.auth_event_id, "reason": request.created_reason},
    ))

    await db.flush()
    return FraudCaseResponse(
        case_id=case.case_id,
        auth_event_id=case.auth_event_id,
        case_status=case.case_status,
        queue_name=case.queue_name,
        priority=case.priority,
        assigned_to=case.assigned_to,
        created_reason=case.created_reason,
        created_at=case.created_at or datetime.now(timezone.utc),
        updated_at=case.updated_at or datetime.now(timezone.utc),
        closed_at=case.closed_at,
    )


@router.post("/review")
async def review_case(
    request: CaseReviewRequest,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_role("admin", "investigator")),
):
    result = await db.execute(
        select(FactFraudCase).where(FactFraudCase.case_id == request.case_id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    now = datetime.now(timezone.utc)
    case.case_status = request.decision
    case.updated_at = now
    if request.decision in ("resolved_fraud", "resolved_not_fraud", "closed"):
        case.closed_at = now

    action = FactCaseAction(
        case_id=request.case_id,
        action_time=now,
        action_type=f"review_{request.decision}",
        actor_id=request.reviewer_id,
        payload_json={"reason": request.reason, "notes": request.notes},
    )
    db.add(action)

    db.add(AuditEvent(
        entity_type="case",
        entity_id=str(request.case_id),
        event_type="case_reviewed",
        payload_json={
            "reviewer": request.reviewer_id,
            "decision": request.decision,
        },
    ))

    await db.flush()
    return {"case_id": request.case_id, "status": request.decision, "reviewer": request.reviewer_id}


@router.get("/{case_id}/investigate")
async def investigate_case(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_role("admin", "investigator")),
):
    """AI-assisted case investigation with full agent trace."""
    copilot = InvestigatorCopilot(db)
    return await copilot.investigate_case(case_id)


@router.get("/{case_id}/recommend")
async def recommend_action(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_role("admin", "investigator")),
):
    copilot = InvestigatorCopilot(db)
    return await copilot.recommend_action(case_id)
