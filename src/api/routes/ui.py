"""
/ui endpoints — Jinja2 HTML dashboard for fraud ops.
Read-only views backed by DashboardService, FraudEconomicsService,
DecisionReplayService, and FraudGraphService.
"""
from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.dashboard.service import DashboardService
from src.services.economics.service import FraudEconomicsService
from src.services.replay.service import DecisionReplayService
from src.services.graph.service import FraudGraphService

_TEMPLATE_DIR = pathlib.Path(__file__).resolve().parents[3] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

router = APIRouter(prefix="/ui", tags=["ui"], default_response_class=HTMLResponse)


@router.get("/")
async def overview(request: Request, db: AsyncSession = Depends(get_db)):
    service = DashboardService(db)
    summary = await service.get_ops_summary()
    models = await service.get_model_health_dashboard()

    recent = await service.search_transactions(limit=10)
    recent_txns = recent.get("transactions", [])

    recent_decisions: list[dict] = []
    for txn in recent_txns:
        detail = await service.get_transaction_detail(txn["auth_event_id"])
        merged = {**txn}
        if detail.get("decision"):
            merged.update(detail["decision"])
        if detail.get("model_scores"):
            merged["risk_band"] = detail["model_scores"][0].get("risk_band")
        recent_decisions.append(merged)

    return templates.TemplateResponse(
        "dashboard/overview.html",
        {
            "request": request,
            "active_page": "overview",
            "summary": summary,
            "models": models,
            "recent_decisions": recent_decisions,
        },
    )


@router.get("/transactions")
async def transactions(
    request: Request,
    customer_id: Optional[int] = None,
    card_id: Optional[int] = None,
    merchant_id: Optional[int] = None,
    auth_status: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    filters = {
        "customer_id": customer_id or "",
        "card_id": card_id or "",
        "merchant_id": merchant_id or "",
        "auth_status": auth_status or "",
        "min_amount": min_amount if min_amount is not None else "",
        "max_amount": max_amount if max_amount is not None else "",
        "start_time": start_time or "",
        "end_time": end_time or "",
    }

    parsed_start = _parse_dt(start_time)
    parsed_end = _parse_dt(end_time)

    has_filter = any([customer_id, card_id, merchant_id, auth_status,
                      min_amount is not None, max_amount is not None,
                      start_time, end_time])

    result = None
    if has_filter:
        service = DashboardService(db)
        result = await service.search_transactions(
            customer_id=customer_id,
            merchant_id=merchant_id,
            card_id=card_id,
            auth_status=auth_status or None,
            min_amount=min_amount,
            max_amount=max_amount,
            start_time=parsed_start,
            end_time=parsed_end,
            limit=limit,
            offset=offset,
        )

    return templates.TemplateResponse(
        "dashboard/transactions.html",
        {
            "request": request,
            "active_page": "transactions",
            "filters": filters,
            "result": result,
        },
    )


@router.get("/transaction/{auth_event_id}")
async def transaction_detail(
    request: Request,
    auth_event_id: int,
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService(db)
    detail = await service.get_transaction_detail(auth_event_id)

    return templates.TemplateResponse(
        "dashboard/transaction_detail.html",
        {
            "request": request,
            "active_page": "transactions",
            "auth_event_id": auth_event_id,
            "detail": detail,
        },
    )


@router.get("/cases")
async def cases(
    request: Request,
    queue_name: Optional[str] = None,
    status: str = "open",
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService(db)
    queue_summary = await service.get_queue_summary()
    case_data = await service.get_case_queue(
        queue_name=queue_name or None,
        status=status,
        limit=limit,
    )

    return templates.TemplateResponse(
        "dashboard/cases.html",
        {
            "request": request,
            "active_page": "cases",
            "queue_summary": queue_summary,
            "cases": case_data,
            "filters": {"queue_name": queue_name or "", "status": status},
        },
    )


@router.get("/models")
async def models(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService(db)
    model_list = await service.get_model_health_dashboard()

    return templates.TemplateResponse(
        "dashboard/models.html",
        {
            "request": request,
            "active_page": "models",
            "models": model_list,
        },
    )


@router.get("/audit")
async def audit(
    request: Request,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService(db)
    events = await service.get_audit_trail(
        entity_type=entity_type or None,
        entity_id=entity_id or None,
        limit=limit,
    )

    return templates.TemplateResponse(
        "dashboard/audit.html",
        {
            "request": request,
            "active_page": "audit",
            "events": events,
            "filters": {"entity_type": entity_type or "", "entity_id": entity_id or ""},
        },
    )


@router.get("/graph")
async def graph_page(
    request: Request,
    node_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    graph_svc = FraudGraphService(db)
    rings: list[dict] = []
    cluster_detail: Optional[dict] = None

    try:
        rings = await graph_svc.find_fraud_rings(min_size=3)
    except Exception:
        pass

    if node_id:
        try:
            cluster_detail = await graph_svc.expand_cluster(node_id, max_hops=3)
        except Exception:
            pass

    return templates.TemplateResponse(
        "dashboard/graph.html",
        {
            "request": request,
            "active_page": "graph",
            "rings": rings,
            "cluster_detail": cluster_detail,
            "search_node": node_id or "",
        },
    )


@router.get("/economics")
async def economics(
    request: Request,
    segment_by: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    econ_svc = FraudEconomicsService(db)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=30)

    economics_data = await econ_svc.compute_economics(start, now)

    thresholds = [i / 100 for i in range(5, 100, 5)]
    threshold_data = await econ_svc.compute_threshold_economics(start, now, thresholds)

    loss_curve = await econ_svc.compute_loss_curve(start, now)

    segments: list[dict] = []
    if segment_by:
        segments = await econ_svc.compute_economics_by_segment(start, now, segment_by)

    return templates.TemplateResponse(
        "dashboard/economics.html",
        {
            "request": request,
            "active_page": "economics",
            "economics": economics_data,
            "segments": segments,
            "threshold_data": threshold_data,
            "loss_curve": loss_curve,
        },
    )


@router.get("/replay")
async def replay_page(
    request: Request,
    auth_event_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    replay_data: Optional[dict] = None
    if auth_event_id:
        svc = DecisionReplayService(db)
        replay_data = await svc.replay_decision(auth_event_id)
        if "error" in replay_data:
            replay_data = {"error": replay_data["error"], "auth_event_id": auth_event_id}

    return templates.TemplateResponse(
        "dashboard/replay.html",
        {
            "request": request,
            "active_page": "replay",
            "replay": replay_data,
            "search_id": auth_event_id,
        },
    )


@router.get("/threshold")
async def threshold_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    econ_svc = FraudEconomicsService(db)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=30)

    thresholds = [i / 100 for i in range(5, 100, 5)]
    threshold_results = await econ_svc.compute_threshold_economics(start, now, thresholds)

    optimal_threshold: Optional[float] = None
    best_savings = float("-inf")
    for t in threshold_results:
        savings = t.get("net_savings", 0) or 0
        if savings > best_savings:
            best_savings = savings
            optimal_threshold = t.get("threshold")

    return templates.TemplateResponse(
        "dashboard/threshold.html",
        {
            "request": request,
            "active_page": "economics",
            "threshold_results": threshold_results,
            "optimal_threshold": optimal_threshold,
        },
    )


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            continue
    return None
