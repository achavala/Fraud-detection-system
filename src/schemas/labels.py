from __future__ import annotations

from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date


class LabelSource(BaseModel):
    source: str
    confidence: float = 1.0


class FraudLabelCreate(BaseModel):
    auth_event_id: int
    transaction_id: int
    label_type: str
    is_fraud: bool
    fraud_category: Optional[str] = None
    fraud_subcategory: Optional[str] = None
    label_source: str
    source_confidence: float = 1.0
    event_occurred_at: Optional[datetime] = None
    investigator_id: Optional[str] = None
    notes: Optional[str] = None


class FraudLabelResponse(BaseModel):
    label_id: int
    auth_event_id: int
    is_fraud: bool
    fraud_category: Optional[str]
    label_source: str
    source_confidence: float
    label_received_at: datetime
    effective_label_date: date


class ChargebackCreate(BaseModel):
    transaction_id: int
    auth_event_id: int
    chargeback_reason_code: str
    chargeback_amount: float
    representment_flag: bool = False


class ChargebackResponse(BaseModel):
    chargeback_id: int
    transaction_id: int
    chargeback_reason_code: str
    chargeback_amount: float
    chargeback_received_at: datetime
    outcome: Optional[str]
    outcome_time: Optional[datetime]


class LabelSnapshotRequest(BaseModel):
    auth_event_id: int
    snapshot_date: date
    maturity_days: int
