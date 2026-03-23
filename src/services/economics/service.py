"""
Fraud economics service — tracks business decision metrics, not just ML metrics.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.transactions import FactAuthorizationEvent
from src.models.dimensions import DimMerchant
from src.models.scoring import FactDecision, FactModelScore
from src.models.labels import FactFraudLabel

REVIEW_COST_USD = Decimal("15.00")


class FraudEconomicsService:
    """Computes business metrics from fact tables: volume, fraud, decisions, costs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def compute_economics(
        self,
        start_time: datetime,
        end_time: datetime,
        segment_name: Optional[str] = None,
    ) -> dict:
        """
        Query across fact_authorization_event, fact_decision, fact_fraud_label,
        fact_model_score to compute business decision metrics.
        """
        filters = [
            FactAuthorizationEvent.event_time >= start_time,
            FactAuthorizationEvent.event_time < end_time,
        ]
        if segment_name:
            filters.append(FactAuthorizationEvent.merchant_country_code == segment_name)

        # Base query: auth events in window
        q_base = select(FactAuthorizationEvent).where(and_(*filters))
        auth_events = (await self.db.execute(q_base)).scalars().all()

        auth_ids = [a.auth_event_id for a in auth_events]
        if not auth_ids:
            return self._empty_economics()

        total_transactions = len(auth_ids)
        total_volume_usd = sum(float(a.billing_amount_usd or a.auth_amount or 0) for a in auth_events)

        # Fraud labels
        q_fraud = select(FactFraudLabel).where(
            and_(
                FactFraudLabel.auth_event_id.in_(auth_ids),
                FactFraudLabel.is_fraud.is_(True),
            )
        )
        fraud_labels = (await self.db.execute(q_fraud)).scalars().all()
        fraud_auth_ids = {f.auth_event_id for f in fraud_labels}

        fraud_transactions = len(fraud_auth_ids)
        auth_by_id = {a.auth_event_id: a for a in auth_events}
        fraud_volume_usd = sum(
            float(auth_by_id[fid].billing_amount_usd or auth_by_id[fid].auth_amount or 0)
            for fid in fraud_auth_ids
            if fid in auth_by_id
        )

        # Decisions
        q_dec = select(FactDecision).where(FactDecision.auth_event_id.in_(auth_ids))
        decisions = (await self.db.execute(q_dec)).scalars().all()
        dec_by_id = {d.auth_event_id: d for d in decisions}

        # Prevented: fraud that was declined or reviewed
        prevented_auth_ids = set()
        for auth_id in fraud_auth_ids:
            dec = dec_by_id.get(auth_id)
            if not dec:
                prevented_auth_ids.add(auth_id)
                continue
            dt = dec.decision_type.lower() if dec.decision_type else ""
            if "decline" in dt or dt == "manual_review" or dt == "hard_decline" or dt == "soft_decline":
                prevented_auth_ids.add(auth_id)

        prevented_fraud_usd = sum(
            float(auth_by_id[fid].billing_amount_usd or auth_by_id[fid].auth_amount or 0)
            for fid in prevented_auth_ids
            if fid in auth_by_id
        )

        # Missed: fraud that was approved
        missed_fraud_usd = fraud_volume_usd - prevented_fraud_usd

        # False positives: non-fraud declined
        non_fraud_auth_ids = set(auth_ids) - fraud_auth_ids
        fp_count = 0
        fp_volume_usd = 0.0
        for auth_id in non_fraud_auth_ids:
            dec = dec_by_id.get(auth_id)
            if not dec:
                continue
            dt = dec.decision_type.lower() if dec.decision_type else ""
            if "decline" in dt or dt == "hard_decline" or dt == "soft_decline":
                fp_count += 1
                fp_volume_usd += float(auth_by_id[auth_id].billing_amount_usd or auth_by_id[auth_id].auth_amount or 0)

        # Manual review
        manual_review_count = sum(
            1 for d in decisions
            if d.decision_type and d.decision_type.lower() == "manual_review"
        )
        manual_review_cost_usd = float(manual_review_count * REVIEW_COST_USD)

        # Rates
        approved_count = sum(
            1 for d in decisions
            if d.decision_type and d.decision_type.lower() in ("approve", "allow_with_monitoring")
        )
        declined_count = sum(
            1 for d in decisions
            if d.decision_type and "decline" in (d.decision_type or "").lower()
        )
        review_count = sum(
            1 for d in decisions
            if d.decision_type and d.decision_type.lower() == "manual_review"
        )
        step_up_count = sum(
            1 for d in decisions
            if d.decision_type and d.decision_type.lower() == "step_up"
        )

        approval_rate = approved_count / total_transactions if total_transactions else 0
        decline_rate = declined_count / total_transactions if total_transactions else 0
        review_rate = review_count / total_transactions if total_transactions else 0
        challenge_rate = step_up_count / total_transactions if total_transactions else 0

        fraud_basis_points = (
            (fraud_volume_usd / total_volume_usd * 10000)
            if total_volume_usd and total_volume_usd > 0
            else 0
        )

        net_fraud_savings_usd = (
            prevented_fraud_usd - fp_volume_usd - manual_review_cost_usd
        )

        friction_count = declined_count + step_up_count + review_count
        customer_friction_rate = friction_count / total_transactions if total_transactions else 0

        return {
            "total_transactions": total_transactions,
            "total_volume_usd": total_volume_usd,
            "fraud_transactions": fraud_transactions,
            "fraud_volume_usd": fraud_volume_usd,
            "prevented_fraud_usd": prevented_fraud_usd,
            "missed_fraud_usd": missed_fraud_usd,
            "false_positive_count": fp_count,
            "false_positive_volume_usd": fp_volume_usd,
            "manual_review_count": manual_review_count,
            "manual_review_cost_usd": manual_review_cost_usd,
            "approval_rate": approval_rate,
            "decline_rate": decline_rate,
            "review_rate": review_rate,
            "challenge_rate": challenge_rate,
            "fraud_basis_points": fraud_basis_points,
            "net_fraud_savings_usd": net_fraud_savings_usd,
            "customer_friction_rate": customer_friction_rate,
        }

    def _empty_economics(self) -> dict:
        return {
            "total_transactions": 0,
            "total_volume_usd": 0.0,
            "fraud_transactions": 0,
            "fraud_volume_usd": 0.0,
            "prevented_fraud_usd": 0.0,
            "missed_fraud_usd": 0.0,
            "false_positive_count": 0,
            "false_positive_volume_usd": 0.0,
            "manual_review_count": 0,
            "manual_review_cost_usd": 0.0,
            "approval_rate": 0.0,
            "decline_rate": 0.0,
            "review_rate": 0.0,
            "challenge_rate": 0.0,
            "fraud_basis_points": 0.0,
            "net_fraud_savings_usd": 0.0,
            "customer_friction_rate": 0.0,
        }

    async def compute_economics_by_segment(
        self,
        start_time: datetime,
        end_time: datetime,
        segment_by: str,
    ) -> list[dict]:
        """
        Group by: merchant_country_code, channel, auth_type, mcc (via merchant_id join),
        risk_band. Return list of economics dicts per segment.
        """
        segment_col_map = {
            "merchant_country_code": FactAuthorizationEvent.merchant_country_code,
            "channel": FactAuthorizationEvent.channel,
            "auth_type": FactAuthorizationEvent.auth_type,
            "risk_band": FactModelScore.risk_band,
        }

        if segment_by == "mcc":
            # Join to dim_merchant for mcc
            q = (
                select(DimMerchant.mcc, FactAuthorizationEvent.auth_event_id)
                .join(
                    FactAuthorizationEvent,
                    FactAuthorizationEvent.merchant_id == DimMerchant.merchant_id,
                )
                .where(
                    and_(
                        FactAuthorizationEvent.event_time >= start_time,
                        FactAuthorizationEvent.event_time < end_time,
                    )
                )
            )
        elif segment_by in segment_col_map:
            col = segment_col_map[segment_by]
            if segment_by == "risk_band":
                q = (
                    select(col, FactAuthorizationEvent.auth_event_id)
                    .join(
                        FactModelScore,
                        FactModelScore.auth_event_id == FactAuthorizationEvent.auth_event_id,
                    )
                    .where(
                        and_(
                            FactAuthorizationEvent.event_time >= start_time,
                            FactAuthorizationEvent.event_time < end_time,
                            FactModelScore.shadow_mode_flag.is_(False),
                        )
                    )
                )
            else:
                q = select(col, FactAuthorizationEvent.auth_event_id).where(
                    and_(
                        FactAuthorizationEvent.event_time >= start_time,
                        FactAuthorizationEvent.event_time < end_time,
                    )
                )
        else:
            return []

        rows = (await self.db.execute(q)).all()

        # Group auth_event_ids by segment value
        segments: dict[Optional[str], list[int]] = {}
        for row in rows:
            val = row[0] if row[0] is not None else "_unknown"
            aid = row[1]
            if val not in segments:
                segments[val] = []
            segments[val].append(aid)

        results = []
        for segment_val, auth_ids in segments.items():
            # Compute economics for this segment's time window
            # We need to filter by auth_event_id - create synthetic start/end that covers all
            ec = await self._compute_economics_for_auth_ids(auth_ids)
            ec["segment_value"] = segment_val
            ec["segment_by"] = segment_by
            results.append(ec)

        return results

    async def _compute_economics_for_auth_ids(self, auth_ids: list[int]) -> dict:
        """Compute economics for a specific set of auth_event_ids."""
        if not auth_ids:
            return self._empty_economics()

        q_auth = select(FactAuthorizationEvent).where(
            FactAuthorizationEvent.auth_event_id.in_(auth_ids)
        )
        auth_events = (await self.db.execute(q_auth)).scalars().all()
        auth_by_id = {a.auth_event_id: a for a in auth_events}

        total_transactions = len(auth_ids)
        total_volume_usd = sum(float(a.billing_amount_usd or a.auth_amount or 0) for a in auth_events)

        q_fraud = select(FactFraudLabel).where(
            and_(
                FactFraudLabel.auth_event_id.in_(auth_ids),
                FactFraudLabel.is_fraud.is_(True),
            )
        )
        fraud_labels = (await self.db.execute(q_fraud)).scalars().all()
        fraud_auth_ids = {f.auth_event_id for f in fraud_labels}

        fraud_transactions = len(fraud_auth_ids)
        fraud_volume_usd = sum(
            float(auth_by_id[fid].billing_amount_usd or auth_by_id[fid].auth_amount or 0)
            for fid in fraud_auth_ids
            if fid in auth_by_id
        )

        q_dec = select(FactDecision).where(FactDecision.auth_event_id.in_(auth_ids))
        decisions = (await self.db.execute(q_dec)).scalars().all()
        dec_by_id = {d.auth_event_id: d for d in decisions}

        prevented_auth_ids = set()
        for auth_id in fraud_auth_ids:
            dec = dec_by_id.get(auth_id)
            if not dec:
                prevented_auth_ids.add(auth_id)
                continue
            dt = (dec.decision_type or "").lower()
            if "decline" in dt or dt == "manual_review":
                prevented_auth_ids.add(auth_id)

        prevented_fraud_usd = sum(
            float(auth_by_id[fid].billing_amount_usd or auth_by_id[fid].auth_amount or 0)
            for fid in prevented_auth_ids
            if fid in auth_by_id
        )
        missed_fraud_usd = fraud_volume_usd - prevented_fraud_usd

        non_fraud_auth_ids = set(auth_ids) - fraud_auth_ids
        fp_count = 0
        fp_volume_usd = 0.0
        for auth_id in non_fraud_auth_ids:
            dec = dec_by_id.get(auth_id)
            if not dec:
                continue
            dt = (dec.decision_type or "").lower()
            if "decline" in dt:
                fp_count += 1
                fp_volume_usd += float(auth_by_id[auth_id].billing_amount_usd or auth_by_id[auth_id].auth_amount or 0)

        manual_review_count = sum(
            1 for d in decisions
            if d.decision_type and d.decision_type.lower() == "manual_review"
        )
        manual_review_cost_usd = float(manual_review_count * REVIEW_COST_USD)

        approved_count = sum(
            1 for d in decisions
            if d.decision_type and d.decision_type.lower() in ("approve", "allow_with_monitoring")
        )
        declined_count = sum(
            1 for d in decisions
            if d.decision_type and "decline" in (d.decision_type or "").lower()
        )
        review_count = sum(
            1 for d in decisions
            if d.decision_type and d.decision_type.lower() == "manual_review"
        )
        step_up_count = sum(
            1 for d in decisions
            if d.decision_type and d.decision_type.lower() == "step_up"
        )

        approval_rate = approved_count / total_transactions if total_transactions else 0
        decline_rate = declined_count / total_transactions if total_transactions else 0
        review_rate = review_count / total_transactions if total_transactions else 0
        challenge_rate = step_up_count / total_transactions if total_transactions else 0

        fraud_basis_points = (
            (fraud_volume_usd / total_volume_usd * 10000)
            if total_volume_usd and total_volume_usd > 0
            else 0
        )
        net_fraud_savings_usd = prevented_fraud_usd - fp_volume_usd - manual_review_cost_usd
        friction_count = declined_count + step_up_count + review_count
        customer_friction_rate = friction_count / total_transactions if total_transactions else 0

        return {
            "total_transactions": total_transactions,
            "total_volume_usd": total_volume_usd,
            "fraud_transactions": fraud_transactions,
            "fraud_volume_usd": fraud_volume_usd,
            "prevented_fraud_usd": prevented_fraud_usd,
            "missed_fraud_usd": missed_fraud_usd,
            "false_positive_count": fp_count,
            "false_positive_volume_usd": fp_volume_usd,
            "manual_review_count": manual_review_count,
            "manual_review_cost_usd": manual_review_cost_usd,
            "approval_rate": approval_rate,
            "decline_rate": decline_rate,
            "review_rate": review_rate,
            "challenge_rate": challenge_rate,
            "fraud_basis_points": fraud_basis_points,
            "net_fraud_savings_usd": net_fraud_savings_usd,
            "customer_friction_rate": customer_friction_rate,
        }

    async def compute_threshold_economics(
        self,
        start_time: datetime,
        end_time: datetime,
        thresholds: list[float],
    ) -> list[dict]:
        """
        For each candidate threshold, simulate what would happen if that were
        the review threshold. Re-classify all scored transactions and compute
        approval_rate, decline_rate, false_positive_rate, missed_fraud_rate, net_savings.
        """
        q = (
            select(
                FactModelScore.auth_event_id,
                FactModelScore.fraud_probability,
                FactModelScore.calibrated_probability,
                FactAuthorizationEvent.billing_amount_usd,
                FactAuthorizationEvent.auth_amount,
            )
            .join(
                FactAuthorizationEvent,
                FactAuthorizationEvent.auth_event_id == FactModelScore.auth_event_id,
            )
            .where(
                and_(
                    FactAuthorizationEvent.event_time >= start_time,
                    FactAuthorizationEvent.event_time < end_time,
                    FactModelScore.shadow_mode_flag.is_(False),
                )
            )
        )
        rows = (await self.db.execute(q)).all()

        q_labels = select(FactFraudLabel).where(
            and_(
                FactFraudLabel.auth_event_id.in_([r[0] for r in rows]),
                FactFraudLabel.is_fraud.isnot(None),
            )
        )
        labels = (await self.db.execute(q_labels)).scalars().all()
        label_by_id = {l.auth_event_id: l for l in labels}

        results = []
        for thresh in thresholds:
            approved = 0
            declined = 0
            tp = fp = tn = fn = 0
            prevented_usd = 0.0
            missed_usd = 0.0
            fp_volume_usd = 0.0

            for auth_id, raw_prob, cal_prob, bill_usd, auth_amt in rows:
                prob = float(cal_prob or raw_prob or 0)
                amt = float(bill_usd or auth_amt or 0)
                is_fraud = label_by_id.get(auth_id)
                fraud_label = is_fraud.is_fraud if is_fraud else None

                if prob >= thresh:
                    declined += 1
                    if fraud_label is True:
                        tp += 1
                        prevented_usd += amt
                    else:
                        fp += 1
                        fp_volume_usd += amt
                else:
                    approved += 1
                    if fraud_label is True:
                        fn += 1
                        missed_usd += amt
                    else:
                        tn += 1

            total = len(rows)
            approval_rate = approved / total if total else 0
            decline_rate = declined / total if total else 0
            false_positive_rate = fp / (fp + tn) if (fp + tn) else 0
            missed_fraud_rate = fn / (tp + fn) if (tp + fn) else 0
            review_cost = declined * float(REVIEW_COST_USD)
            net_savings = prevented_usd - fp_volume_usd - review_cost

            results.append({
                "threshold": thresh,
                "approval_rate": approval_rate,
                "decline_rate": decline_rate,
                "false_positive_rate": false_positive_rate,
                "missed_fraud_rate": missed_fraud_rate,
                "net_savings": net_savings,
            })

        return results

    async def compute_loss_curve(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> dict:
        """
        Generate data for a loss curve. Sort all scored transactions by fraud_probability
        descending. At each decile, compute cumulative fraud caught, cumulative false
        positives, cumulative review load. Return arrays suitable for charting.
        """
        q = (
            select(
                FactModelScore.auth_event_id,
                FactModelScore.fraud_probability,
                FactModelScore.calibrated_probability,
                FactAuthorizationEvent.billing_amount_usd,
                FactAuthorizationEvent.auth_amount,
            )
            .join(
                FactAuthorizationEvent,
                FactAuthorizationEvent.auth_event_id == FactModelScore.auth_event_id,
            )
            .where(
                and_(
                    FactAuthorizationEvent.event_time >= start_time,
                    FactAuthorizationEvent.event_time < end_time,
                    FactModelScore.shadow_mode_flag.is_(False),
                )
            )
        )
        rows = (await self.db.execute(q)).all()

        q_labels = select(FactFraudLabel).where(
            and_(
                FactFraudLabel.auth_event_id.in_([r[0] for r in rows]),
                FactFraudLabel.is_fraud.isnot(None),
            )
        )
        labels = (await self.db.execute(q_labels)).scalars().all()
        label_by_id = {l.auth_event_id: l for l in labels}

        # Sort by probability descending
        def key_fn(r):
            return float(r[2] or r[1] or 0)

        sorted_rows = sorted(rows, key=key_fn, reverse=True)
        n = len(sorted_rows)

        deciles = list(range(1, 11))
        cumulative_fraud_caught: list[float] = []
        cumulative_false_positives: list[int] = []
        cumulative_review_load: list[int] = []

        for d in deciles:
            pct = d / 10.0
            end_idx = min(int(n * pct), n)
            slice_rows = sorted_rows[:end_idx]

            fraud_caught = 0.0
            fp_count = 0
            for auth_id, _rp, _cp, bill_usd, auth_amt in slice_rows:
                amt = float(bill_usd or auth_amt or 0)
                lbl = label_by_id.get(auth_id)
                fraud_label = lbl.is_fraud if lbl else None
                if fraud_label is True:
                    fraud_caught += amt
                elif fraud_label is False:
                    fp_count += 1

            cumulative_fraud_caught.append(fraud_caught)
            cumulative_false_positives.append(fp_count)
            cumulative_review_load.append(len(slice_rows))

        return {
            "deciles": deciles,
            "cumulative_fraud_caught_usd": cumulative_fraud_caught,
            "cumulative_false_positives": cumulative_false_positives,
            "cumulative_review_load": cumulative_review_load,
        }
