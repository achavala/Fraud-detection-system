"""
Labels, disputes, and truth management.
Ground truth is delayed and messy — this layer handles the full chargeback lifecycle
and prevents label leakage in training.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from src.core.database import Base


class FactFraudLabel(Base):
    """
    Ground truth table. Labels arrive delayed from multiple sources:
    confirmed_chargeback, customer_report, merchant_report,
    investigator_confirmed, network_alert, synthetic_test_case.
    """
    __tablename__ = "fact_fraud_label"

    label_id = Column(BigInteger, primary_key=True, autoincrement=True)
    auth_event_id = Column(
        BigInteger,
        ForeignKey("fact_authorization_event.auth_event_id"),
        nullable=False,
        index=True,
    )
    transaction_id = Column(BigInteger, index=True)
    label_type = Column(String(50), nullable=False)
    is_fraud = Column(Boolean, nullable=False)
    fraud_category = Column(String(100))
    fraud_subcategory = Column(String(100))
    label_source = Column(String(100), nullable=False)
    source_confidence = Column(Numeric(8, 4), default=1.0)
    event_occurred_at = Column(TIMESTAMP(timezone=True))
    label_received_at = Column(TIMESTAMP(timezone=True), nullable=False)
    effective_label_date = Column(Date, nullable=False, index=True)
    investigator_id = Column(String(255))
    notes = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")


class FactChargebackCase(Base):
    __tablename__ = "fact_chargeback_case"

    chargeback_id = Column(BigInteger, primary_key=True, autoincrement=True)
    transaction_id = Column(BigInteger, index=True)
    auth_event_id = Column(BigInteger, index=True)
    chargeback_reason_code = Column(String(50))
    chargeback_amount = Column(Numeric(18, 2))
    chargeback_received_at = Column(TIMESTAMP(timezone=True), nullable=False)
    representment_flag = Column(Boolean, default=False)
    outcome = Column(String(50))
    outcome_time = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")


class FactLabelSnapshot(Base):
    """
    Training reproducibility: captures label state at a given maturity window.
    Prevents the classic fraud ML mistake of leaking future labels into past training.
    """
    __tablename__ = "fact_label_snapshot"

    snapshot_id = Column(BigInteger, primary_key=True, autoincrement=True)
    auth_event_id = Column(BigInteger, nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    label_status = Column(String(50))
    is_fraud_snapshot = Column(Boolean)
    maturity_days = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")
