"""
Model evaluation, drift monitoring, and threshold experiments.
Maps to DRA's evaluation harness tailored for fraud operations.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from src.core.database import Base


class FactModelEvalMetric(Base):
    __tablename__ = "fact_model_eval_metric"

    eval_id = Column(BigInteger, primary_key=True, autoincrement=True)
    model_version = Column(String(100), nullable=False, index=True)
    eval_date = Column(Date, nullable=False, index=True)
    segment_name = Column(String(100))
    population_name = Column(String(100))
    auc_roc = Column(Numeric(8, 6))
    auc_pr = Column(Numeric(8, 6))
    precision_at_decline = Column(Numeric(8, 6))
    recall_at_decline = Column(Numeric(8, 6))
    false_positive_rate = Column(Numeric(8, 6))
    false_negative_rate = Column(Numeric(8, 6))
    approval_rate = Column(Numeric(8, 6))
    decline_rate = Column(Numeric(8, 6))
    review_rate = Column(Numeric(8, 6))
    expected_loss = Column(Numeric(18, 4))
    prevented_loss = Column(Numeric(18, 4))
    eval_window_start = Column(TIMESTAMP(timezone=True))
    eval_window_end = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")


class FactFeatureDriftMetric(Base):
    __tablename__ = "fact_feature_drift_metric"

    drift_id = Column(BigInteger, primary_key=True, autoincrement=True)
    model_version = Column(String(100), nullable=False, index=True)
    feature_name = Column(String(200), nullable=False)
    metric_date = Column(Date, nullable=False, index=True)
    psi = Column(Numeric(8, 6))
    js_divergence = Column(Numeric(8, 6))
    null_rate = Column(Numeric(8, 6))
    train_mean = Column(Numeric(18, 6))
    prod_mean = Column(Numeric(18, 6))
    alert_flag = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")


class FactThresholdExperiment(Base):
    __tablename__ = "fact_threshold_experiment"

    experiment_id = Column(BigInteger, primary_key=True, autoincrement=True)
    challenger_model_version = Column(String(100), nullable=False)
    champion_model_version = Column(String(100), nullable=False)
    threshold_set_version = Column(String(100))
    mode = Column(String(30), nullable=False)
    start_time = Column(TIMESTAMP(timezone=True), nullable=False)
    end_time = Column(TIMESTAMP(timezone=True))
    traffic_pct = Column(Numeric(5, 2))
    outcome_summary_json = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")
