"""
/ops endpoints — observability and metrics dashboard.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.middleware.auth import require_role
from src.services.observability.metrics import PlatformMetrics

router = APIRouter(prefix="/ops", tags=["observability"])
_metrics = PlatformMetrics()


@router.get("/metrics")
async def full_metrics_dashboard():
    """Full metrics dashboard."""
    return _metrics.get_full_dashboard()


@router.get("/metrics/scoring")
async def scoring_metrics():
    """Scoring metrics only."""
    return _metrics.get_scoring_metrics()


@router.get("/metrics/decisions")
async def decision_metrics():
    """Decision distribution."""
    return _metrics.get_decision_distribution()


@router.get("/metrics/rules")
async def rule_metrics():
    """Rule fire rates."""
    return _metrics.get_rule_fire_rates()


@router.get("/metrics/parity")
async def parity_metrics():
    """Parity metrics."""
    return _metrics.get_parity_metrics()


@router.get("/metrics/api")
async def api_metrics():
    """API metrics."""
    return _metrics.get_api_metrics()


@router.post("/metrics/reset")
async def reset_metrics(
    _auth: dict = Depends(require_role("admin")),
):
    """Reset all metrics (admin only)."""
    _metrics.reset()
    return {"status": "ok", "message": "All metrics reset"}
