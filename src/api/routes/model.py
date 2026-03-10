"""
/model endpoints — model governance, evaluation, drift, and experiments.
"""
from __future__ import annotations

from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.governance.service import ModelGovernanceService
from src.schemas.governance import (
    ModelEvalRequest,
    ExperimentCreate,
    ApprovalRequest,
)
from src.schemas.scoring import ModelRegistryEntry

router = APIRouter(prefix="/model", tags=["model governance"])


@router.post("/register")
async def register_model(
    entry: ModelRegistryEntry,
    db: AsyncSession = Depends(get_db),
):
    service = ModelGovernanceService(db)
    model = await service.register_model(
        model_version=entry.model_version,
        model_family=entry.model_family,
        model_type=entry.model_type,
        feature_version=entry.feature_version,
        threshold_decline=entry.threshold_decline,
        threshold_review=entry.threshold_review,
        threshold_stepup=entry.threshold_stepup,
        owner=entry.owner,
        training_data_start=entry.training_data_start,
        training_data_end=entry.training_data_end,
    )
    return {"model_version": model.model_version, "status": model.deployment_status}


@router.post("/promote")
async def promote_model(
    model_version: str,
    approved_by: str,
    reason: str,
    db: AsyncSession = Depends(get_db),
):
    """Approval-gated model promotion — requires explicit sign-off."""
    service = ModelGovernanceService(db)
    try:
        model = await service.promote_model(model_version, approved_by, reason)
        return {"model_version": model.model_version, "status": model.deployment_status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/evaluate")
async def evaluate_model(
    request: ModelEvalRequest,
    db: AsyncSession = Depends(get_db),
):
    service = ModelGovernanceService(db)
    result = await service.evaluate_model(
        model_version=request.model_version,
        eval_window_start=request.eval_window_start,
        eval_window_end=request.eval_window_end,
        segment_name=request.segment_name,
        population_name=request.population_name,
    )
    return {
        "eval_id": result.eval_id,
        "model_version": result.model_version,
        "auc_roc": float(result.auc_roc) if result.auc_roc else None,
        "auc_pr": float(result.auc_pr) if result.auc_pr else None,
    }


@router.post("/experiment")
async def create_experiment(
    request: ExperimentCreate,
    db: AsyncSession = Depends(get_db),
):
    service = ModelGovernanceService(db)
    exp = await service.create_experiment(
        challenger_version=request.challenger_model_version,
        champion_version=request.champion_model_version,
        mode=request.mode,
        traffic_pct=request.traffic_pct,
    )
    return {"experiment_id": exp.experiment_id, "mode": exp.mode}


@router.get("/health/{model_version}")
async def model_health(
    model_version: str,
    db: AsyncSession = Depends(get_db),
):
    service = ModelGovernanceService(db)
    return await service.get_model_health(model_version)
