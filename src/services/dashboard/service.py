"""
Service 7: Fraud Ops Dashboard (Read-Only)
Transaction search, model score view, rule firings, case queue,
fraud ring view, decision replay, audit trail, model health.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Any

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models.transactions import (
    FactAuthorizationEvent,
    FactTransactionLifecycleEvent,
)
from src.models.scoring import FactModelScore, FactRuleScore, FactDecision, DimModelRegistry
from src.models.labels import FactFraudLabel, FactChargebackCase
from src.models.investigation import FactFraudCase, FactCaseAction
from src.models.governance import FactModelEvalMetric, FactFeatureDriftMetric
from src.models.audit import AuditEvent, AgentTrace
from src.models.graph import FactGraphClusterScore

logger = get_logger(__name__)


class DashboardService:
    """Read-only service powering investigator, fraud ops, model risk, and leadership dashboards."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_transaction_detail(self, auth_event_id: int) -> dict:
        """Full 360-degree view of a transaction — the core investigator screen."""
        auth = await self._get_one(FactAuthorizationEvent, FactAuthorizationEvent.auth_event_id == auth_event_id)
        scores = await self._get_list(FactModelScore, FactModelScore.auth_event_id == auth_event_id)
        rules = await self._get_list(FactRuleScore, FactRuleScore.auth_event_id == auth_event_id)
        decision = await self._get_one(FactDecision, FactDecision.auth_event_id == auth_event_id)
        labels = await self._get_list(FactFraudLabel, FactFraudLabel.auth_event_id == auth_event_id)
        lifecycle = await self._get_list(
            FactTransactionLifecycleEvent,
            FactTransactionLifecycleEvent.auth_event_id == auth_event_id,
        )
        graph_score = await self._get_one(FactGraphClusterScore, FactGraphClusterScore.auth_event_id == auth_event_id)

        return {
            "authorization": self._serialize(auth) if auth else None,
            "model_scores": [self._serialize(s) for s in scores],
            "rule_scores": [self._serialize(r) for r in rules if r.fired_flag],
            "decision": self._serialize(decision) if decision else None,
            "labels": [self._serialize(l) for l in labels],
            "lifecycle_events": [self._serialize(e) for e in lifecycle],
            "graph_score": self._serialize(graph_score) if graph_score else None,
        }

    async def search_transactions(
        self,
        customer_id: Optional[int] = None,
        merchant_id: Optional[int] = None,
        card_id: Optional[int] = None,
        auth_status: Optional[str] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        query = select(FactAuthorizationEvent)
        conditions = []

        if customer_id:
            conditions.append(FactAuthorizationEvent.customer_id == customer_id)
        if merchant_id:
            conditions.append(FactAuthorizationEvent.merchant_id == merchant_id)
        if card_id:
            conditions.append(FactAuthorizationEvent.card_id == card_id)
        if auth_status:
            conditions.append(FactAuthorizationEvent.auth_status == auth_status)
        if min_amount is not None:
            conditions.append(FactAuthorizationEvent.billing_amount_usd >= min_amount)
        if max_amount is not None:
            conditions.append(FactAuthorizationEvent.billing_amount_usd <= max_amount)
        if start_time:
            conditions.append(FactAuthorizationEvent.event_time >= start_time)
        if end_time:
            conditions.append(FactAuthorizationEvent.event_time <= end_time)

        if conditions:
            query = query.where(and_(*conditions))

        count_q = select(func.count()).select_from(query.subquery())
        count_result = await self.db.execute(count_q)
        total = count_result.scalar()

        query = query.order_by(desc(FactAuthorizationEvent.event_time)).offset(offset).limit(limit)
        result = await self.db.execute(query)
        transactions = result.scalars().all()

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "transactions": [self._serialize(t) for t in transactions],
        }

    async def get_case_queue(
        self,
        queue_name: Optional[str] = None,
        status: str = "open",
        limit: int = 50,
    ) -> dict:
        query = select(FactFraudCase).where(FactFraudCase.case_status == status)
        if queue_name:
            query = query.where(FactFraudCase.queue_name == queue_name)

        query = query.order_by(
            desc(FactFraudCase.priority == "critical"),
            desc(FactFraudCase.priority == "high"),
            FactFraudCase.created_at,
        ).limit(limit)

        result = await self.db.execute(query)
        cases = result.scalars().all()

        return {
            "queue": queue_name or "all",
            "status": status,
            "cases": [self._serialize(c) for c in cases],
            "count": len(cases),
        }

    async def get_queue_summary(self) -> list[dict]:
        query = select(
            FactFraudCase.queue_name,
            FactFraudCase.case_status,
            func.count().label("cnt"),
        ).group_by(FactFraudCase.queue_name, FactFraudCase.case_status)

        result = await self.db.execute(query)
        rows = result.all()

        summary = {}
        for queue, status, count in rows:
            if queue not in summary:
                summary[queue] = {"queue_name": queue, "open": 0, "in_progress": 0, "closed": 0, "total": 0}
            summary[queue][status] = count
            summary[queue]["total"] += count

        return list(summary.values())

    async def get_model_health_dashboard(self) -> list[dict]:
        query = select(DimModelRegistry).where(
            DimModelRegistry.deployment_status.in_(["production", "shadow", "staging"])
        )
        result = await self.db.execute(query)
        models = result.scalars().all()

        dashboard = []
        for model in models:
            eval_q = await self.db.execute(
                select(FactModelEvalMetric)
                .where(FactModelEvalMetric.model_version == model.model_version)
                .order_by(desc(FactModelEvalMetric.eval_date))
                .limit(1)
            )
            latest_eval = eval_q.scalar_one_or_none()

            drift_q = await self.db.execute(
                select(func.count())
                .select_from(FactFeatureDriftMetric)
                .where(
                    and_(
                        FactFeatureDriftMetric.model_version == model.model_version,
                        FactFeatureDriftMetric.alert_flag == True,
                    )
                )
            )
            drift_count = drift_q.scalar() or 0

            dashboard.append({
                "model_version": model.model_version,
                "status": model.deployment_status,
                "family": model.model_family,
                "owner": model.owner,
                "auc_roc": float(latest_eval.auc_roc) if latest_eval and latest_eval.auc_roc else None,
                "eval_date": str(latest_eval.eval_date) if latest_eval else None,
                "drift_alerts": drift_count,
                "health": "healthy" if drift_count == 0 else "degraded" if drift_count < 3 else "critical",
            })

        return dashboard

    async def get_audit_trail(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        query = select(AuditEvent)
        conditions = []
        if entity_type:
            conditions.append(AuditEvent.entity_type == entity_type)
        if entity_id:
            conditions.append(AuditEvent.entity_id == entity_id)
        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(desc(AuditEvent.created_at)).limit(limit)
        result = await self.db.execute(query)
        return [self._serialize(e) for e in result.scalars().all()]

    async def get_agent_traces(self, case_id: int) -> list[dict]:
        result = await self.db.execute(
            select(AgentTrace)
            .where(AgentTrace.case_id == case_id)
            .order_by(AgentTrace.step_index)
        )
        return [self._serialize(t) for t in result.scalars().all()]

    async def get_ops_summary(self) -> dict:
        """High-level fraud ops KPIs for leadership dashboard."""
        now = datetime.now(timezone.utc)
        h24_ago = now - timedelta(hours=24)

        txn_count = await self.db.execute(
            select(func.count())
            .select_from(FactAuthorizationEvent)
            .where(FactAuthorizationEvent.event_time >= h24_ago)
        )

        decline_count = await self.db.execute(
            select(func.count())
            .select_from(FactDecision)
            .where(
                and_(
                    FactDecision.created_at >= h24_ago,
                    FactDecision.decision_type.in_(["decline", "hard_decline"]),
                )
            )
        )

        review_count = await self.db.execute(
            select(func.count())
            .select_from(FactDecision)
            .where(
                and_(
                    FactDecision.created_at >= h24_ago,
                    FactDecision.decision_type == "manual_review",
                )
            )
        )

        fraud_count = await self.db.execute(
            select(func.count())
            .select_from(FactFraudLabel)
            .where(
                and_(
                    FactFraudLabel.created_at >= h24_ago,
                    FactFraudLabel.is_fraud == True,
                )
            )
        )

        open_cases = await self.db.execute(
            select(func.count())
            .select_from(FactFraudCase)
            .where(FactFraudCase.case_status.in_(["open", "in_progress"]))
        )

        total_txn = txn_count.scalar() or 0
        return {
            "period": "last_24h",
            "total_transactions": total_txn,
            "total_declines": decline_count.scalar() or 0,
            "total_reviews": review_count.scalar() or 0,
            "confirmed_fraud": fraud_count.scalar() or 0,
            "decline_rate": (decline_count.scalar() or 0) / max(total_txn, 1),
            "review_rate": (review_count.scalar() or 0) / max(total_txn, 1),
            "open_cases": open_cases.scalar() or 0,
        }

    async def _get_one(self, model, condition):
        result = await self.db.execute(select(model).where(condition))
        return result.scalar_one_or_none()

    async def _get_list(self, model, condition):
        result = await self.db.execute(select(model).where(condition))
        return list(result.scalars().all())

    def _serialize(self, obj) -> dict:
        if obj is None:
            return {}
        result = {}
        for col in obj.__table__.columns:
            val = getattr(obj, col.name)
            if isinstance(val, datetime):
                val = val.isoformat()
            elif hasattr(val, "__float__"):
                val = float(val)
            result[col.name] = val
        return result
