from __future__ import annotations

from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime, date
from decimal import Decimal


class ModelScoreResult(BaseModel):
    score_id: int
    auth_event_id: int
    model_version: str
    fraud_probability: float
    calibrated_probability: Optional[float]
    predicted_label: bool
    risk_band: str
    top_reason_codes: list[str]
    shap_values: Optional[dict[str, float]] = None
    latency_ms: int
    shadow_mode: bool = False


class RuleScoreResult(BaseModel):
    rule_id: str
    rule_name: str
    fired: bool
    severity: Optional[str]
    contribution_score: Optional[float]
    explanation: Optional[str]


class DecisionResult(BaseModel):
    decision_id: int
    auth_event_id: int
    decision_type: str
    final_risk_score: float
    decision_source: str
    model_version: str
    rule_set_version: Optional[str]
    case_id: Optional[int]
    timestamp: datetime


class ModelRegistryEntry(BaseModel):
    model_version: str
    model_family: str
    model_type: str
    training_data_start: Optional[date]
    training_data_end: Optional[date]
    feature_version: str
    threshold_decline: float
    threshold_review: float
    threshold_stepup: float
    deployment_status: str
    owner: str


class ScoringRequest(BaseModel):
    auth_event_id: int
    features: dict[str, Any]
    model_version: Optional[str] = None
    include_shadow: bool = True
    include_shap: bool = False
