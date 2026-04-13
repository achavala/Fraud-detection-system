"""
/economics endpoints — fraud business decision metrics.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import require_role
from src.core.database import get_db
from src.services.economics.service import FraudEconomicsService

router = APIRouter(prefix="/economics", tags=["economics"])


class ThresholdRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    thresholds: list[float]


@router.get("/summary")
async def economics_summary(
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    segment_name: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    svc = FraudEconomicsService(db)
    return await svc.compute_economics(start_time, end_time, segment_name)


@router.get("/by-segment")
async def economics_by_segment(
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    segment_by: str = Query(..., description="merchant_country_code|channel|auth_type|mcc|risk_band"),
    db: AsyncSession = Depends(get_db),
):
    svc = FraudEconomicsService(db)
    return await svc.compute_economics_by_segment(start_time, end_time, segment_by)


@router.post("/threshold-sweep")
async def threshold_sweep(
    request: ThresholdRequest,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_role("admin", "model_risk")),
):
    svc = FraudEconomicsService(db)
    return await svc.compute_threshold_economics(
        request.start_time, request.end_time, request.thresholds
    )


@router.get("/loss-curve")
async def loss_curve(
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
):
    svc = FraudEconomicsService(db)
    return await svc.compute_loss_curve(start_time, end_time)
