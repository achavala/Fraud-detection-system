"""
Threshold optimization by business cost — finds the decision threshold that
minimizes total fraud loss while respecting approval rate and false positive constraints.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class ThresholdOptimizationResult:
    optimal_threshold: float
    net_savings_usd: float
    approval_rate: float
    false_positive_rate: float
    missed_fraud_rate: float
    fraud_caught_pct: float
    review_load: int
    detail_by_threshold: list[dict]


class ThresholdOptimizer:
    """
    Finds the loss-optimal decision threshold given scored transactions.

    Inputs: arrays of (probability, amount_usd, is_fraud) for each transaction.
    Business parameters: review_cost, fp_cost_multiplier, missed_fraud_cost_multiplier.
    Constraints: min_approval_rate, max_false_positive_rate.
    """

    def __init__(
        self,
        review_cost_per_txn: float = 15.0,
        fp_cost_multiplier: float = 0.1,
        missed_fraud_cost_multiplier: float = 1.0,
        min_approval_rate: float = 0.90,
        max_false_positive_rate: float = 0.05,
    ):
        self.review_cost = review_cost_per_txn
        self.fp_cost_mult = fp_cost_multiplier
        self.missed_fraud_mult = missed_fraud_cost_multiplier
        self.min_approval_rate = min_approval_rate
        self.max_fp_rate = max_false_positive_rate

    def optimize(
        self,
        probabilities: np.ndarray,
        amounts_usd: np.ndarray,
        is_fraud: np.ndarray,
        thresholds: Optional[np.ndarray] = None,
    ) -> ThresholdOptimizationResult:
        """
        Sweep thresholds and find the one that minimizes total business cost.

        Business cost = missed_fraud_$ * multiplier + fp_$ * multiplier + review_count * review_cost
        Net savings = prevented_fraud_$ - business_cost
        """
        if thresholds is None:
            thresholds = np.arange(0.05, 0.96, 0.01)

        probs = np.asarray(probabilities, dtype=np.float64)
        amts = np.asarray(amounts_usd, dtype=np.float64)
        fraud = np.asarray(is_fraud, dtype=bool)

        n = len(probs)
        total_fraud_usd = float(amts[fraud].sum())

        detail = []
        best_savings = float("-inf")
        best_idx = 0

        for i, t in enumerate(thresholds):
            declined = probs >= t
            approved = ~declined

            tp = int((declined & fraud).sum())
            fp = int((declined & ~fraud).sum())
            fn = int((approved & fraud).sum())
            tn = int((approved & ~fraud).sum())

            prevented_usd = float(amts[declined & fraud].sum())
            missed_usd = float(amts[approved & fraud].sum())
            fp_usd = float(amts[declined & ~fraud].sum())

            business_cost = (
                missed_usd * self.missed_fraud_mult
                + fp_usd * self.fp_cost_mult
                + (tp + fp) * self.review_cost
            )
            net_savings = prevented_usd - business_cost

            approval_rate = int(approved.sum()) / n if n else 0
            fpr = fp / (fp + tn) if (fp + tn) else 0
            fnr = fn / (fn + tp) if (fn + tp) else 0
            fraud_caught_pct = tp / (tp + fn) if (tp + fn) else 0

            entry = {
                "threshold": float(t),
                "net_savings_usd": net_savings,
                "prevented_fraud_usd": prevented_usd,
                "missed_fraud_usd": missed_usd,
                "fp_volume_usd": fp_usd,
                "business_cost_usd": business_cost,
                "approval_rate": approval_rate,
                "false_positive_rate": fpr,
                "missed_fraud_rate": fnr,
                "fraud_caught_pct": fraud_caught_pct,
                "review_load": tp + fp,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
                "meets_constraints": (
                    approval_rate >= self.min_approval_rate
                    and fpr <= self.max_fp_rate
                ),
            }
            detail.append(entry)

            if entry["meets_constraints"] and net_savings > best_savings:
                best_savings = net_savings
                best_idx = i

        if best_savings == float("-inf"):
            best_idx = max(
                range(len(detail)),
                key=lambda j: detail[j]["net_savings_usd"],
            )

        best = detail[best_idx]
        return ThresholdOptimizationResult(
            optimal_threshold=best["threshold"],
            net_savings_usd=best["net_savings_usd"],
            approval_rate=best["approval_rate"],
            false_positive_rate=best["false_positive_rate"],
            missed_fraud_rate=best["missed_fraud_rate"],
            fraud_caught_pct=best["fraud_caught_pct"],
            review_load=best["review_load"],
            detail_by_threshold=detail,
        )

    def optimize_multi_threshold(
        self,
        probabilities: np.ndarray,
        amounts_usd: np.ndarray,
        is_fraud: np.ndarray,
    ) -> dict:
        """
        Find optimal thresholds for a 3-tier system:
        decline_threshold, review_threshold, step_up_threshold.

        Optimizes: decline > review > step_up
        """
        probs = np.asarray(probabilities, dtype=np.float64)
        amts = np.asarray(amounts_usd, dtype=np.float64)
        fraud = np.asarray(is_fraud, dtype=bool)
        n = len(probs)

        best_savings = float("-inf")
        best_combo = (0.8, 0.5, 0.3)

        for decline_t in np.arange(0.70, 0.96, 0.05):
            for review_t in np.arange(0.30, decline_t, 0.05):
                for stepup_t in np.arange(0.10, review_t, 0.05):
                    hard_decline = probs >= decline_t
                    review = (probs >= review_t) & ~hard_decline
                    step_up = (probs >= stepup_t) & ~hard_decline & ~review
                    approved = ~(hard_decline | review | step_up)

                    prevented = float(amts[(hard_decline | review) & fraud].sum())
                    missed = float(amts[approved & fraud].sum())
                    stepped_missed = float(amts[step_up & fraud].sum()) * 0.3
                    fp_usd = float(amts[(hard_decline | review) & ~fraud].sum())

                    review_count = int(review.sum())
                    cost = (
                        missed * self.missed_fraud_mult
                        + stepped_missed * self.missed_fraud_mult
                        + fp_usd * self.fp_cost_mult
                        + review_count * self.review_cost
                    )
                    savings = prevented - cost
                    approval_rate = int(approved.sum()) / n if n else 0

                    if approval_rate >= self.min_approval_rate and savings > best_savings:
                        best_savings = savings
                        best_combo = (float(decline_t), float(review_t), float(stepup_t))

        return {
            "decline_threshold": best_combo[0],
            "review_threshold": best_combo[1],
            "step_up_threshold": best_combo[2],
            "net_savings_usd": best_savings,
        }
