"""
Investigation and operations: fraud cases and investigator actions.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from src.core.database import Base


class FactFraudCase(Base):
    __tablename__ = "fact_fraud_case"

    case_id = Column(BigInteger, primary_key=True, autoincrement=True)
    auth_event_id = Column(
        BigInteger,
        ForeignKey("fact_authorization_event.auth_event_id"),
        nullable=False,
        index=True,
    )
    case_status = Column(String(50), default="open", index=True)
    queue_name = Column(String(100), index=True)
    priority = Column(String(20), default="medium")
    assigned_to = Column(String(255))
    created_reason = Column(String(200))
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")
    updated_at = Column(TIMESTAMP(timezone=True), server_default="now()")
    closed_at = Column(TIMESTAMP(timezone=True))


class FactCaseAction(Base):
    """Append-only investigator actions — immutable audit of all case activity."""
    __tablename__ = "fact_case_action"

    case_action_id = Column(BigInteger, primary_key=True, autoincrement=True)
    case_id = Column(
        BigInteger,
        ForeignKey("fact_fraud_case.case_id"),
        nullable=False,
        index=True,
    )
    action_time = Column(TIMESTAMP(timezone=True), nullable=False)
    action_type = Column(String(100), nullable=False)
    actor_id = Column(String(255), nullable=False)
    payload_json = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")
