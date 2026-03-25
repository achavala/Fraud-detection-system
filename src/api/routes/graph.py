"""
/graph endpoints — fraud ring detection and graph intelligence.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import require_role
from src.core.database import get_db
from src.services.graph.service import FraudGraphService
from src.schemas.graph import GraphRiskRequest, GraphNodeCreate, GraphEdgeCreate

router = APIRouter(prefix="/graph", tags=["graph"])


@router.post("/risk")
async def compute_graph_risk(
    request: GraphRiskRequest,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_role("admin", "model_risk", "investigator")),
):
    """Compute fraud graph risk for an authorization."""
    service = FraudGraphService(db)
    score = await service.compute_graph_risk(
        auth_event_id=request.auth_event_id,
        account_id=request.account_id,
        device_id=request.device_id,
        ip_address=request.ip_address,
        max_hops=request.max_hops,
    )
    return {
        "auth_event_id": score.auth_event_id,
        "cluster_id": score.cluster_id,
        "cluster_size": score.cluster_size,
        "risky_neighbor_count": score.risky_neighbor_count,
        "hop2_risk_score": float(score.hop2_risk_score),
        "synthetic_identity_flag": score.synthetic_identity_flag,
        "mule_pattern_flag": score.mule_pattern_flag,
    }


@router.get("/rings")
async def detect_fraud_rings(
    min_size: int = 3,
    db: AsyncSession = Depends(get_db),
):
    """Detect fraud rings across the entity graph."""
    service = FraudGraphService(db)
    return await service.find_fraud_rings(min_size=min_size)


@router.get("/expand/{node_id}")
async def expand_cluster(
    node_id: str,
    max_hops: int = 3,
    db: AsyncSession = Depends(get_db),
):
    """Expand a graph node's cluster — for investigator use."""
    service = FraudGraphService(db)
    return await service.expand_cluster(node_id, max_hops=max_hops)


@router.post("/node")
async def add_node(
    request: GraphNodeCreate,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_role("admin")),
):
    service = FraudGraphService(db)
    await service._upsert_node(
        request.node_id, request.node_type, request.entity_ref,
        __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    await db.flush()
    return {"status": "ok", "node_id": request.node_id}


@router.post("/edge")
async def add_edge(
    request: GraphEdgeCreate,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_role("admin")),
):
    service = FraudGraphService(db)
    await service._upsert_edge(
        request.src_node_id, request.dst_node_id, request.edge_type,
        __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    await db.flush()
    return {"status": "ok", "edge": f"{request.src_node_id} -> {request.dst_node_id}"}
