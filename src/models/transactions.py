"""
Transaction and authorization facts: the heart of the fraud platform.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, TIMESTAMP
from src.core.database import Base


class FactAuthorizationEvent(Base):
    __tablename__ = "fact_authorization_event"

    auth_event_id = Column(BigInteger, primary_key=True, autoincrement=True)
    transaction_id = Column(BigInteger, index=True)
    event_time = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    account_id = Column(BigInteger, ForeignKey("dim_account.account_id"), index=True)
    card_id = Column(BigInteger, ForeignKey("dim_card.card_id"), index=True)
    customer_id = Column(BigInteger, ForeignKey("dim_customer.customer_id"), index=True)
    merchant_id = Column(BigInteger, ForeignKey("dim_merchant.merchant_id"), index=True)
    device_id = Column(String(255), ForeignKey("dim_device.device_id"), nullable=True)
    ip_address = Column(INET, nullable=True)
    auth_type = Column(String(50))
    channel = Column(String(30))
    entry_mode = Column(String(30))
    auth_amount = Column(Numeric(18, 2), nullable=False)
    currency_code = Column(String(3))
    merchant_country_code = Column(String(2))
    billing_amount_usd = Column(Numeric(18, 2))
    velocity_bucket = Column(String(50))
    auth_status = Column(String(30), default="pending", index=True)
    decline_reason_code = Column(String(50))
    challenge_type = Column(String(50))
    request_payload_json = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")

    __table_args__ = (
        # Composite index for common query patterns
    )


class FactClearingEvent(Base):
    __tablename__ = "fact_clearing_event"

    clearing_event_id = Column(BigInteger, primary_key=True, autoincrement=True)
    transaction_id = Column(BigInteger, index=True)
    auth_event_id = Column(BigInteger, ForeignKey("fact_authorization_event.auth_event_id"), index=True)
    clearing_time = Column(TIMESTAMP(timezone=True), nullable=False)
    clearing_amount = Column(Numeric(18, 2))
    currency_code = Column(String(3))
    settlement_status = Column(String(30))
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")


class FactTransactionLifecycleEvent(Base):
    """Append-only event stream — the fraud equivalent of DRA's immutable audit_event."""
    __tablename__ = "fact_transaction_lifecycle_event"

    lifecycle_event_id = Column(BigInteger, primary_key=True, autoincrement=True)
    transaction_id = Column(BigInteger, index=True)
    auth_event_id = Column(BigInteger, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    event_time = Column(TIMESTAMP(timezone=True), nullable=False)
    actor_type = Column(String(50))
    actor_id = Column(String(255))
    payload_json = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")
