"""
Service 3: Real-time Scoring Service
Receives authorization context, fetches/computes online features,
executes rules + model, records scores, outputs final decision in milliseconds.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.logging import get_logger
from src.models.scoring import FactDecision
from src.models.transactions import FactAuthorizationEvent, FactTransactionLifecycleEvent
from src.models.investigation import FactFraudCase
from src.models.audit import AuditEvent
from src.services.features.service import FeatureService
from src.services.scoring.ml_model import FraudModelScorer
from src.services.scoring.rules_engine import RulesEngine
from src.schemas.transactions import AuthorizationRequest, AuthorizationResponse, DecisionType

logger = get_logger(__name__)


class ScoringService:
    """
    Orchestrates the full real-time fraud scoring pipeline:
    1. Ingest authorization event
    2. Compute online features
    3. Run rules engine
    4. Run ML model (champion + shadow)
    5. Combine signals into final decision
    6. Record decision + audit trail
    7. Optionally create case for manual review
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self.feature_service = FeatureService(db)
        self.model_scorer = FraudModelScorer(db)
        self.rules_engine = RulesEngine(db)

    async def score_authorization(
        self, request: AuthorizationRequest
    ) -> AuthorizationResponse:
        pipeline_start = time.monotonic()
        now = datetime.now(timezone.utc)

        auth_event = FactAuthorizationEvent(
            transaction_id=request.transaction_id,
            event_time=now,
            account_id=request.account_id,
            card_id=request.card_id,
            customer_id=request.customer_id,
            merchant_id=request.merchant_id,
            device_id=request.device_id,
            ip_address=request.ip_address,
            auth_type=request.auth_type.value,
            channel=request.channel.value,
            entry_mode=request.entry_mode.value if request.entry_mode else None,
            auth_amount=request.auth_amount,
            currency_code=request.currency_code,
            merchant_country_code=request.merchant_country_code,
            billing_amount_usd=request.billing_amount_usd or request.auth_amount,
            auth_status="pending",
            request_payload_json=request.request_payload,
        )
        self.db.add(auth_event)
        await self.db.flush()

        self.db.add(FactTransactionLifecycleEvent(
            transaction_id=request.transaction_id,
            auth_event_id=auth_event.auth_event_id,
            event_type="auth_received",
            event_time=now,
            actor_type="system",
            actor_id="scoring_service",
        ))

        features = await self.feature_service.compute_online_features(
            auth_event_id=auth_event.auth_event_id,
            account_id=request.account_id,
            card_id=request.card_id,
            customer_id=request.customer_id,
            merchant_id=request.merchant_id,
            auth_amount=request.auth_amount,
            event_time=now,
            device_id=request.device_id,
            ip_address=request.ip_address,
        )

        self.db.add(FactTransactionLifecycleEvent(
            transaction_id=request.transaction_id,
            auth_event_id=auth_event.auth_event_id,
            event_type="features_built",
            event_time=datetime.now(timezone.utc),
            actor_type="system",
            actor_id="feature_service",
        ))

        feature_vector = self.feature_service.to_scoring_vector(features)

        rule_results = await self.rules_engine.evaluate(
            auth_event_id=auth_event.auth_event_id,
            features=feature_vector,
        )
        rule_score = self.rules_engine.compute_aggregate_rule_score(rule_results)

        self.db.add(FactTransactionLifecycleEvent(
            transaction_id=request.transaction_id,
            auth_event_id=auth_event.auth_event_id,
            event_type="rules_scored",
            event_time=datetime.now(timezone.utc),
            actor_type="system",
            actor_id="rules_engine",
        ))

        model_score = await self.model_scorer.score(
            auth_event_id=auth_event.auth_event_id,
            features=feature_vector,
        )

        await self.model_scorer.score_shadow(
            auth_event_id=auth_event.auth_event_id,
            features=feature_vector,
        )

        self.db.add(FactTransactionLifecycleEvent(
            transaction_id=request.transaction_id,
            auth_event_id=auth_event.auth_event_id,
            event_type="model_scored",
            event_time=datetime.now(timezone.utc),
            actor_type="system",
            actor_id="model_scorer",
        ))

        final_score = self._blend_scores(
            float(model_score.calibrated_probability or model_score.fraud_probability),
            rule_score,
        )
        decision_type = self._make_decision(final_score, rule_results)

        case_id = None
        if decision_type == DecisionType.MANUAL_REVIEW:
            case = FactFraudCase(
                auth_event_id=auth_event.auth_event_id,
                case_status="open",
                queue_name=self._select_queue(final_score),
                priority=self._select_priority(final_score),
                created_reason=f"auto_review: score={final_score:.4f}",
            )
            self.db.add(case)
            await self.db.flush()
            case_id = case.case_id

        decision = FactDecision(
            auth_event_id=auth_event.auth_event_id,
            decision_time=datetime.now(timezone.utc),
            decision_type=decision_type.value,
            final_risk_score=final_score,
            decision_source="scoring_service",
            model_version=model_score.model_version,
            rule_set_version="rules-v3.1.0",
            case_id=case_id,
            manual_override_flag=False,
        )
        self.db.add(decision)

        auth_event.auth_status = self._decision_to_auth_status(decision_type)

        self.db.add(FactTransactionLifecycleEvent(
            transaction_id=request.transaction_id,
            auth_event_id=auth_event.auth_event_id,
            event_type=decision_type.value,
            event_time=datetime.now(timezone.utc),
            actor_type="system",
            actor_id="scoring_service",
            payload_json={"final_score": float(final_score), "case_id": case_id},
        ))

        self.db.add(AuditEvent(
            entity_type="authorization",
            entity_id=str(auth_event.auth_event_id),
            event_type="decision_made",
            payload_json={
                "decision": decision_type.value,
                "score": float(final_score),
                "model_version": model_score.model_version,
            },
        ))

        await self.db.flush()
        total_latency_ms = int((time.monotonic() - pipeline_start) * 1000)

        logger.info(
            "authorization_scored",
            auth_event_id=auth_event.auth_event_id,
            decision=decision_type.value,
            score=float(final_score),
            latency_ms=total_latency_ms,
        )

        return AuthorizationResponse(
            auth_event_id=auth_event.auth_event_id,
            transaction_id=request.transaction_id,
            decision=decision_type,
            fraud_probability=float(model_score.calibrated_probability or model_score.fraud_probability),
            risk_band=model_score.risk_band,
            model_version=model_score.model_version,
            top_reason_codes=model_score.top_reason_codes or [],
            latency_ms=total_latency_ms,
            challenge_type="otp" if decision_type == DecisionType.STEP_UP else None,
            case_id=case_id,
            timestamp=now,
        )

    def _blend_scores(self, model_score: float, rule_score: float) -> float:
        return 0.7 * model_score + 0.3 * rule_score

    def _make_decision(self, final_score: float, rule_results) -> DecisionType:
        high_severity_fired = any(
            r.fired_flag and r.severity == "high" for r in rule_results
        )

        if final_score >= self.settings.score_threshold_decline:
            return DecisionType.HARD_DECLINE
        elif final_score >= self.settings.score_threshold_review or high_severity_fired:
            return DecisionType.MANUAL_REVIEW
        elif final_score >= self.settings.score_threshold_stepup:
            return DecisionType.STEP_UP
        return DecisionType.APPROVE

    def _decision_to_auth_status(self, decision: DecisionType) -> str:
        mapping = {
            DecisionType.APPROVE: "approved",
            DecisionType.DECLINE: "declined",
            DecisionType.HARD_DECLINE: "declined",
            DecisionType.SOFT_DECLINE: "declined",
            DecisionType.MANUAL_REVIEW: "review",
            DecisionType.STEP_UP: "challenged",
            DecisionType.ALLOW_WITH_MONITORING: "approved",
        }
        return mapping.get(decision, "pending")

    def _select_queue(self, score: float) -> str:
        if score >= 0.8:
            return "high_risk"
        elif score >= 0.6:
            return "medium_risk"
        return "general"

    def _select_priority(self, score: float) -> str:
        if score >= 0.8:
            return "critical"
        elif score >= 0.6:
            return "high"
        return "medium"
