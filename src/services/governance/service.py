"""
Service 6: Model Governance Service
Model registry, threshold management, challenger/champion evaluation,
drift monitoring, and approval gates for rollout.
"""
from __future__ import annotations

from datetime import datetime, timezone, date as date_type
from typing import Optional, Any

import numpy as np
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.logging import get_logger
from src.models.scoring import DimModelRegistry, FactModelScore, FactDecision
from src.models.labels import FactFraudLabel
from src.models.governance import (
    FactModelEvalMetric,
    FactFeatureDriftMetric,
    FactThresholdExperiment,
)
from src.models.audit import AuditEvent

logger = get_logger(__name__)


class ModelGovernanceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def register_model(
        self,
        model_version: str,
        model_family: str,
        model_type: str,
        feature_version: str,
        threshold_decline: float,
        threshold_review: float,
        threshold_stepup: float,
        owner: str,
        training_data_start: Optional[date_type] = None,
        training_data_end: Optional[date_type] = None,
    ) -> DimModelRegistry:
        model = DimModelRegistry(
            model_version=model_version,
            model_family=model_family,
            model_type=model_type,
            training_data_start=training_data_start,
            training_data_end=training_data_end,
            feature_version=feature_version,
            threshold_decline=threshold_decline,
            threshold_review=threshold_review,
            threshold_stepup=threshold_stepup,
            deployment_status="staging",
            owner=owner,
        )
        self.db.add(model)

        self.db.add(AuditEvent(
            entity_type="model",
            entity_id=model_version,
            event_type="model_registered",
            payload_json={
                "family": model_family,
                "type": model_type,
                "owner": owner,
                "feature_version": feature_version,
            },
        ))

        await self.db.flush()
        logger.info("model_registered", model_version=model_version)
        return model

    async def promote_model(
        self,
        model_version: str,
        approved_by: str,
        approval_reason: str,
    ) -> DimModelRegistry:
        """Approval-gated promotion — no model goes live without explicit sign-off."""
        result = await self.db.execute(
            select(DimModelRegistry).where(DimModelRegistry.model_version == model_version)
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Model {model_version} not found")

        if model.deployment_status not in ("staging", "shadow"):
            raise ValueError(f"Model must be in staging/shadow to promote, current: {model.deployment_status}")

        model.deployment_status = "production"

        self.db.add(AuditEvent(
            entity_type="model",
            entity_id=model_version,
            event_type="model_promoted",
            payload_json={
                "approved_by": approved_by,
                "reason": approval_reason,
                "previous_status": "staging",
            },
        ))

        await self.db.flush()
        logger.info("model_promoted", model_version=model_version, approved_by=approved_by)
        return model

    async def evaluate_model(
        self,
        model_version: str,
        eval_window_start: datetime,
        eval_window_end: datetime,
        segment_name: Optional[str] = None,
        population_name: Optional[str] = None,
    ) -> FactModelEvalMetric:
        """Compute evaluation metrics for a model version over a time window."""
        scores_q = select(
            FactModelScore.auth_event_id,
            FactModelScore.calibrated_probability,
            FactModelScore.fraud_probability,
        ).where(
            and_(
                FactModelScore.model_version == model_version,
                FactModelScore.score_time >= eval_window_start,
                FactModelScore.score_time <= eval_window_end,
            )
        )
        scores_result = await self.db.execute(scores_q)
        scores = scores_result.all()

        if not scores:
            logger.warning("no_scores_for_eval", model_version=model_version)
            return await self._store_empty_eval(model_version, segment_name, population_name)

        auth_ids = [s[0] for s in scores]
        probs = [float(s[1] or s[2]) for s in scores]

        labels_q = select(
            FactFraudLabel.auth_event_id,
            FactFraudLabel.is_fraud,
        ).where(FactFraudLabel.auth_event_id.in_(auth_ids))
        labels_result = await self.db.execute(labels_q)
        labels_map = {r[0]: r[1] for r in labels_result.all()}

        y_true = []
        y_score = []
        for auth_id, prob in zip(auth_ids, probs):
            if auth_id in labels_map:
                y_true.append(1 if labels_map[auth_id] else 0)
                y_score.append(prob)

        metrics = self._compute_metrics(y_true, y_score)

        decisions_q = select(FactDecision.decision_type).where(
            and_(
                FactDecision.auth_event_id.in_(auth_ids),
                FactDecision.model_version == model_version,
            )
        )
        decisions_result = await self.db.execute(decisions_q)
        decisions = [r[0] for r in decisions_result.all()]
        total_decisions = len(decisions) or 1

        eval_record = FactModelEvalMetric(
            model_version=model_version,
            eval_date=datetime.now(timezone.utc).date(),
            segment_name=segment_name,
            population_name=population_name,
            auc_roc=metrics.get("auc_roc"),
            auc_pr=metrics.get("auc_pr"),
            precision_at_decline=metrics.get("precision"),
            recall_at_decline=metrics.get("recall"),
            false_positive_rate=metrics.get("fpr"),
            false_negative_rate=metrics.get("fnr"),
            approval_rate=decisions.count("approve") / total_decisions,
            decline_rate=(decisions.count("decline") + decisions.count("hard_decline")) / total_decisions,
            review_rate=decisions.count("manual_review") / total_decisions,
            expected_loss=metrics.get("expected_loss"),
            prevented_loss=metrics.get("prevented_loss"),
            eval_window_start=eval_window_start,
            eval_window_end=eval_window_end,
        )
        self.db.add(eval_record)
        await self.db.flush()

        logger.info(
            "model_evaluated",
            model_version=model_version,
            auc_roc=metrics.get("auc_roc"),
            sample_size=len(y_true),
        )
        return eval_record

    async def compute_drift(
        self,
        model_version: str,
        feature_name: str,
        metric_date: date_type,
        train_values: list[float],
        prod_values: list[float],
    ) -> FactFeatureDriftMetric:
        """Compute PSI and JS divergence between training and production distributions."""
        psi = self._compute_psi(train_values, prod_values)
        js_div = self._compute_js_divergence(train_values, prod_values)

        train_arr = np.array(train_values)
        prod_arr = np.array(prod_values)

        alert = psi > 0.25 or js_div > 0.1

        drift = FactFeatureDriftMetric(
            model_version=model_version,
            feature_name=feature_name,
            metric_date=metric_date,
            psi=psi,
            js_divergence=js_div,
            null_rate=float(np.mean(np.isnan(prod_arr))) if len(prod_arr) > 0 else 0,
            train_mean=float(np.nanmean(train_arr)) if len(train_arr) > 0 else 0,
            prod_mean=float(np.nanmean(prod_arr)) if len(prod_arr) > 0 else 0,
            alert_flag=alert,
        )
        self.db.add(drift)
        await self.db.flush()

        if alert:
            logger.warning(
                "feature_drift_alert",
                model_version=model_version,
                feature=feature_name,
                psi=psi,
            )

        return drift

    async def create_experiment(
        self,
        challenger_version: str,
        champion_version: str,
        mode: str = "shadow",
        traffic_pct: float = 5.0,
        threshold_set_version: Optional[str] = None,
    ) -> FactThresholdExperiment:
        experiment = FactThresholdExperiment(
            challenger_model_version=challenger_version,
            champion_model_version=champion_version,
            threshold_set_version=threshold_set_version,
            mode=mode,
            start_time=datetime.now(timezone.utc),
            traffic_pct=traffic_pct,
        )
        self.db.add(experiment)

        self.db.add(AuditEvent(
            entity_type="experiment",
            entity_id=f"{challenger_version}_vs_{champion_version}",
            event_type="experiment_created",
            payload_json={
                "mode": mode,
                "traffic_pct": traffic_pct,
            },
        ))

        await self.db.flush()
        logger.info(
            "experiment_created",
            challenger=challenger_version,
            champion=champion_version,
            mode=mode,
        )
        return experiment

    async def get_model_health(self, model_version: str) -> dict:
        """Aggregate health view of a model for dashboard/alerting."""
        latest_eval = await self.db.execute(
            select(FactModelEvalMetric)
            .where(FactModelEvalMetric.model_version == model_version)
            .order_by(FactModelEvalMetric.eval_date.desc())
            .limit(1)
        )
        eval_record = latest_eval.scalar_one_or_none()

        drift_alerts = await self.db.execute(
            select(func.count())
            .select_from(FactFeatureDriftMetric)
            .where(
                and_(
                    FactFeatureDriftMetric.model_version == model_version,
                    FactFeatureDriftMetric.alert_flag == True,
                )
            )
        )
        drift_count = drift_alerts.scalar() or 0

        return {
            "model_version": model_version,
            "latest_auc_roc": float(eval_record.auc_roc) if eval_record and eval_record.auc_roc else None,
            "latest_eval_date": str(eval_record.eval_date) if eval_record else None,
            "drift_alert_count": drift_count,
            "health_status": "healthy" if drift_count == 0 else "degraded" if drift_count < 3 else "critical",
        }

    def _compute_metrics(self, y_true: list, y_score: list) -> dict:
        if not y_true or not y_score:
            return {}

        try:
            from sklearn.metrics import (
                roc_auc_score,
                average_precision_score,
                precision_score,
                recall_score,
            )

            y_pred = [1 if s >= self.settings.score_threshold_review else 0 for s in y_score]

            return {
                "auc_roc": roc_auc_score(y_true, y_score) if len(set(y_true)) > 1 else None,
                "auc_pr": average_precision_score(y_true, y_score) if len(set(y_true)) > 1 else None,
                "precision": precision_score(y_true, y_pred, zero_division=0),
                "recall": recall_score(y_true, y_pred, zero_division=0),
                "fpr": sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1) / max(sum(1 for t in y_true if t == 0), 1),
                "fnr": sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0) / max(sum(1 for t in y_true if t == 1), 1),
                "expected_loss": None,
                "prevented_loss": None,
            }
        except ImportError:
            return {}

    def _compute_psi(self, expected: list, actual: list, n_bins: int = 10) -> float:
        """Population Stability Index."""
        if not expected or not actual:
            return 0.0

        exp_arr = np.array(expected)
        act_arr = np.array(actual)

        breakpoints = np.linspace(
            min(exp_arr.min(), act_arr.min()),
            max(exp_arr.max(), act_arr.max()),
            n_bins + 1,
        )

        exp_counts = np.histogram(exp_arr, bins=breakpoints)[0] / len(exp_arr)
        act_counts = np.histogram(act_arr, bins=breakpoints)[0] / len(act_arr)

        exp_counts = np.clip(exp_counts, 1e-6, None)
        act_counts = np.clip(act_counts, 1e-6, None)

        psi = np.sum((act_counts - exp_counts) * np.log(act_counts / exp_counts))
        return float(psi)

    def _compute_js_divergence(self, p_vals: list, q_vals: list, n_bins: int = 10) -> float:
        """Jensen-Shannon divergence."""
        if not p_vals or not q_vals:
            return 0.0

        p_arr = np.array(p_vals)
        q_arr = np.array(q_vals)

        breakpoints = np.linspace(
            min(p_arr.min(), q_arr.min()),
            max(p_arr.max(), q_arr.max()),
            n_bins + 1,
        )

        p_hist = np.histogram(p_arr, bins=breakpoints)[0].astype(float) + 1e-10
        q_hist = np.histogram(q_arr, bins=breakpoints)[0].astype(float) + 1e-10

        p_hist /= p_hist.sum()
        q_hist /= q_hist.sum()

        m = 0.5 * (p_hist + q_hist)
        js = 0.5 * np.sum(p_hist * np.log(p_hist / m)) + 0.5 * np.sum(q_hist * np.log(q_hist / m))
        return float(js)

    async def _store_empty_eval(self, model_version, segment_name, population_name):
        eval_record = FactModelEvalMetric(
            model_version=model_version,
            eval_date=datetime.now(timezone.utc).date(),
            segment_name=segment_name,
            population_name=population_name,
        )
        self.db.add(eval_record)
        await self.db.flush()
        return eval_record
