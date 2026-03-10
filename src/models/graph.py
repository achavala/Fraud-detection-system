"""
Graph / fraud ring layer: entity nodes, edges, and cluster scores.
Adapts DRA's networkx blast-radius into fraud-neighbor spread
and suspicious cluster expansion.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from src.core.database import Base


class GraphEntityNode(Base):
    __tablename__ = "graph_entity_node"

    node_id = Column(String(255), primary_key=True)
    node_type = Column(String(50), nullable=False, index=True)
    entity_ref = Column(String(255), index=True)
    first_seen_at = Column(TIMESTAMP(timezone=True), server_default="now()")
    last_seen_at = Column(TIMESTAMP(timezone=True), server_default="now()")
    risk_score = Column(Numeric(8, 4), default=0)
    attributes_json = Column(JSONB)


class GraphEntityEdge(Base):
    __tablename__ = "graph_entity_edge"

    edge_id = Column(BigInteger, primary_key=True, autoincrement=True)
    src_node_id = Column(String(255), nullable=False, index=True)
    dst_node_id = Column(String(255), nullable=False, index=True)
    edge_type = Column(String(100), nullable=False, index=True)
    weight = Column(Numeric(12, 4), default=1.0)
    first_seen_at = Column(TIMESTAMP(timezone=True), server_default="now()")
    last_seen_at = Column(TIMESTAMP(timezone=True), server_default="now()")
    attributes_json = Column(JSONB)


class FactGraphClusterScore(Base):
    __tablename__ = "fact_graph_cluster_score"

    cluster_score_id = Column(BigInteger, primary_key=True, autoincrement=True)
    auth_event_id = Column(BigInteger, nullable=False, index=True)
    cluster_id = Column(String(255), index=True)
    cluster_size = Column(Integer)
    risky_neighbor_count = Column(Integer, default=0)
    hop2_risk_score = Column(Numeric(8, 4), default=0)
    synthetic_identity_flag = Column(Boolean, default=False)
    mule_pattern_flag = Column(Boolean, default=False)
    score_time = Column(TIMESTAMP(timezone=True), nullable=False)
