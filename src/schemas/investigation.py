from __future__ import annotations

from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class CaseStatus(BaseModel):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    ESCALATED = "escalated"
    RESOLVED_FRAUD = "resolved_fraud"
    RESOLVED_NOT_FRAUD = "resolved_not_fraud"
    CLOSED = "closed"


class FraudCaseCreate(BaseModel):
    auth_event_id: int
    queue_name: str = "general"
    priority: str = "medium"
    assigned_to: Optional[str] = None
    created_reason: str


class FraudCaseResponse(BaseModel):
    case_id: int
    auth_event_id: int
    case_status: str
    queue_name: str
    priority: str
    assigned_to: Optional[str]
    created_reason: str
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime]


class CaseActionCreate(BaseModel):
    case_id: int
    action_type: str
    actor_id: str
    payload: Optional[dict[str, Any]] = None


class CaseActionResponse(BaseModel):
    case_action_id: int
    case_id: int
    action_time: datetime
    action_type: str
    actor_id: str
    payload: Optional[dict[str, Any]]


class CaseReviewRequest(BaseModel):
    case_id: int
    reviewer_id: str
    decision: str
    reason: Optional[str] = None
    notes: Optional[str] = None


class CaseQueueSummary(BaseModel):
    queue_name: str
    open_count: int
    in_progress_count: int
    avg_age_hours: float
    oldest_case_hours: float
