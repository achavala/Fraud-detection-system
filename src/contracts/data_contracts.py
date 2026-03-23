"""
Strict data contracts for all system interfaces.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError


# -----------------------------------------------------------------------------
# AuthEventContract
# -----------------------------------------------------------------------------


class AuthEventContract(BaseModel):
    """Strict schema for auth event payload."""

    transaction_id: int
    account_id: int
    card_id: int
    customer_id: int
    merchant_id: int
    device_id: Optional[str] = None
    ip_address: Optional[str] = None
    auth_type: Literal["card_present", "card_not_present", "recurring"]
    channel: Literal["pos", "web", "mobile", "api"]
    entry_mode: Optional[Literal["chip", "swipe", "tap", "keyed"]] = None
    auth_amount: Decimal = Field(gt=0)
    currency_code: str = Field(min_length=3, max_length=3)
    merchant_country_code: str = Field(min_length=2, max_length=2)
    billing_amount_usd: Optional[Decimal] = None


# -----------------------------------------------------------------------------
# FeatureVectorContract
# -----------------------------------------------------------------------------


class FeatureVectorContract(BaseModel):
    """Strict schema for model input vector — all 19 features."""

    customer_txn_count_1h: int = Field(ge=0)
    customer_txn_count_24h: int = Field(ge=0)
    customer_spend_24h: float = Field(ge=0)
    card_txn_count_10m: int = Field(ge=0)
    merchant_txn_count_10m: int = Field(ge=0)
    merchant_chargeback_rate_30d: float = Field(ge=0, le=1)
    device_txn_count_1d: int = Field(ge=0)
    device_account_count_30d: int = Field(ge=0)
    ip_account_count_7d: int = Field(ge=0)
    ip_card_count_7d: int = Field(ge=0)
    geo_distance_from_home_km: float = Field(ge=0)
    geo_distance_from_last_txn_km: float = Field(ge=0)
    seconds_since_last_txn: Optional[int] = Field(default=None, ge=0)
    amount_vs_customer_p95_ratio: float = Field(ge=0)
    amount_vs_merchant_p95_ratio: float = Field(ge=0)
    proxy_vpn_tor_flag: bool = False
    device_risk_score: float = Field(ge=0, le=1)
    behavioral_risk_score: float = Field(ge=0, le=1)
    graph_cluster_risk_score: float = Field(ge=0, le=1)

    @classmethod
    def validate_from_dict(cls, d: dict) -> FeatureVectorContract:
        """Coerce types from raw dict to validated FeatureVectorContract."""
        return cls.model_validate(_coerce_feature_dict(d))


def _coerce_feature_dict(d: dict) -> dict:
    """Coerce dict values to correct types for FeatureVectorContract."""
    out: dict[str, Any] = {}
    int_keys = {
        "customer_txn_count_1h",
        "customer_txn_count_24h",
        "card_txn_count_10m",
        "merchant_txn_count_10m",
        "device_txn_count_1d",
        "device_account_count_30d",
        "ip_account_count_7d",
        "ip_card_count_7d",
        "seconds_since_last_txn",
    }
    float_keys = {
        "customer_spend_24h",
        "merchant_chargeback_rate_30d",
        "geo_distance_from_home_km",
        "geo_distance_from_last_txn_km",
        "amount_vs_customer_p95_ratio",
        "amount_vs_merchant_p95_ratio",
        "device_risk_score",
        "behavioral_risk_score",
        "graph_cluster_risk_score",
    }
    for k, v in d.items():
        if k not in int_keys and k not in float_keys and k != "proxy_vpn_tor_flag":
            continue
        if v is None:
            if k == "seconds_since_last_txn":
                out[k] = None
            else:
                out[k] = 0 if k != "proxy_vpn_tor_flag" else False
        elif k == "proxy_vpn_tor_flag":
            out[k] = bool(v) if isinstance(v, (bool, int, float)) else False
        elif k in int_keys:
            try:
                out[k] = int(v) if v is not None else (None if k == "seconds_since_last_txn" else 0)
            except (TypeError, ValueError):
                out[k] = 0
        elif k in float_keys:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                out[k] = 0.0
        else:
            out[k] = v
    for k in FeatureVectorContract.model_fields:
        if k not in out:
            if k == "seconds_since_last_txn":
                out[k] = None
            elif k == "proxy_vpn_tor_flag":
                out[k] = False
            elif k in int_keys:
                out[k] = 0
            else:
                out[k] = 0.0
    return out


# -----------------------------------------------------------------------------
# ModelScoreContract
# -----------------------------------------------------------------------------


class ModelScoreContract(BaseModel):
    """Strict output schema for scoring."""

    auth_event_id: int
    model_version: str
    fraud_probability: float = Field(ge=0, le=1)
    calibrated_probability: float = Field(ge=0, le=1)
    predicted_label: bool
    risk_band: Literal["critical", "high", "medium", "low", "minimal"]
    top_reason_codes: list[str] = Field(default_factory=list)
    shadow_mode: bool = False
    latency_ms: int = Field(ge=0)
    score_time: datetime


# -----------------------------------------------------------------------------
# ReplayContract
# -----------------------------------------------------------------------------


class ReplayContract(BaseModel):
    """Schema for replay response."""

    auth_event_id: int
    transaction_payload: dict = Field(default_factory=dict)
    features_at_decision_time: dict = Field(default_factory=dict)
    model_scores: list[dict] = Field(default_factory=list)
    rule_firings: list[dict] = Field(default_factory=list)
    decision_thresholds: dict = Field(default_factory=dict)
    final_decision: Optional[dict] = None
    later_arriving_labels: list[dict] = Field(default_factory=list)
    decision_correct: Optional[bool] = None
    time_to_label_seconds: Optional[float] = None


# -----------------------------------------------------------------------------
# EconomicsContract
# -----------------------------------------------------------------------------


class EconomicsContract(BaseModel):
    """Schema for economics output — 17 fields from FraudEconomicsService.compute_economics."""

    total_transactions: int = 0
    total_volume_usd: float = 0.0
    fraud_transactions: int = 0
    fraud_volume_usd: float = 0.0
    prevented_fraud_usd: float = 0.0
    missed_fraud_usd: float = 0.0
    false_positive_count: int = 0
    false_positive_volume_usd: float = 0.0
    manual_review_count: int = 0
    manual_review_cost_usd: float = 0.0
    approval_rate: float = 0.0
    decline_rate: float = 0.0
    review_rate: float = 0.0
    challenge_rate: float = 0.0
    fraud_basis_points: float = 0.0
    net_fraud_savings_usd: float = 0.0
    customer_friction_rate: float = 0.0


# -----------------------------------------------------------------------------
# ModelCardContract
# -----------------------------------------------------------------------------


class ModelCardContract(BaseModel):
    """Schema for model card."""

    model_version: str
    model_type: str
    feature_version: str
    performance: dict = Field(default_factory=dict)
    threshold_set: dict = Field(default_factory=dict)
    trained_at: Optional[str] = None
    model_hash: Optional[str] = None


# -----------------------------------------------------------------------------
# ContractRegistry
# -----------------------------------------------------------------------------


class ContractRegistry:
    """Registry of all data contracts with validation helpers."""

    @staticmethod
    def get_all_contracts() -> dict:
        """Return name -> schema dict for each contract."""
        return {
            "AuthEventContract": AuthEventContract,
            "FeatureVectorContract": FeatureVectorContract,
            "ModelScoreContract": ModelScoreContract,
            "ReplayContract": ReplayContract,
            "EconomicsContract": EconomicsContract,
            "ModelCardContract": ModelCardContract,
        }

    @staticmethod
    def validate_auth_event(data: dict) -> tuple[bool, list[str]]:
        """Validate auth event payload. Returns (valid, error_messages)."""
        try:
            AuthEventContract.model_validate(data)
            return True, []
        except ValidationError as e:
            return False, [
                f"{'.'.join(str(x) for x in err.get('loc', []))}: {err.get('msg', err)}"
                for err in e.errors()
            ]

    @staticmethod
    def validate_feature_vector(data: dict) -> tuple[bool, list[str]]:
        """Validate feature vector. Returns (valid, error_messages)."""
        try:
            FeatureVectorContract.validate_from_dict(data)
            return True, []
        except ValidationError as e:
            return False, [
                f"{'.'.join(str(x) for x in err.get('loc', []))}: {err.get('msg', err)}"
                for err in e.errors()
            ]

    @staticmethod
    def validate_model_score(data: dict) -> tuple[bool, list[str]]:
        """Validate model score output. Returns (valid, error_messages)."""
        try:
            ModelScoreContract.model_validate(data)
            return True, []
        except ValidationError as e:
            return False, [
                f"{'.'.join(str(x) for x in err.get('loc', []))}: {err.get('msg', err)}"
                for err in e.errors()
            ]
