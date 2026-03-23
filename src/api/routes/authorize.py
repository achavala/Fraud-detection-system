"""
/authorize endpoints — real-time fraud scoring.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.schemas.transactions import AuthorizationRequest, AuthorizationResponse
from src.services.scoring.service import ScoringService

router = APIRouter(prefix="/authorize", tags=["authorization"])


@router.post("/score", response_model=AuthorizationResponse)
async def score_authorization(
    request: AuthorizationRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Real-time fraud scoring endpoint.
    Receives auth context, computes features, runs rules + ML model,
    and returns decision in milliseconds.
    """
    try:
        service = ScoringService(db)
        return await service.score_authorization(request)
    except (ConnectionError, OSError) as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e!s}")
