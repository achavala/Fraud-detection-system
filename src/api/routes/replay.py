"""
Replay and feature parity API routes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.features.parity import FeatureParityValidator
from src.services.replay.service import DecisionReplayService


# --- Schemas for request bodies ---
class CompareReplayRequest(BaseModel):
    auth_event_id: int
    model_version: str
    thresholds: dict[str, float] | None = None


class BatchReplayRequest(BaseModel):
    auth_event_ids: list[int]
    model_version: str


# --- Replay routes ---
replay_router = APIRouter(prefix="/replay", tags=["replay"])


@replay_router.post("/decision/{auth_event_id}")
async def replay_decision(
    auth_event_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Full decision replay — reconstruct exact decision as-of transaction time."""
    service = DecisionReplayService(db)
    result = await service.replay_decision(auth_event_id)
    if "error" in result and "auth_event_not_found" in result.get("error", ""):
        raise HTTPException(status_code=404, detail=result.get("error", "Not found"))
    return result


@replay_router.post("/compare")
async def compare_replay(
    request: CompareReplayRequest,
    db: AsyncSession = Depends(get_db),
):
    """What-if comparison: re-score with different model/thresholds, compare to actual."""
    service = DecisionReplayService(db)
    result = await service.compare_replay(
        auth_event_id=request.auth_event_id,
        new_model_version=request.model_version,
        new_thresholds=request.thresholds or {},
    )
    if "error" in result and "auth_event_not_found" in result.get("error", ""):
        raise HTTPException(status_code=404, detail=result.get("error", "Not found"))
    return result


@replay_router.post("/batch")
async def batch_replay(
    request: BatchReplayRequest,
    db: AsyncSession = Depends(get_db),
):
    """Batch replay for backtesting — replay many decisions with specified model."""
    service = DecisionReplayService(db)
    return await service.batch_replay(
        auth_event_ids=request.auth_event_ids,
        model_version=request.model_version,
    )


# --- Feature parity routes (under /features) ---
parity_router = APIRouter(prefix="/features", tags=["features-parity"])


@parity_router.get("/parity/report")
async def feature_parity_report(
    sample_size: int = Query(1000, ge=1, le=10000),
    tolerance: float = Query(0.01, ge=0, le=1),
    db: AsyncSession = Depends(get_db),
):
    """Full parity report — sample-based validation with per-feature statistics."""
    validator = FeatureParityValidator(db)
    return await validator.generate_parity_report(sample_size, tolerance)


@parity_router.get("/parity/{auth_event_id}")
async def feature_parity_single(
    auth_event_id: int,
    tolerance: float = Query(0.01, ge=0, le=1),
    db: AsyncSession = Depends(get_db),
):
    """Single feature parity check — compare online vs offline features."""
    validator = FeatureParityValidator(db)
    return await validator.validate_single(auth_event_id, tolerance)


@parity_router.get("/registry")
async def feature_registry(db: AsyncSession = Depends(get_db)):
    """Feature contract/registry — 19 features, types, ranges, schema checksum."""
    validator = FeatureParityValidator(db)
    return validator.get_feature_registry()
