"""
/dashboard endpoints — read-only investigator and ops views.

Supports two pagination modes:
- **Offset**: ``?offset=N&limit=M`` — simple, good for small datasets
- **Cursor**: ``?cursor=<opaque>&limit=M`` — stable under concurrent writes,
  preferred for large result sets. The cursor is the last ``auth_event_id``
  or ``case_id`` from the previous page (base64-encoded).
"""
import base64
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.dashboard.service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _encode_cursor(value: int | str) -> str:
    return base64.urlsafe_b64encode(str(value).encode()).decode()


def _decode_cursor(cursor: str | None) -> int | None:
    if not cursor:
        return None
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, Exception):
        return None


def _paginated_response(
    items: list,
    limit: int,
    id_field: str = "auth_event_id",
) -> dict:
    """Wrap result list with pagination metadata."""
    next_cursor = None
    has_more = len(items) == limit
    if has_more and items:
        last_item = items[-1]
        last_id = last_item.get(id_field) if isinstance(last_item, dict) else getattr(last_item, id_field, None)
        if last_id is not None:
            next_cursor = _encode_cursor(last_id)
    return {
        "items": items,
        "count": len(items),
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


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
    cursor: Optional[str] = Query(default=None, description="Opaque cursor from previous page"),
    db: AsyncSession = Depends(get_db),
):
    after_id = _decode_cursor(cursor)
    service = DashboardService(db)
    result = await service.search_transactions(
        customer_id=customer_id,
        merchant_id=merchant_id,
        card_id=card_id,
        auth_status=auth_status,
        min_amount=min_amount,
        max_amount=max_amount,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset if after_id is None else 0,
        after_id=after_id,
    )
    if isinstance(result, dict) and "results" in result:
        return _paginated_response(result["results"], limit, "auth_event_id")
    return result


@router.get("/cases")
async def case_queue(
    queue_name: Optional[str] = None,
    status: str = "open",
    limit: int = Query(default=50, le=200),
    cursor: Optional[str] = Query(default=None, description="Opaque cursor from previous page"),
    db: AsyncSession = Depends(get_db),
):
    after_id = _decode_cursor(cursor)
    service = DashboardService(db)
    result = await service.get_case_queue(
        queue_name=queue_name,
        status=status,
        limit=limit,
        after_id=after_id,
    )
    if isinstance(result, dict) and "cases" in result:
        return _paginated_response(result["cases"], limit, "case_id")
    return result


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
    cursor: Optional[str] = Query(default=None, description="Opaque cursor from previous page"),
    db: AsyncSession = Depends(get_db),
):
    after_id = _decode_cursor(cursor)
    service = DashboardService(db)
    result = await service.get_audit_trail(
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        after_id=after_id,
    )
    if isinstance(result, dict) and "events" in result:
        return _paginated_response(result["events"], limit, "event_id")
    return result


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
