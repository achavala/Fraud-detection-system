"""
Evaluation Harness — offline model evaluation with accuracy, precision, recall,
F1, AUC-ROC, AUC-PR, false positive/negative rates, approval rates,
and regression testing across segments.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional, Any
from dataclasses import dataclass, field, asdict

import numpy as np

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EvalResult:
    model_version: str
    segment: str
    sample_size: int
    fraud_rate: float
    auc_roc: Optional[float] = None
    auc_pr: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    false_positive_rate: Optional[float] = None
    false_negative_rate: Optional[float] = None
    approval_rate: Optional[float] = None
    decline_rate: Optional[float] = None
    review_rate: Optional[float] = None
    expected_loss: Optional[float] = None
    prevented_loss: Optional[float] = None
    threshold_decline: float = 0.85
    threshold_review: float = 0.55
    eval_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EvaluationHarness:
    """
    Runs comprehensive model evaluation — matches DRA's eval harness pattern
    but tailored for fraud detection metrics.
    """

    def __init__(self, threshold_decline: float = 0.85, threshold_review: float = 0.55):
        self.threshold_decline = threshold_decline
        self.threshold_review = threshold_review

    def evaluate(
        self,
        y_true: list[int],
        y_score: list[float],
        model_version: str,
        segment: str = "all",
        amounts: Optional[list[float]] = None,
    ) -> EvalResult:
        y_true_arr = np.array(y_true)
        y_score_arr = np.array(y_score)

        y_pred_decline = (y_score_arr >= self.threshold_decline).astype(int)
        y_pred_review = (y_score_arr >= self.threshold_review).astype(int)

        fraud_rate = float(np.mean(y_true_arr))

        auc_roc = self._safe_auc_roc(y_true_arr, y_score_arr)
        auc_pr = self._safe_auc_pr(y_true_arr, y_score_arr)

        tp = np.sum((y_pred_review == 1) & (y_true_arr == 1))
        fp = np.sum((y_pred_review == 1) & (y_true_arr == 0))
        fn = np.sum((y_pred_review == 0) & (y_true_arr == 1))
        tn = np.sum((y_pred_review == 0) & (y_true_arr == 0))

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

        total = len(y_score_arr)
        approval_rate = float(np.mean(y_score_arr < self.threshold_review))
        decline_rate = float(np.mean(y_score_arr >= self.threshold_decline))
        review_rate = float(np.mean((y_score_arr >= self.threshold_review) & (y_score_arr < self.threshold_decline)))

        expected_loss = None
        prevented_loss = None
        if amounts:
            amounts_arr = np.array(amounts)
            fraud_mask = y_true_arr == 1
            expected_loss = float(np.sum(amounts_arr[fraud_mask]))
            caught_mask = fraud_mask & (y_pred_review == 1)
            prevented_loss = float(np.sum(amounts_arr[caught_mask]))

        result = EvalResult(
            model_version=model_version,
            segment=segment,
            sample_size=total,
            fraud_rate=fraud_rate,
            auc_roc=auc_roc,
            auc_pr=auc_pr,
            precision=float(precision),
            recall=float(recall),
            f1=float(f1),
            false_positive_rate=float(fpr),
            false_negative_rate=float(fnr),
            approval_rate=approval_rate,
            decline_rate=decline_rate,
            review_rate=review_rate,
            expected_loss=expected_loss,
            prevented_loss=prevented_loss,
            threshold_decline=self.threshold_decline,
            threshold_review=self.threshold_review,
        )

        logger.info(
            "model_eval_complete",
            model_version=model_version,
            segment=segment,
            auc_roc=auc_roc,
            precision=float(precision),
            recall=float(recall),
            sample_size=total,
        )
        return result

    def compare_models(
        self,
        champion_result: EvalResult,
        challenger_result: EvalResult,
    ) -> dict:
        """Champion vs challenger comparison for model promotion decisions."""
        metrics = ["auc_roc", "auc_pr", "precision", "recall", "f1", "false_positive_rate", "false_negative_rate"]
        comparison = {}

        for metric in metrics:
            champ_val = getattr(champion_result, metric)
            chall_val = getattr(challenger_result, metric)
            if champ_val is not None and chall_val is not None:
                delta = chall_val - champ_val
                pct_change = (delta / champ_val * 100) if champ_val != 0 else 0
                improved = delta > 0 if metric not in ("false_positive_rate", "false_negative_rate") else delta < 0
                comparison[metric] = {
                    "champion": champ_val,
                    "challenger": chall_val,
                    "delta": delta,
                    "pct_change": pct_change,
                    "improved": improved,
                }

        improvements = sum(1 for v in comparison.values() if v.get("improved"))
        recommendation = "promote" if improvements >= len(comparison) * 0.7 else "hold"

        return {
            "champion": champion_result.model_version,
            "challenger": challenger_result.model_version,
            "comparison": comparison,
            "improvements": improvements,
            "total_metrics": len(comparison),
            "recommendation": recommendation,
        }

    def regression_test(
        self,
        baseline_result: EvalResult,
        current_result: EvalResult,
        max_regression_pct: float = 5.0,
    ) -> dict:
        """Check for metric regression beyond tolerance."""
        regressions = []
        for metric in ["auc_roc", "precision", "recall", "f1"]:
            baseline_val = getattr(baseline_result, metric)
            current_val = getattr(current_result, metric)
            if baseline_val and current_val:
                pct_change = (current_val - baseline_val) / baseline_val * 100 if baseline_val else 0
                if pct_change < -max_regression_pct:
                    regressions.append({
                        "metric": metric,
                        "baseline": baseline_val,
                        "current": current_val,
                        "regression_pct": abs(pct_change),
                    })

        return {
            "passed": len(regressions) == 0,
            "regressions": regressions,
            "max_regression_pct": max_regression_pct,
        }

    def _safe_auc_roc(self, y_true, y_score) -> Optional[float]:
        if len(set(y_true)) < 2:
            return None
        try:
            from sklearn.metrics import roc_auc_score
            return float(roc_auc_score(y_true, y_score))
        except Exception:
            return None

    def _safe_auc_pr(self, y_true, y_score) -> Optional[float]:
        if len(set(y_true)) < 2:
            return None
        try:
            from sklearn.metrics import average_precision_score
            return float(average_precision_score(y_true, y_score))
        except Exception:
            return None
