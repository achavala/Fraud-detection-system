"""
Decision replay engine — reconstruct the exact decision as-of transaction time
for any transaction. Supports what-if analysis and batch backtesting.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.models.audit import AgentTrace
from src.models.features import FactTransactionFeaturesOnline
from src.models.labels import FactFraudLabel
from src.models.scoring import (
    DimModelRegistry,
    FactDecision,
    FactModelScore,
    FactRuleScore,
)
from src.models.transactions import (
    FactAuthorizationEvent,
    FactTransactionLifecycleEvent,
)
from src.services.features.service import FeatureService
from src.services.scoring.ml_model import FraudModelScorer, _load_model_artifact

FEATURE_COLUMNS = [
    "customer_txn_count_1h",
    "customer_txn_count_24h",
    "customer_spend_24h",
    "card_txn_count_10m",
    "merchant_txn_count_10m",
    "merchant_chargeback_rate_30d",
    "device_txn_count_1d",
    "device_account_count_30d",
    "ip_account_count_7d",
    "ip_card_count_7d",
    "geo_distance_from_home_km",
    "geo_distance_from_last_txn_km",
    "seconds_since_last_txn",
    "amount_vs_customer_p95_ratio",
    "amount_vs_merchant_p95_ratio",
    "proxy_vpn_tor_flag",
    "device_risk_score",
    "behavioral_risk_score",
    "graph_cluster_risk_score",
]


def _serialize_row(row: Any) -> dict[str, Any]:
    """Convert a SQLAlchemy row to a JSON-serializable dict."""
    if row is None:
        return {}
    result: dict[str, Any] = {}
    for c in row.__table__.columns:
        val = getattr(row, c.name)
        if isinstance(val, (datetime,)):
            result[c.name] = val.isoformat() if val else None
        elif isinstance(val, Decimal):
            result[c.name] = float(val) if val is not None else None
        elif hasattr(val, "compiled"):
            result[c.name] = str(val)
        else:
            result[c.name] = val
    return result


def _decision_from_score(
    probability: float,
    threshold_decline: float | None,
    threshold_review: float | None,
    threshold_stepup: float | None,
) -> str:
    """Map probability to decision type using thresholds."""
    settings = get_settings()
    decline = threshold_decline if threshold_decline is not None else settings.score_threshold_decline
    review = threshold_review if threshold_review is not None else settings.score_threshold_review
    stepup = threshold_stepup if threshold_stepup is not None else settings.score_threshold_stepup

    if probability >= decline:
        return "hard_decline"
    elif probability >= review:
        return "manual_review"
    elif probability >= stepup:
        return "step_up"
    return "approve"


class DecisionReplayService:
    """
    Reconstruct the exact decision as-of transaction time for any transaction.
    Supports full replay, what-if comparison, and batch backtesting.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def replay_decision(self, auth_event_id: int) -> dict:
        """
        Returns complete reconstruction of the decision at transaction time.
        """
        # 1. Original transaction payload
        auth_result = await self.db.execute(
            select(FactAuthorizationEvent).where(
                FactAuthorizationEvent.auth_event_id == auth_event_id
            )
        )
        auth_event = auth_result.scalar_one_or_none()
        if not auth_event:
            return {"error": "auth_event_not_found", "auth_event_id": auth_event_id}

        transaction_payload = _serialize_row(auth_event)

        # 2. Features available at decision time
        feat_result = await self.db.execute(
            select(FactTransactionFeaturesOnline).where(
                FactTransactionFeaturesOnline.auth_event_id == auth_event_id
            )
        )
        features_row = feat_result.scalar_one_or_none()
        features = {}
        if features_row:
            features = FeatureService(self.db).to_scoring_vector(features_row)
            features = {k: v for k, v in features.items() if k in FEATURE_COLUMNS}

        # 3. Model scores (champion and shadow)
        scores_result = await self.db.execute(
            select(FactModelScore)
            .where(FactModelScore.auth_event_id == auth_event_id)
            .order_by(FactModelScore.score_time.asc())
        )
        scores = scores_result.scalars().all()
        model_scores = []
        for s in scores:
            model_scores.append({
                "model_version": s.model_version,
                "fraud_probability": float(s.fraud_probability) if s.fraud_probability else None,
                "calibrated_probability": float(s.calibrated_probability) if s.calibrated_probability else None,
                "predicted_label": s.predicted_label,
                "risk_band": s.risk_band,
                "shadow_mode": s.shadow_mode_flag,
                "score_time": s.score_time.isoformat() if s.score_time else None,
                "top_reason_codes": s.top_reason_codes,
                "latency_ms": s.latency_ms,
            })

        # 4. Rule firings
        rules_result = await self.db.execute(
            select(FactRuleScore)
            .where(FactRuleScore.auth_event_id == auth_event_id)
            .order_by(FactRuleScore.score_time.asc())
        )
        rule_rows = rules_result.scalars().all()
        rule_firings = []
        for r in rule_rows:
            rule_firings.append({
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "fired_flag": r.fired_flag,
                "severity": r.severity,
                "contribution_score": float(r.contribution_score) if r.contribution_score else None,
                "explanation": r.explanation,
                "score_time": r.score_time.isoformat() if r.score_time else None,
            })

        # 5. Decision thresholds (from dim_model_registry)
        decision_model_version = None
        thresholds = {}
        dec_result = await self.db.execute(
            select(FactDecision).where(FactDecision.auth_event_id == auth_event_id)
        )
        decision_row = dec_result.scalar_one_or_none()
        if decision_row and decision_row.model_version:
            decision_model_version = decision_row.model_version
            reg_result = await self.db.execute(
                select(DimModelRegistry).where(
                    DimModelRegistry.model_version == decision_row.model_version
                )
            )
            reg = reg_result.scalar_one_or_none()
            if reg:
                thresholds = {
                    "threshold_decline": float(reg.threshold_decline) if reg.threshold_decline else None,
                    "threshold_review": float(reg.threshold_review) if reg.threshold_review else None,
                    "threshold_stepup": float(reg.threshold_stepup) if reg.threshold_stepup else None,
                }
        if not thresholds:
            thresholds = {
                "threshold_decline": self.settings.score_threshold_decline,
                "threshold_review": self.settings.score_threshold_review,
                "threshold_stepup": self.settings.score_threshold_stepup,
            }

        # 6. Final decision and source
        final_decision = None
        if decision_row:
            final_decision = {
                "decision_type": decision_row.decision_type,
                "decision_time": decision_row.decision_time.isoformat() if decision_row.decision_time else None,
                "final_risk_score": float(decision_row.final_risk_score) if decision_row.final_risk_score else None,
                "decision_source": decision_row.decision_source,
                "model_version": decision_row.model_version,
                "rule_set_version": decision_row.rule_set_version,
                "manual_override_flag": decision_row.manual_override_flag,
                "manual_override_reason": decision_row.manual_override_reason,
                "case_id": decision_row.case_id,
            }

        # 7. Later-arriving labels
        label_result = await self.db.execute(
            select(FactFraudLabel)
            .where(FactFraudLabel.auth_event_id == auth_event_id)
            .order_by(FactFraudLabel.label_received_at.asc())
        )
        labels = label_result.scalars().all()
        later_labels = []
        for lb in labels:
            later_labels.append({
                "label_type": lb.label_type,
                "is_fraud": lb.is_fraud,
                "label_source": lb.label_source,
                "source_confidence": float(lb.source_confidence) if lb.source_confidence else None,
                "label_received_at": lb.label_received_at.isoformat() if lb.label_received_at else None,
                "effective_label_date": lb.effective_label_date.isoformat() if lb.effective_label_date else None,
            })

        # 8. Full lifecycle timeline
        lifecycle_result = await self.db.execute(
            select(FactTransactionLifecycleEvent)
            .where(FactTransactionLifecycleEvent.auth_event_id == auth_event_id)
            .order_by(FactTransactionLifecycleEvent.event_time.asc())
        )
        lifecycle_rows = lifecycle_result.scalars().all()
        lifecycle_timeline = []
        for ev in lifecycle_rows:
            lifecycle_timeline.append({
                "event_type": ev.event_type,
                "event_time": ev.event_time.isoformat() if ev.event_time else None,
                "actor_type": ev.actor_type,
                "actor_id": ev.actor_id,
                "payload_json": ev.payload_json,
            })

        # 9. Agent traces
        trace_result = await self.db.execute(
            select(AgentTrace)
            .where(AgentTrace.auth_event_id == auth_event_id)
            .order_by(AgentTrace.step_index.asc())
        )
        traces = trace_result.scalars().all()
        agent_traces = []
        for t in traces:
            agent_traces.append({
                "step_index": t.step_index,
                "step_type": t.step_type,
                "model_name": t.model_name,
                "input_json": t.input_json,
                "output_json": t.output_json,
                "latency_ms": t.latency_ms,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })

        # 10. Was the decision correct? (based on later labels)
        decision_correct = None
        if later_labels and final_decision:
            latest_label = later_labels[-1]
            true_is_fraud = latest_label.get("is_fraud", False)
            decided_approve = final_decision.get("decision_type") in ("approve", "step_up")
            decided_decline = final_decision.get("decision_type") in ("hard_decline", "decline")
            if true_is_fraud:
                decision_correct = not decided_approve  # Correct: declined/reviewed fraud
            else:
                decision_correct = decided_approve  # Correct: approved genuine

        # 11. Time-to-label
        event_time = auth_event.event_time
        time_to_label_seconds = None
        if later_labels and event_time:
            first_label = later_labels[0]
            received_at = first_label.get("label_received_at")
            if received_at:
                try:
                    received_dt = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
                    if event_time.tzinfo is None:
                        event_time = event_time.replace(tzinfo=timezone.utc)
                    delta = received_dt - event_time
                    time_to_label_seconds = delta.total_seconds()
                except (ValueError, TypeError):
                    pass

        return {
            "auth_event_id": auth_event_id,
            "transaction_payload": transaction_payload,
            "features_at_decision_time": features,
            "model_scores": model_scores,
            "rule_firings": rule_firings,
            "decision_thresholds": thresholds,
            "final_decision": final_decision,
            "later_arriving_labels": later_labels,
            "lifecycle_timeline": lifecycle_timeline,
            "agent_traces": agent_traces,
            "decision_correct": decision_correct,
            "time_to_label_seconds": time_to_label_seconds,
        }

    async def compare_replay(
        self,
        auth_event_id: int,
        new_model_version: str,
        new_thresholds: dict,
    ) -> dict:
        """
        What-if analysis: re-score with different model and thresholds,
        show what the decision WOULD have been vs actual outcome.
        """
        replay = await self.replay_decision(auth_event_id)
        if "error" in replay:
            return replay

        features = replay.get("features_at_decision_time", {})
        if not features:
            return {
                **replay,
                "compare_error": "no_features_available",
                "what_if_decision": None,
                "what_if_probability": None,
                "actual_vs_what_if": None,
            }

        # Re-score with new model (do not persist)
        scorer = FraudModelScorer(self.db)
        artifact_data = _load_model_artifact(new_model_version)
        if artifact_data:
            raw_prob, calibrated = scorer._predict_with_model(features, artifact_data)
        else:
            raw_prob = scorer._predict_heuristic(features, new_model_version)
            calibrated = scorer._calibrate_heuristic(raw_prob)

        thresh = new_thresholds or {}
        what_if_decision = _decision_from_score(
            calibrated,
            thresh.get("threshold_decline"),
            thresh.get("threshold_review"),
            thresh.get("threshold_stepup"),
        )

        actual_decision = replay.get("final_decision", {}).get("decision_type") if replay.get("final_decision") else None
        decision_changed = actual_decision != what_if_decision if actual_decision else True

        return {
            **replay,
            "what_if": {
                "new_model_version": new_model_version,
                "new_thresholds": new_thresholds,
                "computed_probability": calibrated,
                "what_if_decision": what_if_decision,
            },
            "actual_vs_what_if": {
                "actual_decision": actual_decision,
                "what_if_decision": what_if_decision,
                "decision_changed": decision_changed,
            },
        }

    async def batch_replay(
        self,
        auth_event_ids: list[int],
        model_version: str,
    ) -> dict:
        """
        Replay many decisions with specified model for backtesting.
        Aggregates: decisions changed, approval rate impact, FPR, FNR.
        """
        results = []
        decisions_changed = 0
        total_with_decision = 0
        total_with_label = 0
        true_positives = 0
        false_positives = 0
        true_negatives = 0
        false_negatives = 0
        would_approve_count = 0
        would_decline_count = 0
        would_review_count = 0

        # Get model thresholds
        reg_result = await self.db.execute(
            select(DimModelRegistry).where(
                DimModelRegistry.model_version == model_version
            )
        )
        reg = reg_result.scalar_one_or_none()
        thresh_decline = float(reg.threshold_decline) if reg and reg.threshold_decline else self.settings.score_threshold_decline
        thresh_review = float(reg.threshold_review) if reg and reg.threshold_review else self.settings.score_threshold_review
        thresh_stepup = float(reg.threshold_stepup) if reg and reg.threshold_stepup else self.settings.score_threshold_stepup

        scorer = FraudModelScorer(self.db)
        artifact = _load_model_artifact(model_version)

        for aid in auth_event_ids:
            replay = await self.replay_decision(aid)
            if "error" in replay:
                results.append({"auth_event_id": aid, "error": replay["error"]})
                continue

            features = replay.get("features_at_decision_time", {})
            if not features:
                results.append({"auth_event_id": aid, "error": "no_features"})
                continue

            # Re-score
            if artifact:
                raw_prob, calibrated = scorer._predict_with_model(features, artifact)
            else:
                raw_prob = scorer._predict_heuristic(features, model_version)
                calibrated = scorer._calibrate_heuristic(raw_prob)

            what_if_decision = _decision_from_score(
                calibrated, thresh_decline, thresh_review, thresh_stepup
            )
            actual_decision = replay.get("final_decision", {}).get("decision_type") if replay.get("final_decision") else None

            if what_if_decision == "approve":
                would_approve_count += 1
            elif what_if_decision in ("hard_decline", "decline"):
                would_decline_count += 1
            else:
                would_review_count += 1

            if actual_decision:
                total_with_decision += 1
                if actual_decision != what_if_decision:
                    decisions_changed += 1

            # Ground truth from labels
            labels = replay.get("later_arriving_labels", [])
            is_fraud = None
            if labels:
                total_with_label += 1
                is_fraud = labels[-1].get("is_fraud", False)

            if is_fraud is not None:
                pred_positive = what_if_decision in ("hard_decline", "decline", "manual_review", "step_up")
                if is_fraud and pred_positive:
                    true_positives += 1
                elif not is_fraud and pred_positive:
                    false_positives += 1
                elif not is_fraud and not pred_positive:
                    true_negatives += 1
                else:
                    false_negatives += 1

            results.append({
                "auth_event_id": aid,
                "actual_decision": actual_decision,
                "what_if_decision": what_if_decision,
                "probability": calibrated,
                "decision_changed": actual_decision != what_if_decision if actual_decision else None,
                "is_fraud": is_fraud,
            })

        # Aggregate metrics
        fpr = false_positives / (false_positives + true_negatives) if (false_positives + true_negatives) > 0 else None
        fnr = false_negatives / (false_negatives + true_positives) if (false_negatives + true_positives) > 0 else None
        total_replayed = len(auth_event_ids)
        approval_rate = would_approve_count / total_replayed if total_replayed > 0 else 0

        return {
            "model_version": model_version,
            "auth_event_ids": auth_event_ids,
            "total_replayed": total_replayed,
            "decisions_changed": decisions_changed,
            "total_with_actual_decision": total_with_decision,
            "total_with_label": total_with_label,
            "approval_rate": approval_rate,
            "would_approve_count": would_approve_count,
            "would_decline_count": would_decline_count,
            "would_review_count": would_review_count,
            "fpr": fpr,
            "fnr": fnr,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "true_negatives": true_negatives,
            "false_negatives": false_negatives,
            "results": results,
        }
