"""
Point-in-time feature store: online serving features + offline training features.
Separated to prevent leakage and training/serving skew.
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
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from src.core.database import Base


class FactTransactionFeaturesOnline(Base):
    """Features computed at scoring time — frozen point-in-time snapshot."""
    __tablename__ = "fact_transaction_features_online"

    feature_row_id = Column(BigInteger, primary_key=True, autoincrement=True)
    auth_event_id = Column(
        BigInteger,
        ForeignKey("fact_authorization_event.auth_event_id"),
        nullable=False,
        unique=True,
        index=True,
    )
    feature_timestamp = Column(TIMESTAMP(timezone=True), nullable=False)
    feature_version = Column(String(50), nullable=False)

    customer_txn_count_1h = Column(Integer, default=0)
    customer_txn_count_24h = Column(Integer, default=0)
    customer_spend_24h = Column(Numeric(18, 2), default=0)
    card_txn_count_10m = Column(Integer, default=0)
    merchant_txn_count_10m = Column(Integer, default=0)
    merchant_chargeback_rate_30d = Column(Numeric(8, 4), default=0)
    device_txn_count_1d = Column(Integer, default=0)
    device_account_count_30d = Column(Integer, default=0)
    ip_account_count_7d = Column(Integer, default=0)
    ip_card_count_7d = Column(Integer, default=0)
    geo_distance_from_home_km = Column(Numeric(12, 3))
    geo_distance_from_last_txn_km = Column(Numeric(12, 3))
    seconds_since_last_txn = Column(BigInteger)
    amount_vs_customer_p95_ratio = Column(Numeric(12, 4))
    amount_vs_merchant_p95_ratio = Column(Numeric(12, 4))
    proxy_vpn_tor_flag = Column(Boolean, default=False)
    device_risk_score = Column(Numeric(8, 4), default=0)
    behavioral_risk_score = Column(Numeric(8, 4), default=0)
    graph_cluster_risk_score = Column(Numeric(8, 4), default=0)

    feature_json = Column(JSONB)


class FactTransactionFeaturesOffline(Base):
    """Training features regenerated offline — same definitions, warehouse history."""
    __tablename__ = "fact_transaction_features_offline"

    offline_feature_row_id = Column(BigInteger, primary_key=True, autoincrement=True)
    auth_event_id = Column(BigInteger, index=True, nullable=False)
    as_of_time = Column(TIMESTAMP(timezone=True), nullable=False)
    feature_version = Column(String(50), nullable=False)
    label_snapshot_date = Column(Date)
    feature_json = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")
