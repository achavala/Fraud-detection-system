from __future__ import annotations

from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime, date


class ModelEvalRequest(BaseModel):
    model_version: str
    eval_window_start: datetime
    eval_window_end: datetime
    segment_name: Optional[str] = None
    population_name: Optional[str] = None


class ModelEvalResponse(BaseModel):
    eval_id: int
    model_version: str
    eval_date: date
    auc_roc: Optional[float]
    auc_pr: Optional[float]
    precision_at_decline: Optional[float]
    recall_at_decline: Optional[float]
    false_positive_rate: Optional[float]
    false_negative_rate: Optional[float]
    approval_rate: Optional[float]
    decline_rate: Optional[float]
    review_rate: Optional[float]
    expected_loss: Optional[float]
    prevented_loss: Optional[float]


class DriftAlertResponse(BaseModel):
    drift_id: int
    model_version: str
    feature_name: str
    metric_date: date
    psi: float
    js_divergence: float
    train_mean: float
    prod_mean: float
    alert_flag: bool


class ExperimentCreate(BaseModel):
    challenger_model_version: str
    champion_model_version: str
    threshold_set_version: Optional[str] = None
    mode: str = "shadow"
    traffic_pct: float = 5.0


class ExperimentResult(BaseModel):
    experiment_id: int
    challenger_model_version: str
    champion_model_version: str
    mode: str
    traffic_pct: float
    start_time: datetime
    end_time: Optional[datetime]
    outcome_summary: Optional[dict[str, Any]]


class ApprovalRequest(BaseModel):
    action_type: str
    entity_type: str
    entity_id: str
    requested_by: str
    reason: str
    payload: dict[str, Any]


class ApprovalResponse(BaseModel):
    approval_id: int
    status: str
    approved_by: Optional[str]
    approved_at: Optional[datetime]
