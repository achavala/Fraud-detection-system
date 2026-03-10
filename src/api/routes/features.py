"""
/features endpoints — feature retrieval and offline feature generation.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.features.service import FeatureService
from src.schemas.features import FeatureRequest, OfflineFeaturesRequest

router = APIRouter(prefix="/features", tags=["features"])


@router.get("/get/{auth_event_id}")
async def get_features(
    auth_event_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve stored online features for a given authorization."""
    service = FeatureService(db)
    features = await service.get_online_features(auth_event_id)
    if not features:
        raise HTTPException(status_code=404, detail="Features not found")
    return service.to_scoring_vector(features)


@router.post("/compute")
async def compute_features(
    request: FeatureRequest,
    db: AsyncSession = Depends(get_db),
):
    """Compute and store online features for an authorization."""
    service = FeatureService(db)
    features = await service.compute_online_features(
        auth_event_id=request.auth_event_id,
        account_id=request.account_id,
        card_id=request.card_id,
        customer_id=request.customer_id,
        merchant_id=request.merchant_id,
        auth_amount=request.auth_amount,
        event_time=request.event_time,
        device_id=request.device_id,
        ip_address=request.ip_address,
    )
    return service.to_scoring_vector(features)


@router.post("/offline/build")
async def build_offline_features(
    request: OfflineFeaturesRequest,
    db: AsyncSession = Depends(get_db),
):
    """Build offline features for training — uses same definitions, no leakage."""
    service = FeatureService(db)
    result = await service.build_offline_features(
        auth_event_id=request.auth_event_id,
        as_of_time=request.as_of_time,
        feature_version=request.feature_version,
        label_snapshot_date=request.label_snapshot_date,
    )
    return {"offline_feature_row_id": result.offline_feature_row_id, "feature_version": result.feature_version}
