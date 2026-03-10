"""
Audit and agent trace — immutable, append-only.
Directly mirrors DRA's audit_event and agent_trace design.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from src.core.database import Base


class AuditEvent(Base):
    """Immutable audit log — no updates, no deletes."""
    __tablename__ = "audit_event"

    event_id = Column(BigInteger, primary_key=True, autoincrement=True)
    entity_type = Column(String(100), nullable=False, index=True)
    entity_id = Column(String(255), nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    payload_json = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")


class AgentTrace(Base):
    """
    Structured trace for AI-assisted fraud investigations.
    Records every step of agent reasoning for explainability and safety.
    """
    __tablename__ = "agent_trace"

    trace_id = Column(BigInteger, primary_key=True, autoincrement=True)
    auth_event_id = Column(BigInteger, index=True)
    case_id = Column(BigInteger, index=True)
    step_index = Column(Integer, nullable=False)
    step_type = Column(String(100), nullable=False)
    input_json = Column(JSONB)
    output_json = Column(JSONB)
    model_name = Column(String(100))
    token_usage = Column(JSONB)
    latency_ms = Column(Integer)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")
