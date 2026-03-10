from __future__ import annotations

from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class GraphNodeCreate(BaseModel):
    node_id: str
    node_type: str
    entity_ref: str
    risk_score: float = 0.0
    attributes: Optional[dict[str, Any]] = None


class GraphEdgeCreate(BaseModel):
    src_node_id: str
    dst_node_id: str
    edge_type: str
    weight: float = 1.0
    attributes: Optional[dict[str, Any]] = None


class GraphRiskRequest(BaseModel):
    auth_event_id: int
    account_id: int
    device_id: Optional[str] = None
    ip_address: Optional[str] = None
    email: Optional[str] = None
    max_hops: int = 2


class GraphRiskResponse(BaseModel):
    auth_event_id: int
    cluster_id: Optional[str]
    cluster_size: int
    risky_neighbor_count: int
    hop2_risk_score: float
    synthetic_identity_flag: bool
    mule_pattern_flag: bool
    connected_nodes: list[dict[str, Any]]
    risk_paths: list[list[str]]


class ClusterAnalysis(BaseModel):
    cluster_id: str
    node_count: int
    edge_count: int
    fraud_node_pct: float
    high_risk_nodes: list[str]
    expansion_candidates: list[str]
    pattern_type: Optional[str]
