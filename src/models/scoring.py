"""
Model scoring and decisioning: model registry, scores, rules, and final decisions.
Separates prediction from business action — critical for auditability.
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


class DimModelRegistry(Base):
    __tablename__ = "dim_model_registry"

    model_version = Column(String(100), primary_key=True)
    model_family = Column(String(100))
    model_type = Column(String(50))
    training_data_start = Column(Date)
    training_data_end = Column(Date)
    feature_version = Column(String(50))
    threshold_decline = Column(Numeric(8, 4))
    threshold_review = Column(Numeric(8, 4))
    threshold_stepup = Column(Numeric(8, 4))
    deployment_status = Column(String(30), default="staging")
    owner = Column(String(200))
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")


class FactModelScore(Base):
    """One row per model score per auth event — supports shadow/champion/challenger."""
    __tablename__ = "fact_model_score"

    score_id = Column(BigInteger, primary_key=True, autoincrement=True)
    auth_event_id = Column(
        BigInteger,
        ForeignKey("fact_authorization_event.auth_event_id"),
        nullable=False,
        index=True,
    )
    model_version = Column(
        String(100),
        ForeignKey("dim_model_registry.model_version"),
        nullable=False,
        index=True,
    )
    score_time = Column(TIMESTAMP(timezone=True), nullable=False)
    fraud_probability = Column(Numeric(8, 6), nullable=False)
    calibrated_probability = Column(Numeric(8, 6))
    predicted_label = Column(Boolean)
    risk_band = Column(String(20))
    top_reason_codes = Column(JSONB)
    shap_values_json = Column(JSONB)
    latency_ms = Column(Integer)
    shadow_mode_flag = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")


class FactRuleScore(Base):
    __tablename__ = "fact_rule_score"

    rule_score_id = Column(BigInteger, primary_key=True, autoincrement=True)
    auth_event_id = Column(
        BigInteger,
        ForeignKey("fact_authorization_event.auth_event_id"),
        nullable=False,
        index=True,
    )
    rule_set_version = Column(String(100))
    rule_id = Column(String(100), index=True)
    rule_name = Column(String(300))
    fired_flag = Column(Boolean, default=False)
    severity = Column(String(20))
    contribution_score = Column(Numeric(8, 4))
    explanation = Column(Text)
    score_time = Column(TIMESTAMP(timezone=True), nullable=False)


class FactDecision(Base):
    """
    Final business decision — separates model output from business action.
    Decision types: approve, decline, manual_review, step_up, soft_decline,
    hard_decline, allow_with_monitoring.
    """
    __tablename__ = "fact_decision"

    decision_id = Column(BigInteger, primary_key=True, autoincrement=True)
    auth_event_id = Column(
        BigInteger,
        ForeignKey("fact_authorization_event.auth_event_id"),
        nullable=False,
        index=True,
    )
    decision_time = Column(TIMESTAMP(timezone=True), nullable=False)
    decision_type = Column(String(50), nullable=False, index=True)
    final_risk_score = Column(Numeric(8, 6))
    decision_source = Column(String(50))
    model_version = Column(String(100))
    rule_set_version = Column(String(100))
    case_id = Column(BigInteger, nullable=True)
    manual_override_flag = Column(Boolean, default=False)
    manual_override_reason = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")
