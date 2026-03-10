from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime, date
from decimal import Decimal
from enum import Enum


class AuthStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    CHALLENGED = "challenged"
    REVIEW = "review"


class AuthType(str, Enum):
    CARD_PRESENT = "card_present"
    CARD_NOT_PRESENT = "card_not_present"
    RECURRING = "recurring"


class Channel(str, Enum):
    POS = "pos"
    WEB = "web"
    MOBILE = "mobile"
    API = "api"


class EntryMode(str, Enum):
    CHIP = "chip"
    SWIPE = "swipe"
    TAP = "tap"
    KEYED = "keyed"


class DecisionType(str, Enum):
    APPROVE = "approve"
    DECLINE = "decline"
    MANUAL_REVIEW = "manual_review"
    STEP_UP = "step_up"
    SOFT_DECLINE = "soft_decline"
    HARD_DECLINE = "hard_decline"
    ALLOW_WITH_MONITORING = "allow_with_monitoring"


class AuthorizationRequest(BaseModel):
    transaction_id: int
    account_id: int
    card_id: int
    customer_id: int
    merchant_id: int
    device_id: Optional[str] = None
    ip_address: Optional[str] = None
    auth_type: AuthType
    channel: Channel
    entry_mode: Optional[EntryMode] = None
    auth_amount: Decimal
    currency_code: str = Field(max_length=3)
    merchant_country_code: str = Field(max_length=2)
    billing_amount_usd: Optional[Decimal] = None
    request_payload: Optional[dict[str, Any]] = None


class AuthorizationResponse(BaseModel):
    auth_event_id: int
    transaction_id: int
    decision: DecisionType
    fraud_probability: float
    risk_band: str
    model_version: str
    top_reason_codes: list[str]
    latency_ms: int
    challenge_type: Optional[str] = None
    case_id: Optional[int] = None
    timestamp: datetime


class TransactionDetail(BaseModel):
    auth_event_id: int
    transaction_id: int
    event_time: datetime
    account_id: int
    card_id: int
    customer_id: int
    merchant_id: int
    auth_amount: Decimal
    currency_code: str
    billing_amount_usd: Optional[Decimal]
    auth_status: str
    decision_type: Optional[str]
    fraud_probability: Optional[float]
    risk_band: Optional[str]
    model_version: Optional[str]
    is_fraud: Optional[bool]
    label_source: Optional[str]


class ClearingEventCreate(BaseModel):
    transaction_id: int
    auth_event_id: int
    clearing_amount: Decimal
    currency_code: str = Field(max_length=3)
    settlement_status: str


class LifecycleEventCreate(BaseModel):
    transaction_id: int
    auth_event_id: int
    event_type: str
    actor_type: Optional[str] = None
    actor_id: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
