"""
/dashboard endpoints — read-only investigator and ops views.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.dashboard.service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/transaction/{auth_event_id}")
async def transaction_detail(
    auth_event_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Full 360-degree view of a transaction."""
    service = DashboardService(db)
    return await service.get_transaction_detail(auth_event_id)


@router.get("/transactions")
async def search_transactions(
    customer_id: Optional[int] = None,
    merchant_id: Optional[int] = None,
    card_id: Optional[int] = None,
    auth_status: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService(db)
    return await service.search_transactions(
        customer_id=customer_id,
        merchant_id=merchant_id,
        card_id=card_id,
        auth_status=auth_status,
        min_amount=min_amount,
        max_amount=max_amount,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )


@router.get("/cases")
async def case_queue(
    queue_name: Optional[str] = None,
    status: str = "open",
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService(db)
    return await service.get_case_queue(queue_name=queue_name, status=status, limit=limit)


@router.get("/cases/summary")
async def queue_summary(
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService(db)
    return await service.get_queue_summary()


@router.get("/models")
async def model_health_dashboard(
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService(db)
    return await service.get_model_health_dashboard()


@router.get("/audit")
async def audit_trail(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService(db)
    return await service.get_audit_trail(
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )


@router.get("/traces/{case_id}")
async def agent_traces(
    case_id: int,
    db: AsyncSession = Depends(get_db),
):
    """View AI agent traces for a case — full explainability chain."""
    service = DashboardService(db)
    return await service.get_agent_traces(case_id)


@router.get("/ops/summary")
async def ops_summary(
    db: AsyncSession = Depends(get_db),
):
    """High-level fraud ops KPIs — leadership dashboard."""
    service = DashboardService(db)
    return await service.get_ops_summary()
