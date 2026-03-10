from __future__ import annotations

from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime, date
from decimal import Decimal


class OnlineFeaturesResponse(BaseModel):
    auth_event_id: int
    feature_version: str
    feature_timestamp: datetime
    customer_txn_count_1h: int = 0
    customer_txn_count_24h: int = 0
    customer_spend_24h: Decimal = Decimal("0")
    card_txn_count_10m: int = 0
    merchant_txn_count_10m: int = 0
    merchant_chargeback_rate_30d: float = 0.0
    device_txn_count_1d: int = 0
    device_account_count_30d: int = 0
    ip_account_count_7d: int = 0
    ip_card_count_7d: int = 0
    geo_distance_from_home_km: Optional[float] = None
    geo_distance_from_last_txn_km: Optional[float] = None
    seconds_since_last_txn: Optional[int] = None
    amount_vs_customer_p95_ratio: Optional[float] = None
    amount_vs_merchant_p95_ratio: Optional[float] = None
    proxy_vpn_tor_flag: bool = False
    device_risk_score: float = 0.0
    behavioral_risk_score: float = 0.0
    graph_cluster_risk_score: float = 0.0


class FeatureRequest(BaseModel):
    auth_event_id: int
    account_id: int
    card_id: int
    customer_id: int
    merchant_id: int
    device_id: Optional[str] = None
    ip_address: Optional[str] = None
    auth_amount: Decimal
    event_time: datetime


class OfflineFeaturesRequest(BaseModel):
    auth_event_id: int
    as_of_time: datetime
    feature_version: str
    label_snapshot_date: Optional[date] = None


class FeatureVector(BaseModel):
    """Flattened feature vector for model scoring."""
    features: dict[str, Any]
    version: str
    timestamp: datetime
